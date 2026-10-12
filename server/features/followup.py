"""Follow-up tracker: threads where you wrote last and nobody has answered for N days.

Sent mail comes from the local cache only: mail from one of your configured
accounts (live), plus fixtures/demo_sent.json in demo mode. A thread is waiting
when your latest message in it has no later incoming mail in the same thread
(same thread id, or the same subject from one of the recipients). It surfaces
once it has waited `days` days (default 3, saved in followup_settings).

Done / snooze marks and nudge drafts are the user's own record (they survive a
local-cache clear) and are tied to the sent message they were made for, so a
newer message in the thread starts a fresh follow-up. A nudge is a local draft
only: nothing is ever sent.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

import yhbmail
from features import get, post
from features._origin import local_origin, refuse

try:
    from features import compose
except Exception:  # compose is optional; drafts fall back to the core drafts table
    compose = None

DEFAULT_DAYS = 3
MAX_DAYS = 90
SENT_FIXTURE = yhbmail.ROOT / "fixtures" / "demo_sent.json"
DEMO_FIXTURE = yhbmail.ROOT / "fixtures" / "followup_demo.json"
STATUSES = ("overdue", "waiting", "snoozed", "done")
ACTIONS = ("done", "snooze", "reopen")

ADDR_RE = re.compile(r"[^@\s<>,;\"']+@[^@\s<>,;\"']+\.[^@\s<>,;\"']+")
NAME_ADDR_RE = re.compile(r'^\s*"?([^"<]*?)"?\s*<([^>]+)>\s*$')
PREFIX_RE = re.compile(r"^\s*((re|fwd?|aw|sv|回覆|轉寄)\s*[:：]\s*)+", re.I)
CJK_RE = re.compile(r"[\u3400-\u9fff]")
QUESTION_RE = re.compile(
    r"(\?|？|\b(can|could|would|will) you\b|let me know|please (confirm|reply|send|share|check)|"
    r"請|麻煩|幫我|能否|是否|嗎|呢)", re.I)
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|(?<=[。！？])\s*|\n+")


def _zh(lang) -> bool:
    return str(lang or "").lower().startswith("zh")


def _lang(req) -> str:
    return "zh-Hant" if req.lang_zh() else "en"


def _int(value, default: int, lo: int, hi: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


# ───────────────────────── storage ─────────────────────────

def ensure_tables() -> None:
    yhbmail.init_db()
    con = yhbmail.db()
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS followup_settings (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS followup_state (
            thread TEXT PRIMARY KEY,
            sent_id TEXT NOT NULL,
            status TEXT NOT NULL,
            until_ts INTEGER,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS followup_nudges (
            thread TEXT NOT NULL,
            sent_id TEXT NOT NULL,
            draft_id INTEGER,
            created_at TEXT,
            PRIMARY KEY (thread, sent_id)
        );
        """
    )
    con.commit()
    con.close()


def load_settings() -> dict:
    ensure_tables()
    con = yhbmail.db()
    raw = {r["key"]: r["value"] for r in con.execute("SELECT key, value FROM followup_settings")}
    con.close()
    return {"days": _int(raw.get("days"), DEFAULT_DAYS, 1, MAX_DAYS)}


def save_settings(changes: dict) -> tuple[dict, int]:
    if "days" not in changes:
        return {"error": "days is required"}, 400
    try:
        days = int(changes["days"])
    except (TypeError, ValueError):
        return {"error": "days must be a number"}, 400
    if not 1 <= days <= MAX_DAYS:
        return {"error": f"days must be between 1 and {MAX_DAYS}"}, 400
    ensure_tables()
    con = yhbmail.db()
    con.execute("INSERT INTO followup_settings(key, value) VALUES ('days', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(days),))
    con.commit()
    con.close()
    return load_settings(), 200


def _states() -> dict:
    ensure_tables()
    con = yhbmail.db()
    out = {r["thread"]: dict(r) for r in con.execute("SELECT * FROM followup_state")}
    con.close()
    return out


def _nudges() -> dict:
    ensure_tables()
    con = yhbmail.db()
    out = {(r["thread"], r["sent_id"]): r["draft_id"] for r in con.execute("SELECT * FROM followup_nudges")}
    con.close()
    return out


# ───────────────────────── mail sources ─────────────────────────

def split_addrs(raw: str) -> list[tuple[str, str]]:
    out = []
    for part in re.split(r"[,;，；](?![^<]*>)", raw or ""):
        part = part.strip()
        if not part:
            continue
        m = NAME_ADDR_RE.match(part)
        if m:
            name, addr = m.group(1).strip(), m.group(2).strip()
        else:
            hit = ADDR_RE.search(part)
            if not hit:
                continue
            name, addr = "", hit.group(0)
        out.append((name if "@" not in name else "", addr.lower()))
    return out


def own_addresses() -> set:
    cfg = yhbmail.load_cfg()
    return {str(a.get("email") or "").lower() for a in (cfg.get("accounts") or []) if a.get("email")}


def is_demo() -> bool:
    cfg = yhbmail.load_cfg()
    accounts = cfg.get("accounts") or []
    return (cfg.get("mode") or "demo") == "demo" or not accounts or all(a.get("driver") == "demo" for a in accounts)


def norm_subject(subject: str) -> str:
    return re.sub(r"\s+", " ", PREFIX_RE.sub("", subject or "")).strip().lower()


def _fixture(path, key: str) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    return [x for x in data.get(key) or [] if isinstance(x, dict) and x.get("id")]


def _msg(row: dict, in_db: bool) -> dict:
    body = row.get("body_text") or row.get("snippet") or ""
    return {
        "id": row["id"], "account": (row.get("account") or "").lower(),
        "thread_id": str(row.get("thread_id") or row["id"]),
        "subject": row.get("subject") or "", "from_addr": row.get("from_addr") or "",
        "to_addr": row.get("to_addr") or "", "cc_addr": row.get("cc_addr") or "",
        "date_raw": row.get("date_raw") or "",
        "ts": int(row.get("date_ts") or yhbmail.parse_date_ts(row.get("date_raw") or "")),
        "body": body, "in_db": in_db,
    }


def load_messages() -> tuple[list[dict], list[dict]]:
    """(sent, received) from the local cache; demo mode adds the fictional sent mail and replies."""
    own = own_addresses()
    sent, received = [], []
    for row in yhbmail.list_emails(limit=5000):
        frm = split_addrs(row.get("from_addr") or "")
        (sent if frm and frm[0][1] in own else received).append(_msg(row, True))
    if is_demo():
        seen = {m["id"] for m in sent} | {m["id"] for m in received}
        sent += [_msg(r, False) for r in _fixture(SENT_FIXTURE, "sent") if r["id"] not in seen]
        received += [_msg(r, False) for r in _fixture(DEMO_FIXTURE, "replies") if r["id"] not in seen]
    return [m for m in sent if m["ts"]], [m for m in received if m["ts"]]


def own_lines(body: str) -> list[str]:
    out = []
    for ln in (body or "").splitlines():
        s = ln.strip()
        if s in ("--", "-- ", "—") or re.match(r"^on .{4,80} wrote:$", s, re.I) or re.search(r"寫道[:：]$", s):
            break
        if s.startswith(">"):
            continue
        out.append(s)
    return [s for s in out if s]


def first_question(body: str) -> str:
    lines = own_lines(body)
    for sentence in SENT_SPLIT.split("\n".join(lines[1:] if len(lines) > 1 else lines)):
        sentence = sentence.strip()
        if len(sentence) >= 6 and QUESTION_RE.search(sentence):
            return sentence[:200]
    return ""


def _recipients(m: dict, own: set) -> list[tuple[str, str]]:
    seen, out = set(), []
    for name, addr in split_addrs(m["to_addr"]) + split_addrs(m["cc_addr"]):
        if addr in own or addr in seen:
            continue
        seen.add(addr)
        out.append((name, addr))
    return out


def _is_bulk(addr: str) -> bool:
    return any(x in addr for x in yhbmail.NOISE_FROM)


def _first_name(name: str, addr: str) -> str:
    if compose is not None:
        return compose.first_name(f"{name} <{addr}>" if name else addr)
    if name:
        return name if CJK_RE.search(name) else name.split()[0]
    local = addr.split("@")[0]
    return local.capitalize() if local.isalpha() else ""


def _is_reply_to(r: dict, s: dict, subject: str, recipients: set) -> bool:
    if r["account"] != s["account"] or r["ts"] <= s["ts"]:
        return False
    if r["thread_id"] == s["thread_id"]:
        return True
    frm = split_addrs(r["from_addr"])
    return bool(subject) and norm_subject(r["subject"]) == subject and bool(frm) and frm[0][1] in recipients


# ───────────────────────── analysis ─────────────────────────

def parse_now(value) -> int:
    if value in (None, ""):
        return int(datetime.now(yhbmail.TZ).timestamp())
    if isinstance(value, (int, float)):
        return int(value)
    raw = str(value).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        try:
            return int(datetime.fromisoformat(raw).replace(tzinfo=yhbmail.TZ).timestamp())
        except ValueError:
            return int(datetime.now(yhbmail.TZ).timestamp())
    ts = yhbmail.parse_date_ts(raw)
    return ts or int(datetime.now(yhbmail.TZ).timestamp())


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, yhbmail.TZ).isoformat(timespec="minutes")


def analyze(days: int | None = None, now=None) -> dict:
    """Every thread you are waiting on, with status, plus the threads that were answered."""
    days = load_settings()["days"] if days is None else max(1, min(MAX_DAYS, int(days)))
    now_ts = parse_now(now)
    own = own_addresses()
    sent, received = load_messages()
    threads: dict[str, list[dict]] = {}
    for s in sent:
        if s["ts"] <= now_ts:
            threads.setdefault(f"{s['account']}|{s['thread_id']}", []).append(s)
    received = [r for r in received if r["ts"] <= now_ts]
    states, nudges = _states(), _nudges()
    items, answered = [], 0
    for key, msgs in threads.items():
        last = max(msgs, key=lambda m: m["ts"])
        recips = _recipients(last, own)
        if not recips or all(_is_bulk(a) for _, a in recips):
            continue
        subject = norm_subject(last["subject"])
        addrs = {a for _, a in recips}
        if any(_is_reply_to(r, last, subject, addrs) for r in received):
            answered += 1
            continue
        waited = max(0, now_ts - last["ts"])
        due_ts = last["ts"] + days * 86400
        status = "overdue" if now_ts >= due_ts else "waiting"
        st = states.get(key)
        snoozed_until = ""
        if st and st["sent_id"] == last["id"]:
            if st["status"] == "done":
                status = "done"
            elif st["status"] == "snoozed" and (st["until_ts"] or 0) > now_ts:
                status, snoozed_until = "snoozed", _iso(st["until_ts"])
        name, addr = recips[0]
        question = first_question(last["body"])
        lines = own_lines(last["body"])
        items.append({
            "thread": key, "sent_id": last["id"], "account": last["account"],
            "subject": last["subject"], "to_name": name or addr, "to_email": addr,
            "first_name": _first_name(name, addr), "recipients": [a for _, a in recips],
            "sent_at": last["date_raw"], "sent_ts": last["ts"],
            "days_waiting": round(waited / 86400, 1), "waiting_days": waited // 86400,
            "due_at": _iso(due_ts), "due_ts": due_ts, "overdue": status == "overdue", "status": status,
            "snoozed_until": snoozed_until, "asked": bool(question), "question": question,
            "excerpt": " ".join(lines[1:3] if len(lines) > 2 else lines)[:220],
            "lang": "zh" if CJK_RE.search(last["body"] + last["subject"]) else "en",
            "in_db": last["in_db"], "messages": len(msgs),
            "sender_name": (split_addrs(last["from_addr"]) or [("", "")])[0][0],
            "nudge_draft_id": nudges.get((key, last["id"])),
        })
    order = {s: i for i, s in enumerate(STATUSES)}
    items.sort(key=lambda i: (order[i["status"]], i["sent_ts"] if i["status"] in ("overdue", "waiting") else -i["sent_ts"]))
    counts = {s: sum(1 for i in items if i["status"] == s) for s in STATUSES}
    counts["answered"] = answered
    return {"days": days, "now": _iso(now_ts), "now_ts": now_ts, "items": items, "counts": counts,
            "demo": is_demo()}


def replied_received_ids(now=None) -> set:
    """Incoming mail you already answered (a later message of yours in the same thread)."""
    now_ts = parse_now(now)
    own = own_addresses()
    sent, received = load_messages()
    out = set()
    for r in received:
        frm = split_addrs(r["from_addr"])
        sender = frm[0][1] if frm else ""
        subject = norm_subject(r["subject"])
        for s in sent:
            if s["account"] != r["account"] or not r["ts"] < s["ts"] <= now_ts:
                continue
            if s["thread_id"] == r["thread_id"] or (
                    subject and norm_subject(s["subject"]) == subject and sender in {a for _, a in _recipients(s, own)}):
                out.add(r["id"])
                break
    return out


def find(thread: str, now=None) -> dict | None:
    return next((i for i in analyze(now=now)["items"] if i["thread"] == thread), None)


def set_state(thread: str, action: str, days=None, now=None, lang: str = "en") -> tuple[dict, int]:
    zh = _zh(lang)
    if action not in ACTIONS:
        return {"error": f"action must be one of {', '.join(ACTIONS)}"}, 400
    item = find(thread, now)
    if not item:
        return {"error": "找不到這個待回覆信件串" if zh else "follow-up not found"}, 404
    ensure_tables()
    con = yhbmail.db()
    if action == "reopen":
        con.execute("DELETE FROM followup_state WHERE thread=?", (thread,))
    else:
        until = None
        if action == "snooze":
            until = parse_now(now) + _int(days, 2, 1, MAX_DAYS) * 86400
        con.execute(
            "INSERT INTO followup_state(thread, sent_id, status, until_ts, updated_at) VALUES (?,?,?,?,?) "
            "ON CONFLICT(thread) DO UPDATE SET sent_id=excluded.sent_id, status=excluded.status, "
            "until_ts=excluded.until_ts, updated_at=excluded.updated_at",
            (thread, item["sent_id"], "done" if action == "done" else "snoozed", until, yhbmail.now_iso()))
    con.commit()
    con.close()
    return {"ok": True, "item": find(thread, now)}, 200


# ───────────────────────── nudge drafts ─────────────────────────

def nudge_text(item: dict) -> tuple[str, str]:
    """(subject, body) of a short, polite follow-up in the thread's own language."""
    zh = item["lang"] == "zh"
    subject = item["subject"].strip()
    subject = subject if re.match(r"^\s*re\s*[:：]", subject, re.I) else f"Re: {subject}".strip()
    topic = PREFIX_RE.sub("", item["subject"]).strip()[:100]
    date = item["sent_at"][:10]
    name, q = item["first_name"], item["question"]
    signer = item["sender_name"]
    signer = signer if CJK_RE.search(signer) else signer.split()[0] if signer else ""
    if zh:
        lines = [f"{name} 你好：" if name else "你好：", "",
                 f"想跟進一下我 {date} 寄的「{topic}」。",
                 f"想再確認：「{q}」方便時回我一下。" if q else "方便的時候再回我一下就好。",
                 "", "謝謝！"]
    else:
        lines = [f"Hi {name}," if name else "Hi,", "",
                 f"Just following up on my note from {date} about “{topic}”.",
                 f"Quick check on this one: “{q}”" if q else "Let me know when you have a chance.",
                 "", "Thanks,"]
    if signer:
        lines.append(signer)
    return subject, "\n".join(lines)


def _draft_exists(draft_id) -> bool:
    if not draft_id:
        return False
    con = yhbmail.db()
    row = con.execute("SELECT 1 FROM drafts WHERE id=?", (int(draft_id),)).fetchone()
    con.close()
    return bool(row)


def _save_local_draft(item: dict, subject: str, body: str) -> int:
    lang = "zh-Hant" if item["lang"] == "zh" else "en"
    if compose is not None:
        data = {"kind": "reply" if item["in_db"] else "new", "account": item["account"],
                "to": item["to_email"], "subject": subject, "text": body}
        if item["in_db"]:
            data["source_id"] = item["sent_id"]
        out, status = compose.save_draft(data, lang)
        if status in (200, 201):
            return out["draft"]["id"]
    return yhbmail.save_draft(item["account"], item["to_email"], subject, body, lang)["id"]


def nudge(thread: str, now=None, lang: str = "en") -> tuple[dict, int]:
    zh = _zh(lang)
    item = find(thread, now)
    if not item:
        return {"error": "找不到這個待回覆信件串" if zh else "follow-up not found"}, 404
    note = "草稿只存在本機，不會寄出。" if zh else "Saved as a local draft only. Nothing is sent."
    if _draft_exists(item["nudge_draft_id"]):
        return {"ok": True, "existing": True, "draft_id": item["nudge_draft_id"], "item": item, "note": note}, 200
    subject, body = nudge_text(item)
    draft_id = _save_local_draft(item, subject, body)
    ensure_tables()
    con = yhbmail.db()
    con.execute("INSERT INTO followup_nudges(thread, sent_id, draft_id, created_at) VALUES (?,?,?,?) "
                "ON CONFLICT(thread, sent_id) DO UPDATE SET draft_id=excluded.draft_id, created_at=excluded.created_at",
                (thread, item["sent_id"], draft_id, yhbmail.now_iso()))
    con.commit()
    con.close()
    item["nudge_draft_id"] = draft_id
    return {"ok": True, "existing": False, "draft_id": draft_id, "subject": subject, "body": body,
            "item": item, "note": note}, 201


# ───────────────────────── routes ─────────────────────────

def view(req_query: dict, lang: str) -> dict:
    days = req_query.get("days")
    out = analyze(days=_int(days, DEFAULT_DAYS, 1, MAX_DAYS) if days not in (None, "") else None,
                  now=req_query.get("now"))
    status = req_query.get("status") or ""
    if status == "open":
        out["items"] = [i for i in out["items"] if i["status"] in ("overdue", "waiting")]
    elif status in STATUSES:
        out["items"] = [i for i in out["items"] if i["status"] == status]
    if str(req_query.get("only_questions") or "") in ("1", "true", "yes"):
        out["items"] = [i for i in out["items"] if i["asked"]]
    out["settings"] = load_settings()
    out["note"] = ("你寫了最後一封、對方超過 N 天沒回的信件串。追蹤草稿只存本機，不會寄出。" if _zh(lang) else
                   "Threads where you wrote last and nobody answered for N days. Nudges are local drafts; nothing is sent.")
    return out


@get("/api/followup")
def followup_list(req):
    return view(req.query, _lang(req))


@get("/api/followup/settings")
def followup_settings(req):
    return load_settings()


@post("/api/followup/settings")
def followup_settings_save(req):
    if not local_origin(req):
        return refuse(req.lang_zh())
    return save_settings(req.body)


@post("/api/followup/state")
def followup_state(req):
    if not local_origin(req):
        return refuse(req.lang_zh())
    b = req.body
    return set_state(str(b.get("thread") or ""), str(b.get("action") or ""), b.get("days"), b.get("now"), _lang(req))


@post("/api/followup/nudge")
def followup_nudge(req):
    if not local_origin(req):
        return refuse(req.lang_zh())
    return nudge(str(req.body.get("thread") or ""), req.body.get("now"), _lang(req))
