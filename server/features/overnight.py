"""Overnight run: one pass of sync, triage, rules, follow-ups and local drafts, then a morning brief.

    sync       optional (scripts/overnight.py does it by default; the UI button does not)
    triage     the Super Agent lanes; Needs You mail you already answered is marked as such
    rules      the automation rules, as a dry run unless apply_rules=true
    follow-ups threads waiting on others for N days
    drafts     a reply draft for each unanswered Needs You mail from a person, and a nudge
               for each overdue follow-up that asked a question; local drafts only, each
               prepared once (ledger table overnight_drafts)
    brief      Markdown + JSON in data/briefs/ and the overnight_runs table

Nothing is sent and the remote mailbox is never changed.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime

import yhbmail
from features import followup, get, post, rules
from features._origin import local_origin, refuse

try:
    from features import compose
except Exception:  # optional: reply drafts need it
    compose = None
try:
    from features import triage
except Exception:  # optional: without it the brief uses the core buckets
    triage = None

BRIEFS = yhbmail.DATA / "briefs"
_lock = threading.Lock()


def _zh(lang) -> bool:
    return str(lang or "").lower().startswith("zh")


def _lang(req) -> str:
    return "zh-Hant" if req.lang_zh() else "en"


def ensure_tables() -> None:
    yhbmail.init_db()
    con = yhbmail.db()
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS overnight_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT,
            finished_at TEXT,
            ok INTEGER,
            lang TEXT,
            source TEXT,
            brief_path TEXT,
            summary TEXT,
            markdown TEXT
        );
        CREATE TABLE IF NOT EXISTS overnight_drafts (
            kind TEXT NOT NULL,
            ref TEXT NOT NULL,
            draft_id INTEGER,
            at TEXT,
            PRIMARY KEY (kind, ref)
        );
        """
    )
    con.commit()
    con.close()


def _prepared() -> dict:
    ensure_tables()
    con = yhbmail.db()
    out = {(r["kind"], r["ref"]): r["draft_id"] for r in con.execute("SELECT * FROM overnight_drafts")}
    con.close()
    return out


def _remember(kind: str, ref: str, draft_id: int) -> None:
    con = yhbmail.db()
    con.execute("INSERT OR REPLACE INTO overnight_drafts(kind, ref, draft_id, at) VALUES (?,?,?,?)",
                (kind, ref, draft_id, yhbmail.now_iso()))
    con.commit()
    con.close()


# ───────────────────────── steps ─────────────────────────

def step_triage(lang: str, now_ts: int) -> dict:
    replied = followup.replied_received_ids(now_ts)
    archived = rules.archived_ids()
    day = datetime.fromtimestamp(now_ts, yhbmail.TZ).date()
    if triage is not None:
        board = triage.build_lanes(lang, today=day.isoformat())
        lanes = {lane["id"]: lane for lane in board["lanes"]}
        needs = lanes["needs_you"]["items"]
        counts = board["counts"]
        events = lanes["upcoming_today"].get("events") or []
    else:
        rows = yhbmail.list_emails(category="needs_you", limit=200)
        needs = [{"id": r["id"], "subject": r["subject"], "from_name": r["from_addr"], "from_email": r["from_addr"],
                  "summary": r.get("snippet") or "", "unread": bool(r.get("unread"))} for r in rows]
        counts = {"needs_you": len(needs)}
        events = []
    items = []
    for it in needs:
        if it["id"] in archived:
            continue
        items.append({"id": it["id"], "subject": it.get("subject") or "", "from_name": it.get("from_name") or "",
                      "from_email": it.get("from_email") or "", "summary": it.get("summary") or "",
                      "unread": bool(it.get("unread")), "replied": it["id"] in replied,
                      "bulk": any(x in (it.get("from_email") or "").lower() for x in yhbmail.NOISE_FROM)})
    return {"counts": counts, "needs_you": items, "events": events, "archived": len(archived)}


def _reply_draft(item: dict, lang: str) -> tuple[int | None, str]:
    """Create one reply draft; (draft id, source) or (None, reason)."""
    if compose is None:
        return None, "compose module missing"
    row = yhbmail.get_email(item["id"])
    if not row:
        return None, "email not found"
    dlang = "zh-Hant" if rules.CJK_RE.search(f"{row.get('subject') or ''} {row.get('body_text') or ''}") else lang
    out, status = compose.ai_write({"kind": "reply", "item_id": row["id"]}, dlang)
    if status != 200:
        return None, out.get("error") or str(status)
    subject = row.get("subject") or ""
    subject = subject if subject.lower().startswith("re:") else f"Re: {subject}".strip()
    saved, status = compose.save_draft({
        "kind": "reply", "source_id": row["id"], "account": row.get("account") or "",
        "to": compose.parse_addr(row.get("from_addr") or "")[1], "subject": subject, "text": out["text"],
        "quote": compose.reply_quote(row, dlang)}, dlang)
    if status not in (200, 201):
        return None, saved.get("error") or str(status)
    return saved["draft"]["id"], out["source"]


def step_drafts(tri: dict, fu: dict, lang: str, now_ts: int, max_drafts: int) -> dict:
    prepared = _prepared()
    made, existing, skipped = [], [], []
    for it in tri["needs_you"]:
        ref = it["id"]
        if it["replied"] or it["bulk"]:
            continue
        old = prepared.get(("reply", ref)) or rules._existing_reply_draft(ref)
        if old:
            existing.append({"kind": "reply", "ref": ref, "subject": it["subject"], "draft_id": old})
            continue
        if len(made) >= max_drafts:
            skipped.append({"kind": "reply", "ref": ref, "subject": it["subject"], "reason": "max_drafts"})
            continue
        draft_id, source = _reply_draft(it, lang)
        if draft_id:
            _remember("reply", ref, draft_id)
            made.append({"kind": "reply", "ref": ref, "subject": it["subject"], "draft_id": draft_id,
                         "source": source})
        else:
            skipped.append({"kind": "reply", "ref": ref, "subject": it["subject"], "reason": source})
    for item in fu["items"]:
        if item["status"] != "overdue" or not item["asked"]:
            continue
        ref = f"{item['thread']}#{item['sent_id']}"
        if item["nudge_draft_id"] and followup._draft_exists(item["nudge_draft_id"]):
            existing.append({"kind": "nudge", "ref": ref, "subject": item["subject"], "draft_id": item["nudge_draft_id"]})
            continue
        if ("nudge", ref) in prepared:
            continue
        if len(made) >= max_drafts:
            skipped.append({"kind": "nudge", "ref": ref, "subject": item["subject"], "reason": "max_drafts"})
            continue
        out, status = followup.nudge(item["thread"], now_ts, lang)
        if status in (200, 201):
            _remember("nudge", ref, out["draft_id"])
            item["nudge_draft_id"] = out["draft_id"]
            made.append({"kind": "nudge", "ref": ref, "subject": item["subject"], "draft_id": out["draft_id"],
                         "source": "template"})
        else:
            skipped.append({"kind": "nudge", "ref": ref, "subject": item["subject"], "reason": out.get("error")})
    return {"made": made, "existing": existing, "skipped": skipped}


# ───────────────────────── brief ─────────────────────────

def _s(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def brief_markdown(d: dict, lang: str) -> str:
    zh = _zh(lang)
    tri, fu, ru, dr = d["triage"], d["followups"], d["rules"], d["drafts"]
    overdue = [i for i in fu["items"] if i["status"] == "overdue"]
    answered = sum(1 for i in tri["needs_you"] if i["replied"])
    draft_of = {x["ref"]: x["draft_id"] for x in dr["made"] + dr["existing"]}
    sync = d["sync"]
    if zh:
        sync_text = {"skipped": "未同步（沿用本機快取）", "ok": "已同步", "error": "同步失敗"}[sync["status"]]
        lines = [f"# 早晨交接 · {d['date']}", "",
                 f"夜班 {d['finished_at']} 跑完：{sync_text}、分流、自動化規則（{'已套用' if not ru['dry_run'] else 'dry-run'}）、"
                 f"待回覆追蹤、{'預備草稿' if d['options']['drafts'] else '不預備草稿'}。",
                 "全部只在這台電腦上進行，沒有寄出任何信，也沒有改動遠端信箱。", "",
                 "## 一眼看完", "",
                 f"- 需要你：{len(tri['needs_you'])} 封（其中 {answered} 封你已回覆）",
                 f"- 對方逾期未回：{len(overdue)} 串（超過 {fu['days']} 天）",
                 f"- 自動化規則：符合 {ru['emails_matched']} 封，"
                 + (f"預計 {ru['counts']['planned']} 個動作（dry-run，尚未套用）" if ru["dry_run"]
                    else f"已套用 {ru['counts']['applied']} 個動作"),
                 f"- 預備草稿：新增 {len(dr['made'])} 份、先前已有 {len(dr['existing'])} 份（都在草稿匣，不會寄出）",
                 f"- 今天行程：{len(tri['events'])} 個", ""]
        lines += ["## 需要你", ""]
        if not tri["needs_you"]:
            lines.append("- 目前沒有。")
        for n, it in enumerate(tri["needs_you"], 1):
            tag = ("✓ 已回覆" if it["replied"] else f"✎ 草稿 #{draft_of[it['id']]}" if it["id"] in draft_of
                   else "系統通知，請自行審閱" if it["bulk"] else "待處理")
            lines.append(f"{n}. **{it['subject'] or '—'}** — {it['summary'] or it['from_name']}（{tag}）")
        lines += ["", "## 等對方回覆（逾期）", ""]
        if not overdue:
            lines.append("- 沒有逾期的信件串。")
        for n, it in enumerate(overdue, 1):
            ref = f"{it['thread']}#{it['sent_id']}"
            tag = f"✎ 追蹤草稿 #{draft_of[ref]}" if ref in draft_of else ("有提問" if it["asked"] else "沒有直接提問")
            lines.append(f"{n}. **{it['subject'] or '—'}** → {it['to_name']} · 已等 {it['waiting_days']} 天（{tag}）")
        lines += ["", "## 自動化規則" + ("（dry-run）" if ru["dry_run"] else ""), ""]
        if not ru["matched"]:
            lines.append("- 沒有信件符合規則。")
        for m in ru["matched"][:20]:
            acts = "、".join(f"{a['label']}（{a['status_label']}）" for a in m["actions"])
            lines.append(f"- {m['rule_name']}：{m['subject'] or '—'} → {acts}")
        lines += ["", "## 今天行程", ""]
        lines += [f"- {str(e.get('start_local') or '')[11:16] or '整天'} {e.get('title') or ''}" for e in tri["events"]] \
            or ["- 今天沒有行程。"]
        if d["errors"]:
            lines += ["", "## 夜班備註", ""] + [f"- {e}" for e in d["errors"]]
    else:
        sync_text = {"skipped": "no sync (local cache)", "ok": "synced", "error": "sync failed"}[sync["status"]]
        lines = [f"# Morning handoff · {d['date']}", "",
                 f"Overnight run finished {d['finished_at']}: {sync_text}, triage, rules "
                 f"({'applied' if not ru['dry_run'] else 'dry run'}), follow-ups, "
                 f"{'drafts prepared' if d['options']['drafts'] else 'no drafts'}.",
                 "Everything stayed on this machine: nothing was sent and the remote mailbox was not changed.", "",
                 "## At a glance", "",
                 f"- Needs you: {len(tri['needs_you'])} ({answered} already answered)",
                 f"- Overdue follow-ups: {_s(len(overdue), 'thread')} waiting over {fu['days']} days",
                 f"- Rules: {_s(ru['emails_matched'], 'email')} matched, "
                 + (f"{_s(ru['counts']['planned'], 'action')} planned (dry run, not applied)" if ru["dry_run"]
                    else f"{_s(ru['counts']['applied'], 'action')} applied"),
                 f"- Drafts prepared: {len(dr['made'])} new, {len(dr['existing'])} already there "
                 "(in Drafts, never sent)",
                 f"- Today: {_s(len(tri['events']), 'event')}", ""]
        lines += ["## Needs you", ""]
        if not tri["needs_you"]:
            lines.append("- Nothing right now.")
        for n, it in enumerate(tri["needs_you"], 1):
            tag = ("✓ answered" if it["replied"] else f"✎ draft #{draft_of[it['id']]}" if it["id"] in draft_of
                   else "automated notice, review it" if it["bulk"] else "to do")
            lines.append(f"{n}. **{it['subject'] or '—'}** — {it['summary'] or it['from_name']} ({tag})")
        lines += ["", "## Waiting on others (overdue)", ""]
        if not overdue:
            lines.append("- No overdue threads.")
        for n, it in enumerate(overdue, 1):
            ref = f"{it['thread']}#{it['sent_id']}"
            tag = f"✎ nudge draft #{draft_of[ref]}" if ref in draft_of else ("asked a question" if it["asked"]
                                                                              else "no direct question")
            lines.append(f"{n}. **{it['subject'] or '—'}** → {it['to_name']} · waiting {_s(it['waiting_days'], 'day')} ({tag})")
        lines += ["", "## Rules" + (" (dry run)" if ru["dry_run"] else ""), ""]
        if not ru["matched"]:
            lines.append("- No mail matched a rule.")
        for m in ru["matched"][:20]:
            acts = ", ".join(f"{a['label']} ({a['status_label']})" for a in m["actions"])
            lines.append(f"- {m['rule_name']}: {m['subject'] or '—'} → {acts}")
        lines += ["", "## Today", ""]
        lines += [f"- {str(e.get('start_local') or '')[11:16] or 'all day'} {e.get('title') or ''}" for e in tri["events"]] \
            or ["- Nothing on the calendar today."]
        if d["errors"]:
            lines += ["", "## Notes from the night shift", ""] + [f"- {e}" for e in d["errors"]]
    return "\n".join(lines).rstrip() + "\n"


# ───────────────────────── run ─────────────────────────

def run(lang: str = "en", sync: bool = False, apply_rules: bool = False, drafts: bool = True, max_drafts: int = 10,
        now=None, days=None, write: bool = True, source: str = "api", sync_limit: int = 25) -> tuple[dict, int]:
    if not _lock.acquire(blocking=False):
        return {"error": "夜班正在執行中" if _zh(lang) else "an overnight run is already in progress"}, 409
    try:
        return _run(lang, sync, apply_rules, drafts, max(0, min(50, int(max_drafts))), now, days, write, source,
                    sync_limit), 200
    finally:
        _lock.release()


def _run(lang, sync, apply_rules, drafts, max_drafts, now, days, write, source, sync_limit) -> dict:
    ensure_tables()
    started = yhbmail.now_iso()
    errors: list[str] = []
    if sync:
        try:
            report = yhbmail.sync_all(sync_limit)
            import persona
            import second_brain
            persona.rebuild()
            second_brain.rebuild()
            bad = [a for a in report.get("accounts") or [] if a.get("error")]
            errors += [f"sync {a.get('email')}: {a['error']}" for a in bad]
            sync_info = {"status": "error" if bad and len(bad) == len(report.get("accounts") or []) else "ok",
                         "mode": report.get("mode")}
        except Exception as e:
            errors.append(f"sync: {type(e).__name__}: {e}"[:300])
            sync_info = {"status": "error"}
    else:
        sync_info = {"status": "skipped"}
    now_ts = followup.parse_now(now)
    tri = step_triage(lang, now_ts)
    ru, status = rules.run(dry_run=not apply_rules, lang=lang, now=now_ts, source="overnight")
    if status != 200:
        errors.append(f"rules: {ru.get('error')}")
        ru = {"dry_run": not apply_rules, "matched": [], "counts": {"planned": 0, "applied": 0}, "emails_matched": 0}
    errors += [f"rules: {e['message']}" for e in ru.get("errors") or []]
    errors += [f"rules: {a['label']} · {m['subject']}: {a['detail'].get('reason')}"
               for m in ru["matched"] for a in m["actions"] if a["status"] == "error"]
    fu = followup.analyze(days=days, now=now_ts)
    if drafts:
        dr = step_drafts(tri, fu, lang, now_ts, max_drafts)
    else:
        dr = {"made": [], "existing": [], "skipped": []}
    if drafts and triage is not None and dr["made"]:
        tri = step_triage(lang, now_ts)
    finished = yhbmail.now_iso()
    data = {
        "date": datetime.fromtimestamp(now_ts, yhbmail.TZ).date().isoformat(), "now": followup._iso(now_ts),
        "started_at": started, "finished_at": finished, "lang": "zh-Hant" if _zh(lang) else "en", "source": source,
        "options": {"sync": sync, "apply_rules": apply_rules, "drafts": drafts, "max_drafts": max_drafts},
        "sync": sync_info, "triage": tri, "rules": ru, "followups": fu, "drafts": dr, "errors": errors,
        "sent": 0,
    }
    md = brief_markdown(data, lang)
    summary = {
        "needs_you": len(tri["needs_you"]), "answered": sum(1 for i in tri["needs_you"] if i["replied"]),
        "overdue": fu["counts"]["overdue"], "waiting": fu["counts"]["waiting"],
        "rules_matched": ru["emails_matched"], "rules_planned": ru["counts"].get("planned", 0),
        "rules_applied": ru["counts"].get("applied", 0), "rules_dry_run": ru["dry_run"],
        "drafts_new": len(dr["made"]), "drafts_existing": len(dr["existing"]), "events_today": len(tri["events"]),
        "errors": len(errors), "sent": 0,
    }
    path = ""
    if write:
        BRIEFS.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(yhbmail.TZ).strftime("%Y%m%d-%H%M%S")
        base = BRIEFS / f"overnight-{stamp}"
        n = 1
        while base.with_suffix(".md").exists():
            n += 1
            base = BRIEFS / f"overnight-{stamp}-{n}"
        base.with_suffix(".md").write_text(md)
        base.with_suffix(".json").write_text(json.dumps({**data, "summary": summary}, ensure_ascii=False, indent=2))
        (BRIEFS / "latest.md").write_text(md)
        path = rules._rel(base.with_suffix(".md"))
    ok = not errors
    con = yhbmail.db()
    run_id = con.execute(
        "INSERT INTO overnight_runs(started_at, finished_at, ok, lang, source, brief_path, summary, markdown) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (started, finished, 1 if ok else 0, data["lang"], source, path, json.dumps(summary), md)).lastrowid
    con.commit()
    con.close()
    return {"ok": ok, "id": run_id, "brief_path": path, "markdown": md, "summary": summary, "data": data}


def _run_view(row) -> dict:
    row = dict(row)
    try:
        row["summary"] = json.loads(row.get("summary") or "{}")
    except json.JSONDecodeError:
        row["summary"] = {}
    row["ok"] = bool(row.get("ok"))
    return row


def list_runs(limit: int = 20) -> list[dict]:
    ensure_tables()
    con = yhbmail.db()
    rows = [_run_view(r) for r in con.execute(
        "SELECT id, started_at, finished_at, ok, lang, source, brief_path, summary FROM overnight_runs "
        "ORDER BY id DESC LIMIT ?", (limit,))]
    con.close()
    return rows


def get_run(run_id: int | None = None) -> dict | None:
    ensure_tables()
    con = yhbmail.db()
    if run_id is None:
        row = con.execute("SELECT * FROM overnight_runs ORDER BY id DESC LIMIT 1").fetchone()
    else:
        row = con.execute("SELECT * FROM overnight_runs WHERE id=?", (run_id,)).fetchone()
    con.close()
    return _run_view(row) if row else None


# ───────────────────────── routes ─────────────────────────

@post("/api/overnight/run")
def overnight_run(req):
    if not local_origin(req):
        return refuse(req.lang_zh())
    b = req.body
    flag = rules._flag
    days = b.get("days")
    out, status = run(_lang(req), sync=flag(b.get("sync"), False), apply_rules=flag(b.get("apply_rules"), False),
                      drafts=flag(b.get("drafts"), True), max_drafts=followup._int(b.get("max_drafts"), 10, 0, 50),
                      now=b.get("now"), days=followup._int(days, followup.DEFAULT_DAYS, 1, followup.MAX_DAYS)
                      if days not in (None, "") else None, source="ui")
    if status == 200:
        out.pop("data", None)
    return out, status


@get("/api/overnight/latest")
def overnight_latest(req):
    return {"run": get_run()}


@get("/api/overnight/runs")
def overnight_runs(req):
    return {"runs": list_runs()}


@get("/api/overnight/run/*")
def overnight_run_get(req):
    try:
        run_id = int(req.params)
    except ValueError:
        return {"error": "bad id"}, 400
    row = get_run(run_id)
    return row or {"error": "not found"}, 200 if row else 404
