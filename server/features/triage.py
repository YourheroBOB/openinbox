"""Super Agent triage view: four lanes on top of the five core buckets.

    needs_you    -> Needs You
    upcoming     -> Upcoming Today (plus today's calendar events)
    worth_a_look -> FYI (flagged high priority, sorted first)
    fyi          -> FYI (a clear newsletter is moved to Other)
    other        -> Other (rolled up into a newsletter / promotion digest)

Every mail carries a one-line summary. With a BYO agent configured in agent.json
(openai_compatible / cli / http) `POST /api/triage/summarize` asks that agent and
caches the answer in `agent_turns` (so the local-cache clear removes it too);
otherwise the summary is a rule-based extract, always labelled as heuristic.
Suggested next actions never send anything: replies end up as local drafts.
Tasks and their history are the user's own record and survive a cache clear.
"""
from __future__ import annotations

import json
import os
import re
from datetime import date, datetime
from urllib.parse import unquote

import agent_bridge
import yhbmail
from features import get, post

LANES = [
    {"id": "needs_you", "buckets": ["needs_you"],
     "en": "Needs You", "zh": "需要你",
     "desc_en": "A question, deadline or decision sitting on you.",
     "desc_zh": "有人在等你回覆、決定或趕期限。"},
    {"id": "upcoming_today", "buckets": ["upcoming"],
     "en": "Upcoming Today", "zh": "今日行程",
     "desc_en": "Invites and today's calendar.",
     "desc_zh": "會議邀請與今天的行事曆。"},
    {"id": "fyi", "buckets": ["worth_a_look", "fyi"],
     "en": "FYI", "zh": "僅供參考",
     "desc_en": "No hard ask. Money and renewals float to the top.",
     "desc_zh": "沒有明確要求；帳單與續約排在最前面。"},
    {"id": "other", "buckets": ["other"],
     "en": "Other", "zh": "其他",
     "desc_en": "Newsletters and promotions, rolled into one digest.",
     "desc_zh": "電子報與廣告，整理成一份摘要。"},
]
LANE_IDS = [lane["id"] for lane in LANES]
BUCKET_TO_LANE = {b: lane["id"] for lane in LANES for b in lane["buckets"]}

ACTIONS = {
    "reply": {"en": "Draft a reply", "zh": "起草回覆", "ui": "draft"},
    "review": {"en": "Review and decide", "zh": "審閱並決定", "ui": "open"},
    "read_attachment": {"en": "Read the attachment", "zh": "讀附件", "ui": "open"},
    "rsvp": {"en": "Check calendar / RSVP", "zh": "看行事曆／回覆邀請", "ui": "calendar"},
    "pay_or_file": {"en": "Check payment / file receipt", "zh": "核對款項／歸檔收據", "ui": "task"},
    "unsubscribe": {"en": "Unsubscribe or archive", "zh": "退訂或封存", "ui": "task"},
    "mark_read": {"en": "Mark read", "zh": "標為已讀", "ui": "mark_read"},
    "follow_up": {"en": "Follow up later", "zh": "稍後追蹤", "ui": "task"},
    "review_digest": {"en": "Skim the digest", "zh": "瀏覽電子報摘要", "ui": "task"},
}
TASK_STATUSES = ("open", "done", "dismissed")
EVENT_RE = re.compile(r"^[a-z][a-z_]{0,39}$")

NEWSLETTER_RE = re.compile(r"(newsletter|digest|weekly|changelog|電子報|週報|月報)", re.I)
PROMO_HINT_RE = re.compile(r"(% off|sale|limited time|優惠|促銷|限時|折扣|coupon|deal)", re.I)
ATTACH_WORD_RE = re.compile(r"(attached|attachment|enclosed|see the file|附件|附檔|檢附)", re.I)
FILENAME_RE = re.compile(
    r"\b[\w\-]+\.(?:pdf|docx?|xlsx?|pptx?|csv|zip|ics|png|jpe?g|txt|key|pages|numbers)\b", re.I)
DEADLINE_RE = re.compile(
    r"((?:by|before|due|until|no later than)\s+)?"
    r"(\d{1,2}:\d{2}\s+)?"
    r"(\d{4}-\d{2}-\d{2}|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
    r"|(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day|today|tomorrow|tonight|EOD|end of (?:day|week)"
    r"|\d{1,2}月\d{1,2}日|週[一二三四五六日]|星期[一二三四五六日天]|今天|明天|本週)"
    r"(\s+\d{1,2}:\d{2})?",
    re.I)
AMOUNT_RE = re.compile(r"((?:NT|US|HK)?\$\s?\d[\d,]*(?:\.\d+)?|(?:USD|TWD|EUR|GBP|JPY|NTD)\s?\d[\d,]*(?:\.\d+)?|€\s?\d[\d,]*(?:\.\d+)?|£\s?\d[\d,]*(?:\.\d+)?)")
GREETING_RE = re.compile(r"^(hi|hello|hey|dear|good (morning|afternoon|evening)|您好|你好|嗨|哈囉)\b[^.!?。！？]{0,40}[,，:：!！]?\s*", re.I)
SENT_SPLIT_RE = re.compile(r"(?<=[.!?。！？])\s+|\n+")
QUESTION_RE = re.compile(r"(\?|？|can you|could you|would you|will you|let me know|請|麻煩)", re.I)


def _zh(lang) -> bool:
    return str(lang or "").lower().startswith("zh")


def _lang(req) -> str:
    return "zh-Hant" if req.lang_zh() else "en"


def _int(value, default: int, lo: int = 1, hi: int = 500) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def ensure_tables() -> None:
    con = yhbmail.db()
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS triage_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_id TEXT,
            action TEXT NOT NULL,
            status TEXT NOT NULL,
            note TEXT,
            created_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS triage_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER,
            email_id TEXT,
            event TEXT NOT NULL,
            detail TEXT,
            at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_triage_tasks_email ON triage_tasks(email_id);
        CREATE INDEX IF NOT EXISTS idx_triage_history_email ON triage_history(email_id);
        """
    )
    con.commit()
    con.close()


# ───────────────────────── classification ─────────────────────────

def lane_of(row: dict) -> str:
    bucket = row.get("category") or "fyi"
    lane = BUCKET_TO_LANE.get(bucket, "fyi")
    if bucket == "fyi" and NEWSLETTER_RE.search(f"{row.get('from_addr') or ''} {row.get('subject') or ''}"):
        return "other"
    return lane


def sender(row: dict) -> tuple[str, str]:
    raw = (row.get("from_addr") or "").strip()
    m = re.match(r'^"?([^"<]*?)"?\s*<([^>]+)>', raw)
    if m:
        name, addr = m.group(1).strip(), m.group(2).strip()
        return name or addr, addr.lower()
    return raw or "?", raw.lower()


def _blob(row: dict) -> str:
    return f"{row.get('subject') or ''} {row.get('snippet') or ''} {row.get('body_text') or ''}"


def attachment_info(row: dict) -> dict:
    text = f"{row.get('snippet') or ''} {row.get('body_text') or ''}"
    names = []
    for m in FILENAME_RE.finditer(text):
        if m.group(0) not in names:
            names.append(m.group(0))
    mentioned = bool(ATTACH_WORD_RE.search(text) or names)
    flagged = bool(row.get("has_attachment"))
    return {"has": flagged or mentioned, "flagged": flagged, "mentioned": mentioned, "names": names[:5]}


def _is_bulk(addr: str) -> bool:
    return any(x in addr for x in yhbmail.NOISE_FROM)


def suggested_actions(row: dict, lang: str = "en", lane: str | None = None, att: dict | None = None) -> list[dict]:
    zh = _zh(lang)
    lane = lane or lane_of(row)
    att = att if att is not None else attachment_info(row)
    blob = _blob(row)
    _, addr = sender(row)
    bulk = _is_bulk(addr)
    out: list[tuple[str, str, str]] = []

    def add(kind: str, reason_en: str, reason_zh: str) -> None:
        if kind not in (k for k, _, _ in out):
            out.append((kind, reason_en, reason_zh))

    if lane == "needs_you":
        if bulk:
            add("review", "Automated notice that asks for a decision.", "系統通知，要你做決定。")
        else:
            add("reply", "Someone is waiting on your answer.", "對方在等你回覆。")
    elif not bulk and lane in ("fyi", "upcoming_today") and QUESTION_RE.search(row.get("body_text") or row.get("snippet") or ""):
        add("reply", "Contains a direct question.", "信裡有直接提問。")
    if att["has"]:
        add("read_attachment", "Has an attachment." if att["flagged"] else "Mentions an attachment.",
            "有附件。" if att["flagged"] else "內文提到附件。")
    if lane == "upcoming_today" or yhbmail.CAL_RE.search(blob):
        add("rsvp", "Calendar invite or meeting.", "會議邀請或行程。")
    if yhbmail.MONEY_RE.search(blob):
        add("pay_or_file", "Money, receipt or renewal.", "金流、收據或續約。")
    if lane == "other" and re.search(r"unsubscribe|退訂|取消訂閱", blob, re.I):
        add("unsubscribe", "Bulk mail with an unsubscribe link.", "大量寄送信件，附退訂連結。")
    if row.get("unread") and lane in ("fyi", "other"):
        add("mark_read", "Nothing to do but read it.", "看過即可。")
    if not out:
        add("follow_up", "No clear ask; keep an eye on it.", "沒有明確要求，留意即可。")
    return [
        {"kind": k, "label": ACTIONS[k]["zh" if zh else "en"], "ui": ACTIONS[k]["ui"],
         "reason": rz if zh else re_, "primary": i == 0}
        for i, (k, re_, rz) in enumerate(out)
    ]


# ───────────────────────── summaries ─────────────────────────

def _clip(text: str, n: int) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def heuristic_summary(row: dict, lang: str = "en") -> str:
    """Extractive, rule-based: never invents names, dates or amounts."""
    zh = _zh(lang)
    name, _ = sender(row)
    body = row.get("body_text") or row.get("snippet") or ""
    body = "\n".join(ln for ln in body.splitlines() if not ln.lstrip().startswith(">"))
    body = re.split(r"\n--\s*\n|\nSent from my ", body)[0]
    sentences = [GREETING_RE.sub("", s).strip(" -—–") for s in SENT_SPLIT_RE.split(body)]
    sentences = [s for s in sentences if len(s) >= 8]
    lane = lane_of(row)
    if not sentences:
        core = row.get("subject") or ("（無內文）" if zh else "(no body)")
    else:
        asks = [s for s in sentences[1:] if yhbmail.ACTION_RE.search(s) or QUESTION_RE.search(s)]
        core = sentences[0]
        if asks:
            core = f"{core} {asks[0]}"
        elif len(sentences) > 1 and len(core) + len(sentences[1]) < 110:
            core = f"{core} {sentences[1]}"
    core = re.sub(r"^[A-Z][a-z]+\s+[—–-]\s+", "", core)
    extra = []
    dm = DEADLINE_RE.search(body)
    explicit = dm and re.match(r"\d{4}-\d{2}-\d{2}|\d{1,2}月", dm.group(3))
    if dm and (dm.group(1) or dm.group(2) or explicit or lane in ("needs_you", "upcoming_today")):
        if lane == "upcoming_today":
            label = "時間：" if zh else "when: "
        elif dm.group(1) or lane == "needs_you":
            label = "期限：" if zh else "deadline: "
        else:
            label = "日期：" if zh else "date: "
        extra.append(label + dm.group(0).strip())
    am = AMOUNT_RE.search(body)
    if am:
        extra.append(("金額：" if zh else "amount: ") + am.group(0).strip())
    sep = "：" if zh else ": "
    text = f"{name}{sep}{_clip(core, 150)}"
    if extra:
        text += ("（" + "；".join(extra) + "）") if zh else (" (" + "; ".join(extra) + ")")
    return text


def _summary_skill(lang: str) -> str:
    return f"triage:summary:{'zh' if _zh(lang) else 'en'}"


def cached_agent_summaries(ids: list[str], lang: str) -> dict:
    if not ids:
        return {}
    con = yhbmail.db()
    out = {}
    marks = ",".join("?" for _ in ids)
    for r in con.execute(
        f"SELECT ask, answer, driver FROM agent_turns WHERE skill=? AND ask IN ({marks}) ORDER BY id",
        [_summary_skill(lang), *ids],
    ):
        out[r["ask"]] = {"summary": r["answer"], "driver": r["driver"]}
    con.close()
    return out


def summary_label(source: str, driver: str, lang: str) -> str:
    if source == "agent":
        return f"AI 摘要 · {driver}" if _zh(lang) else f"AI summary · {driver}"
    return "規則摘要（未接 LLM）" if _zh(lang) else "Heuristic summary (no LLM)"


def agent_driver() -> str:
    return agent_bridge.load_agent_cfg().get("driver") or "local"


def ask_agent(prompt: str, lang: str) -> tuple[str, str, str | None]:
    """Run one prompt through the configured BYO agent. Returns (text, driver, error)."""
    cfg = agent_bridge.load_agent_cfg()
    driver = cfg.get("driver") or "local"
    if driver == "local":
        return "", "local", None
    system = agent_bridge.COPILOT_SYSTEM["zh" if _zh(lang) else "en"]
    try:
        if driver == "openai_compatible":
            block = cfg.get("openai_compatible") or {}
            base = (block.get("base_url") or "").rstrip("/")
            key = os.environ.get(block.get("api_key_env") or "OPENAI_API_KEY") or ""
            body = json.dumps({
                "model": block.get("model") or "gpt-4.1-mini",
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                "temperature": 0.2,
            }).encode()
            data = agent_bridge._post_json(
                f"{base}/chat/completions",
                {"Content-Type": "application/json", **({"Authorization": f"Bearer {key}"} if key else {})},
                body, timeout=90, allow_private=bool(block.get("allow_private")))
            text = data["choices"][0]["message"]["content"] or ""
        elif driver in ("cli", "http"):
            pack = {"ask": system + "\n\n" + prompt, "lang": "zh-Hant" if _zh(lang) else "en", "mode": "triage"}
            text = agent_bridge._cli(pack, cfg) if driver == "cli" else agent_bridge._http(pack, cfg)
        else:
            return "", driver, f"unknown agent driver {driver}"
    except Exception as e:
        return "", driver, f"{type(e).__name__}: {e}"[:300]
    text = (text or "").strip()
    return text, driver, None if text else "agent returned an empty answer"


def summarize_prompt(item_id: str, lang: str) -> str:
    if _zh(lang):
        ask = ("用一到兩句繁體中文摘要這封信，讓人不開信就懂：誰、要什麼、期限。"
               "人名、金額、日期只能照抄原文，不要編造。只回摘要本身。")
    else:
        ask = ("Summarize this email in one or two sentences so it can be understood without opening it: "
               "who, what they want, any deadline. Copy names, amounts and dates verbatim; never invent them. "
               "Reply with the summary only.")
    return ask + "\n\n" + agent_bridge.copilot_thread_context(item_id)


def agent_summarize(ids: list[str], lang: str) -> dict:
    driver = agent_driver()
    zh = _zh(lang)
    if driver == "local":
        note = ("未接 LLM（agent.json 的 driver 為 local），摘要維持規則式 heuristic。"
                if zh else "No LLM wired (agent.json driver is local); summaries stay heuristic.")
        log_event("summarize", detail={"driver": "local", "count": len(ids), "agent": 0})
        return {"ok": True, "driver": "local", "heuristic": True, "results": [], "note": note}
    results = []
    con = yhbmail.db()
    for item_id in ids:
        if not yhbmail.get_email(item_id):
            results.append({"id": item_id, "error": "not found"})
            continue
        text, used, error = ask_agent(summarize_prompt(item_id, lang), lang)
        if error:
            results.append({"id": item_id, "error": error, "driver": used})
            continue
        text = _clip(text, 600)
        con.execute(
            "INSERT INTO agent_turns(skill, ask, answer, driver, created_at) VALUES (?,?,?,?,?)",
            (_summary_skill(lang), item_id, text, used, yhbmail.now_iso()),
        )
        con.commit()
        results.append({"id": item_id, "summary": text, "driver": used, "summary_source": "agent"})
    con.close()
    ok_n = sum(1 for r in results if r.get("summary"))
    log_event("summarize", detail={"driver": driver, "count": len(ids), "agent": ok_n,
                                   "errors": len(results) - ok_n})
    if zh:
        note = f"BYO agent（{driver}）已摘要 {ok_n}／{len(ids)} 封。"
    else:
        note = f"BYO agent ({driver}) summarized {ok_n}/{len(ids)} emails."
    return {"ok": ok_n > 0 or not ids, "driver": driver, "heuristic": False, "results": results, "note": note}


# ───────────────────────── tasks + history ─────────────────────────

def log_event(event: str, email_id: str = "", task_id: int | None = None, detail: dict | None = None) -> dict:
    ensure_tables()
    con = yhbmail.db()
    at = yhbmail.now_iso()
    cur = con.execute(
        "INSERT INTO triage_history(task_id, email_id, event, detail, at) VALUES (?,?,?,?,?)",
        (task_id, email_id or "", event, json.dumps(detail or {}, ensure_ascii=False)[:2000], at),
    )
    con.commit()
    hid = cur.lastrowid
    con.close()
    return {"id": hid, "task_id": task_id, "email_id": email_id or "", "event": event, "detail": detail or {}, "at": at}


def _subjects(ids) -> dict:
    ids = [i for i in set(ids) if i]
    if not ids:
        return {}
    con = yhbmail.db()
    marks = ",".join("?" for _ in ids)
    out = {r["id"]: r["subject"] for r in con.execute(f"SELECT id, subject FROM emails WHERE id IN ({marks})", ids)}
    con.close()
    return out


def _task_view(r: dict, lang: str, subjects: dict) -> dict:
    meta = ACTIONS.get(r["action"]) or {}
    return {
        "id": r["id"], "email_id": r["email_id"] or "", "action": r["action"],
        "label": meta.get("zh" if _zh(lang) else "en", r["action"]),
        "status": r["status"], "note": r["note"] or "",
        "subject": subjects.get(r["email_id"] or "", ""),
        "created_at": r["created_at"], "updated_at": r["updated_at"],
    }


def list_tasks(lang: str = "en", status: str = "", email_id: str = "", limit: int = 100) -> list[dict]:
    ensure_tables()
    sql, args = "SELECT * FROM triage_tasks WHERE 1=1", []
    if status:
        sql += " AND status=?"; args.append(status)
    if email_id:
        sql += " AND email_id=?"; args.append(email_id)
    sql += " ORDER BY id DESC LIMIT ?"; args.append(limit)
    con = yhbmail.db()
    rows = [dict(r) for r in con.execute(sql, args)]
    con.close()
    subjects = _subjects(r["email_id"] for r in rows)
    return [_task_view(r, lang, subjects) for r in rows]


def create_task(email_id: str, action: str, note: str = "", lang: str = "en") -> tuple[dict, int]:
    if action not in ACTIONS:
        return {"error": f"unknown action {action}", "actions": sorted(ACTIONS)}, 400
    if email_id and not yhbmail.get_email(email_id):
        return {"error": "email not found"}, 404
    ensure_tables()
    now = yhbmail.now_iso()
    con = yhbmail.db()
    cur = con.execute(
        "INSERT INTO triage_tasks(email_id, action, status, note, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (email_id or "", action, "open", (note or "")[:500], now, now),
    )
    con.commit()
    tid = cur.lastrowid
    con.close()
    log_event("task_created", email_id, tid, {"action": action})
    return get_task(tid, lang), 201


def get_task(task_id: int, lang: str = "en") -> dict | None:
    ensure_tables()
    con = yhbmail.db()
    row = con.execute("SELECT * FROM triage_tasks WHERE id=?", (task_id,)).fetchone()
    con.close()
    if not row:
        return None
    row = dict(row)
    return _task_view(row, lang, _subjects([row["email_id"]]))


def update_task(task_id, status: str = "", note=None, lang: str = "en") -> tuple[dict, int]:
    try:
        task_id = int(task_id)
    except (TypeError, ValueError):
        return {"error": "bad id"}, 400
    if status and status not in TASK_STATUSES:
        return {"error": f"status must be one of {', '.join(TASK_STATUSES)}"}, 400
    ensure_tables()
    con = yhbmail.db()
    row = con.execute("SELECT * FROM triage_tasks WHERE id=?", (task_id,)).fetchone()
    if not row:
        con.close()
        return {"error": "task not found"}, 404
    row = dict(row)
    new_status = status or row["status"]
    new_note = row["note"] if note is None else str(note)[:500]
    con.execute("UPDATE triage_tasks SET status=?, note=?, updated_at=? WHERE id=?",
                (new_status, new_note, yhbmail.now_iso(), task_id))
    con.commit()
    con.close()
    log_event("task_" + new_status if status and status != row["status"] else "task_updated",
              row["email_id"], task_id, {"action": row["action"], "from": row["status"], "to": new_status})
    return get_task(task_id, lang), 200


def list_history(lang: str = "en", email_id: str = "", limit: int = 50) -> list[dict]:
    ensure_tables()
    sql, args = "SELECT * FROM triage_history WHERE 1=1", []
    if email_id:
        sql += " AND email_id=?"; args.append(email_id)
    sql += " ORDER BY id DESC LIMIT ?"; args.append(limit)
    con = yhbmail.db()
    rows = [dict(r) for r in con.execute(sql, args)]
    con.close()
    subjects = _subjects(r["email_id"] for r in rows)
    out = []
    for r in rows:
        try:
            detail = json.loads(r["detail"] or "{}")
        except json.JSONDecodeError:
            detail = {}
        out.append({"id": r["id"], "task_id": r["task_id"], "email_id": r["email_id"] or "",
                    "event": r["event"], "detail": detail, "at": r["at"],
                    "subject": subjects.get(r["email_id"] or "", ""),
                    "text": describe_event(r["event"], detail, lang)})
    return out


EVENT_TEXT = {
    "summarize": ("Summaries refreshed", "重新產生摘要"),
    "digest": ("Digest generated", "產生電子報摘要"),
    "task_created": ("Task added", "新增任務"),
    "task_done": ("Task done", "任務完成"),
    "task_dismissed": ("Task dismissed", "任務略過"),
    "task_open": ("Task reopened", "任務重開"),
    "task_updated": ("Task updated", "任務更新"),
    "reply_draft": ("Reply draft requested (local only)", "請 Copilot 起草回覆（只存本機）"),
    "opened": ("Opened the email", "開啟信件"),
    "marked_read": ("Marked read", "標為已讀"),
}


def describe_event(event: str, detail: dict, lang: str) -> str:
    en, zh = EVENT_TEXT.get(event, (event.replace("_", " "), event.replace("_", " ")))
    text = zh if _zh(lang) else en
    action = detail.get("action")
    if action in ACTIONS:
        text += f" · {ACTIONS[action]['zh' if _zh(lang) else 'en']}"
    if event == "summarize":
        text += f" · {detail.get('driver')} {detail.get('agent', 0)}/{detail.get('count', 0)}"
    if event == "digest":
        text += f" · {detail.get('source')} {detail.get('items', 0)}"
    return text


# ───────────────────────── lanes + digest ─────────────────────────

def item_view(row: dict, lang: str = "en", agent: dict | None = None, open_tasks: int = 0) -> dict:
    lane = lane_of(row)
    att = attachment_info(row)
    name, addr = sender(row)
    if agent:
        summary, source, driver = agent["summary"], "agent", agent["driver"]
    else:
        summary, source, driver = heuristic_summary(row, lang), "heuristic", "local"
    return {
        "id": row["id"], "subject": row.get("subject") or "", "from_addr": row.get("from_addr") or "",
        "from_name": name, "from_email": addr, "account": row.get("account") or "",
        "date_raw": row.get("date_raw") or "", "date_ts": row.get("date_ts") or 0,
        "unread": bool(row.get("unread")), "bucket": row.get("category") or "fyi", "lane": lane,
        "priority": "high" if row.get("category") in ("needs_you", "worth_a_look") else "normal",
        "flag_reason": row.get("flag_reason") or "",
        "summary": summary, "summary_source": source, "summary_driver": driver,
        "summary_label": summary_label(source, driver, lang),
        "has_attachment": att["has"], "attachment": att,
        "suggested_actions": suggested_actions(row, lang, lane, att),
        "open_tasks": open_tasks,
    }


def _open_task_counts() -> dict:
    ensure_tables()
    con = yhbmail.db()
    out = {r[0]: r[1] for r in con.execute(
        "SELECT email_id, COUNT(*) FROM triage_tasks WHERE status='open' AND email_id!='' GROUP BY 1")}
    con.close()
    return out


def build_items(rows: list[dict], lang: str) -> list[dict]:
    agent = cached_agent_summaries([r["id"] for r in rows], lang)
    tasks = _open_task_counts()
    return [item_view(r, lang, agent.get(r["id"]), tasks.get(r["id"], 0)) for r in rows]


def _event_date(ev: dict) -> date | None:
    raw = (ev.get("start_local") or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(yhbmail.TZ)
    return dt.date()


def parse_today(value) -> date:
    if value:
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            pass
    return datetime.now(yhbmail.TZ).date()


def calendar_today(today: date) -> tuple[list[dict], list[dict]]:
    todays, later = [], []
    for ev in yhbmail.list_events():
        d = _event_date(ev)
        view = {"id": f"cal:{ev['id']}", "title": ev.get("title") or "", "start_local": ev.get("start_local") or "",
                "end_local": ev.get("end_local") or "", "all_day": bool(ev.get("all_day"))}
        if d == today:
            todays.append(view)
        elif d and d > today:
            later.append(view)
    return todays, later[:3]


def build_lanes(lang: str = "en", account: str | None = None, limit: int = 200, today=None) -> dict:
    zh = _zh(lang)
    rows = yhbmail.list_emails(account=account or None, limit=limit)
    items = build_items(rows, lang)
    lanes = {
        lane["id"]: {"id": lane["id"], "name": lane["zh" if zh else "en"],
                     "description": lane["desc_zh" if zh else "desc_en"], "buckets": lane["buckets"],
                     "count": 0, "unread": 0, "items": []}
        for lane in LANES
    }
    for it in items:
        lane = lanes[it["lane"]]
        lane["items"].append(it)
        lane["count"] += 1
        lane["unread"] += 1 if it["unread"] else 0
    for lane in lanes.values():
        lane["items"].sort(key=lambda i: (i["priority"] != "high", not i["unread"], -(i["date_ts"] or 0)))
    day = parse_today(today)
    todays, later = calendar_today(day)
    lanes["upcoming_today"]["events"] = todays
    lanes["upcoming_today"]["next_events"] = later
    driver = agent_driver()
    sources = {"agent": sum(1 for i in items if i["summary_source"] == "agent"),
               "heuristic": sum(1 for i in items if i["summary_source"] == "heuristic")}
    return {
        "lanes": [lanes[i] for i in LANE_IDS],
        "counts": {i: lanes[i]["count"] for i in LANE_IDS},
        "mapping": BUCKET_TO_LANE,
        "today": day.isoformat(),
        "agent_driver": driver,
        "llm": driver != "local",
        "summary_sources": sources,
        "open_tasks": sum(_open_task_counts().values()),
        "lang": "zh-Hant" if zh else "en",
        "generated_at": yhbmail.now_iso(),
    }


def digest_kind(row: dict) -> str:
    if "CATEGORY_PROMOTIONS" in (row.get("labels") or []) or PROMO_HINT_RE.search(_blob(row)):
        return "promotion"
    return "newsletter"


def build_digest(lang: str = "en", account: str | None = None, limit: int = 200) -> dict:
    zh = _zh(lang)
    rows = [r for r in yhbmail.list_emails(account=account or None, limit=limit) if lane_of(r) == "other"]
    groups: dict[str, dict] = {}
    for r in rows:
        name, addr = sender(r)
        g = groups.setdefault(addr or name, {"sender": name, "sender_email": addr, "kind": digest_kind(r),
                                             "count": 0, "unread": 0, "items": []})
        g["count"] += 1
        g["unread"] += 1 if r.get("unread") else 0
        if digest_kind(r) == "promotion":
            g["kind"] = "promotion"
        g["items"].append({"id": r["id"], "subject": r.get("subject") or "", "date_raw": r.get("date_raw") or "",
                           "unread": bool(r.get("unread")), "has_attachment": attachment_info(r)["has"],
                           "highlight": _clip(heuristic_summary(r, lang).split("：" if zh else ": ", 1)[-1], 140)})
    ordered = sorted(groups.values(), key=lambda g: (-g["count"], g["sender"].lower()))
    n_news = sum(g["count"] for g in ordered if g["kind"] == "newsletter")
    n_promo = sum(g["count"] for g in ordered if g["kind"] == "promotion")
    unread = sum(g["unread"] for g in ordered)
    if zh:
        headline = (f"{len(rows)} 封電子報／廣告，來自 {len(ordered)} 個寄件者"
                    f"（電子報 {n_news}、廣告 {n_promo}；未讀 {unread}）") if rows else "「其他」類目前沒有電子報或廣告。"
    else:
        plural = lambda n, word: f"{n} {word}" + ("" if n == 1 else "s")
        headline = (f"{plural(len(rows), 'bulk email')} from {plural(len(ordered), 'sender')} "
                    f"({plural(n_news, 'newsletter')}, {plural(n_promo, 'promotion')}; {unread} unread)") if rows \
            else "Nothing in Other right now."
    lines = [("# 電子報摘要" if zh else "# Newsletter digest"), "", headline, ""]
    kind_label = {"newsletter": "電子報" if zh else "newsletter", "promotion": "廣告" if zh else "promotion"}
    for g in ordered:
        lines.append(f"## {g['sender']} · {kind_label[g['kind']]} · {g['count']}")
        for it in g["items"]:
            lines.append(f"- {it['subject']} — {it['highlight']}")
        lines.append("")
    return {
        "headline": headline, "groups": ordered, "total": len(rows), "senders": len(ordered),
        "newsletters": n_news, "promotions": n_promo, "unread": unread,
        "markdown": "\n".join(lines).rstrip() + "\n",
        "source": "heuristic", "source_label": summary_label("heuristic", "local", lang),
        "agent_text": "", "lang": "zh-Hant" if zh else "en", "generated_at": yhbmail.now_iso(),
    }


def digest_with_agent(lang: str, account: str | None = None) -> dict:
    out = build_digest(lang, account)
    if out["total"] and agent_driver() != "local":
        ask = ("把下面的電子報與廣告整理成一段三到五點的重點摘要，只講值得知道的新消息，人名、金額、日期照抄原文。"
               if _zh(lang) else
               "Condense these newsletters and promotions into 3-5 bullets of what is actually worth knowing. "
               "Copy names, amounts and dates verbatim.")
        text, driver, error = ask_agent(ask + "\n\n" + out["markdown"], lang)
        if text:
            out.update(source="agent", agent_text=text[:3000], source_label=summary_label("agent", driver, lang))
        else:
            out["agent_error"] = error
    log_event("digest", detail={"source": out["source"], "items": out["total"], "senders": out["senders"]})
    return out


# ───────────────────────── routes ─────────────────────────

@get("/api/triage")
def triage_lanes(req):
    return build_lanes(_lang(req), account=req.query.get("account"),
                       limit=_int(req.query.get("limit"), 200), today=req.query.get("today"))


@get("/api/triage/item/*")
def triage_item(req):
    item_id = unquote(req.params)
    row = yhbmail.get_email(item_id)
    if not row:
        return {"error": "not found"}, 404
    lang = _lang(req)
    item = build_items([row], lang)[0]
    item["tasks"] = list_tasks(lang, email_id=item_id)
    item["history"] = list_history(lang, email_id=item_id, limit=30)
    return item


@post("/api/triage/summaries")
def triage_summaries(req):
    ids = req.body.get("ids") or []
    if not isinstance(ids, list):
        return {"error": "ids must be a list"}, 400
    ids = [str(i) for i in ids][:300]
    lang = _lang(req)
    con = yhbmail.db()
    marks = ",".join("?" for _ in ids) or "''"
    rows = [dict(r) for r in con.execute(f"SELECT * FROM emails WHERE id IN ({marks})", ids)]
    con.close()
    for r in rows:
        r["labels"] = json.loads(r.pop("labels_json", None) or "[]")
    return {"summaries": {
        it["id"]: {k: it[k] for k in ("summary", "summary_source", "summary_label", "has_attachment",
                                       "attachment", "lane")}
        for it in build_items(rows, lang)
    }}


@post("/api/triage/summarize")
def triage_summarize(req):
    lang = _lang(req)
    ids = req.body.get("ids")
    if ids is not None and not isinstance(ids, list):
        return {"error": "ids must be a list"}, 400
    limit = _int(req.body.get("limit"), 20, hi=50)
    if not ids:
        lane = req.body.get("lane") or ""
        rows = yhbmail.list_emails(limit=200)
        ids = [r["id"] for r in rows if not lane or lane_of(r) == lane]
    return agent_summarize([str(i) for i in ids][:limit], lang)


@get("/api/triage/digest")
def triage_digest(req):
    return build_digest(_lang(req), account=req.query.get("account"))


@post("/api/triage/digest")
def triage_digest_run(req):
    return digest_with_agent(_lang(req), account=req.body.get("account"))


@get("/api/triage/tasks")
def triage_tasks(req):
    status = req.query.get("status") or ""
    if status and status not in TASK_STATUSES:
        return {"error": f"status must be one of {', '.join(TASK_STATUSES)}"}, 400
    return {"tasks": list_tasks(_lang(req), status, req.query.get("email_id") or "",
                                _int(req.query.get("limit"), 100)),
            "statuses": list(TASK_STATUSES),
            "actions": {k: v["zh" if req.lang_zh() else "en"] for k, v in ACTIONS.items()}}


@post("/api/triage/tasks")
def triage_task_create(req):
    b = req.body
    return create_task(str(b.get("email_id") or ""), str(b.get("action") or ""), str(b.get("note") or ""), _lang(req))


@post("/api/triage/tasks/update")
def triage_task_update(req):
    b = req.body
    return update_task(b.get("id"), str(b.get("status") or ""), b.get("note"), _lang(req))


@get("/api/triage/history")
def triage_history(req):
    return {"history": list_history(_lang(req), req.query.get("email_id") or "", _int(req.query.get("limit"), 50))}


@post("/api/triage/history")
def triage_history_log(req):
    event = str(req.body.get("event") or "")
    if not EVENT_RE.match(event):
        return {"error": "event must be lowercase letters/underscores"}, 400
    email_id = str(req.body.get("email_id") or "")
    if email_id and not yhbmail.get_email(email_id):
        return {"error": "email not found"}, 404
    detail = req.body.get("detail") if isinstance(req.body.get("detail"), dict) else {}
    action = req.body.get("action")
    if action in ACTIONS:
        detail = {**detail, "action": action}
    entry = log_event(event, email_id, None, detail)
    entry["text"] = describe_event(event, entry["detail"], _lang(req))
    return entry, 201
