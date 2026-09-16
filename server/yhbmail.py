"""Mail connectors, taxonomy, and local cache.

Drivers:
  demo  — fixtures, zero setup
  gog   — Gmail via gog (https://gogcli.sh)
  gsk   — Outlook / extra boxes via Genspark CLI (transport only, no Super Agent)
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(os.environ.get("OPENINBOX_ROOT", Path(__file__).resolve().parents[1]))
DATA = ROOT / "data"
DB = DATA / "openinbox.db"
ACCOUNTS_PATH = ROOT / "accounts.json"
FIXTURE = ROOT / "fixtures" / "demo_inbox.json"
TZ = timezone(timedelta(hours=int(os.environ.get("OPENINBOX_TZ_OFFSET", "8"))))

TAXONOMY = [
    {"id": "needs_you", "name": "Needs you", "order": 0,
     "description": "A question, deadline, or decision sitting on you."},
    {"id": "upcoming", "name": "Upcoming", "order": 1,
     "description": "Calendar and scheduled events."},
    {"id": "worth_a_look", "name": "Worth a look", "order": 2,
     "description": "No hard ask, but missing it would hurt."},
    {"id": "fyi", "name": "FYI", "order": 3,
     "description": "Status, newsletters, threads you are only copied on."},
    {"id": "other", "name": "Cleanup", "order": 4,
     "description": "Bulk marketing. Cost of missing it is zero."},
]

NOISE_FROM = (
    "noreply", "no-reply", "no_reply", "donotreply", "newsletter",
    "notifications@", "mailer-daemon", "news@", "marketing@",
)
ACTION_RE = re.compile(
    r"(請回|請確認|請審|需要您|需要你|待決|回一句|action required|please (reply|confirm|review)|kindly reply|can you confirm|yes/no)",
    re.I,
)
MONEY_RE = re.compile(
    r"(receipt|invoice|帳單|發票|payment|續約|renewal|statement|對帳單|credit card)",
    re.I,
)
CAL_RE = re.compile(
    r"(invitation|invite|行事曆|會議邀請|accepted:|declined:|tentative:|calendar)",
    re.I,
)
PROMO_RE = re.compile(
    r"(unsubscribe|優惠|促銷|限時|電子報|newsletter|% off|折扣|行銷)",
    re.I,
)


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def load_cfg() -> dict:
    if ACCOUNTS_PATH.exists():
        return json.loads(ACCOUNTS_PATH.read_text())
    example = ROOT / "accounts.example.json"
    return json.loads(example.read_text()) if example.exists() else {"mode": "demo", "accounts": []}


def db() -> sqlite3.Connection:
    DATA.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=30000")
    return con


def init_db() -> None:
    con = db()
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS emails (
            id TEXT PRIMARY KEY,
            account TEXT NOT NULL,
            platform TEXT NOT NULL,
            thread_id TEXT,
            subject TEXT,
            snippet TEXT,
            from_addr TEXT,
            to_addr TEXT,
            date_raw TEXT,
            date_ts INTEGER,
            unread INTEGER,
            has_attachment INTEGER,
            labels_json TEXT,
            body_text TEXT,
            category TEXT,
            flag_reason TEXT,
            synced_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_emails_ts ON emails(date_ts DESC);
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            calendar_id TEXT,
            title TEXT,
            start_local TEXT,
            end_local TEXT,
            all_day INTEGER,
            synced_at TEXT
        );
        CREATE TABLE IF NOT EXISTS drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account TEXT,
            to_addr TEXT,
            subject TEXT,
            body TEXT,
            in_reply_to TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS agent_turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill TEXT,
            ask TEXT,
            answer TEXT,
            driver TEXT,
            created_at TEXT
        );
        """
    )
    con.commit()
    con.close()


def parse_date_ts(raw: str) -> int:
    if not raw:
        return 0
    raw = raw.strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(raw.replace("Z", "+0000"), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=TZ)
            return int(dt.timestamp())
        except ValueError:
            continue
    try:
        return int(datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return 0


def classify(row: dict) -> tuple[str, str]:
    frm = (row.get("from_addr") or "").lower()
    blob = f"{row.get('subject') or ''} {row.get('snippet') or ''} {row.get('body_text') or ''}"
    labels = row.get("labels") or []
    if CAL_RE.search(blob):
        return "upcoming", "Calendar or meeting"
    if ACTION_RE.search(blob):
        return "needs_you", "Direct ask or deadline"
    if MONEY_RE.search(blob):
        return "worth_a_look", "Money or renewal"
    if PROMO_RE.search(blob) or "CATEGORY_PROMOTIONS" in labels:
        return "other", "Promotion"
    if any(x in frm for x in NOISE_FROM):
        return "fyi", "Automated notice"
    if row.get("unread"):
        return "worth_a_look", "Unread, not obviously junk"
    return "fyi", "No hard action"


def upsert_email(con: sqlite3.Connection, item: dict) -> None:
    cat, reason = classify(item)
    ts = item.get("date_ts") or parse_date_ts(item.get("date_raw") or "")
    con.execute(
        """
        INSERT INTO emails(
            id, account, platform, thread_id, subject, snippet, from_addr, to_addr,
            date_raw, date_ts, unread, has_attachment, labels_json, body_text,
            category, flag_reason, synced_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
            subject=excluded.subject, snippet=excluded.snippet, from_addr=excluded.from_addr,
            date_raw=excluded.date_raw, date_ts=excluded.date_ts, unread=excluded.unread,
            body_text=COALESCE(excluded.body_text, emails.body_text),
            category=excluded.category, flag_reason=excluded.flag_reason, synced_at=excluded.synced_at
        """,
        (
            item["id"], item["account"], item.get("platform") or "demo",
            item.get("thread_id") or item["id"], item.get("subject") or "",
            item.get("snippet") or "", item.get("from_addr") or "",
            item.get("to_addr") or "", item.get("date_raw") or "", ts,
            1 if item.get("unread") else 0, 1 if item.get("has_attachment") else 0,
            json.dumps(item.get("labels") or [], ensure_ascii=False),
            item.get("body_text") or "", cat, reason, now_iso(),
        ),
    )


def run(cmd: list[str], timeout: int = 45) -> tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except FileNotFoundError as e:
        return 127, "", str(e)


def parse_json(text: str):
    text = (text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        if start < 0:
            start = text.find("[")
        if start < 0:
            return None
        try:
            return json.loads(text[start:])
        except json.JSONDecodeError:
            return None


def seed_demo() -> dict:
    fixture = json.loads(FIXTURE.read_text())
    con = db()
    for e in fixture.get("emails") or []:
        upsert_email(con, e)
    for ev in fixture.get("events") or []:
        con.execute(
            """
            INSERT INTO events(id, calendar_id, title, start_local, end_local, all_day, synced_at)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET title=excluded.title, start_local=excluded.start_local,
                end_local=excluded.end_local, synced_at=excluded.synced_at
            """,
            (ev["id"], ev.get("calendar_id"), ev.get("title"), ev.get("start_local"),
             ev.get("end_local"), ev.get("all_day") or 0, now_iso()),
        )
    con.commit()
    con.close()
    return {"ok": True, "mode": "demo", "emails": len(fixture.get("emails") or []),
            "events": len(fixture.get("events") or [])}


def gog_search(account: str, query: str, limit: int = 25) -> list[dict]:
    code, out, err = run(["gog", "gmail", "search", query, "-a", account, "--max", str(limit), "-j", "--no-input"])
    data = parse_json(out) or {}
    threads = data.get("threads") if isinstance(data, dict) else data
    rows = []
    for t in threads or []:
        labels = t.get("labels") or t.get("labelIds") or []
        rows.append({
            "id": f"gmail:{account}:{t.get('id')}",
            "account": account, "platform": "gmail", "thread_id": t.get("id"),
            "subject": t.get("subject") or "", "snippet": t.get("snippet") or "",
            "from_addr": t.get("from") or "", "to_addr": t.get("to") or "",
            "date_raw": t.get("date") or "", "unread": "UNREAD" in labels,
            "has_attachment": bool(t.get("hasAttachment")), "labels": labels,
        })
    if code != 0 and not rows:
        raise RuntimeError(err.strip() or f"gog search failed {code}")
    return rows


def gsk_list(account: str, limit: int = 25) -> list[dict]:
    code, out, err = run(
        ["gsk", "email", "list", "inbox", "-n", str(limit), "-a", account, "--output", "json", "--no-input"],
        timeout=70,
    )
    data = parse_json(out) or {}
    emails = ((data.get("data") or {}).get("emails") if isinstance(data, dict) else None) or []
    rows = []
    for e in emails:
        rows.append({
            "id": f"outlook:{account}:{e.get('id')}",
            "account": account, "platform": e.get("platform") or "outlook",
            "thread_id": e.get("threadId") or e.get("id"),
            "subject": e.get("subject") or "", "snippet": e.get("snippet") or "",
            "from_addr": e.get("from") or "", "to_addr": e.get("to") or "",
            "date_raw": e.get("date") or "", "unread": bool(e.get("unread")),
            "has_attachment": bool(e.get("hasAttachment")), "labels": e.get("labelIds") or [],
        })
    if code != 0 and not rows:
        raise RuntimeError(err.strip() or f"gsk email list failed {code}")
    return rows


def sync_all(limit: int = 25) -> dict:
    cfg = load_cfg()
    mode = cfg.get("mode") or "demo"
    accounts = cfg.get("accounts") or []
    if mode == "demo" or not accounts or all(a.get("driver") == "demo" for a in accounts):
        return seed_demo()
    report = {"ok": True, "mode": "live", "accounts": []}
    for acc in accounts:
        started = datetime.now()
        try:
            if acc.get("driver") == "gog":
                rows = gog_search(acc["email"], "in:inbox", limit)
            elif acc.get("driver") == "gsk":
                rows = gsk_list(acc["email"], limit)
            else:
                rows = []
            con = db()
            for r in rows:
                upsert_email(con, r)
            con.commit()
            con.close()
            report["accounts"].append({
                "email": acc["email"], "count": len(rows),
                "seconds": round((datetime.now() - started).total_seconds(), 2),
            })
        except Exception as e:
            report["accounts"].append({"email": acc.get("email"), "error": str(e)[:300]})
    return report


def list_emails(account=None, category=None, q=None, limit=80) -> list[dict]:
    con = db()
    sql = "SELECT * FROM emails WHERE 1=1"
    args: list = []
    if account:
        sql += " AND account=?"; args.append(account)
    if category and category != "all":
        sql += " AND category=?"; args.append(category)
    if q:
        sql += " AND (subject LIKE ? OR snippet LIKE ? OR from_addr LIKE ? OR body_text LIKE ?)"
        like = f"%{q}%"
        args.extend([like, like, like, like])
    sql += " ORDER BY date_ts DESC LIMIT ?"; args.append(limit)
    rows = [dict(r) for r in con.execute(sql, args)]
    con.close()
    for r in rows:
        r["labels"] = json.loads(r.get("labels_json") or "[]")
        r.pop("labels_json", None)
    return rows


def get_email(item_id: str) -> dict | None:
    con = db()
    row = con.execute("SELECT * FROM emails WHERE id=?", (item_id,)).fetchone()
    con.close()
    if not row:
        return None
    item = dict(row)
    item["labels"] = json.loads(item.get("labels_json") or "[]")
    return item


def list_events() -> list[dict]:
    con = db()
    rows = [dict(r) for r in con.execute("SELECT * FROM events ORDER BY start_local")]
    con.close()
    return rows


def brain_board(hours: int = 168) -> dict:
    floor = int((datetime.now(TZ) - timedelta(hours=hours)).timestamp())
    con = db()
    rows = [dict(r) for r in con.execute("SELECT * FROM emails WHERE date_ts>=? OR date_ts=0 ORDER BY date_ts DESC", (floor,))]
    events = [dict(r) for r in con.execute("SELECT * FROM events ORDER BY start_local")]
    con.close()
    buckets = {t["id"]: [] for t in TAXONOMY}
    for r in rows:
        cat = r.get("category") or "fyi"
        buckets.setdefault(cat, []).append({
            "id": r["id"], "kind": "mail", "category": cat, "text": r["subject"],
            "summary": (r.get("snippet") or "")[:180], "flag_reason": r.get("flag_reason"),
            "from_addr": r.get("from_addr"), "account": r.get("account"),
            "unread": bool(r.get("unread")), "date_raw": r.get("date_raw"),
        })
    for ev in events:
        buckets["upcoming"].append({
            "id": f"cal:{ev['id']}", "kind": "calendar", "category": "upcoming",
            "text": ev["title"], "summary": f"{ev.get('start_local')} → {ev.get('end_local')}",
            "flag_reason": "Calendar", "from_addr": ev.get("calendar_id"),
            "account": "", "unread": False, "date_raw": ev.get("start_local"),
        })
    return {
        "taxonomy": TAXONOMY,
        "counts": {k: len(v) for k, v in buckets.items()},
        "todos": buckets,
        "window_hours": hours,
        "source": "local-heuristic",
    }


def counts() -> dict:
    con = db()
    n = con.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
    cats = {r[0]: r[1] for r in con.execute("SELECT category, COUNT(*) FROM emails GROUP BY 1")}
    ev = con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    unread = con.execute("SELECT COUNT(*) FROM emails WHERE unread=1").fetchone()[0]
    con.close()
    return {"emails": n, "unread": unread, "events": ev, "categories": cats}


def save_draft(account: str, to_addr: str, subject: str, body: str) -> dict:
    con = db()
    cur = con.execute(
        "INSERT INTO drafts(account, to_addr, subject, body, created_at) VALUES (?,?,?,?,?)",
        (account, to_addr, subject, body, now_iso()),
    )
    con.commit()
    did = cur.lastrowid
    con.close()
    return {"id": did, "note": "Local draft only. Send is disabled by default."}
