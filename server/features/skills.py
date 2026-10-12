"""Skills: eight one-click jobs over the local mail cache, each switchable in settings.

    morning-brief   Morning Brief        晨間簡報
    catch-me-up     Catch Me Up          幫我跟上
    organize-inbox  Organize Inbox       整理收件匣（只提建議，不搬信）
    find-it         Find It For Me       幫我找
    meeting-prep    Meeting Prep         會前準備
    brief-person    Brief this person    這個人是誰
    slide           Turn into a slide    轉成投影片（寫出 data/slides/*.html）
    crm-contact     CRM this contact     加入聯絡人 CRM（data/contacts.json）

Every skill computes a deterministic, extractive result locally (names, dates
and amounts are copied, never invented). With a BYO agent in agent.json the
text skills also ask that agent to rewrite the result; the local result stays
the fallback. A skill switched off in `data/skills.json` refuses to run (403),
including through /api/v1/agent/run. Nothing here moves, labels or sends mail.
"""
from __future__ import annotations

import functools
import html
import json
import os
import re
import threading
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import unquote

import agent_bridge
import second_brain
import yhbmail
from features import Raw, get, post
from features import triage
from features import usage
from features._origin import local_origin, refuse

SKILLS = [
    {"slug": "morning-brief", "group": "F09", "prompt": "morning-brief", "inputs": ["today"],
     "en": "Morning Brief", "zh": "晨間簡報",
     "desc_en": "What landed since the last working day; Needs-you items spelled out, the rest compressed.",
     "desc_zh": "上個工作日之後進來的信；「需要你」寫到能直接決定，其餘壓縮。"},
    {"slug": "catch-me-up", "group": "F09", "prompt": "catch-me-up", "inputs": ["hours"],
     "en": "Catch Me Up", "zh": "幫我跟上",
     "desc_en": "Recent activity grouped by sender: replies needed first, then skimmable.",
     "desc_zh": "最近的信依寄件者分組：先列要回的，再列可以掃過的。"},
    {"slug": "organize-inbox", "group": "F09", "prompt": "categorize-inbox", "inputs": [],
     "en": "Organize Inbox", "zh": "整理收件匣",
     "desc_en": "Proposes folders, filter rules and noise sources. Read-only: nothing is moved.",
     "desc_zh": "提出資料夾、篩選規則與噪音來源建議。唯讀：不會搬動任何信。"},
    {"slug": "find-it", "group": "F09", "prompt": "find-it-for-me", "inputs": ["query"],
     "en": "Find It For Me", "zh": "幫我找",
     "desc_en": "Search mail, calendar and Second Brain. Supports from: to: has:attachment is:unread after: before:.",
     "desc_zh": "搜尋信件、行事曆與第二大腦。支援 from: to: has:attachment is:unread after: before:。"},
    {"slug": "meeting-prep", "group": "F10", "prompt": "meeting-prep", "inputs": ["event_id"],
     "en": "Meeting Prep", "zh": "會前準備",
     "desc_en": "For a calendar event: related mail, people, open questions, attachments, checklist.",
     "desc_zh": "針對一個行程：相關信件、與會者、待解問題、附件與準備清單。"},
    {"slug": "brief-person", "group": "F10", "prompt": "brief-this-person", "inputs": ["person", "email_id"],
     "en": "Brief this person", "zh": "這個人是誰",
     "desc_en": "Everything the local cache knows about one sender: history, topics, open asks.",
     "desc_zh": "本機快取裡關於這位寄件人的一切：往來紀錄、主題、未結事項。"},
    {"slug": "slide", "group": "F10", "prompt": "turn-into-a-slide", "inputs": ["email_id", "from_skill", "markdown", "title"],
     "en": "Turn into a slide", "zh": "轉成投影片",
     "desc_en": "Turns an email, a skill result or Markdown into a self-contained HTML slide deck file.",
     "desc_zh": "把一封信、一個技能結果或 Markdown 轉成獨立的 HTML 投影片檔。"},
    {"slug": "crm-contact", "group": "F10", "prompt": "crm-this-contact", "inputs": ["person", "email_id", "note", "tags", "stage"],
     "en": "CRM this contact", "zh": "加入聯絡人 CRM",
     "desc_en": "Adds or refreshes the sender in the local contacts CRM (data/contacts.json).",
     "desc_zh": "把寄件人加入或更新到本機聯絡人 CRM（data/contacts.json）。"},
]
BY_SLUG = {s["slug"]: s for s in SKILLS}
AGENT_SKILLS = {"morning-brief", "catch-me-up", "organize-inbox", "find-it", "meeting-prep", "brief-person"}
# core skill prompts in skills/*.md that /api/v1/agent/run accepts -> the switch that governs them
CORE_SKILL_SWITCH = {**{s["slug"]: s["slug"] for s in SKILLS}, **{s["prompt"]: s["slug"] for s in SKILLS}}
STAGES = ("lead", "active", "customer", "partner", "vendor", "other")
SLIDE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{0,80}\.html$")
TAG_RE = re.compile(r"^[^\s,<>\"'&]{1,32}$")
CJK_RUN_RE = re.compile(r"[\u3400-\u9fff]+")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9'\-]+")
STOP_WORDS = {
    "the", "and", "with", "for", "from", "call", "meeting", "sync", "chat", "about", "re", "fw", "fwd",
    "weekly", "daily", "today", "tomorrow", "this", "that", "your", "our", "into",
}
STOP_CJK = {"會議", "討論", "同步", "例會", "通話"}
_lock = threading.Lock()


def _zh(lang) -> bool:
    return str(lang or "").lower().startswith("zh")


def _lang(req) -> str:
    return "zh-Hant" if req.lang_zh() else "en"


def _int(value, default: int, lo: int = 1, hi: int = 720) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _clip(text: str, n: int) -> str:
    return triage._clip(text, n)


def _data_dir() -> Path:
    return yhbmail.DATA


def settings_path() -> Path:
    return _data_dir() / "skills.json"


def contacts_path() -> Path:
    return _data_dir() / "contacts.json"


def slides_dir() -> Path:
    return _data_dir() / "slides"


def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(yhbmail.ROOT))
    except ValueError:
        return str(p)


def _read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return default
    return data if isinstance(data, type(default)) else default


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


# ───────────────────────── settings ─────────────────────────

def load_settings() -> dict:
    raw = _read_json(settings_path(), {})
    enabled = raw.get("enabled") if isinstance(raw.get("enabled"), dict) else {}
    runs = raw.get("runs") if isinstance(raw.get("runs"), dict) else {}
    return {
        "enabled": {s["slug"]: bool(enabled.get(s["slug"], True)) for s in SKILLS},
        "runs": {k: v for k, v in runs.items() if k in BY_SLUG and isinstance(v, dict)},
        "updated_at": raw.get("updated_at") or "",
    }


def save_settings(settings: dict) -> None:
    _write_json(settings_path(), {"enabled": settings["enabled"], "runs": settings["runs"],
                                  "updated_at": yhbmail.now_iso()})


def is_enabled(slug: str) -> bool:
    return load_settings()["enabled"].get(slug, False)


def set_enabled(changes: dict) -> tuple[dict, int]:
    unknown = [k for k in changes if k not in BY_SLUG]
    if unknown:
        return {"error": f"unknown skill {', '.join(sorted(unknown))}", "skills": sorted(BY_SLUG)}, 400
    with _lock:
        s = load_settings()
        for k, v in changes.items():
            s["enabled"][k] = bool(v)
        save_settings(s)
    return {"ok": True, "enabled": s["enabled"]}, 200


def _mark_run(slug: str, source: str) -> None:
    with _lock:
        s = load_settings()
        prev = s["runs"].get(slug) or {}
        s["runs"][slug] = {"count": int(prev.get("count") or 0) + 1, "last_run_at": yhbmail.now_iso(),
                           "last_source": source}
        save_settings(s)


def skill_view(meta: dict, lang: str, settings: dict) -> dict:
    zh = _zh(lang)
    run = settings["runs"].get(meta["slug"]) or {}
    return {
        "slug": meta["slug"], "group": meta["group"], "name": meta["zh" if zh else "en"],
        "name_en": meta["en"], "name_zh": meta["zh"],
        "description": meta["desc_zh" if zh else "desc_en"], "inputs": meta["inputs"],
        "enabled": settings["enabled"][meta["slug"]], "agent": meta["slug"] in AGENT_SKILLS,
        "prompt": f"skills/{meta['prompt']}.md" if (agent_bridge.SKILLS_DIR / f"{meta['prompt']}.md").exists() else "",
        "runs": int(run.get("count") or 0), "last_run_at": run.get("last_run_at") or "",
    }


def disabled_error(slug: str, lang: str) -> dict:
    meta = BY_SLUG[slug]
    if _zh(lang):
        msg = f"技能「{meta['zh']}」已在設定中關閉，拒絕執行。到「技能」頁打開開關即可使用。"
    else:
        msg = f"The skill \"{meta['en']}\" is switched off in settings, so it will not run. Turn it on in Skills."
    return {"error": "skill_disabled", "skill": slug, "message": msg, "enabled": False}


# ───────────────────────── shared mail helpers ─────────────────────────

def all_mail(limit: int = 500) -> list[dict]:
    return yhbmail.list_emails(limit=limit)


def _py_lower(value) -> str:
    return value.lower() if isinstance(value, str) else ""


def query_mail(where: list[str], args: list) -> list[dict]:
    """Every cached email matching all `where` clauses, newest first, with no row cap.

    Clauses may call tpi_lower(col), which is Python str.lower (SQLite's lower() only folds ASCII),
    so `instr(tpi_lower(col), ?) > 0` selects exactly the rows a Python `term in col.lower()` would.
    """
    sql = "SELECT * FROM emails" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY date_ts DESC"
    con = yhbmail.db()
    try:
        con.create_function("tpi_lower", 1, _py_lower, deterministic=True)
        rows = [dict(r) for r in con.execute(sql, args)]
    finally:
        con.close()
    for r in rows:
        r["labels"] = json.loads(r.pop("labels_json", None) or "[]")
    return rows


def _contains_any(cols: tuple[str, ...], needles: list[str], args: list) -> str:
    hay = " || ' ' || ".join(f"COALESCE({c}, '')" for c in cols)
    args.extend(needles)
    return "(" + " OR ".join(f"instr(tpi_lower({hay}), ?) > 0" for _ in needles) + ")"


def mail_containing(cols: tuple[str, ...], needles: list[str]) -> list[dict]:
    args: list = []
    return query_mail([_contains_any(cols, needles, args)], args)


def mail_item(row: dict, lang: str) -> dict:
    name, addr = triage.sender(row)
    att = triage.attachment_info(row)
    return {
        "id": row["id"], "subject": row.get("subject") or "", "from_name": name, "from_email": addr,
        "date_raw": row.get("date_raw") or "", "date_ts": row.get("date_ts") or 0,
        "unread": bool(row.get("unread")), "bucket": row.get("category") or "fyi",
        "lane": triage.lane_of(row), "summary": triage.heuristic_summary(row, lang),
        "has_attachment": att["has"], "attachments": att["names"],
        "actions": [a["label"] for a in triage.suggested_actions(row, lang)],
    }


def _summary_tail(item: dict, lang: str) -> str:
    sep = "：" if _zh(lang) else ": "
    return item["summary"].split(sep, 1)[-1]


def _parse_ref(value) -> datetime:
    if value:
        raw = str(value).strip()
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=yhbmail.TZ)
        except ValueError:
            pass
    return datetime.now(yhbmail.TZ)


def _sentences(row: dict) -> list[str]:
    body = row.get("body_text") or row.get("snippet") or ""
    body = "\n".join(ln for ln in body.splitlines() if not ln.lstrip().startswith(">"))
    out = []
    for s in triage.SENT_SPLIT_RE.split(body):
        s = triage.GREETING_RE.sub("", s).strip(" -—–")
        s = re.sub(r"^[A-Z][a-z]+\s+[—–-]\s+", "", s)
        if len(s) >= 8:
            out.append(s)
    return out


def open_asks(row: dict) -> list[str]:
    return [s for s in _sentences(row) if yhbmail.ACTION_RE.search(s) or triage.QUESTION_RE.search(s)]


def deadlines(row: dict) -> list[str]:
    text = row.get("body_text") or row.get("snippet") or ""
    out = []
    for m in triage.DEADLINE_RE.finditer(text):
        explicit = re.match(r"\d{4}-\d{2}-\d{2}|\d{1,2}月", m.group(3))
        if m.group(1) or m.group(2) or explicit:
            val = m.group(0).strip()
            if val not in out:
                out.append(val)
    return out


def _md_item(item: dict, lang: str) -> str:
    att = " 📎" if item["has_attachment"] else ""
    return f"- **{item['subject'] or '—'}**{att} — {item['summary']}"


# ───────────────────────── F09: morning brief / catch me up / organize / find ─────────────────────────

def _last_working_day(today):
    d = today - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def run_morning_brief(args: dict, lang: str) -> dict:
    zh = _zh(lang)
    today = triage.parse_today(args.get("today"))
    since = _last_working_day(today)
    since_ts = int(datetime(since.year, since.month, since.day, tzinfo=yhbmail.TZ).timestamp())
    rows = all_mail()
    items = [mail_item(r, lang) for r in rows]
    new = [i for i in items if (i["date_ts"] or 0) >= since_ts]
    need = [i for i in items if i["bucket"] == "needs_you"]
    look = [i for i in items if i["bucket"] == "worth_a_look"]
    rest = [i for i in items if i["bucket"] in ("fyi", "other")]
    todays, later = triage.calendar_today(today)
    unread = sum(1 for i in items if i["unread"])
    if zh:
        lines = [f"# 晨間簡報 · {today.isoformat()}", "",
                 f"上個工作日（{since.isoformat()}）之後新進 {len(new)} 封；收件匣未讀 {unread} 封。", "",
                 f"## 需要你（{len(need)}）"]
    else:
        lines = [f"# Morning brief · {today.isoformat()}", "",
                 f"{len(new)} new since the last working day ({since.isoformat()}); {unread} unread in the inbox.", "",
                 f"## Needs you ({len(need)})"]
    for i in need:
        nxt = ""
        if i["actions"]:
            nxt = ("　→ 下一步：" if zh else " → Next: ") + ("；" if zh else "; ").join(i["actions"][:2])
        lines.append(_md_item(i, lang) + nxt)
    if not need:
        lines.append("- 沒有等你決定的信。" if zh else "- Nothing is waiting on you.")
    lines += ["", "## 今天的行程" if zh else "## Today's calendar"]
    for ev in todays:
        when = ("整天" if zh else "all day") if ev["all_day"] else ev["start_local"][11:16]
        lines.append(f"- {when} {ev['title']}")
    if not todays:
        lines.append("- 今天沒有行程。" if zh else "- Nothing on the calendar today.")
    if later:
        lines.append(("接下來：" if zh else "Next up: ") + ("；" if zh else "; ").join(
            f"{e['start_local'][:16].replace('T', ' ')} {e['title']}" for e in later))
    lines += ["", (f"## 值得一看（{len(look)}）" if zh else f"## Worth a look ({len(look)})")]
    for i in look[:6]:
        lines.append(f"- {i['subject'] or '—'} — {_summary_tail(i, lang)}")
    if not look:
        lines.append("- 無。" if zh else "- None.")
    rest_unread = sum(1 for i in rest if i["unread"])
    lines += ["", ("## 其餘" if zh else "## The rest"),
              (f"- 僅供參考／電子報／廣告共 {len(rest)} 封（未讀 {rest_unread}），可以晚點掃。" if zh
               else f"- {len(rest)} FYI / newsletter / promotion emails ({rest_unread} unread) can wait.")]
    return {
        "title": BY_SLUG["morning-brief"]["zh" if zh else "en"] + f" · {today.isoformat()}",
        "markdown": "\n".join(lines) + "\n",
        "data": {"today": today.isoformat(), "since": since.isoformat(), "new_count": len(new),
                 "unread": unread, "needs_you": need, "worth_a_look": look,
                 "rest_count": len(rest), "events_today": todays, "next_events": later},
    }


def run_catch_me_up(args: dict, lang: str) -> dict:
    zh = _zh(lang)
    hours = _int(args.get("hours"), 72)
    ref = _parse_ref(args.get("now"))
    floor = int((ref - timedelta(hours=hours)).timestamp())
    rows = all_mail()
    window = [r for r in rows if (r.get("date_ts") or 0) >= floor]
    fallback = not window
    if fallback:
        window = rows[:20]
    groups: dict[str, dict] = {}
    for r in window:
        it = mail_item(r, lang)
        key = it["from_email"] or it["from_name"]
        g = groups.setdefault(key, {"sender": it["from_name"], "email": it["from_email"], "count": 0,
                                    "unread": 0, "reply_needed": False, "latest_ts": 0, "items": []})
        g["count"] += 1
        g["unread"] += 1 if it["unread"] else 0
        bulk = triage._is_bulk(it["from_email"])
        if it["bucket"] == "needs_you" or (not bulk and open_asks(r)):
            g["reply_needed"] = True
        g["latest_ts"] = max(g["latest_ts"], it["date_ts"] or 0)
        g["items"].append(it)
    ordered = sorted(groups.values(), key=lambda g: (not g["reply_needed"], -g["count"], -g["latest_ts"]))
    reply = [g for g in ordered if g["reply_needed"]]
    skim = [g for g in ordered if not g["reply_needed"]]
    if zh:
        head = (f"沒有 {hours} 小時內的新信，改列最近 {len(window)} 封。" if fallback
                else f"最近 {hours} 小時 {len(window)} 封信，來自 {len(ordered)} 個寄件者。")
        lines = ["# 幫我跟上", "", head, "", f"## 要回的（{len(reply)}）"]
    else:
        head = (f"No mail in the last {hours} hours; showing the latest {len(window)} instead." if fallback
                else f"{len(window)} emails from {len(ordered)} senders in the last {hours} hours.")
        lines = ["# Catch me up", "", head, "", f"## Reply needed ({len(reply)})"]

    def block(gs):
        for g in gs:
            unread = (f"，未讀 {g['unread']}" if zh else f", {g['unread']} unread") if g["unread"] else ""
            lines.append(f"### {g['sender']} ({g['count']}{unread})")
            for it in g["items"][:4]:
                lines.append(f"- {it['subject'] or '—'} — {_summary_tail(it, lang)}")
        if not gs:
            lines.append("- 無。" if zh else "- None.")
    block(reply)
    lines += ["", (f"## 可以掃過的（{len(skim)}）" if zh else f"## Skimmable ({len(skim)})")]
    block(skim)
    return {
        "title": BY_SLUG["catch-me-up"]["zh" if zh else "en"],
        "markdown": "\n".join(lines) + "\n",
        "data": {"hours": hours, "fallback": fallback, "emails": len(window), "senders": len(ordered),
                 "reply_needed": reply, "skimmable": skim},
    }


FOLDERS = [
    ("action", "Action", "待處理"),
    ("calendar", "Calendar", "行程"),
    ("receipts", "Receipts & billing", "收據與帳單"),
    ("newsletters", "Newsletters", "電子報"),
    ("promotions", "Promotions", "廣告"),
    ("notifications", "Notifications", "系統通知"),
    ("reference", "Reference", "參考"),
]


def folder_of(row: dict) -> str:
    bucket = row.get("category") or "fyi"
    blob = triage._blob(row)
    _, addr = triage.sender(row)
    if bucket == "needs_you":
        return "action"
    if bucket == "upcoming":
        return "calendar"
    if yhbmail.MONEY_RE.search(blob):
        return "receipts"
    if triage.lane_of(row) == "other":
        return "promotions" if triage.digest_kind(row) == "promotion" else "newsletters"
    if triage._is_bulk(addr):
        return "notifications"
    return "reference"


def run_organize_inbox(args: dict, lang: str) -> dict:
    zh = _zh(lang)
    rows = all_mail()
    names = {k: (zh_name if zh else en) for k, en, zh_name in FOLDERS}
    folders = {k: {"folder": k, "name": names[k], "count": 0, "unread": 0, "items": []} for k, _, _ in FOLDERS}
    noise: dict[str, dict] = {}
    domains: dict[str, set] = {}
    for r in rows:
        f = folder_of(r)
        name, addr = triage.sender(r)
        g = folders[f]
        g["count"] += 1
        g["unread"] += 1 if r.get("unread") else 0
        g["items"].append({"id": r["id"], "subject": r.get("subject") or "", "from_name": name,
                           "unread": bool(r.get("unread"))})
        if f in ("newsletters", "promotions", "notifications"):
            n = noise.setdefault(addr, {"sender": name, "email": addr, "count": 0, "folder": f,
                                        "unsubscribe": False})
            n["count"] += 1
            n["unsubscribe"] = n["unsubscribe"] or bool(re.search(r"unsubscribe|退訂|取消訂閱", triage._blob(r), re.I))
            domain = addr.split("@")[-1] if "@" in addr else ""
            if domain:
                domains.setdefault(domain, set()).add(f)
    rules = [{"match": f"from:@{d}", "folder": sorted(fs)[0], "folder_name": names[sorted(fs)[0]]}
             for d, fs in sorted(domains.items()) if len(fs) == 1]
    noise_list = sorted(noise.values(), key=lambda n: (-n["count"], n["sender"].lower()))
    archive = [it for k in ("newsletters", "promotions") for it in folders[k]["items"]]
    ordered = [folders[k] for k, _, _ in FOLDERS if folders[k]["count"]]
    if zh:
        lines = ["# 整理收件匣（建議）", "", f"{len(rows)} 封信建議分成 {len(ordered)} 個資料夾。這只是建議，沒有搬動或貼標任何信。", ""]
    else:
        lines = ["# Organize inbox (proposal)", "",
                 f"{len(rows)} emails fit into {len(ordered)} folders. This is a proposal: nothing was moved or labelled.", ""]
    for g in ordered:
        lines.append(f"## {g['name']} ({g['count']})")
        for it in g["items"][:6]:
            lines.append(f"- {it['subject'] or '—'} · {it['from_name']}")
    lines += ["", "## 篩選規則建議" if zh else "## Suggested filter rules"]
    for rule in rules:
        lines.append(f"- `{rule['match']}` → {rule['folder_name']}")
    if not rules:
        lines.append("- 無。" if zh else "- None.")
    lines += ["", "## 噪音來源" if zh else "## Noise sources"]
    for n in noise_list[:8]:
        extra = ("（可退訂）" if zh else " (has unsubscribe)") if n["unsubscribe"] else ""
        lines.append(f"- {n['sender']} · {n['count']}{extra}")
    if not noise_list:
        lines.append("- 無。" if zh else "- None.")
    return {
        "title": BY_SLUG["organize-inbox"]["zh" if zh else "en"],
        "markdown": "\n".join(lines) + "\n",
        "data": {"folders": ordered, "rules": rules, "noise": noise_list,
                 "archive_candidates": archive, "read_only": True},
    }


QUERY_TOKEN_RE = re.compile(r'(\w+):("[^"]*"|\S+)|"([^"]+)"|(\S+)')


def parse_query(q: str) -> dict:
    out = {"terms": [], "from": [], "to": [], "has_attachment": False, "unread": False,
           "after": None, "before": None, "in": []}
    for m in QUERY_TOKEN_RE.finditer(q or ""):
        key, val, phrase, word = m.groups()
        if key:
            key, val = key.lower(), val.strip('"')
            if key == "from":
                out["from"].append(val.lower())
            elif key == "to":
                out["to"].append(val.lower())
            elif key == "has" and val.lower() in ("attachment", "attachments", "附件"):
                out["has_attachment"] = True
            elif key == "is" and val.lower() == "unread":
                out["unread"] = True
            elif key in ("after", "before"):
                try:
                    out[key] = int(datetime.fromisoformat(val[:10]).replace(tzinfo=yhbmail.TZ).timestamp())
                except ValueError:
                    out["terms"].append(f"{key}:{val}".lower())
            elif key == "in":
                out["in"].append(val.lower())
            else:
                out["terms"].append(f"{key}:{val}".lower())
        else:
            out["terms"].append((phrase or word).lower())
    return out


def _snippet_around(text: str, term: str, n: int = 140) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    i = text.lower().find(term) if term else -1
    if i < 0:
        return _clip(text, n)
    start = max(0, i - n // 3)
    piece = text[start:start + n]
    return ("…" if start else "") + piece + ("…" if start + n < len(text) else "")


def run_find_it(args: dict, lang: str) -> dict:
    zh = _zh(lang)
    q = str(args.get("query") or args.get("q") or "").strip()
    if not q:
        return {"error": "missing query", "message": "請輸入要找的關鍵字。" if zh else "Type something to look for."}
    p = parse_query(q)
    limit = _int(args.get("limit"), 20, hi=100)

    def mail_score(r: dict, mode: str) -> int:
        subj = (r.get("subject") or "").lower()
        frm = (r.get("from_addr") or "").lower()
        to = (r.get("to_addr") or "").lower()
        body = f"{r.get('snippet') or ''} {r.get('body_text') or ''}".lower()
        if any(f not in frm for f in p["from"]) or any(t not in to for t in p["to"]):
            return 0
        if p["has_attachment"] and not triage.attachment_info(r)["has"]:
            return 0
        if p["unread"] and not r.get("unread"):
            return 0
        ts = r.get("date_ts") or 0
        if (p["after"] and ts < p["after"]) or (p["before"] and ts >= p["before"]):
            return 0
        if p["in"] and (r.get("category") or "") not in p["in"] and triage.lane_of(r) not in p["in"]:
            return 0
        if not p["terms"]:
            return 1
        score, hits = 0, 0
        for t in p["terms"]:
            s = (3 if t in subj else 0) + (2 if t in frm else 0) + (1 if t in body else 0)
            hits += 1 if s else 0
            score += s
        if mode == "all" and hits < len(p["terms"]):
            return 0
        return score

    def candidates(mode: str) -> list[dict]:
        where, sql_args = [], []
        for f in p["from"]:
            where.append(_contains_any(("from_addr",), [f], sql_args))
        for t in p["to"]:
            where.append(_contains_any(("to_addr",), [t], sql_args))
        if p["unread"]:
            where.append("unread = 1")
        if p["after"]:
            where.append("COALESCE(date_ts, 0) >= ?")
            sql_args.append(p["after"])
        if p["before"]:
            where.append("COALESCE(date_ts, 0) < ?")
            sql_args.append(p["before"])
        if p["terms"]:
            cols = ("subject", "from_addr", "snippet", "body_text")
            if mode == "all":
                where += [_contains_any(cols, [t], sql_args) for t in p["terms"]]
            else:
                where.append(_contains_any(cols, p["terms"], sql_args))
        return query_mail(where, sql_args)

    mode = "all"
    scored = [x for x in ((mail_score(r, mode), r) for r in candidates(mode)) if x[0] > 0]
    if not scored and len(p["terms"]) > 1:
        mode = "any"
        scored = [x for x in ((mail_score(r, mode), r) for r in candidates(mode)) if x[0] > 0]
    scored.sort(key=lambda x: (-x[0], -(x[1].get("date_ts") or 0)))
    first = p["terms"][0] if p["terms"] else ""
    mails = []
    for score, r in scored[:limit]:
        it = mail_item(r, lang)
        it["score"] = score
        it["match"] = _snippet_around(r.get("body_text") or r.get("snippet") or "", first)
        mails.append(it)
    plain = " ".join(p["terms"])
    events = []
    if p["terms"]:
        for ev in yhbmail.list_events():
            title = (ev.get("title") or "").lower()
            if any(t in title for t in p["terms"]):
                events.append({"id": f"cal:{ev['id']}", "title": ev.get("title") or "",
                               "start_local": ev.get("start_local") or ""})
    cards = []
    if plain:
        seen = set()
        for t in [plain] + p["terms"]:
            for c in second_brain.search(t):
                if c.get("id") in seen:
                    continue
                seen.add(c.get("id"))
                cards.append({"id": c.get("id"), "title": c.get("title") or "", "kind": c.get("kind") or "",
                              "excerpt": _clip(c.get("body") or "", 140)})
        cards = cards[:10]
    total = len(mails) + len(events) + len(cards)
    if zh:
        lines = [f"# 幫我找：{q}", "",
                 f"找到 {len(mails)} 封信、{len(events)} 個行程、{len(cards)} 張第二大腦卡片。"
                 + ("（沒有全部條件都符合的結果，改列符合任一關鍵字的。）" if mode == "any" else "")]
    else:
        lines = [f"# Find it: {q}", "",
                 f"{len(mails)} emails, {len(events)} events, {len(cards)} Second Brain cards."
                 + (" (Nothing matched every word, so these match any of them.)" if mode == "any" else "")]
    if mails:
        lines += ["", "## 信件" if zh else "## Mail"]
        for it in mails:
            lines.append(f"- **{it['subject'] or '—'}** · {it['from_name']} · {it['date_raw']} — {it['match']}")
    if events:
        lines += ["", "## 行程" if zh else "## Calendar"]
        lines += [f"- {e['start_local'][:16].replace('T', ' ')} {e['title']}" for e in events]
    if cards:
        lines += ["", "## 第二大腦" if zh else "## Second Brain"]
        lines += [f"- {c['title']} — {c['excerpt']}" for c in cards]
    if not total:
        lines += ["", "- 沒找到。換個關鍵字，或用 from: has:attachment 縮小範圍。" if zh
                  else "- Nothing found. Try other words, or narrow with from: / has:attachment."]
    return {
        "title": (f"幫我找：{q}" if zh else f"Find it: {q}"),
        "markdown": "\n".join(lines) + "\n",
        "data": {"query": q, "parsed": p, "mode": mode, "mails": mails, "events": events, "cards": cards,
                 "total": total},
    }


# ───────────────────────── F10: meeting prep / brief person / slide / CRM ─────────────────────────

def keywords(title: str) -> dict:
    """Title words -> weight. Capitalised words (likely names / projects) weigh 2; CJK bigrams weigh 1."""
    out: dict[str, int] = {}
    for w in WORD_RE.findall(title or ""):
        lw = w.lower()
        if lw in STOP_WORDS or len(lw) < 3:
            continue
        out[lw] = max(out.get(lw, 0), 2 if w[0].isupper() else 1)
    for run in CJK_RUN_RE.findall(title or ""):
        for stop in STOP_CJK:
            run = run.replace(stop, " ")
        for piece in run.split():
            for i in range(len(piece) - 1):
                out.setdefault(piece[i:i + 2], 1)
    return out


def _event_view(ev: dict) -> dict:
    return {"id": f"cal:{ev['id']}", "title": ev.get("title") or "", "start_local": ev.get("start_local") or "",
            "end_local": ev.get("end_local") or "", "all_day": bool(ev.get("all_day"))}


def _event_dt(ev: dict) -> datetime | None:
    raw = (ev.get("start_local") or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=yhbmail.TZ)


def pick_event(event_id: str, ref: datetime) -> tuple[dict | None, str]:
    events = yhbmail.list_events()
    if event_id:
        eid = event_id[4:] if event_id.startswith("cal:") else event_id
        return next((e for e in events if e["id"] == eid), None), "chosen"
    dated = [(d, e) for e in events if (d := _event_dt(e))]
    upcoming = sorted((x for x in dated if x[0] >= ref), key=lambda x: x[0])
    if upcoming:
        return upcoming[0][1], "next"
    if dated:
        return min(dated, key=lambda x: abs((x[0] - ref).total_seconds()))[1], "closest"
    return None, "none"


def run_meeting_prep(args: dict, lang: str) -> dict:
    zh = _zh(lang)
    ref = _parse_ref(args.get("now"))
    ev, how = pick_event(str(args.get("event_id") or ""), ref)
    if not ev:
        if how == "chosen":
            return {"error": "event not found", "status": 404,
                    "message": "找不到這個行程。" if zh else "That calendar event was not found."}
        return {"error": "no events", "status": 404,
                "message": "行事曆是空的，先按「同步」。" if zh else "The calendar is empty; hit Sync first."}
    kw = keywords(ev.get("title") or "")
    related = []
    cols = ("subject", "from_addr", "snippet", "body_text")
    for r in (mail_containing(cols, list(kw)) if kw else []):
        hay = f"{r.get('subject') or ''} {r.get('from_addr') or ''} {r.get('snippet') or ''} {r.get('body_text') or ''}".lower()
        score = sum(w for k, w in kw.items() if k in hay)
        if score >= 2:
            related.append((score, r))
    related.sort(key=lambda x: (-x[0], -(x[1].get("date_ts") or 0)))
    floor = max(2, related[0][0] / 2) if related else 2
    rows = [r for s, r in related if s >= floor][:10]
    items = [mail_item(r, lang) for r in rows]
    people: dict[str, dict] = {}
    for it in items:
        if it["from_email"] and not triage._is_bulk(it["from_email"]):
            p = people.setdefault(it["from_email"], {"name": it["from_name"], "email": it["from_email"], "emails": 0})
            p["emails"] += 1
    asks = []
    for r in rows:
        for s in open_asks(r):
            asks.append({"text": s, "email_id": r["id"], "subject": r.get("subject") or ""})
    dls = [{"text": d, "email_id": r["id"]} for r in rows for d in deadlines(r)]
    atts = [{"email_id": it["id"], "subject": it["subject"], "names": it["attachments"]}
            for it in items if it["has_attachment"]]
    view = _event_view(ev)
    when = view["start_local"][:16].replace("T", " ")
    if zh:
        lines = [f"# 會前準備：{view['title']}", "", f"時間：{when}" + (f" → {view['end_local'][11:16]}" if not view["all_day"] and len(view["end_local"]) > 15 else "")]
        if how == "closest":
            lines.append("（沒有之後的行程，改用時間最接近的一個。）")
        lines += ["", f"## 與會者（從相關信件推得，{len(people)}）"]
    else:
        lines = [f"# Meeting prep: {view['title']}", "", f"When: {when}" + (f" → {view['end_local'][11:16]}" if not view["all_day"] and len(view["end_local"]) > 15 else "")]
        if how == "closest":
            lines.append("(No upcoming events, so this is the closest one.)")
        lines += ["", f"## People (from related mail, {len(people)})"]
    lines += [f"- {p['name']} <{p['email']}> · {p['emails']}" for p in people.values()] or ["- —"]
    lines += ["", (f"## 相關信件（{len(items)}）" if zh else f"## Related mail ({len(items)})")]
    lines += [_md_item(it, lang) for it in items] or [("- 沒找到相關信件。" if zh else "- No related mail found.")]
    lines += ["", "## 待解問題" if zh else "## Open questions"]
    lines += [f"- {a['text']}" for a in asks] or ["- 無。" if zh else "- None."]
    if dls:
        lines += ["", "## 期限" if zh else "## Deadlines"] + [f"- {d['text']}" for d in dls]
    if atts:
        lines += ["", "## 附件" if zh else "## Attachments"]
        lines += [f"- {a['subject']}" + (f" · {', '.join(a['names'])}" if a["names"] else "") for a in atts]
    lines += ["", "## 準備清單" if zh else "## Checklist"]
    checklist = []
    if items:
        checklist.append(f"重讀「{items[0]['subject']}」" if zh else f"Re-read \"{items[0]['subject']}\"")
    for a in asks[:3]:
        checklist.append(f"想好怎麼回：{a['text']}" if zh else f"Have an answer for: {a['text']}")
    if atts:
        checklist.append("打開並帶上附件" if zh else "Open and bring the attachments")
    if not checklist:
        checklist.append("確認議程與目的" if zh else "Confirm the agenda and goal")
    lines += [f"- [ ] {c}" for c in checklist]
    return {
        "title": (f"會前準備：{view['title']}" if zh else f"Meeting prep: {view['title']}"),
        "markdown": "\n".join(lines) + "\n",
        "data": {"event": view, "picked": how, "keywords": kw, "people": list(people.values()),
                 "related": items, "open_questions": asks, "deadlines": dls, "attachments": atts,
                 "checklist": checklist},
    }


def resolve_person(args: dict) -> tuple[str, str]:
    """Returns (query, email) where email may be empty if only a name was given."""
    person = str(args.get("person") or "").strip()
    if not person and args.get("email_id"):
        row = yhbmail.get_email(str(args["email_id"]))
        if row:
            _, addr = triage.sender(row)
            return addr, addr
    if "@" in person:
        m = re.search(r"<([^>]+)>", person)
        addr = (m.group(1) if m else person).strip().lower()
        return addr, addr
    if person:
        for r in mail_containing(("from_addr",), [person.lower()]):
            name, addr = triage.sender(r)
            if person.lower() in name.lower():
                return person, addr
    return person, ""


def person_profile(email: str, lang: str) -> dict | None:
    email = email.lower()
    rows = []
    name = ""
    for r in mail_containing(("from_addr", "to_addr"), [email]):
        n, addr = triage.sender(r)
        frm = addr == email
        to = email in (r.get("to_addr") or "").lower()
        if frm or to:
            rows.append((r, frm))
            if frm and not name:
                name = n
    if not rows:
        return None
    rows.sort(key=lambda x: x[0].get("date_ts") or 0)
    items = [mail_item(r, lang) for r, _ in rows]
    buckets: dict[str, int] = {}
    for it in items:
        buckets[it["lane"]] = buckets.get(it["lane"], 0) + 1
    asks = [{"text": s, "email_id": r["id"], "subject": r.get("subject") or ""}
            for r, frm in rows if frm for s in open_asks(r)]
    first_name = (name or email).split()[0].split("@")[0]
    events = [_event_view(e) for e in yhbmail.list_events()
              if len(first_name) >= 3 and first_name.lower() in (e.get("title") or "").lower()]
    domain = email.split("@")[-1] if "@" in email else ""
    return {
        "name": name or email, "email": email, "org": domain,
        "total": len(rows), "from_them": sum(1 for _, f in rows if f), "to_them": sum(1 for _, f in rows if not f),
        "unread": sum(1 for it in items if it["unread"]),
        "first_seen": items[0]["date_raw"], "last_seen": items[-1]["date_raw"],
        "first_ts": items[0]["date_ts"], "last_ts": items[-1]["date_ts"],
        "lanes": buckets, "topics": [it["subject"] for it in reversed(items)][:8],
        "open_asks": asks, "attachments": [{"email_id": it["id"], "subject": it["subject"], "names": it["attachments"]}
                                           for it in items if it["has_attachment"]],
        "deadlines": [d for r, f in rows if f for d in deadlines(r)],
        "events": events, "emails": list(reversed(items)),
    }


def run_brief_person(args: dict, lang: str) -> dict:
    zh = _zh(lang)
    query, email = resolve_person(args)
    if not query:
        return {"error": "missing person", "message": "請輸入姓名或信箱，或先選一封信。" if zh
                else "Give a name or address, or select an email first."}
    prof = person_profile(email, lang) if email else None
    if not prof:
        return {"error": "person not found", "status": 404,
                "message": f"本機快取裡找不到「{query}」。" if zh else f"No mail with \"{query}\" in the local cache."}
    contact = get_contact(prof["email"])
    if zh:
        lines = [f"# 這個人是誰：{prof['name']}", "", f"- 信箱：{prof['email']}", f"- 組織網域：{prof['org'] or '—'}",
                 f"- 往來：共 {prof['total']} 封（對方寄來 {prof['from_them']}、寄給對方 {prof['to_them']}；未讀 {prof['unread']}）",
                 f"- 第一次：{prof['first_seen']}；最近：{prof['last_seen']}"]
    else:
        lines = [f"# Brief: {prof['name']}", "", f"- Address: {prof['email']}", f"- Org domain: {prof['org'] or '—'}",
                 f"- History: {prof['total']} emails ({prof['from_them']} from them, {prof['to_them']} to them; {prof['unread']} unread)",
                 f"- First seen: {prof['first_seen']}; last: {prof['last_seen']}"]
    if contact:
        stage = contact.get("stage") or "—"
        tags = ", ".join(contact.get("tags") or []) or "—"
        lines.append(f"- CRM：{stage} · {tags}" if zh else f"- CRM: {stage} · {tags}")
    lines += ["", "## 最近的主題" if zh else "## Recent topics"] + [f"- {t or '—'}" for t in prof["topics"]]
    lines += ["", "## 對方在等你的" if zh else "## Waiting on you"]
    lines += [f"- {a['text']} （{a['subject']}）" if zh else f"- {a['text']} ({a['subject']})" for a in prof["open_asks"]] \
        or ["- 無。" if zh else "- Nothing."]
    if prof["deadlines"]:
        lines += ["", "## 期限" if zh else "## Deadlines"] + [f"- {d}" for d in prof["deadlines"]]
    if prof["attachments"]:
        lines += ["", "## 附件" if zh else "## Attachments"] + [f"- {a['subject']}" for a in prof["attachments"]]
    if prof["events"]:
        lines += ["", "## 相關行程" if zh else "## Related events"]
        lines += [f"- {e['start_local'][:16].replace('T', ' ')} {e['title']}" for e in prof["events"]]
    if contact and contact.get("notes"):
        lines += ["", "## CRM 筆記" if zh else "## CRM notes"] + [f"- {n['text']}" for n in contact["notes"][-5:]]
    return {
        "title": (f"這個人是誰：{prof['name']}" if zh else f"Brief: {prof['name']}"),
        "markdown": "\n".join(lines) + "\n",
        "data": {**prof, "crm": contact},
    }


# slides

def _inline(text: str) -> str:
    s = html.escape(text, quote=True)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", s)


def markdown_to_slides(md: str, title: str = "") -> list[dict]:
    slides: list[dict] = []
    cur: dict | None = None
    for raw in (md or "").splitlines():
        line = raw.rstrip()
        m = re.match(r"^\s{0,3}(#{1,3})\s+(.*)$", line)
        if m:
            if cur and (cur["title"] or cur["lines"]):
                slides.append(cur)
            cur = {"title": m.group(2).strip(), "level": len(m.group(1)), "lines": []}
            continue
        if not line.strip():
            continue
        if cur is None:
            cur = {"title": title, "level": 1, "lines": []}
        b = re.match(r"^\s*(?:[-*•]|\d+[.)、])\s+(?:\[[ x]\]\s+)?(.*)$", line)
        cur["lines"].append({"bullet": bool(b), "text": (b.group(1) if b else line.strip())})
    if cur and (cur["title"] or cur["lines"]):
        slides.append(cur)
    out = []
    for s in slides:
        chunks = [s["lines"][i:i + 8] for i in range(0, len(s["lines"]), 8)] or [[]]
        for n, chunk in enumerate(chunks):
            t = s["title"] + (f" ({n + 1}/{len(chunks)})" if len(chunks) > 1 else "")
            out.append({"title": t, "level": s["level"], "lines": chunk})
    return out[:40]


SLIDE_CSS = """
*{box-sizing:border-box}html,body{margin:0;height:100%;background:#15120f;color:#efe7da;font:18px/1.5 -apple-system,"Segoe UI","Noto Sans TC","PingFang TC",sans-serif}
.deck{height:100%}.slide{display:none;height:100%;padding:7vh 9vw;flex-direction:column;justify-content:center}
.slide.on{display:flex}.slide h1{font-size:2.6em;margin:0 0 .4em;color:#e8c27a;line-height:1.2}
.slide h2{font-size:1.9em;margin:0 0 .6em;color:#e8c27a;line-height:1.25}.slide ul{margin:0;padding-left:1.2em}
.slide li{margin:.35em 0;font-size:1.15em}.slide p{font-size:1.15em;margin:.4em 0;color:#d8cfc1}
code{background:#2a241d;padding:0 .3em;border-radius:4px}.foot{position:fixed;bottom:12px;right:18px;font-size:13px;color:#8a8070}
.foot button{background:#2a241d;color:#efe7da;border:1px solid #4a4136;border-radius:6px;padding:2px 10px;margin-left:6px;cursor:pointer}
@media print{.slide{display:flex!important;page-break-after:always;height:100vh}.foot{display:none}}
"""

SLIDE_JS = """
(function(){var s=document.querySelectorAll('.slide'),i=0,c=document.getElementById('n');
function go(n){i=Math.max(0,Math.min(s.length-1,n));s.forEach(function(e,k){e.classList.toggle('on',k===i)});c.textContent=(i+1)+' / '+s.length;}
document.addEventListener('keydown',function(e){if(['ArrowRight','PageDown',' '].indexOf(e.key)>=0){e.preventDefault();go(i+1)}
else if(['ArrowLeft','PageUp'].indexOf(e.key)>=0){e.preventDefault();go(i-1)}else if(e.key==='Home')go(0);else if(e.key==='End')go(s.length-1)});
document.getElementById('prev').onclick=function(){go(i-1)};document.getElementById('next').onclick=function(){go(i+1)};go(0);})();
"""


def render_slides_html(title: str, slides: list[dict], lang: str) -> str:
    zh = _zh(lang)
    parts = []
    for n, s in enumerate(slides):
        tag = "h1" if n == 0 else "h2"
        body, bullets = [], []
        for ln in s["lines"]:
            if ln["bullet"]:
                bullets.append(f"<li>{_inline(ln['text'])}</li>")
            else:
                if bullets:
                    body.append("<ul>" + "".join(bullets) + "</ul>")
                    bullets = []
                body.append(f"<p>{_inline(ln['text'])}</p>")
        if bullets:
            body.append("<ul>" + "".join(bullets) + "</ul>")
        parts.append(f'<section class="slide"><{tag}>{_inline(s["title"])}</{tag}>{"".join(body)}</section>')
    prev, nxt = ("上一張", "下一張") if zh else ("Prev", "Next")
    return (
        "<!doctype html>\n"
        f'<html lang="{"zh-Hant" if zh else "en"}"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; script-src \'unsafe-inline\'">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<meta name="generator" content="TooPowerInbox skills/slide"><title>{html.escape(title)}</title>'
        f"<style>{SLIDE_CSS}</style></head><body><main class=\"deck\">{''.join(parts)}</main>"
        f'<div class="foot"><span id="n"></span><button id="prev">{prev}</button><button id="next">{nxt}</button></div>'
        f"<script>{SLIDE_JS}</script></body></html>\n"
    )


def _slug_name(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")[:40].strip("-")
    return s or "deck"


def email_markdown(row: dict, lang: str) -> str:
    zh = _zh(lang)
    it = mail_item(row, lang)
    lines = [f"# {it['subject'] or '—'}", f"{it['from_name']} · {it['date_raw']}", "",
             "## 摘要" if zh else "## Summary", f"- {_summary_tail(it, lang)}", "",
             "## 重點" if zh else "## Key points"]
    lines += [f"- {s}" for s in _sentences(row)[:8]] or ["- —"]
    asks, dls = open_asks(row), deadlines(row)
    if asks or dls:
        lines += ["", "## 要求與期限" if zh else "## Asks & deadlines"]
        lines += [f"- {a}" for a in asks] + [("- 期限：" if zh else "- Deadline: ") + d for d in dls]
    lines += ["", "## 下一步" if zh else "## Next steps"] + [f"- {a}" for a in it["actions"]]
    return "\n".join(lines) + "\n"


def run_slide(args: dict, lang: str) -> dict:
    zh = _zh(lang)
    md = str(args.get("markdown") or "")
    source = "markdown"
    if not md.strip() and args.get("from_skill"):
        inner = str(args["from_skill"])
        if inner not in AGENT_SKILLS:
            return {"error": f"cannot turn {inner!r} into slides", "status": 400}
        if not is_enabled(inner):
            return {**disabled_error(inner, lang), "status": 403}
        res = RUNNERS[inner]({k: v for k, v in args.items() if k not in ("from_skill", "markdown", "title")}, lang)
        if res.get("error"):
            return res
        md, source = res["markdown"], f"skill:{inner}"
    elif not md.strip() and args.get("email_id"):
        row = yhbmail.get_email(str(args["email_id"]))
        if not row:
            return {"error": "email not found", "status": 404}
        md, source = email_markdown(row, lang), "email"
    if not md.strip():
        return {"error": "nothing to turn into slides",
                "message": "請給 email_id、from_skill 或 markdown。" if zh else "Give an email_id, a from_skill or markdown."}
    md = md[:40000]
    title = str(args.get("title") or "").strip()
    if not title:
        m = re.search(r"^\s{0,3}#{1,3}\s+(.+)$", md, re.M)
        title = m.group(1).strip() if m else ("投影片" if zh else "Slides")
    title = title[:120]
    slides = markdown_to_slides(md, title)
    doc = render_slides_html(title, slides, lang)
    stamp = datetime.now(yhbmail.TZ).strftime("%Y%m%d-%H%M%S")
    folder = slides_dir()
    folder.mkdir(parents=True, exist_ok=True)
    base = f"{_slug_name(title)}-{stamp}"
    name, n = f"{base}.html", 2
    while (folder / name).exists():
        name, n = f"{base}-{n}.html", n + 1
    path = folder / name
    path.write_text(doc, encoding="utf-8")
    note = (f"已寫出 {len(slides)} 張投影片：{_rel(path)}" if zh else f"Wrote {len(slides)} slides to {_rel(path)}")
    return {
        "title": title,
        "markdown": md,
        "data": {"file": _rel(path), "name": name, "url": f"/api/skills/slides/{name}", "slides": len(slides),
                 "source": source, "bytes": path.stat().st_size, "note": note},
    }


# contacts CRM

def load_contacts() -> list[dict]:
    data = _read_json(contacts_path(), {})
    rows = data.get("contacts") if isinstance(data.get("contacts"), list) else []
    return [c for c in rows if isinstance(c, dict) and c.get("email")]


def save_contacts(rows: list[dict]) -> None:
    rows = sorted(rows, key=lambda c: c["email"])
    _write_json(contacts_path(), {"version": 1, "updated_at": yhbmail.now_iso(), "contacts": rows})


def get_contact(email: str) -> dict | None:
    email = (email or "").lower()
    return next((c for c in load_contacts() if c["email"] == email), None)


def _clean_tags(tags) -> list[str]:
    if isinstance(tags, str):
        tags = re.split(r"[,，\s]+", tags)
    if not isinstance(tags, list):
        return []
    out = []
    for t in tags:
        t = str(t).strip()
        if t and TAG_RE.match(t) and t not in out:
            out.append(t)
    return out[:20]


def upsert_contact(email: str, lang: str, note: str = "", tags=None, stage: str = "") -> tuple[dict, bool]:
    prof = person_profile(email, lang)
    now = yhbmail.now_iso()
    with _lock:
        rows = load_contacts()
        existing = next((c for c in rows if c["email"] == email), None)
        created = existing is None
        c = existing or {"email": email, "created_at": now, "tags": [], "notes": [], "stage": "lead",
                         "source": "skills:crm-contact"}
        if prof:
            c.update({
                "name": prof["name"], "org": prof["org"], "emails_total": prof["total"],
                "from_them": prof["from_them"], "unread": prof["unread"],
                "first_seen": prof["first_seen"], "last_seen": prof["last_seen"],
                "last_subject": prof["topics"][0] if prof["topics"] else "",
                "topics": prof["topics"][:5], "open_asks": len(prof["open_asks"]),
            })
        else:
            c.setdefault("name", email)
            c.setdefault("org", email.split("@")[-1])
        if tags is not None:
            c["tags"] = _clean_tags(list(c.get("tags") or []) + _clean_tags(tags))
        if stage and stage in STAGES:
            c["stage"] = stage
        if note and note.strip():
            c.setdefault("notes", []).append({"at": now, "text": note.strip()[:1000]})
            c["notes"] = c["notes"][-50:]
        c["updated_at"] = now
        if created:
            rows.append(c)
        save_contacts(rows)
    return c, created


def run_crm_contact(args: dict, lang: str) -> dict:
    zh = _zh(lang)
    query, email = resolve_person(args)
    if not query:
        return {"error": "missing person", "message": "請輸入姓名或信箱，或先選一封信。" if zh
                else "Give a name or address, or select an email first."}
    if not email or not person_profile(email, lang):
        return {"error": "person not found", "status": 404,
                "message": f"本機快取裡找不到「{query}」。" if zh else f"No mail with \"{query}\" in the local cache."}
    stage = str(args.get("stage") or "")
    if stage and stage not in STAGES:
        return {"error": f"stage must be one of {', '.join(STAGES)}", "status": 400}
    contact, created = upsert_contact(email, lang, str(args.get("note") or ""), args.get("tags"), stage)
    verb = ("新增" if created else "更新") if zh else ("Added" if created else "Updated")
    if zh:
        lines = [f"# 聯絡人 CRM：{contact['name']}", "", f"{verb}到 {_rel(contacts_path())}。", "",
                 f"- 信箱：{contact['email']}", f"- 組織網域：{contact.get('org') or '—'}",
                 f"- 階段：{contact.get('stage')}", f"- 標籤：{', '.join(contact.get('tags') or []) or '—'}",
                 f"- 往來：{contact.get('emails_total', 0)} 封；最近：{contact.get('last_seen') or '—'}",
                 f"- 最近主題：{contact.get('last_subject') or '—'}"]
    else:
        lines = [f"# CRM: {contact['name']}", "", f"{verb} in {_rel(contacts_path())}.", "",
                 f"- Address: {contact['email']}", f"- Org domain: {contact.get('org') or '—'}",
                 f"- Stage: {contact.get('stage')}", f"- Tags: {', '.join(contact.get('tags') or []) or '—'}",
                 f"- History: {contact.get('emails_total', 0)} emails; last: {contact.get('last_seen') or '—'}",
                 f"- Last topic: {contact.get('last_subject') or '—'}"]
    if contact.get("notes"):
        lines += ["", "## 筆記" if zh else "## Notes"] + [f"- {n['at'][:10]} {n['text']}" for n in contact["notes"][-5:]]
    return {
        "title": (f"聯絡人 CRM：{contact['name']}" if zh else f"CRM: {contact['name']}"),
        "markdown": "\n".join(lines) + "\n",
        "data": {"contact": contact, "created": created, "file": _rel(contacts_path())},
    }


RUNNERS = {
    "morning-brief": run_morning_brief,
    "catch-me-up": run_catch_me_up,
    "organize-inbox": run_organize_inbox,
    "find-it": run_find_it,
    "meeting-prep": run_meeting_prep,
    "brief-person": run_brief_person,
    "slide": run_slide,
    "crm-contact": run_crm_contact,
}


# ───────────────────────── runner ─────────────────────────

def agent_prompt(slug: str, markdown: str, lang: str) -> str:
    meta = BY_SLUG[slug]
    body = agent_bridge.skill_body(meta["prompt"])
    if _zh(lang):
        ask = ("以下是本機從信件快取整理出的結果（事實來源）。請依技能說明改寫成更好讀的繁體中文版本；"
               "人名、日期、金額、主旨只能照抄，不要新增結果裡沒有的事實；不要寄信、不要說已寄出。")
    else:
        ask = ("Below is the result computed locally from the mail cache (the source of truth). Rewrite it per the "
               "skill instructions so it reads better. Copy names, dates, amounts and subjects verbatim; add no facts "
               "that are not in it; never send mail or claim to have sent it.")
    return f"{body}\n\n{ask}\n\n{markdown}"


def source_label(source: str, driver: str, lang: str) -> str:
    if source == "agent":
        return f"AI 改寫 · {driver}" if _zh(lang) else f"AI rewrite · {driver}"
    return "本機規則結果（未接 LLM）" if _zh(lang) else "Local rule-based result (no LLM)"


def agent_off(value) -> bool:
    """`agent` arg: missing / "" / "auto" / true -> use the BYO agent; false, 0, "off", "false", "0", "no" -> don't."""
    if value is None:
        return False
    if isinstance(value, bool):
        return not value
    if isinstance(value, (int, float)):
        return value == 0
    return str(value).strip().lower() in ("off", "false", "0", "no")


def run_skill(slug: str, args: dict | None = None, lang: str = "en") -> tuple[dict, int]:
    args = args if isinstance(args, dict) else {}
    if slug not in BY_SLUG:
        return {"error": f"unknown skill {slug}", "skills": sorted(BY_SLUG)}, 404
    if not is_enabled(slug):
        return disabled_error(slug, lang), 403
    zh = _zh(lang)
    with usage.scope(f"skills:{slug}"):
        out = RUNNERS[slug](args, lang)
        if out.get("error"):
            status = int(out.pop("status", 400))
            out.setdefault("skill", slug)
            return out, status
        driver = triage.agent_driver()
        source, agent_text, agent_error = "heuristic", "", None
        if slug in AGENT_SKILLS and driver != "local" and not agent_off(args.get("agent")):
            text, used, agent_error = triage.ask_agent(agent_prompt(slug, out["markdown"], lang), lang)
            if text:
                source, agent_text, driver = "agent", text[:8000], used
    _mark_run(slug, source)
    meta = BY_SLUG[slug]
    result = {
        "ok": True, "skill": slug, "name": meta["zh" if zh else "en"], "title": out["title"],
        "markdown": out["markdown"], "agent_text": agent_text, "source": source,
        "source_label": source_label(source, driver if source == "agent" else "local", lang),
        "driver": driver, "data": out["data"], "lang": "zh-Hant" if zh else "en",
        "generated_at": yhbmail.now_iso(),
    }
    if agent_error:
        result["agent_error"] = agent_error
    return result, 200


def core_skill_switch(skill: str) -> str | None:
    name = str(skill or "")
    if not name or name in CORE_SKILL_SWITCH:
        return CORE_SKILL_SWITCH.get(name)
    # agent_bridge.skill_body opens SKILLS_DIR/<skill>.md as given, so "./find-it-for-me" or
    # "../skills/FIND-IT-FOR-ME" (case-insensitive filesystems) reach the same prompt file
    try:
        base = agent_bridge.SKILLS_DIR.resolve()
        p = (base / f"{name}.md").resolve()
    except (OSError, ValueError):
        return None
    if p.parent != base:
        return None
    return CORE_SKILL_SWITCH.get(p.stem.lower())


def _guard_core_agent(orig):
    @functools.wraps(orig)
    def run_agent(ask: str = "", skill: str = "", driver=None, lang: str = "en"):
        switch = core_skill_switch(skill)
        if switch and not is_enabled(switch):
            err = disabled_error(switch, lang)
            return {"driver": "none", "skill": skill, "ask": ask, "answer": err["message"],
                    "error": "skill_disabled", "disabled": True}
        return orig(ask=ask, skill=skill, driver=driver, lang=lang)
    run_agent.__tpi_skills__ = True
    return run_agent


if not getattr(agent_bridge.run_agent, "__tpi_skills__", False):
    agent_bridge.run_agent = _guard_core_agent(agent_bridge.run_agent)


# ───────────────────────── routes ─────────────────────────

@get("/api/skills")
def skills_list(req):
    lang = _lang(req)
    s = load_settings()
    return {"skills": [skill_view(m, lang, s) for m in SKILLS], "settings_file": _rel(settings_path()),
            "agent_driver": triage.agent_driver(), "stages": list(STAGES), "lang": lang}


@post("/api/skills/settings")
def skills_settings(req):
    if not local_origin(req):
        return refuse(req.lang_zh())
    b = req.body
    if isinstance(b.get("enabled"), dict):
        changes = b["enabled"]
    elif b.get("slug"):
        changes = {str(b["slug"]): bool(b.get("enabled"))}
    else:
        return {"error": "send {slug, enabled} or {enabled: {slug: bool}}"}, 400
    out, status = set_enabled(changes)
    if status != 200:
        return out, status
    lang = _lang(req)
    s = load_settings()
    return {**out, "skills": [skill_view(m, lang, s) for m in SKILLS]}


@post("/api/skills/run")
def skills_run(req):
    if not local_origin(req):
        return refuse(req.lang_zh())
    b = dict(req.body)
    slug = str(b.pop("skill", "") or b.pop("slug", "") or "")
    lang = _lang(req)
    b.pop("lang", None)
    return run_skill(slug, b, lang)


@get("/api/skills/slides")
def slides_list(req):
    folder = slides_dir()
    files = sorted((p for p in folder.glob("*.html") if SLIDE_NAME_RE.match(p.name)),
                   key=lambda p: p.stat().st_mtime, reverse=True) if folder.is_dir() else []
    return {"slides": [{"name": p.name, "url": f"/api/skills/slides/{p.name}", "file": _rel(p),
                        "bytes": p.stat().st_size,
                        "modified": datetime.fromtimestamp(p.stat().st_mtime, yhbmail.TZ).isoformat(timespec="seconds")}
                       for p in files[:100]]}


@get("/api/skills/slides/*")
def slide_file(req):
    name = unquote(req.params)
    path = slides_dir() / name
    if not SLIDE_NAME_RE.match(name) or not path.is_file():
        return {"error": "not found"}, 404
    return Raw(path.read_bytes(), "text/html; charset=utf-8")


@get("/api/crm/contacts")
def contacts_list(req):
    q = (req.query.get("q") or "").strip().lower()
    rows = load_contacts()
    if q:
        rows = [c for c in rows if q in json.dumps(c, ensure_ascii=False).lower()]
    rows.sort(key=lambda c: c.get("updated_at") or "", reverse=True)
    return {"contacts": rows, "file": _rel(contacts_path()), "stages": list(STAGES)}


@post("/api/crm/contacts/update")
def contacts_update(req):
    if not local_origin(req):
        return refuse(req.lang_zh())
    b = req.body
    email = str(b.get("email") or "").strip().lower()
    if not email or not get_contact(email):
        return {"error": "contact not found"}, 404
    stage = str(b.get("stage") or "")
    if stage and stage not in STAGES:
        return {"error": f"stage must be one of {', '.join(STAGES)}"}, 400
    with _lock:
        rows = load_contacts()
        c = next(c for c in rows if c["email"] == email)
        if "tags" in b:
            c["tags"] = _clean_tags(b.get("tags"))
        if stage:
            c["stage"] = stage
        note = str(b.get("note") or "").strip()
        if note:
            c.setdefault("notes", []).append({"at": yhbmail.now_iso(), "text": note[:1000]})
            c["notes"] = c["notes"][-50:]
        c["updated_at"] = yhbmail.now_iso()
        save_contacts(rows)
    return {"ok": True, "contact": c}


@post("/api/crm/contacts/delete")
def contacts_delete(req):
    if not local_origin(req):
        return refuse(req.lang_zh())
    email = str(req.body.get("email") or "").strip().lower()
    with _lock:
        rows = load_contacts()
        keep = [c for c in rows if c["email"] != email]
        if len(keep) == len(rows):
            return {"error": "contact not found"}, 404
        save_contacts(keep)
    return {"ok": True, "deleted": email}
