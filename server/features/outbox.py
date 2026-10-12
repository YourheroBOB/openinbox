"""Schedule Send, Undo Send and confirm-before-release. TooPowerInbox has no delivery transport.

Life of a message:

    draft ──prepare──▶ awaiting_confirm ──confirm (user, token, ack)──▶ undo_window ─┐
                          ▲   │                                   └──▶ scheduled ───┤ due
                 agent ───┘   └─discard / cancel                                     ▼
                 proposes                                                   ready: data/outbox/*.eml,
                                                                            awaiting the user to send it
                                                                            themselves ──▶ done

- Nothing leaves `awaiting_confirm` without a human confirmation: a single-use token
  issued to the app UI, bound to a digest of exactly what was previewed, plus an
  explicit `ack: true`. Agent tools can only propose (`outbox_propose`) and list;
  they never see a token, and no tool confirms. Bodies still holding [TBD] / [待填]
  cannot be confirmed.
- Undo Send: confirming "now" opens a 5–30 s window (default 10). Undo, cancel or
  edit put the message back into Drafts. Scheduled messages sit in the Scheduled
  folder until due; change the time, edit (back to Drafts) or cancel.
- When due, the message is written to `data/outbox/<time>-<id>-<slug>.eml`
  (`X-Unsent: 1`, so mail clients open it as an unsent message) and marked
  "awaiting the user to send it themselves". The transport seam
  (`_outbox_transport.py`) only has `disabled`, which never delivers.
- A daemon ticker, started by the first outbox request (never at import, so scripts that
  load the features do not get one), releases due messages while the server runs (set
  OPENINBOX_OUTBOX_TICK=0 to turn it off); every outbox request also catches up.
- A message claimed for writing (`releasing`) and abandoned for over a minute (the process
  died) is recovered: marked ready if its .eml is complete, else queued again. The file name
  depends only on the message, so a retry never makes a second file.
- The outbox tables are the user's record: the local-cache clear keeps them.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import threading
import traceback
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.policy import default as default_policy
from email.utils import format_datetime, make_msgid
from urllib.parse import unquote

import agent_bridge
import yhbmail
from features import Raw, get, post
from features import _outbox_transport as transport
from features import compose

AWAITING, UNDO, SCHEDULED, RELEASING, READY, DONE, CANCELLED = (
    "awaiting_confirm", "undo_window", "scheduled", "releasing", "ready", "done", "cancelled")
STATES = (AWAITING, UNDO, SCHEDULED, READY, DONE, CANCELLED)
PENDING = (UNDO, SCHEDULED)
UNDO_CHOICES = (5, 10, 20, 30)
DEFAULT_SETTINGS = {"undo_seconds": 10, "transport": transport.DEFAULT}
TOKEN_TTL = 15 * 60
MIN_LEAD = 60
MAX_LEAD_DAYS = 366
MAX_RECIPIENTS = 50
RELEASE_STALE = 60

PLACEHOLDER_RE = re.compile(r"\[(?:TBD|待填)\]", re.I)
ATTACH_RE = re.compile(r"(\battach(?:ed|ment|ments|ing)?\b|\benclosed\b|附件|附檔|檢附|如附)", re.I)
MSGID_RE = re.compile(r"^<[^<>@\s]+@[^<>@\s]+>$")

STATE_LABELS = {
    AWAITING: ("待你確認", "Needs your confirmation"),
    UNDO: ("撤回倒數中", "Undo window open"),
    SCHEDULED: ("已排程", "Scheduled"),
    RELEASING: ("寫出中", "Writing"),
    READY: ("待使用者自行寄出", "Awaiting you to send it yourself"),
    DONE: ("已由你自行寄出", "Sent by you"),
    CANCELLED: ("已取消", "Cancelled"),
}

_lock = threading.RLock()
_ensured: set = set()


def _zh(lang) -> bool:
    return str(lang or "").lower().startswith("zh")


def _lang(req) -> str:
    return "zh-Hant" if req.lang_zh() else "en"


def _msg(zh: bool, zh_text: str, en_text: str) -> str:
    return zh_text if zh else en_text


def _bad(zh: bool, zh_text: str, en_text: str, status: int = 400, **extra) -> tuple[dict, int]:
    return {"error": _msg(zh, zh_text, en_text), **extra}, status


def now_dt() -> datetime:
    return datetime.now(yhbmail.TZ)


def _iso(dt: datetime) -> str:
    return dt.astimezone(yhbmail.TZ).isoformat(timespec="seconds")


def tz_label() -> str:
    off = yhbmail.TZ.utcoffset(None) or timedelta(0)
    minutes = int(off.total_seconds() // 60)
    sign = "+" if minutes >= 0 else "-"
    return f"UTC{sign}{abs(minutes) // 60:02d}:{abs(minutes) % 60:02d}"


def parse_when(value) -> datetime | None:
    """ISO time with an offset, or a wall-clock time (`YYYY-MM-DD HH:MM`) in the app timezone."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=yhbmail.TZ)
    raw = str(value or "").strip()
    if not raw:
        return None
    raw = raw.replace(" ", "T", 1)
    if raw.endswith(("Z", "z")):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=yhbmail.TZ)


# ───────────────────────── storage ─────────────────────────

def ensure_tables() -> None:
    if str(yhbmail.DB) in _ensured and yhbmail.DB.exists():
        return
    compose.ensure_tables()
    con = yhbmail.db()
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            state TEXT NOT NULL,
            created_by TEXT,
            draft_id INTEGER,
            draft_json TEXT,
            account TEXT, to_addr TEXT, cc TEXT, bcc TEXT, subject TEXT, body TEXT, text TEXT,
            kind TEXT, source_id TEXT, in_reply_to TEXT, lang TEXT,
            digest TEXT,
            token_hash TEXT, token_expires REAL,
            mode TEXT, release_ts REAL, release_at TEXT, proposed_at TEXT,
            confirmed_at TEXT, confirmed_by TEXT,
            released_at TEXT, eml_path TEXT, transport TEXT, transport_detail TEXT,
            done_at TEXT, cancelled_at TEXT, cancel_reason TEXT, restored_draft_id INTEGER,
            note TEXT, created_at TEXT, updated_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_outbox_state ON outbox(state, release_ts);
        CREATE TABLE IF NOT EXISTS outbox_settings (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS outbox_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            outbox_id INTEGER, event TEXT, actor TEXT, detail TEXT, at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_outbox_log_item ON outbox_log(outbox_id);
        """
    )
    con.commit()
    con.close()
    _ensured.add(str(yhbmail.DB))


def _log(con, outbox_id: int, event: str, actor: str, detail: str = "") -> None:
    con.execute("INSERT INTO outbox_log(outbox_id, event, actor, detail, at) VALUES (?,?,?,?,?)",
                (outbox_id, event, actor, detail[:500], yhbmail.now_iso()))


def _row(outbox_id) -> dict | None:
    ensure_tables()
    try:
        outbox_id = int(outbox_id)
    except (TypeError, ValueError):
        return None
    con = yhbmail.db()
    row = con.execute("SELECT * FROM outbox WHERE id=?", (outbox_id,)).fetchone()
    con.close()
    return dict(row) if row else None


def history(outbox_id: int) -> list[dict]:
    ensure_tables()
    con = yhbmail.db()
    rows = [dict(r) for r in con.execute(
        "SELECT event, actor, detail, at FROM outbox_log WHERE outbox_id=? ORDER BY id", (outbox_id,))]
    con.close()
    return rows


# ───────────────────────── settings ─────────────────────────

def load_settings() -> dict:
    ensure_tables()
    con = yhbmail.db()
    raw = {r["key"]: r["value"] for r in con.execute("SELECT key, value FROM outbox_settings")}
    con.close()
    out = dict(DEFAULT_SETTINGS)
    for key in out:
        if key in raw:
            try:
                out[key] = json.loads(raw[key])
            except json.JSONDecodeError:
                pass
    if out["undo_seconds"] not in UNDO_CHOICES:
        out["undo_seconds"] = DEFAULT_SETTINGS["undo_seconds"]
    if out["transport"] not in transport.names():
        out["transport"] = transport.DEFAULT
    return out


def save_settings(changes: dict, lang: str) -> tuple[dict, int]:
    zh = _zh(lang)
    clean = {}
    if "undo_seconds" in changes:
        try:
            secs = int(changes["undo_seconds"])
        except (TypeError, ValueError):
            secs = -1
        if secs not in UNDO_CHOICES:
            return _bad(zh, f"撤回秒數只能是 {'、'.join(map(str, UNDO_CHOICES))}",
                        f"undo_seconds must be one of {', '.join(map(str, UNDO_CHOICES))}")
        clean["undo_seconds"] = secs
    if "transport" in changes:
        if changes["transport"] not in transport.names():
            return _bad(zh, "沒有這個寄信傳輸；本專案只有 disabled（不寄信）",
                        "unknown transport; the only one is disabled (nothing is sent)",
                        transports=transport.names())
        clean["transport"] = changes["transport"]
    ensure_tables()
    con = yhbmail.db()
    for key, value in clean.items():
        con.execute("INSERT INTO outbox_settings(key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, json.dumps(value)))
    con.commit()
    con.close()
    return settings_view(lang), 200


def outbox_dir():
    return yhbmail.DATA / "outbox"


def _rel(p) -> str:
    try:
        return str(p.relative_to(yhbmail.ROOT))
    except ValueError:
        return str(p)


def suggestions(now: datetime | None, lang: str) -> list[dict]:
    """Quick picks for the schedule menu, in the app timezone."""
    zh = _zh(lang)
    now = (now or now_dt()).astimezone(yhbmail.TZ)
    out = []
    later = (now + timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)
    if later.date() == now.date() and later.hour <= 20:
        out.append(("later_today", later, "今天稍晚", "Later today"))
    tomorrow = now.date() + timedelta(days=1)
    t_morning = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 8, 0, tzinfo=yhbmail.TZ)
    out.append(("tomorrow_morning", t_morning, "明天早上", "Tomorrow morning"))
    out.append(("tomorrow_afternoon", t_morning.replace(hour=13), "明天下午", "Tomorrow afternoon"))
    days = (7 - now.weekday()) % 7 or 7
    monday = now.date() + timedelta(days=days)
    if monday != tomorrow:
        out.append(("monday_morning", datetime(monday.year, monday.month, monday.day, 8, 0, tzinfo=yhbmail.TZ),
                    "週一早上", "Monday morning"))
    return [{"id": i, "at": _iso(dt), "label": zh_l if zh else en_l} for i, dt, zh_l, en_l in out]


def settings_view(lang: str) -> dict:
    zh = _zh(lang)
    s = load_settings()
    t = transport.get(s["transport"])
    return {
        **s,
        "undo_choices": list(UNDO_CHOICES),
        "transports": transport.names(),
        "transport_info": t.describe(zh),
        "require_confirm": True,
        "outbox_dir": _rel(outbox_dir()),
        "tz": tz_label(),
        "suggestions": suggestions(None, lang),
        "note": _msg(zh, "TooPowerInbox 沒有寄信傳輸：確認或到期後只把信寫成 .eml，放在本機寄件匣待你自行寄出。",
                     "TooPowerInbox has no delivery transport: confirmed or due mail is only written as an .eml "
                     "in the local outbox, waiting for you to send it yourself."),
    }


# ───────────────────────── checks ─────────────────────────

def _addrs(value: str) -> list[str]:
    return compose.split_addrs(value or "")


def address_errors(fields: dict, zh: bool) -> list[str]:
    errs = []
    if not _addrs(fields.get("to_addr")):
        errs.append(_msg(zh, "至少要有一位收件者", "add at least one recipient"))
    total = 0
    for key in ("to_addr", "cc", "bcc"):
        for a in _addrs(fields.get(key)):
            total += 1
            if not compose.ADDR_RE.match(compose.parse_addr(a)[1]):
                label = key.replace("_addr", "")
                errs.append(_msg(zh, f"{label}：「{a}」不是有效的信箱位址", f"{label}: '{a}' is not a valid address"))
    if total > MAX_RECIPIENTS:
        errs.append(_msg(zh, f"收件者超過 {MAX_RECIPIENTS} 位", f"more than {MAX_RECIPIENTS} recipients"))
    account = compose.parse_addr(fields.get("account") or "")[1]
    if not compose.ADDR_RE.match(account):
        errs.append(_msg(zh, "寄件帳號不是有效的信箱位址", "the From account is not a valid address"))
    return errs


def review_notes(fields: dict, zh: bool) -> tuple[list[str], list[str]]:
    """(blocking, warnings) for the confirm dialog. Blocking issues stop confirmation."""
    text = fields.get("text") or ""
    blocking, warnings = [], []
    if PLACEHOLDER_RE.search(text) or PLACEHOLDER_RE.search(fields.get("subject") or ""):
        blocking.append(_msg(zh, "內文或主旨還有 [待填]／[TBD]：先補上真實內容再確認。",
                             "The body or subject still has [TBD] / [待填]: fill in the real facts first."))
    if not (fields.get("subject") or "").strip():
        warnings.append(_msg(zh, "主旨是空的。", "The subject is empty."))
    if not text.strip():
        warnings.append(_msg(zh, "內文是空的（只有引用原信）。", "The body is empty (only the quoted message)."))
    if ATTACH_RE.search(text):
        warnings.append(_msg(zh, "內文提到附件，但本機寄件匣不帶附件；自行寄出前記得附上。",
                             "The body mentions an attachment, but the local outbox carries none; "
                             "attach it before you send."))
    for key in ("to_addr", "cc", "bcc"):
        for a in _addrs(fields.get(key)):
            if any(x in a.lower() for x in yhbmail.NOISE_FROM):
                warnings.append(_msg(zh, f"「{a}」看起來是不收信的系統地址。", f"'{a}' looks like a no-reply address."))
    n = sum(len(_addrs(fields.get(k))) for k in ("to_addr", "cc", "bcc"))
    if n > 10:
        warnings.append(_msg(zh, f"共 {n} 位收件者，請再確認名單。", f"{n} recipients in total: double-check the list."))
    return blocking, warnings


def digest(fields: dict) -> str:
    keys = ("account", "to_addr", "cc", "bcc", "subject", "body")
    raw = json.dumps([fields.get(k) or "" for k in keys], ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ───────────────────────── views ─────────────────────────

def item_view(row: dict, lang: str, now: datetime | None = None) -> dict:
    zh = _zh(lang)
    now = now or now_dt()
    left = None
    if row["state"] in PENDING and row.get("release_ts") is not None:
        left = max(0.0, round(row["release_ts"] - now.timestamp(), 1))
    blocking, warnings = review_notes(row, zh)
    label = STATE_LABELS.get(row["state"], (row["state"], row["state"]))
    eml = row.get("eml_path") or ""
    return {
        "id": row["id"], "state": row["state"], "state_label": label[0 if zh else 1],
        "created_by": row.get("created_by") or "user", "draft_id": row.get("draft_id"),
        "account": row.get("account") or "", "to": row.get("to_addr") or "", "cc": row.get("cc") or "",
        "bcc": row.get("bcc") or "", "subject": row.get("subject") or "", "body": row.get("body") or "",
        "text": row.get("text") or "", "kind": row.get("kind") or "new", "source_id": row.get("source_id") or "",
        "mode": row.get("mode") or "", "release_at": row.get("release_at") or "", "seconds_left": left,
        "proposed_at": row.get("proposed_at") or "", "confirmed_at": row.get("confirmed_at") or "",
        "confirmed_by": row.get("confirmed_by") or "", "released_at": row.get("released_at") or "",
        "eml_path": eml, "eml_name": os.path.basename(eml) if eml else "",
        "eml_url": f"/api/outbox/eml/{row['id']}.eml" if eml and row["state"] in (READY, DONE) else "",
        "transport": row.get("transport") or "", "transport_detail": row.get("transport_detail") or "",
        "done_at": row.get("done_at") or "", "cancelled_at": row.get("cancelled_at") or "",
        "cancel_reason": row.get("cancel_reason") or "", "restored_draft_id": row.get("restored_draft_id"),
        "note": row.get("note") or "", "created_at": row.get("created_at") or "",
        "updated_at": row.get("updated_at") or "", "blocking": blocking, "warnings": warnings,
        "awaiting_user_send": row["state"] == READY,
    }


def list_items(states: list[str] | None, lang: str, limit: int = 200) -> list[dict]:
    """The outbox view (ready/done/cancelled) lists ready mail first, then newest history; the
    Scheduled view lists the soonest first. Ordering happens in SQL so LIMIT never hides new mail."""
    ensure_tables()
    con = yhbmail.db()
    if states:
        marks = ",".join("?" for _ in states)
        if set(states) <= {READY, DONE, CANCELLED} and set(states) & {READY, DONE}:
            rows = con.execute(
                f"SELECT * FROM outbox WHERE state IN ({marks}) "
                "AND (state != ? OR COALESCE(eml_path, '') != '') "
                "ORDER BY (state = ?) DESC, COALESCE(NULLIF(released_at, ''), updated_at) DESC, id DESC LIMIT ?",
                (*states, CANCELLED, READY, limit))
        else:
            rows = con.execute(f"SELECT * FROM outbox WHERE state IN ({marks}) "
                               "ORDER BY COALESCE(release_ts, 9e18), id DESC LIMIT ?", (*states, limit))
    else:
        rows = con.execute("SELECT * FROM outbox ORDER BY id DESC LIMIT ?", (limit,))
    now = now_dt()
    out = [item_view(dict(r), lang, now) for r in rows]
    con.close()
    return out


def summary(lang: str) -> dict:
    ensure_tables()
    con = yhbmail.db()
    counts = {s: 0 for s in STATES}
    for r in con.execute("SELECT state, COUNT(*) AS n FROM outbox GROUP BY state"):
        counts[r["state"]] = r["n"]
    nxt = con.execute("SELECT id, release_at FROM outbox WHERE state IN (?, ?) ORDER BY release_ts LIMIT 1",
                      PENDING).fetchone()
    last = con.execute("SELECT MAX(id) FROM outbox WHERE state=?", (READY,)).fetchone()[0]
    con.close()
    s = load_settings()
    return {"counts": counts, "next": dict(nxt) if nxt else None, "last_ready_id": last or 0,
            "undo_seconds": s["undo_seconds"], "transport": transport.get(s["transport"]).describe(_zh(lang))}


# ───────────────────────── drafts ─────────────────────────

def _draft_row(draft_id: int) -> dict | None:
    compose.ensure_tables()
    con = yhbmail.db()
    row = con.execute("SELECT * FROM drafts WHERE id=?", (draft_id,)).fetchone()
    con.close()
    return dict(row) if row else None


def _fields_from_draft(draft_id) -> dict | None:
    try:
        draft_id = int(draft_id)
    except (TypeError, ValueError):
        return None
    raw = _draft_row(draft_id)
    if not raw:
        return None
    view = compose.draft_view(raw)
    return {
        "draft_id": draft_id, "draft_json": json.dumps(raw, ensure_ascii=False),
        "account": view["account"] or "you@example.com", "to_addr": view["to"], "cc": view["cc"],
        "bcc": view["bcc"], "subject": view["subject"], "body": view["body"], "text": view["text"],
        "kind": view["kind"], "source_id": view["source_id"], "in_reply_to": view["in_reply_to"],
        "lang": view["lang"],
    }


def _fields_from_body(data: dict, lang: str) -> dict:
    clip = compose._clip
    kind = data.get("kind") if data.get("kind") in compose.KINDS else "new"
    text = clip(data.get("text") if data.get("text") is not None else data.get("body"), 100_000)
    quote = clip(data.get("quote"), 100_000)
    source_id = clip(data.get("source_id") or data.get("in_reply_to"), 300)
    return {
        "draft_id": None, "draft_json": "",
        "account": clip(data.get("account") or "you@example.com", 300), "to_addr": clip(data.get("to"), 2000),
        "cc": clip(data.get("cc"), 2000), "bcc": clip(data.get("bcc"), 2000), "subject": clip(data.get("subject"), 500),
        "body": compose.compose_body(text, quote), "text": text, "kind": kind, "source_id": source_id,
        "in_reply_to": source_id if kind == "reply" else "", "lang": "zh-Hant" if _zh(lang) else "en",
        "quote": quote,
    }


def restore_draft(row: dict) -> int:
    """Put an outbox message back into Drafts (same id when it is free) and return the draft id."""
    compose.ensure_tables()
    con = yhbmail.db()
    cols = {r[1] for r in con.execute("PRAGMA table_info(drafts)")}
    try:
        snap = json.loads(row.get("draft_json") or "{}")
    except json.JSONDecodeError:
        snap = {}
    want = row.get("draft_id")
    if want and con.execute("SELECT 1 FROM drafts WHERE id=?", (want,)).fetchone():
        con.close()
        return int(want)
    now = yhbmail.now_iso()
    body = row.get("body") or ""
    text = row.get("text") or ""
    quote = snap.get("quote")
    if quote is None:
        quote = body[len(text):].strip() if text and body.startswith(text) else ""
    fields = {
        **{k: v for k, v in snap.items() if k in cols and k != "id"},
        "account": row.get("account") or "", "to_addr": row.get("to_addr") or "", "cc": row.get("cc") or "",
        "bcc": row.get("bcc") or "", "subject": row.get("subject") or "", "body": body, "quote": quote,
        "kind": row.get("kind") or "new", "source_id": row.get("source_id") or "",
        "in_reply_to": row.get("in_reply_to") or "", "lang": row.get("lang") or "", "updated_at": now,
    }
    fields.setdefault("created_at", now)
    fields = {k: v for k, v in fields.items() if k in cols}
    if want:
        fields["id"] = int(want)
    names = ", ".join(fields)
    marks = ", ".join("?" for _ in fields)
    new_id = con.execute(f"INSERT INTO drafts({names}) VALUES ({marks})", tuple(fields.values())).lastrowid
    con.commit()
    con.close()
    return int(fields.get("id") or new_id)


def _delete_draft(draft_id) -> None:
    if not draft_id:
        return
    con = yhbmail.db()
    con.execute("DELETE FROM drafts WHERE id=?", (int(draft_id),))
    con.commit()
    con.close()


# ───────────────────────── prepare / confirm ─────────────────────────

def prepare(data: dict, lang: str, created_by: str = "user") -> tuple[dict, int]:
    """Snapshot a draft for review. Nothing is queued: the result waits for a human confirmation."""
    zh = _zh(lang)
    if data.get("draft_id") not in (None, ""):
        fields = _fields_from_draft(data.get("draft_id"))
        if not fields:
            return _bad(zh, "找不到這份草稿", "draft not found", 404)
    else:
        fields = _fields_from_body(data, lang)
        if not (fields["text"].strip() or fields["subject"].strip() or fields["to_addr"].strip()):
            return _bad(zh, "空白的信", "empty message")
    errs = address_errors(fields, zh)
    if errs:
        return {"error": errs[0], "errors": errs}, 400
    proposed = parse_when(data.get("send_at")) if data.get("send_at") else None
    now = yhbmail.now_iso()
    token = secrets.token_urlsafe(24) if created_by == "user" else ""
    ensure_tables()
    with _lock:
        con = yhbmail.db()
        if fields["draft_id"]:
            for old in con.execute("SELECT id FROM outbox WHERE state=? AND draft_id=? AND created_by='user'",
                                   (AWAITING, fields["draft_id"])).fetchall():
                con.execute("UPDATE outbox SET state=?, cancelled_at=?, cancel_reason='superseded', updated_at=? "
                            "WHERE id=?", (CANCELLED, now, now, old["id"]))
                _log(con, old["id"], "superseded", created_by)
        cols = ("state", "created_by", "draft_id", "draft_json", "account", "to_addr", "cc", "bcc", "subject",
                "body", "text", "kind", "source_id", "in_reply_to", "lang", "digest", "token_hash",
                "token_expires", "proposed_at", "note", "created_at", "updated_at")
        vals = (AWAITING, created_by, fields["draft_id"], fields["draft_json"], fields["account"], fields["to_addr"],
                fields["cc"], fields["bcc"], fields["subject"], fields["body"], fields["text"], fields["kind"],
                fields["source_id"], fields["in_reply_to"], fields["lang"], digest(fields),
                _hash_token(token) if token else "", now_dt().timestamp() + TOKEN_TTL if token else None,
                _iso(proposed) if proposed else "", compose._clip(data.get("note"), 500), now, now)
        oid = con.execute(f"INSERT INTO outbox({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
                          vals).lastrowid
        _log(con, oid, "proposed" if created_by == "agent" else "prepared", created_by)
        con.commit()
        con.close()
    row = _row(oid)
    out = {"ok": True, "item": item_view(row, lang), "confirm_required": True,
           "settings": settings_view(lang)}
    if token:
        out["token"] = token
    if created_by == "agent":
        out["note"] = _msg(zh, "已放進「待你確認」：只有使用者本人在 TooPowerInbox 介面確認後才會排入寄件匣；"
                               "agent 不能確認，也不會寄出任何東西。",
                           "Queued under 'Needs your confirmation': only the user, in the TooPowerInbox app, "
                           "can confirm it. Agents cannot confirm, and nothing is ever sent.")
    return out, 201


def review(outbox_id, lang: str) -> tuple[dict, int]:
    """Issue a fresh confirmation token for a message waiting for the user (e.g. one an agent proposed)."""
    zh = _zh(lang)
    row = _row(outbox_id)
    if not row:
        return _bad(zh, "找不到這封信", "message not found", 404)
    if row["state"] != AWAITING:
        return _bad(zh, "這封信不在待確認狀態", "this message is not waiting for confirmation", 409, state=row["state"])
    token = secrets.token_urlsafe(24)
    con = yhbmail.db()
    con.execute("UPDATE outbox SET token_hash=?, token_expires=?, updated_at=? WHERE id=?",
                (_hash_token(token), now_dt().timestamp() + TOKEN_TTL, yhbmail.now_iso(), row["id"]))
    _log(con, row["id"], "review", "user")
    con.commit()
    con.close()
    return {"ok": True, "item": item_view(_row(row["id"]), lang), "token": token, "confirm_required": True,
            "settings": settings_view(lang)}, 200


def confirm(data: dict, lang: str, now: datetime | None = None) -> tuple[dict, int]:
    """The human step: the token from prepare/review, ack: true, and now (Undo Send) or a schedule time."""
    zh = _zh(lang)
    now = now or now_dt()
    row = _row(data.get("id"))
    if not row:
        return _bad(zh, "找不到這封信", "message not found", 404)
    if row["state"] != AWAITING:
        return _bad(zh, "這封信已經不在待確認狀態", "this message is no longer waiting for confirmation", 409,
                    state=row["state"])
    token = str(data.get("token") or "")
    if not token or not row.get("token_hash") or not hmac.compare_digest(_hash_token(token), row["token_hash"]):
        return _bad(zh, "缺少或錯誤的確認碼：請在 TooPowerInbox 介面重新確認", "missing or wrong confirmation token: "
                    "confirm again in the TooPowerInbox app", 403)
    if (row.get("token_expires") or 0) < now.timestamp():
        return _bad(zh, "確認碼已過期，請重新檢視後再確認", "the confirmation token expired; review the message again", 403)
    if data.get("ack") is not True:
        return _bad(zh, "請勾選「我已確認收件者與內容」", "tick 'I checked the recipients and content' (ack: true)", 400)
    if digest(row) != row["digest"]:
        return _bad(zh, "內容和預覽時不同，請重新檢視", "the content changed since the preview; review it again", 409)
    blocking, _ = review_notes(row, zh)
    if blocking:
        return {"error": blocking[0], "blocking": blocking}, 409
    mode = data.get("mode") or "now"
    if mode == "now":
        release = now + timedelta(seconds=load_settings()["undo_seconds"])
        state = UNDO
    elif mode == "schedule":
        release = parse_when(data.get("send_at"))
        if not release:
            return _bad(zh, "請給排程時間（send_at）", "give a schedule time (send_at)")
        err = _lead_error(release, now, zh)
        if err:
            return err
        state = SCHEDULED
    else:
        return _bad(zh, "mode 只能是 now 或 schedule", "mode must be now or schedule")
    stamp = _iso(now)
    with _lock:
        con = yhbmail.db()
        n = con.execute(
            "UPDATE outbox SET state=?, mode=?, release_ts=?, release_at=?, confirmed_at=?, confirmed_by='user', "
            "token_hash='', token_expires=NULL, updated_at=? WHERE id=? AND state=?",
            (state, mode, release.timestamp(), _iso(release), stamp, stamp, row["id"], AWAITING)).rowcount
        if not n:
            con.close()
            return _bad(zh, "這封信已經不在待確認狀態", "this message is no longer waiting for confirmation", 409)
        _log(con, row["id"], "confirmed", "user", f"{mode} {_iso(release)}")
        con.commit()
        con.close()
        _delete_draft(row.get("draft_id"))
    item = item_view(_row(row["id"]), lang, now)
    if state == UNDO:
        note = _msg(zh, f"已排入寄件匣：{item['seconds_left']:.0f} 秒內可以撤回，之後寫成 .eml 待你自行寄出。",
                    f"Queued: you can undo for {item['seconds_left']:.0f} s, then it is written as an .eml "
                    f"for you to send yourself.")
    else:
        note = _msg(zh, f"已排程於 {item['release_at'].replace('T', ' ')[:16]}：到時只寫成 .eml，待你自行寄出。",
                    f"Scheduled for {item['release_at'].replace('T', ' ')[:16]}: when due it is only written "
                    f"as an .eml for you to send yourself.")
    return {"ok": True, "item": item, "note": note}, 200


def _lead_error(when: datetime, now: datetime, zh: bool):
    if when.timestamp() < now.timestamp() + MIN_LEAD:
        return _bad(zh, "排程時間要在一分鐘之後；要馬上處理請選「立即」", "schedule at least one minute ahead; "
                    "use 'now' for right away")
    if when - now > timedelta(days=MAX_LEAD_DAYS):
        return _bad(zh, "排程時間不能超過一年", "schedule within a year")
    return None


# ───────────────────────── undo / cancel / edit / reschedule ─────────────────────────

def _back_to_drafts(outbox_id, allowed: tuple, reason: str, lang: str, keep_draft: bool = True,
                    actor: str = "user") -> tuple[dict, int]:
    zh = _zh(lang)
    with _lock:
        row = _row(outbox_id)
        if not row:
            return _bad(zh, "找不到這封信", "message not found", 404)
        if row["state"] not in allowed:
            if reason == "undo":
                return _bad(zh, "來不及撤回：這封信已寫成 .eml（仍未寄出，可在寄件匣移回草稿）",
                            "Too late to undo: it was already written as an .eml (still not sent; move it back "
                            "to Drafts from the outbox)", 409, state=row["state"])
            return _bad(zh, "這封信現在不能這樣處理", "this message cannot do that now", 409, state=row["state"])
        now = yhbmail.now_iso()
        con = yhbmail.db()
        n = con.execute("UPDATE outbox SET state=?, cancelled_at=?, cancel_reason=?, token_hash='', updated_at=? "
                        "WHERE id=? AND state=?", (CANCELLED, now, reason, now, row["id"], row["state"])).rowcount
        con.commit()
        con.close()
        if not n:
            return _bad(zh, "這封信剛剛改變了狀態，請重新整理", "the message just changed state; refresh", 409)
        removed = ""
        if row["state"] == READY and row.get("eml_path"):
            p = yhbmail.ROOT / row["eml_path"]
            if p.is_file() and p.parent.resolve() == outbox_dir().resolve():
                p.unlink()
                removed = row["eml_path"]
        draft_id = restore_draft(row) if keep_draft else None
        con = yhbmail.db()
        con.execute("UPDATE outbox SET restored_draft_id=? WHERE id=?", (draft_id, row["id"]))
        _log(con, row["id"], reason, actor, f"draft {draft_id}" if draft_id else "")
        con.commit()
        con.close()
    notes = {
        "undo": ("已撤回，信放回草稿匣。", "Undone: the message is back in Drafts."),
        "edit": ("已取消排程並放回草稿匣，改完再重新排程。", "Unscheduled and back in Drafts: edit it, then schedule again."),
        "cancel": ("已取消，信放回草稿匣。" if keep_draft else "已取消。",
                   "Cancelled: the message is back in Drafts." if keep_draft else "Cancelled."),
        "discard": ("已捨棄這次確認，草稿不受影響。", "Discarded this confirmation; the draft is unchanged."),
    }[reason]
    return {"ok": True, "item": item_view(_row(row["id"]), lang), "draft_id": draft_id,
            "previous_release_at": row.get("release_at") or row.get("proposed_at") or "",
            "removed_eml": removed, "note": notes[0 if zh else 1]}, 200


def undo(outbox_id, lang: str) -> tuple[dict, int]:
    return _back_to_drafts(outbox_id, (UNDO,), "undo", lang)


def cancel(outbox_id, lang: str, keep_draft: bool = True) -> tuple[dict, int]:
    return _back_to_drafts(outbox_id, (AWAITING, UNDO, SCHEDULED, READY), "cancel", lang, keep_draft)


def edit(outbox_id, lang: str) -> tuple[dict, int]:
    return _back_to_drafts(outbox_id, (AWAITING, UNDO, SCHEDULED, READY), "edit", lang)


def discard(outbox_id, lang: str) -> tuple[dict, int]:
    """Close a confirm dialog without confirming. A user-prepared draft stays where it was."""
    row = _row(outbox_id)
    keep = bool(row and row.get("created_by") != "agent"
                and not (row.get("draft_id") and _draft_row(int(row["draft_id"]))))
    return _back_to_drafts(outbox_id, (AWAITING,), "discard", lang, keep_draft=keep)


def reschedule(outbox_id, send_at, lang: str, now: datetime | None = None) -> tuple[dict, int]:
    zh = _zh(lang)
    now = now or now_dt()
    row = _row(outbox_id)
    if not row:
        return _bad(zh, "找不到這封信", "message not found", 404)
    if row["state"] != SCHEDULED:
        return _bad(zh, "只有已排程的信可以改時間", "only scheduled messages can be rescheduled", 409, state=row["state"])
    if str(send_at or "").strip().lower() == "now":
        when = now
    else:
        when = parse_when(send_at)
        if not when:
            return _bad(zh, "看不懂這個時間", "cannot read that time")
        err = _lead_error(when, now, zh)
        if err:
            return err
    with _lock:
        con = yhbmail.db()
        n = con.execute("UPDATE outbox SET release_ts=?, release_at=?, updated_at=? WHERE id=? AND state=?",
                        (when.timestamp(), _iso(when), _iso(now), row["id"], SCHEDULED)).rowcount
        if n:
            _log(con, row["id"], "rescheduled", "user", _iso(when))
        con.commit()
        con.close()
    if not n:
        return _bad(zh, "這封信剛剛改變了狀態，請重新整理", "the message just changed state; refresh", 409)
    released = release_due(now) if when <= now else []
    item = item_view(_row(row["id"]), lang, now)
    note = (_msg(zh, f"已寫成 {item['eml_name']}，待你自行寄出。", f"Written as {item['eml_name']} for you to send yourself.")
            if released else _msg(zh, f"已改到 {item['release_at'].replace('T', ' ')[:16]}。",
                                  f"Moved to {item['release_at'].replace('T', ' ')[:16]}."))
    return {"ok": True, "item": item, "note": note}, 200


def mark_done(outbox_id, lang: str) -> tuple[dict, int]:
    zh = _zh(lang)
    row = _row(outbox_id)
    if not row:
        return _bad(zh, "找不到這封信", "message not found", 404)
    if row["state"] != READY:
        return _bad(zh, "只有待自行寄出的信可以標成已寄出", "only messages awaiting you can be marked as sent", 409,
                    state=row["state"])
    now = yhbmail.now_iso()
    con = yhbmail.db()
    con.execute("UPDATE outbox SET state=?, done_at=?, updated_at=? WHERE id=? AND state=?",
                (DONE, now, now, row["id"], READY))
    _log(con, row["id"], "marked_done", "user")
    con.commit()
    con.close()
    return {"ok": True, "item": item_view(_row(row["id"]), lang),
            "note": _msg(zh, "已記錄為你已自行寄出。", "Recorded as sent by you.")}, 200


# ───────────────────────── release: write the .eml ─────────────────────────

def _slug(subject: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", subject or "").strip("-").lower()[:40] or "mail"


def build_eml(row: dict, when: datetime) -> bytes:
    msg = EmailMessage(policy=default_policy)
    account = row.get("account") or "you@example.com"
    msg["From"] = account
    msg["To"] = ", ".join(_addrs(row.get("to_addr")))
    if _addrs(row.get("cc")):
        msg["Cc"] = ", ".join(_addrs(row.get("cc")))
    if _addrs(row.get("bcc")):
        msg["Bcc"] = ", ".join(_addrs(row.get("bcc")))
    msg["Subject"] = row.get("subject") or ""
    msg["Date"] = format_datetime(when)
    domain = compose.parse_addr(account)[1].rsplit("@", 1)[-1] or "localhost"
    msg["Message-ID"] = make_msgid(domain=domain)
    thread = ""
    if row.get("in_reply_to"):
        src = yhbmail.get_email(row["in_reply_to"]) or {}
        thread = (src.get("thread_id") or "").strip()
    if MSGID_RE.match(thread):
        msg["In-Reply-To"] = thread
        msg["References"] = thread
    msg["X-Unsent"] = "1"
    msg["X-TooPowerInbox-Outbox-Id"] = str(row["id"])
    msg["X-TooPowerInbox-Status"] = "awaiting-user-send"
    msg["X-TooPowerInbox-Note"] = "待使用者自行寄出 / Awaiting the user to send it themselves"
    msg.set_content(row.get("body") or "")
    return msg.as_bytes(policy=default_policy.clone(linesep="\r\n"))


def _eml_path(row: dict, now: datetime):
    """Where a message is written. Depends only on the row, so a retried release reuses the same file."""
    when = datetime.fromtimestamp(row["release_ts"], yhbmail.TZ) if row.get("release_ts") else now
    return when, outbox_dir() / f"{when:%Y%m%d-%H%M%S}-{int(row['id']):04d}-{_slug(row.get('subject'))}.eml"


def _resume_state(row: dict) -> str:
    return UNDO if row.get("mode") == "now" else SCHEDULED


def _release(outbox_id: int, now: datetime) -> dict | None:
    with _lock:
        con = yhbmail.db()
        row = con.execute("SELECT * FROM outbox WHERE id=?", (outbox_id,)).fetchone()
        if not row or row["state"] not in PENDING:
            con.close()
            return None
        prev = row["state"]
        n = con.execute("UPDATE outbox SET state=?, updated_at=? WHERE id=? AND state=? AND release_ts <= ?",
                        (RELEASING, _iso(now_dt()), outbox_id, prev, now.timestamp())).rowcount
        con.commit()
        con.close()
        if not n:
            return None
        row = dict(row)
        path = None
        try:
            when, path = _eml_path(row, now)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".eml.tmp")
            tmp.write_bytes(build_eml(row, when))
            tmp.replace(path)
            t = transport.get(load_settings()["transport"])
            result = t.deliver(path, {"id": outbox_id}) if t.enabled else {"delivered": False, "detail": t.name}
            con = yhbmail.db()
            n = con.execute("UPDATE outbox SET state=?, released_at=?, eml_path=?, transport=?, transport_detail=?, "
                            "updated_at=? WHERE id=? AND state=?",
                            (READY, _iso(now), _rel(path), t.name, str(result.get("detail") or "")[:300], _iso(now),
                             outbox_id, RELEASING)).rowcount
            if n:
                _log(con, outbox_id, "released", "system", _rel(path))
            con.commit()
            con.close()
            if not n:
                _drop_orphan(outbox_id, path)
                return None
        except Exception as e:
            con = yhbmail.db()
            con.execute("UPDATE outbox SET state=?, note=?, updated_at=? WHERE id=? AND state=?",
                        (prev, f"release failed: {type(e).__name__}: {e}"[:300], _iso(now), outbox_id, RELEASING))
            _log(con, outbox_id, "release_failed", "system", f"{type(e).__name__}: {e}")
            con.commit()
            con.close()
            if path is not None:
                path.with_suffix(".eml.tmp").unlink(missing_ok=True)
            traceback.print_exc(file=sys.stderr)
            return None
    return _row(outbox_id)


def _drop_orphan(outbox_id: int, path) -> None:
    """A release that lost its claim (recovered elsewhere, then cancelled) must not leave a stray .eml."""
    row = _row(outbox_id) or {}
    if row.get("state") in (READY, DONE) and row.get("eml_path") == _rel(path):
        return
    if row.get("state") in PENDING + (RELEASING,):
        return
    path.unlink(missing_ok=True)


def recover_releasing(stale: float = RELEASE_STALE) -> list[int]:
    """Messages left in `releasing` by a process that died mid-write. A complete .eml means the write
    finished: mark it ready. Otherwise drop the partial file and put it back in its queue to retry."""
    if not yhbmail.DB.exists():
        return []
    ensure_tables()
    cutoff = now_dt().timestamp() - stale
    fixed = []
    with _lock:
        con = yhbmail.db()
        rows = [dict(r) for r in con.execute("SELECT * FROM outbox WHERE state=?", (RELEASING,))]
        con.close()
        for row in rows:
            seen = parse_when(row.get("updated_at"))
            if seen is not None and seen.timestamp() > cutoff:
                continue
            now = now_dt()
            _, path = _eml_path(row, now)
            path.with_suffix(".eml.tmp").unlink(missing_ok=True)
            con = yhbmail.db()
            if path.is_file():
                t = transport.get(load_settings()["transport"])
                n = con.execute("UPDATE outbox SET state=?, released_at=?, eml_path=?, transport=?, "
                                "transport_detail=?, updated_at=? WHERE id=? AND state=?",
                                (READY, _iso(now), _rel(path), t.name, "recovered", _iso(now), row["id"],
                                 RELEASING)).rowcount
                event, detail = "release_recovered", _rel(path)
            else:
                back = _resume_state(row)
                n = con.execute("UPDATE outbox SET state=?, updated_at=? WHERE id=? AND state=?",
                                (back, _iso(now), row["id"], RELEASING)).rowcount
                event, detail = "release_retry", back
            if n:
                _log(con, row["id"], event, "system", detail)
                fixed.append(row["id"])
            con.commit()
            con.close()
    return fixed


def release_due(now: datetime | None = None) -> list[dict]:
    """Write every confirmed message whose time has come to data/outbox/*.eml. Idempotent."""
    if not yhbmail.DB.exists():
        return []
    now = now or now_dt()
    ensure_tables()
    recover_releasing()
    con = yhbmail.db()
    ids = [r[0] for r in con.execute("SELECT id FROM outbox WHERE state IN (?, ?) AND release_ts <= ? ORDER BY "
                                     "release_ts", (*PENDING, now.timestamp()))]
    con.close()
    return [r for r in (_release(i, now) for i in ids) if r]


_ticker: dict = {"thread": None, "stop": None, "off": False}


def start_ticker(interval: float = 1.0, enable: bool = False) -> threading.Thread | None:
    """Start the background releaser once. stop_ticker() keeps it off until start_ticker(enable=True)."""
    if enable:
        _ticker["off"] = False
    if _ticker["off"] or os.environ.get("OPENINBOX_OUTBOX_TICK") == "0":
        return None
    th = _ticker["thread"]
    if th is not None and th.is_alive():
        return th
    stop = threading.Event()

    def loop():
        while not stop.wait(interval):
            try:
                release_due()
            except Exception:
                traceback.print_exc(file=sys.stderr)

    th = threading.Thread(target=loop, name="tpi-outbox-ticker", daemon=True)
    _ticker.update(thread=th, stop=stop)
    th.start()
    return th


def stop_ticker() -> None:
    stop, th = _ticker["stop"], _ticker["thread"]
    if stop is not None:
        stop.set()
    if th is not None and th.is_alive() and th is not threading.current_thread():
        th.join(timeout=5)
    _ticker.update(thread=None, stop=None, off=True)


# ───────────────────────── agent tools: propose and list, never confirm ─────────────────────────

AGENT_TOOLS = [
    {"name": "outbox_propose",
     "description": "Propose a message for the outbox; it waits under 'Needs your confirmation' until the user "
                    "confirms it in the app. Agents cannot confirm, schedule or send. Args: draft_id, or to, cc, "
                    "bcc, subject, body, account; optional send_at (suggested time). "
                    "提議一封信進寄件匣，必須由使用者在介面親自確認；agent 不能確認、排程或寄出。"},
    {"name": "outbox_list",
     "description": "List outbox messages. Args: state (awaiting_confirm, undo_window, scheduled, ready, done, "
                    "cancelled, all). 列出寄件匣與排程的信。"},
]


def _install_agent_tools() -> None:
    have = {t["name"] for t in agent_bridge.TOOLS}
    for tool in AGENT_TOOLS:
        if tool["name"] not in have:
            agent_bridge.TOOLS.append(tool)
    core = agent_bridge.invoke_tool
    if getattr(core, "_tpi_outbox", False):
        return

    def invoke_with_outbox(name: str, args: dict | None = None) -> dict:
        args = args or {}
        lang = args.get("lang") or "en"
        if name == "outbox_propose":
            allowed = {k: args[k] for k in ("draft_id", "to", "cc", "bcc", "subject", "body", "text", "account",
                                            "kind", "source_id", "send_at", "note") if k in args}
            out, status = prepare(allowed, lang, created_by="agent")
            out.pop("token", None)
            return out if status in (200, 201) else {**out, "status": status}
        if name == "outbox_list":
            state = args.get("state") or "all"
            states = None if state == "all" else [s for s in str(state).split(",") if s in STATES]
            return {"items": [{k: v for k, v in x.items() if k not in ("body",)}
                              for x in list_items(states, lang, 100)]}
        return core(name, args)

    invoke_with_outbox._tpi_outbox = True
    agent_bridge.invoke_tool = invoke_with_outbox


_install_agent_tools()


# ───────────────────────── routes ─────────────────────────

def _human_origin(req) -> bool:
    """Refuse other web pages: no Origin (scripts) or this app's own origin; browsers' fetch metadata must agree."""
    handler = req.handler
    if handler is None:
        return True
    site = handler.headers.get("Sec-Fetch-Site")
    if site and site.lower() not in ("same-origin", "none"):
        return False
    origin = handler.headers.get("Origin")
    if origin is None:
        return True
    try:
        port = handler.server.server_address[1]
    except (AttributeError, IndexError, TypeError):
        port = int(os.environ.get("OPENINBOX_PORT", "8770"))
    return origin.strip().lower().rstrip("/") in (f"http://127.0.0.1:{port}", f"http://localhost:{port}")


def _guard(fn=None, catch_up: bool = True):
    """Every outbox route: refuse foreign pages on POST, keep the ticker alive, release what is due first."""
    def deco(fn):
        def wrapped(req):
            start_ticker()
            if req.method == "POST" and not _human_origin(req):
                return _bad(req.lang_zh(), "拒絕跨來源請求：請從本機 App 介面操作",
                            "cross-origin request refused: use the app itself", 403)
            if catch_up:
                release_due()
            return fn(req)
        wrapped.__name__ = fn.__name__
        wrapped.__module__ = fn.__module__
        return wrapped
    return deco(fn) if fn else deco


def _id(req):
    return req.body.get("id")


@get("/api/outbox/settings")
@_guard
def outbox_settings(req):
    return settings_view(_lang(req))


@post("/api/outbox/settings")
@_guard
def outbox_settings_save(req):
    return save_settings(req.body, _lang(req))


@get("/api/outbox/summary")
@_guard
def outbox_summary(req):
    return summary(_lang(req))


@get("/api/outbox/items")
@_guard
def outbox_items(req):
    raw = req.query.get("state") or "all"
    if raw == "all":
        states = None
    else:
        states = [s for s in raw.split(",") if s in STATES]
        if not states:
            return {"error": f"state must be all or any of {', '.join(STATES)}"}, 400
    try:
        limit = max(1, min(500, int(req.query.get("limit") or 200)))
    except ValueError:
        limit = 200
    return {"items": list_items(states, _lang(req), limit)}


@get("/api/outbox/item/*")
@_guard
def outbox_item(req):
    row = _row(unquote(req.params))
    if not row:
        return {"error": "not found"}, 404
    return {**item_view(row, _lang(req)), "history": history(row["id"])}


@get("/api/outbox/eml/*")
@_guard
def outbox_eml(req):
    name = unquote(req.params)
    row = _row(name[:-4] if name.endswith(".eml") else name)
    if not row or row["state"] not in (READY, DONE) or not row.get("eml_path"):
        return {"error": "not found"}, 404
    p = yhbmail.ROOT / row["eml_path"]
    if not p.is_file() or p.parent.resolve() != outbox_dir().resolve():
        return {"error": "the .eml file is gone"}, 404
    return Raw(p.read_bytes(), "message/rfc822")


@post("/api/outbox/prepare")
@_guard
def outbox_prepare(req):
    return prepare(req.body, _lang(req), created_by="user")


@post("/api/outbox/review")
@_guard
def outbox_review(req):
    return review(_id(req), _lang(req))


@post("/api/outbox/confirm")
@_guard
def outbox_confirm(req):
    return confirm(req.body, _lang(req))


@post("/api/outbox/discard")
@_guard
def outbox_discard(req):
    return discard(_id(req), _lang(req))


@post("/api/outbox/undo")
@_guard
def outbox_undo(req):
    return undo(_id(req), _lang(req))


@post("/api/outbox/cancel")
@_guard
def outbox_cancel(req):
    return cancel(_id(req), _lang(req), keep_draft=req.body.get("keep_draft", True) is not False)


@post("/api/outbox/edit")
@_guard
def outbox_edit(req):
    return edit(_id(req), _lang(req))


@post("/api/outbox/reschedule")
@_guard
def outbox_reschedule(req):
    return reschedule(_id(req), req.body.get("send_at"), _lang(req))


@post("/api/outbox/done")
@_guard
def outbox_done(req):
    return mark_done(_id(req), _lang(req))


@post("/api/outbox/tick")
@_guard(catch_up=False)
def outbox_tick(req):
    lang = _lang(req)
    return {"released": [item_view(r, lang) for r in release_due()], "summary": summary(lang)}
