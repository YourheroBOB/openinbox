"""Unified calendar: week / month views with extra time-zone columns, local events, RSVP, AI booking
(agent tool `create_event` writes a .ics invite draft) and colleague ICS feeds with a free/busy panel.

- Synced events stay in the core `events` table and are read-only here; your RSVP to them is kept
  in cal_rsvp. Local, AI-booked and imported events live in cal_events (one row per series; RRULE
  is expanded on read) and survive a cache clear, like drafts do.
- Invite drafts (.ics METHOD REQUEST / CANCEL / REPLY) are stored in cal_invites for download.
  Nothing is mailed, posted or pushed anywhere; every response that makes one says sent: false.
- Colleague feeds keep their raw ICS in cal_feeds and are expanded per query. A URL feed is fetched
  only when it is added or refreshed, through the agent bridge's URL guard (loopback / private
  hosts need allow_private, plain http needs it too). Those two routes refuse any browser Origin
  other than this server's own (127.0.0.1 / localhost on the same port), so another web page
  cannot make this machine fetch an intranet URL.
- Feeds and local events are kept by the core cache clear; delete a feed with /api/cal/feed/delete.
- All-day events count as free unless they are marked OPAQUE or read like time off.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import uuid
from datetime import date, datetime, time, timedelta, timezone
from urllib.parse import unquote, urljoin, urlsplit

import agent_bridge
import persona
import yhbmail
from features import Raw, get, post
from features import _ics as ics

UTC = timezone.utc
FIXTURE = yhbmail.ROOT / "fixtures" / "calendar_demo.json"
STATUSES = ("accepted", "tentative", "declined", "needs-action")
REPEATS = {"": "", "daily": "FREQ=DAILY", "weekdays": "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR",
           "weekly": "FREQ=WEEKLY", "monthly": "FREQ=MONTHLY"}
VIEWS = ("week", "month")
MAX_EXTRA_TZS = 3
MAX_EVENT_DAYS = 14
DEFAULT_MINUTES = 30
ADDR_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
OOO_RE = re.compile(r"(out of (the )?office|\booo\b|vacation|holiday|\bpto\b|leave|休假|請假|特休|出差|不在辦公室)", re.I)
COMMON_TZS = ["Asia/Taipei", "Asia/Tokyo", "Asia/Seoul", "Asia/Shanghai", "Asia/Hong_Kong", "Asia/Singapore",
              "Asia/Kolkata", "Australia/Sydney", "Europe/London", "Europe/Berlin", "Europe/Paris",
              "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles", "UTC"]
WD_ZH = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]
WD_EN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
             "November", "December"]
STATUS_TEXT = {
    "accepted": ("已接受", "Accepted"), "tentative": ("未定", "Maybe"), "declined": ("已婉拒", "Declined"),
    "needs-action": ("待回覆", "Needs reply"), "organizer": ("主辦", "Organizer"), "": ("", ""),
}


def _zh(lang) -> bool:
    return str(lang or "").lower().startswith("zh")


def _lang(req) -> str:
    return "zh-Hant" if req.lang_zh() else "en"


def _clip(value, n: int) -> str:
    return str(value if value is not None else "")[:n]


def _int(value, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


# ───────────────────────── storage ─────────────────────────

_ensured: set = set()


def ensure_tables() -> None:
    if str(yhbmail.DB) in _ensured and yhbmail.DB.exists():
        return
    yhbmail.init_db()
    con = yhbmail.db()
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS cal_settings (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS cal_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid TEXT, title TEXT, start TEXT, end TEXT, all_day INTEGER DEFAULT 0, tz TEXT,
            location TEXT, description TEXT, organizer_json TEXT, attendees_json TEXT, my_status TEXT,
            rrule TEXT, exdates_json TEXT, source TEXT, status TEXT, transp TEXT,
            sequence INTEGER DEFAULT 0, created_at TEXT, updated_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_cal_events_uid ON cal_events(uid);
        CREATE TABLE IF NOT EXISTS cal_rsvp (event_key TEXT PRIMARY KEY, status TEXT, updated_at TEXT);
        CREATE TABLE IF NOT EXISTS cal_invites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_key TEXT, method TEXT, uid TEXT, sequence INTEGER, filename TEXT, ics TEXT,
            summary TEXT, recipients TEXT, created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS cal_feeds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, email TEXT, url TEXT, filename TEXT, kind TEXT, allow_private INTEGER DEFAULT 0,
            ics TEXT, error TEXT, fetched_at TEXT, created_at TEXT
        );
        """
    )
    con.commit()
    con.close()
    _ensured.add(str(yhbmail.DB))
    seed_demo()


def _demo_fixture() -> dict:
    try:
        return json.loads(FIXTURE.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def demo_mode() -> bool:
    return (yhbmail.load_cfg().get("mode") or "demo") == "demo"


def seed_demo() -> int:
    """Demo mode only, once per fixture version: fictional local events with attendees and RSVP states."""
    if not demo_mode():
        return 0
    fx = _demo_fixture()
    version = str(fx.get("version") or "")
    if not version or _setting_raw("demo_seeded") == version:
        return 0
    n = 0
    for ev in fx.get("events") or []:
        con = yhbmail.db()
        exists = con.execute("SELECT 1 FROM cal_events WHERE uid=?", (ev["uid"],)).fetchone()
        con.close()
        if exists:
            continue
        data = {"title": ev["title"], "start": ev["start"], "end": ev.get("end"), "tz": ev.get("tz"),
                "location": ev.get("location"), "description": ev.get("description"), "rrule": ev.get("rrule"),
                "attendees": ev.get("attendees") or [], "organizer": ev.get("organizer"), "uid": ev["uid"],
                "make_invite": False}
        out, status = save_event(data, "en", source="demo")
        n += 1 if status in (200, 201) else 0
    _set_setting_raw("demo_seeded", version)
    return n


def _setting_raw(key: str):
    con = yhbmail.db()
    row = con.execute("SELECT value FROM cal_settings WHERE key=?", (key,)).fetchone()
    con.close()
    return row["value"] if row else None


def _set_setting_raw(key: str, value: str) -> None:
    con = yhbmail.db()
    con.execute("INSERT INTO cal_settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value))
    con.commit()
    con.close()


# ───────────────────────── settings ─────────────────────────

def default_tz() -> str:
    env = os.environ.get("OPENINBOX_TZ") or ""
    if env and ics.get_tz(env):
        return env
    offset = yhbmail.TZ.utcoffset(None)
    if offset == timedelta(hours=8):
        return "Asia/Taipei"
    return "UTC" + ics.format_offset(offset).replace("−", "-") if offset else "UTC"


def default_settings() -> dict:
    return {"tz": default_tz(), "extra_tzs": ["America/New_York", "Europe/London"], "week_start": 1,
            "work_start": 9, "work_end": 18, "view": "week", "slot_minutes": 30}


def load_settings() -> dict:
    ensure_tables()
    out = default_settings()
    con = yhbmail.db()
    raw = {r["key"]: r["value"] for r in con.execute("SELECT key, value FROM cal_settings")}
    con.close()
    for key in out:
        if key in raw:
            try:
                out[key] = json.loads(raw[key])
            except json.JSONDecodeError:
                pass
    if not ics.get_tz(out["tz"]):
        out["tz"] = default_tz()
    out["extra_tzs"] = [z for z in out["extra_tzs"] if isinstance(z, str) and ics.get_tz(z)][:MAX_EXTRA_TZS]
    return out


def save_settings(changes: dict) -> tuple[dict, int]:
    clean = {}
    if "tz" in changes:
        if not ics.get_tz(changes["tz"]):
            return {"error": f"unknown time zone: {_clip(changes['tz'], 64)}"}, 400
        clean["tz"] = str(changes["tz"]).strip()
    if "extra_tzs" in changes:
        zones = changes["extra_tzs"]
        if isinstance(zones, str):
            zones = [z.strip() for z in zones.split(",") if z.strip()]
        if not isinstance(zones, list) or len(zones) > MAX_EXTRA_TZS:
            return {"error": f"extra_tzs must be a list of at most {MAX_EXTRA_TZS} time zones"}, 400
        bad = [z for z in zones if not ics.get_tz(z)]
        if bad:
            return {"error": f"unknown time zone: {_clip(bad[0], 64)}"}, 400
        clean["extra_tzs"] = list(dict.fromkeys(str(z).strip() for z in zones))
    if "week_start" in changes:
        if changes["week_start"] not in (0, 1, "0", "1"):
            return {"error": "week_start must be 0 (Sunday) or 1 (Monday)"}, 400
        clean["week_start"] = int(changes["week_start"])
    for key, lo, hi in (("work_start", 0, 23), ("work_end", 1, 24)):
        if key in changes:
            try:
                clean[key] = max(lo, min(hi, int(changes[key])))
            except (TypeError, ValueError):
                return {"error": f"{key} must be an hour"}, 400
    if "view" in changes:
        if changes["view"] not in VIEWS:
            return {"error": "view must be week or month"}, 400
        clean["view"] = changes["view"]
    if "slot_minutes" in changes:
        clean["slot_minutes"] = _int(changes["slot_minutes"], 30, 15, 240)
    merged = {**load_settings(), **clean}
    if merged["work_start"] >= merged["work_end"]:
        return {"error": "work_start must be before work_end"}, 400
    for key, value in clean.items():
        _set_setting_raw(key, json.dumps(value))
    return load_settings(), 200


def tz_label(name: str, at: datetime | None = None) -> dict:
    tz = ics.get_tz(name) or UTC
    at = at or datetime.now(UTC)
    off = at.astimezone(tz).utcoffset()
    city = name.split("/")[-1].replace("_", " ") if "/" in name else name
    return {"tz": name, "city": city, "offset": "UTC" + ics.format_offset(off) if off else "UTC"}


def settings_view(lang: str) -> dict:
    s = load_settings()
    return {**s, "timezones": COMMON_TZS, "tz_labels": [tz_label(z) for z in [s["tz"]] + s["extra_tzs"]],
            "me": me_addresses(), "demo": demo_mode(), "anchor": anchor_date(s).isoformat(),
            "statuses": list(STATUSES), "repeats": list(REPEATS)}


# ───────────────────────── identity ─────────────────────────

def me_addresses() -> list[str]:
    out = [str(a.get("email") or "").lower() for a in (yhbmail.load_cfg().get("accounts") or []) if a.get("email")]
    return out or ["you@example.com"]


def me_person() -> dict:
    name = ((persona.load().get("identity") or {}).get("name") or "").strip()
    return {"email": me_addresses()[0], "name": "" if name.lower() == "you" else name}


def parse_people(value) -> tuple[list[dict], list[str]]:
    """Attendees from a list of {email, name, status} / strings, or one comma-separated string."""
    items = value if isinstance(value, list) else re.split(r"[,;，；\n]", str(value or ""))
    people, bad, seen = [], [], set()
    for item in items[:100]:
        if isinstance(item, dict):
            email, name = str(item.get("email") or "").strip(), str(item.get("name") or "").strip()
            status = str(item.get("status") or "NEEDS-ACTION").upper()
        else:
            raw = str(item or "").strip()
            if not raw:
                continue
            m = re.match(r'^"?([^"<]*?)"?\s*<([^>]+)>$', raw)
            email, name = (m.group(2).strip(), m.group(1).strip()) if m else (raw, "")
            status = "NEEDS-ACTION"
        email = email.lower()
        if email.startswith("mailto:"):
            email = email[7:]
        if not ADDR_RE.fullmatch(email):
            bad.append(_clip(email or item, 120))
            continue
        if email in seen:
            continue
        seen.add(email)
        people.append({"email": email, "name": _clip(name, 120),
                       "status": status if status in ics.PARTSTATS else "NEEDS-ACTION", "role": "REQ-PARTICIPANT"})
    return people, bad


# ───────────────────────── time parsing ─────────────────────────

def parse_when(value, tz, all_day: bool = False):
    """ISO date / datetime (naive = wall time in `tz`) -> date or aware datetime. None when unparsable."""
    raw = str(value or "").strip()
    if not raw:
        return None
    if all_day or re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00").replace(" ", "T", 1))
    except ValueError:
        return None
    return dt.replace(tzinfo=tz) if dt.tzinfo is None else dt


def _iso(value) -> str:
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return value.isoformat() if value else ""


def _local(value, tz) -> str:
    """Wall time in tz as YYYY-MM-DDTHH:MM (or the date for all-day values)."""
    if isinstance(value, datetime):
        return value.astimezone(tz).strftime("%Y-%m-%dT%H:%M")
    return value.isoformat()


def _wall_minutes(dt: datetime, tz) -> int:
    loc = dt.astimezone(tz)
    return loc.hour * 60 + loc.minute


def now_in(tz, override=None) -> datetime:
    if override:
        dt = parse_when(override, tz)
        if isinstance(dt, datetime):
            return dt.astimezone(tz)
        if isinstance(dt, date):
            return datetime.combine(dt, time(9), tzinfo=tz)
    return datetime.now(tz)


# ───────────────────────── unified event model ─────────────────────────

def _sync_row_times(row: dict):
    raw_s, raw_e = (row.get("start_local") or "").strip(), (row.get("end_local") or "").strip()
    if row.get("all_day") or re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_s):
        s = parse_when(raw_s, yhbmail.TZ, all_day=True)
        e = parse_when(raw_e, yhbmail.TZ, all_day=True) if raw_e else None
        if s and (not e or e <= s):
            e = s + timedelta(days=1)
        return s, e, True
    s = parse_when(raw_s, yhbmail.TZ)
    e = parse_when(raw_e, yhbmail.TZ) if raw_e else None
    if isinstance(s, datetime) and (not isinstance(e, datetime) or e <= s):
        e = s + timedelta(minutes=DEFAULT_MINUTES)
    return s, e, False


def _rsvp_overrides() -> dict:
    con = yhbmail.db()
    out = {r["event_key"]: r["status"] for r in con.execute("SELECT event_key, status FROM cal_rsvp")}
    con.close()
    return out


def _invite_counts() -> dict:
    con = yhbmail.db()
    out = {r[0]: r[1] for r in con.execute("SELECT event_key, COUNT(*) FROM cal_invites GROUP BY event_key")}
    con.close()
    return out


def _my_status(organizer: dict | None, attendees: list[dict], override: str | None = None) -> str:
    me = set(me_addresses())
    if organizer and organizer.get("email", "").lower() in me:
        return "organizer"
    if override in STATUSES:
        return override
    for a in attendees:
        if a.get("email", "").lower() in me:
            return a.get("status", "NEEDS-ACTION").lower()
    return ""


def _counts(attendees: list[dict]) -> dict:
    out = {s: 0 for s in STATUSES}
    for a in attendees:
        st = (a.get("status") or "NEEDS-ACTION").lower()
        if st in out:
            out[st] += 1
    return out


def _public(base: dict, organizer, attendees, my_status: str, lang: str) -> dict:
    zh = _zh(lang)
    me = set(me_addresses())
    people = [{**a, "status": (a.get("status") or "NEEDS-ACTION").lower(), "me": a.get("email") in me,
               "status_label": STATUS_TEXT.get((a.get("status") or "NEEDS-ACTION").lower(), ("", ""))[0 if zh else 1]}
              for a in attendees]
    return {**base, "organizer": organizer, "attendees": people, "my_status": my_status,
            "my_status_label": STATUS_TEXT.get(my_status, ("", ""))[0 if zh else 1],
            "rsvp_counts": _counts(attendees), "can_rsvp": my_status not in ("organizer",) and bool(
                my_status or attendees or organizer)}


def series(lang: str = "en") -> list[dict]:
    """Every event series: {pub, ics_ev, key}. ics_ev is in the shape _ics.occurrences expects."""
    ensure_tables()
    out = []
    overrides = _rsvp_overrides()
    invites = _invite_counts()
    meta = (_demo_fixture().get("sync_meta") or {}) if demo_mode() else {}
    for row in yhbmail.list_events():
        s, e, all_day = _sync_row_times(row)
        if s is None:
            continue
        key = f"sync:{row['id']}"
        m = meta.get(row["id"]) or {}
        organizer = m.get("organizer")
        attendees = parse_people(m.get("attendees") or [])[0]
        my = _my_status(organizer, attendees, overrides.get(key))
        if my and my != "organizer":
            attendees = [{**a, "status": my.upper()} if a["email"] in me_addresses() else a for a in attendees]
        base = {"id": key, "source": "sync", "calendar": f"sync:{row.get('calendar_id') or 'default'}",
                "calendar_name": row.get("calendar_id") or "sync", "editable": False, "title": row.get("title") or "",
                "location": m.get("location") or "", "description": m.get("description") or "",
                "all_day": all_day, "tz": "" if all_day else ics.tz_name(s.tzinfo), "repeat": "", "rrule": "",
                "status": "", "transp": "", "invites": invites.get(key, 0)}
        out.append({"key": key, "pub": _public(base, organizer, attendees, my, lang),
                    "ics_ev": {"start": s, "end": e, "rrule": None, "exdates": [], "rdates": []}})
    con = yhbmail.db()
    rows = [dict(r) for r in con.execute("SELECT * FROM cal_events ORDER BY id")]
    con.close()
    for row in rows:
        item = _local_series(row, lang, invites)
        if item:
            out.append(item)
    return out


def _local_series(row: dict, lang: str, invites: dict | None = None) -> dict | None:
    tz = ics.get_tz(row.get("tz")) or ics.get_tz(load_settings()["tz"]) or UTC
    all_day = bool(row.get("all_day"))
    s, e = parse_when(row["start"], tz, all_day), parse_when(row["end"], tz, all_day)
    if s is None or e is None:
        return None
    rule = None
    if row.get("rrule"):
        try:
            rule = ics.parse_rrule(row["rrule"])
            if rule.get("until_raw"):
                rule["until"] = ics.parse_dt(rule["until_raw"], {}, {}, tz)
        except ics.IcsError:
            rule = None
    exdates = [parse_when(x, tz, all_day) for x in json.loads(row.get("exdates_json") or "[]")]
    organizer = json.loads(row.get("organizer_json") or "null")
    attendees = json.loads(row.get("attendees_json") or "[]")
    key = f"local:{row['id']}"
    my = row.get("my_status") or _my_status(organizer, attendees)
    repeat = next((k for k, v in REPEATS.items() if v and v == (row.get("rrule") or "")), "custom" if row.get("rrule") else "")
    base = {"id": key, "source": row.get("source") or "local", "calendar": "local", "calendar_name": "local",
            "editable": True, "title": row.get("title") or "", "location": row.get("location") or "",
            "description": row.get("description") or "", "all_day": all_day, "tz": row.get("tz") or "",
            "repeat": repeat, "rrule": row.get("rrule") or "", "status": row.get("status") or "",
            "transp": row.get("transp") or "", "uid": row.get("uid") or "", "sequence": row.get("sequence") or 0,
            "invites": (invites or {}).get(key, 0), "created_at": row.get("created_at") or "",
            "updated_at": row.get("updated_at") or ""}
    return {"key": key, "pub": _public(base, organizer, attendees, my, lang), "row": row,
            "ics_ev": {"start": s, "end": e, "rrule": rule, "exdates": [x for x in exdates if x], "rdates": []}}


def instances(ws: datetime, we: datetime, tz, lang: str = "en", cals: set | None = None) -> list[dict]:
    out = []
    for item in series(lang):
        pub = item["pub"]
        if cals and pub["calendar"] not in cals:
            continue
        if pub["status"] == "CANCELLED":
            continue
        for s, e in ics.occurrences(item["ics_ev"], ws, we, tz):
            out.append({"pub": pub, "s": s, "e": e})
    out.sort(key=lambda x: (not x["pub"]["all_day"], ics.as_utc(x["s"], tz), x["pub"]["title"]))
    return out


def _inst_view(inst: dict, tz) -> dict:
    s, e, pub = inst["s"], inst["e"], inst["pub"]
    timed = isinstance(s, datetime)
    return {**pub, "start": _local(s, tz), "end": _local(e, tz),
            "start_utc": ics.fmt_utc(s) if timed else "", "end_utc": ics.fmt_utc(e) if timed else "",
            "instance": ics.fmt_utc(s) if timed else s.isoformat()}


# ───────────────────────── week / month view ─────────────────────────

def anchor_date(settings: dict | None = None) -> date:
    """Today, or in demo mode with nothing near today, the first demo event's date."""
    s = settings or load_settings()
    tz = ics.get_tz(s["tz"]) or UTC
    today = datetime.now(tz).date()
    if not demo_mode():
        return today
    days = []
    for r in yhbmail.list_events():
        try:
            days.append(date.fromisoformat((r.get("start_local") or "")[:10]))
        except ValueError:
            continue
    if not days or any(abs((d - today).days) <= 7 for d in days):
        return today
    return min(days)


def range_for(view: str, anchor: date, week_start: int) -> tuple[date, date]:
    shift = (anchor.weekday() - (0 if week_start == 1 else 6)) % 7
    if view == "week":
        start = anchor - timedelta(days=shift)
        return start, start + timedelta(days=7)
    first = anchor.replace(day=1)
    lead = (first.weekday() - (0 if week_start == 1 else 6)) % 7
    start = first - timedelta(days=lead)
    nxt = (first + timedelta(days=32)).replace(day=1)
    weeks = -(-((nxt - start).days) // 7)
    return start, start + timedelta(days=7 * weeks)


def _bounds(d: date, tz) -> tuple[datetime, datetime]:
    return (datetime.combine(d, time(0), tzinfo=tz).astimezone(UTC),
            datetime.combine(d + timedelta(days=1), time(0), tzinfo=tz).astimezone(UTC))


def _layout(segs: list[dict]) -> None:
    """Side-by-side columns for overlapping timed segments of one day (sets col / ncols)."""
    segs.sort(key=lambda x: (x["top"], -x["bottom"]))
    cluster, cols, cluster_end = [], [], -1
    for seg in segs + [None]:
        if seg is None or seg["top"] >= cluster_end:
            for c in cluster:
                c["ncols"] = len(cols)
            if seg is None:
                break
            cluster, cols, cluster_end = [], [], -1
        for i, end in enumerate(cols):
            if end <= seg["top"]:
                cols[i] = seg["bottom"]
                seg["col"] = i
                break
        else:
            seg["col"] = len(cols)
            cols.append(seg["bottom"])
        cluster.append(seg)
        cluster_end = max(cluster_end, seg["bottom"])


def view_title(view: str, start: date, end: date, anchor: date, lang: str) -> str:
    last = end - timedelta(days=1)
    if view == "month":
        return f"{anchor.year} 年 {anchor.month} 月" if _zh(lang) else f"{MONTHS_EN[anchor.month - 1]} {anchor.year}"
    if _zh(lang):
        tail = f"{last.day} 日" if last.month == start.month else f"{last.month} 月 {last.day} 日"
        head = f"{start.year} 年 {start.month} 月 {start.day} 日"
        return f"{head} – {last.year} 年 {tail}" if last.year != start.year else f"{head} – {tail}"
    m1, m2 = MONTHS_EN[start.month - 1][:3], MONTHS_EN[last.month - 1][:3]
    if start.year != last.year:
        return f"{m1} {start.day}, {start.year} – {m2} {last.day}, {last.year}"
    return f"{m1} {start.day} – {last.day}, {start.year}" if m1 == m2 else f"{m1} {start.day} – {m2} {last.day}, {start.year}"


def build_view(view: str, anchor: date, tz_name: str, extras: list[str], lang: str = "en", today=None,
               cals: set | None = None, week_start: int = 1) -> dict:
    tz = ics.get_tz(tz_name) or UTC
    zh = _zh(lang)
    start, end = range_for(view, anchor, week_start)
    ws, we = _bounds(start, tz)[0], _bounds(end - timedelta(days=1), tz)[1]
    now = now_in(tz, today)
    insts = instances(ws, we, tz, lang, cals)
    days = []
    d = start
    while d < end:
        day_s, day_e = _bounds(d, tz)
        all_day, timed, items = [], [], []
        for inst in insts:
            s, e = inst["s"], inst["e"]
            if not isinstance(s, datetime):
                if s <= d < e:
                    all_day.append({**_inst_view(inst, tz), "first": s == d, "last": e - timedelta(days=1) == d})
                continue
            su, eu = s.astimezone(UTC), e.astimezone(UTC)
            if not (eu > day_s and su < day_e):
                continue
            seg_s, seg_e = max(su, day_s), min(eu, day_e)
            top = 0 if seg_s == day_s else _wall_minutes(seg_s, tz)
            bottom = 1440 if seg_e == day_e else _wall_minutes(seg_e, tz)
            if bottom <= top:
                bottom = min(1440, top + 15)
            seg = {**_inst_view(inst, tz), "top": top, "bottom": bottom, "continues_before": su < day_s,
                   "continues_after": eu > day_e, "time_label": seg_s.astimezone(tz).strftime("%H:%M")}
            timed.append(seg)
        _layout(timed)
        items = [{"id": x["id"], "title": x["title"], "all_day": True, "time_label": "", "my_status": x["my_status"],
                  "calendar": x["calendar"], "source": x["source"], "instance": x["instance"]} for x in all_day]
        items += [{"id": x["id"], "title": x["title"], "all_day": False, "time_label": x["time_label"],
                   "my_status": x["my_status"], "calendar": x["calendar"], "source": x["source"],
                   "instance": x["instance"]} for x in sorted(timed, key=lambda x: x["top"])]
        days.append({"date": d.isoformat(), "day": d.day, "weekday": (WD_ZH if zh else WD_EN)[d.weekday()],
                     "is_today": d == now.date(), "in_month": d.month == anchor.month, "weekend": d.weekday() >= 5,
                     "all_day": all_day, "timed": timed, "items": items})
        d += timedelta(days=1)
    zones = [tz_name] + [z for z in extras if z != tz_name][:MAX_EXTRA_TZS]
    ref = datetime.combine(anchor, time(12), tzinfo=tz)
    hours = []
    for h in range(24):
        at = datetime.combine(anchor, time(h), tzinfo=tz)
        labels = []
        for z in zones:
            loc = at.astimezone(ics.get_tz(z) or UTC)
            labels.append({"tz": z, "label": loc.strftime("%H:%M"), "shift": (loc.date() - anchor).days})
        hours.append({"hour": h, "labels": labels})
    calendars = {}
    for item in series(lang):
        pub = item["pub"]
        calendars.setdefault(pub["calendar"], {"id": pub["calendar"], "name": _calendar_name(pub["calendar"], lang)})
    return {
        "view": view, "anchor": anchor.isoformat(), "start": start.isoformat(), "end": end.isoformat(),
        "title": view_title(view, start, end, anchor, lang), "tz": tz_name,
        "zones": [tz_label(z, ref) for z in zones], "hours": hours, "days": days,
        "now": {"date": now.date().isoformat(), "minute": now.hour * 60 + now.minute},
        "prev": (start - timedelta(days=1)).isoformat() if view == "week" else
        (anchor.replace(day=1) - timedelta(days=1)).replace(day=1).isoformat(),
        "next": end.isoformat() if view == "week" else (anchor.replace(day=1) + timedelta(days=32)).replace(day=1).isoformat(),
        "today": now.date().isoformat(), "calendars": list(calendars.values()),
        "count": len({(i["pub"]["id"], ics.fmt_utc(i["s"]) if isinstance(i["s"], datetime) else i["s"].isoformat())
                      for i in insts}),
    }


def _calendar_name(cal: str, lang: str) -> str:
    zh = _zh(lang)
    if cal == "local":
        return "本機行事曆" if zh else "Local calendar"
    name = cal.split(":", 1)[1] if ":" in cal else cal
    return (f"同步：{name}" if zh else f"Synced: {name}")


# ───────────────────────── one event ─────────────────────────

def find_series(key: str, lang: str = "en") -> dict | None:
    key = str(key or "").strip()
    if re.fullmatch(r"\d+", key):
        key = f"local:{key}"
    return next((s for s in series(lang) if s["key"] == key), None)


def event_detail(key: str, lang: str, tz_name: str, extras: list[str]) -> dict | None:
    item = find_series(key, lang)
    if not item:
        return None
    zh = _zh(lang)
    ev = item["ics_ev"]
    s, e = ev["start"], ev["end"]
    times = []
    for z in [tz_name] + [x for x in extras if x != tz_name]:
        tz = ics.get_tz(z) or UTC
        if isinstance(s, datetime):
            ls, le = s.astimezone(tz), e.astimezone(tz)
            wd = (WD_ZH if zh else WD_EN)[ls.weekday()]
            same = ls.date() == le.date()
            text = f"{ls:%Y-%m-%d} ({wd}) {ls:%H:%M} – " + (f"{le:%H:%M}" if same else f"{le:%Y-%m-%d %H:%M}")
        else:
            last = e - timedelta(days=1)
            text = s.isoformat() + ("" if last == s else f" – {last.isoformat()}") + (" 整天" if zh else " (all day)")
        times.append({**tz_label(z, s if isinstance(s, datetime) else None), "text": text})
    own_tz = ics.get_tz(item["pub"].get("tz")) or ics.get_tz(tz_name) or UTC
    edit = {"title": item["pub"]["title"], "all_day": item["pub"]["all_day"], "tz": item["pub"].get("tz") or tz_name,
            "start": _local(s, own_tz), "end": _local(e, own_tz), "location": item["pub"]["location"],
            "description": item["pub"]["description"], "repeat": item["pub"]["repeat"],
            "attendees": ", ".join((f"{a['name']} <{a['email']}>" if a.get("name") else a["email"])
                                   for a in item["pub"]["attendees"] if not a.get("me"))}
    return {"event": {**item["pub"], "start": _iso(s), "end": _iso(e)}, "times": times, "edit": edit,
            "invites": list_invites(item["key"])}


# ───────────────────────── create / update / delete ─────────────────────────

def _bad(msg_en: str, msg_zh: str, lang: str, status: int = 400, **extra) -> tuple[dict, int]:
    return {"error": msg_zh if _zh(lang) else msg_en, **extra}, status


def _normalize(data: dict, lang: str, existing: dict | None = None) -> tuple[dict | None, tuple | None]:
    s = load_settings()
    title = _clip(data.get("title"), 300).strip()
    if not title:
        return None, _bad("title is required", "請填標題", lang)
    tz_name = str(data.get("tz") or (existing or {}).get("tz") or s["tz"]).strip()
    tz = ics.get_tz(tz_name)
    if tz is None:
        return None, _bad(f"unknown time zone: {tz_name[:64]}", f"不認得的時區：{tz_name[:64]}", lang)
    all_day = bool(data.get("all_day"))
    start = parse_when(data.get("start"), tz, all_day)
    if start is None:
        return None, _bad("start must be an ISO date or date-time", "開始時間要是 ISO 日期或日期時間", lang)
    if all_day and isinstance(start, datetime):
        start = start.date()
    end = parse_when(data.get("end"), tz, all_day) if data.get("end") else None
    if all_day:
        if isinstance(end, datetime):
            end = end.date()
        end = end or start + timedelta(days=1)
    else:
        if end is None:
            minutes = _int(data.get("duration_minutes"), DEFAULT_MINUTES, 5, MAX_EVENT_DAYS * 1440)
            end = start + timedelta(minutes=minutes)
        elif not isinstance(end, datetime):
            return None, _bad("end must be a date-time", "結束時間要有時刻", lang)
    if end <= start:
        return None, _bad("end must be after start", "結束時間要晚於開始時間", lang)
    if end - start > timedelta(days=MAX_EVENT_DAYS):
        return None, _bad(f"events are limited to {MAX_EVENT_DAYS} days", f"單一事件最長 {MAX_EVENT_DAYS} 天", lang)
    rrule = ""
    if data.get("repeat") is not None and str(data.get("repeat")) != "custom":
        if data["repeat"] not in REPEATS:
            return None, _bad("repeat must be one of " + ", ".join(k for k in REPEATS if k),
                              "重複只能選：每天、平日、每週、每月", lang)
        rrule = REPEATS[data["repeat"]]
    if data.get("rrule"):
        try:
            ics.parse_rrule(str(data["rrule"]))
        except ics.IcsError as e:
            return None, _bad(f"bad rrule: {e}", f"重複規則有誤：{e}", lang)
        rrule = re.sub(r"[^A-Za-z0-9=;,+\-]", "", str(data["rrule"])).upper()
    elif data.get("repeat") is None and existing:
        rrule = existing.get("rrule") or ""
    attendees, bad = parse_people(data.get("attendees") if data.get("attendees") is not None
                                  else json.loads((existing or {}).get("attendees_json") or "[]"))
    me = set(me_addresses())
    organizer = data.get("organizer") if isinstance(data.get("organizer"), dict) else None
    if organizer:
        org_people, _ = parse_people([organizer])
        organizer = org_people[0] if org_people else None
        if organizer:
            organizer.pop("status", None)
            organizer.pop("role", None)
    elif existing and existing.get("organizer_json"):
        organizer = json.loads(existing["organizer_json"])
    else:
        organizer = {"email": me_person()["email"], "name": me_person()["name"]}
    if organizer and organizer["email"] in me:
        attendees = [a for a in attendees if a["email"] not in me]
    return {
        "title": title, "start": _iso(start), "end": _iso(end), "all_day": 1 if all_day else 0, "tz": tz_name,
        "location": _clip(data.get("location"), 500).strip(), "description": _clip(data.get("description"), 8000),
        "organizer_json": json.dumps(organizer, ensure_ascii=False) if organizer else "",
        "attendees_json": json.dumps(attendees, ensure_ascii=False), "rrule": rrule,
        "_start": start, "_end": end, "_bad": bad, "_attendees": attendees, "_organizer": organizer,
    }, None


def save_event(data: dict, lang: str = "en", source: str = "local") -> tuple[dict, int]:
    ensure_tables()
    zh = _zh(lang)
    existing = None
    key = str(data.get("id") or "").strip()
    if key:
        if key.startswith("sync:"):
            return _bad("synced events are read-only here; set your RSVP instead",
                        "同步來的行程在這裡唯讀，可以改你的回覆狀態", lang, 403)
        m = re.fullmatch(r"(?:local:)?(\d+)", key)
        if not m:
            return _bad("bad id", "id 有誤", lang)
        con = yhbmail.db()
        row = con.execute("SELECT * FROM cal_events WHERE id=?", (int(m.group(1)),)).fetchone()
        con.close()
        if not row:
            return _bad("event not found", "找不到這個行程", lang, 404)
        existing = dict(row)
    fields, err = _normalize(data, lang, existing)
    if err:
        return err
    now = yhbmail.now_iso()
    store = {k: v for k, v in fields.items() if not k.startswith("_")}
    organizer = fields["_organizer"]
    my = "organizer" if organizer and organizer["email"] in me_addresses() else _my_status(organizer, fields["_attendees"])
    con = yhbmail.db()
    if existing:
        store.update({"sequence": int(existing.get("sequence") or 0) + 1, "updated_at": now,
                      "my_status": existing.get("my_status") if my != "organizer" and existing.get("my_status") else my})
        sets = ", ".join(f"{k}=?" for k in store)
        con.execute(f"UPDATE cal_events SET {sets} WHERE id=?", (*store.values(), existing["id"]))
        event_id, status = existing["id"], 200
    else:
        uid = _clip(data.get("uid"), 300).strip() or f"{uuid.uuid4().hex}@toopowerinbox.example.com"
        store.update({"uid": uid, "source": source if source in ("local", "agent", "demo", "ics") else "local",
                      "sequence": 0, "created_at": now, "updated_at": now, "my_status": my, "status": "", "transp": ""})
        cols = ", ".join(store)
        event_id = con.execute(f"INSERT INTO cal_events({cols}) VALUES ({', '.join('?' for _ in store)})",
                               tuple(store.values())).lastrowid
        status = 201
    con.commit()
    con.close()
    key = f"local:{event_id}"
    invite = None
    want_invite = data.get("make_invite")
    if want_invite is None:
        want_invite = bool(fields["_attendees"]) and my == "organizer"
    if want_invite:
        invite = make_invite(key, "REQUEST")
    warnings = [(f"「{b}」不像信箱位址，已略過" if zh else f"'{b}' does not look like an address; skipped")
                for b in fields["_bad"]]
    clash = conflicts(fields["_start"], fields["_end"], [a["email"] for a in fields["_attendees"]], key, lang)
    item = find_series(key, lang)
    return {"ok": True, "event": {**item["pub"], "start": fields["start"], "end": fields["end"]} if item else None,
            "invite": invite, "sent": False, "conflicts": clash, "warnings": warnings,
            "note": invite_note(lang, bool(invite))}, status


def invite_note(lang: str, has_invite: bool) -> str:
    if _zh(lang):
        return ("已存到本機行事曆，並產生 .ics 邀請草稿；不會寄出，要邀請別人請自行下載附在信裡。" if has_invite
                else "已存到本機行事曆；不會寄出任何東西。")
    return ("Saved to the local calendar with a .ics invite draft. Nothing is sent; download it and attach it "
            "yourself if you want to invite people." if has_invite else
            "Saved to the local calendar. Nothing is sent.")


def delete_event(key: str, lang: str, make_cancel=None) -> tuple[dict, int]:
    item = find_series(key, lang)
    if not item:
        return _bad("event not found", "找不到這個行程", lang, 404)
    if not item["pub"]["editable"]:
        return _bad("synced events are read-only here", "同步來的行程在這裡唯讀", lang, 403)
    invite = None
    if make_cancel is None:
        make_cancel = item["pub"]["my_status"] == "organizer" and bool(item["pub"]["attendees"])
    if make_cancel:
        invite = make_invite(item["key"], "CANCEL")
    con = yhbmail.db()
    n = con.execute("DELETE FROM cal_events WHERE id=?", (int(item["key"].split(":")[1]),)).rowcount
    con.commit()
    con.close()
    note = ("已從本機行事曆刪除" + ("，並產生取消通知 .ics 草稿（不會寄出）。" if invite else "。")) if _zh(lang) else \
        ("Deleted from the local calendar" + (" and a .ics cancellation draft was written (not sent)." if invite else "."))
    return {"ok": True, "deleted": n, "id": item["key"], "invite": invite, "sent": False, "note": note}, 200


def set_rsvp(key: str, status: str, lang: str, make_reply: bool = False) -> tuple[dict, int]:
    status = str(status or "").lower()
    if status not in STATUSES:
        return _bad("status must be accepted, tentative, declined or needs-action",
                    "狀態只能是 accepted、tentative、declined、needs-action", lang)
    item = find_series(key, lang)
    if not item:
        return _bad("event not found", "找不到這個行程", lang, 404)
    if item["pub"]["my_status"] == "organizer":
        return _bad("you organize this event", "你是這個行程的主辦人", lang)
    now = yhbmail.now_iso()
    con = yhbmail.db()
    if item["key"].startswith("local:"):
        row = item["row"]
        people = json.loads(row.get("attendees_json") or "[]")
        me = set(me_addresses())
        if not any(a.get("email") in me for a in people):
            people.append({**me_person(), "status": "NEEDS-ACTION", "role": "REQ-PARTICIPANT"})
        people = [{**a, "status": status.upper()} if a.get("email") in me else a for a in people]
        con.execute("UPDATE cal_events SET my_status=?, attendees_json=?, updated_at=? WHERE id=?",
                    (status, json.dumps(people, ensure_ascii=False), now, row["id"]))
    else:
        con.execute("INSERT INTO cal_rsvp(event_key, status, updated_at) VALUES (?,?,?) "
                    "ON CONFLICT(event_key) DO UPDATE SET status=excluded.status, updated_at=excluded.updated_at",
                    (item["key"], status, now))
    con.commit()
    con.close()
    reply = make_invite(item["key"], "REPLY") if make_reply and (item["pub"].get("organizer") or {}).get("email") else None
    fresh = find_series(item["key"], lang)
    if _zh(lang):
        note = "回覆狀態只記在本機，不會通知主辦人" + ("；已產生 .ics 回覆草稿。" if reply else "。")
    else:
        note = "Your RSVP is recorded locally; the organizer is not notified" + \
               ("; a .ics reply draft was written." if reply else ".")
    return {"ok": True, "event": fresh["pub"] if fresh else None, "my_status": status, "reply": reply,
            "sent": False, "note": note}, 200


# ───────────────────────── invite drafts ─────────────────────────

def _filename(title: str, method: str) -> str:
    stem = re.sub(r"[^\w\-]+", "-", title or "event", flags=re.UNICODE).strip("-")[:60] or "event"
    return f"{stem}{'' if method == 'REQUEST' else '-' + method.lower()}.ics"


def make_invite(key: str, method: str) -> dict | None:
    item = find_series(key)
    if not item:
        return None
    pub, ev = item["pub"], item["ics_ev"]
    me = me_person()
    seq = int(pub.get("sequence") or 0) + (1 if method == "CANCEL" else 0)
    uid = pub.get("uid") or f"{hashlib.sha1(key.encode()).hexdigest()[:16]}@toopowerinbox.example.com"
    attendees = [{"email": a["email"], "name": a.get("name") or "", "status": a["status"].upper(),
                  "role": a.get("role") or "REQ-PARTICIPANT"} for a in pub["attendees"]]
    body = {"uid": uid, "sequence": seq, "title": pub["title"], "start": ev["start"], "end": ev["end"],
            "all_day": pub["all_day"], "location": pub["location"], "description": pub["description"],
            "organizer": pub.get("organizer") or {"email": me["email"], "name": me["name"]},
            "attendees": attendees, "rrule_raw": pub.get("rrule") or "", "transp": pub.get("transp")}
    if method == "REPLY":
        mine = next((a for a in attendees if a["email"] in me_addresses()), None)
        body["reply_as"] = {**(mine or {"email": me["email"], "name": me["name"], "role": "REQ-PARTICIPANT"}),
                            "status": (pub["my_status"] or "needs-action").upper()}
    text = ics.build(method, body, datetime.now(UTC))
    recipients = [body["organizer"]["email"]] if method == "REPLY" else [a["email"] for a in attendees]
    con = yhbmail.db()
    inv_id = con.execute(
        "INSERT INTO cal_invites(event_key, method, uid, sequence, filename, ics, summary, recipients, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (key, method, uid, seq, _filename(pub["title"], method), text, pub["title"], ", ".join(recipients),
         yhbmail.now_iso())).lastrowid
    con.commit()
    con.close()
    return get_invite(inv_id)


def _invite_view(row: dict, with_ics: bool = True) -> dict:
    out = {"id": row["id"], "event_id": row["event_key"], "method": row["method"], "uid": row["uid"],
           "sequence": row["sequence"], "filename": row["filename"], "summary": row["summary"],
           "recipients": [x for x in (row["recipients"] or "").split(", ") if x], "created_at": row["created_at"],
           "url": f"/api/cal/invite/{row['id']}.ics", "sent": False}
    if with_ics:
        out["ics"] = row["ics"]
    return out


def get_invite(inv_id: int) -> dict | None:
    con = yhbmail.db()
    row = con.execute("SELECT * FROM cal_invites WHERE id=?", (inv_id,)).fetchone()
    con.close()
    return _invite_view(dict(row)) if row else None


def list_invites(key: str = "", limit: int = 100) -> list[dict]:
    ensure_tables()
    con = yhbmail.db()
    if key:
        rows = con.execute("SELECT * FROM cal_invites WHERE event_key=? ORDER BY id DESC LIMIT ?", (key, limit))
    else:
        rows = con.execute("SELECT * FROM cal_invites ORDER BY id DESC LIMIT ?", (limit,))
    out = [_invite_view(dict(r), with_ics=False) for r in rows]
    con.close()
    return out


# ───────────────────────── colleague feeds ─────────────────────────

_PARSED: dict = {}


def _guard_message(msg: str) -> str:
    """agent_bridge's URL guard talks about agent.json; a calendar feed opts in with its own allow_private flag."""
    if "loopback/private" in msg:
        return ("calendar URL resolves to a loopback/private address; tick "
                "\"Allow private / http addresses\" (allow_private) only if it is your own or your intranet's server")
    return msg.replace("agent endpoints", "calendar URLs").replace("agent url", "calendar URL") \
        .replace("agent host", "calendar host")


def fetch_ics(url: str, allow_private: bool = False) -> str:
    """GET a calendar over http(s). Every hop goes through agent_bridge._safe_url; 2 MB cap."""
    url = url.strip()
    if url.lower().startswith("webcal://"):
        url = "https://" + url[9:]
    for _ in range(4):
        try:
            parts = urlsplit(agent_bridge._safe_url(url, allow_private=allow_private))
        except RuntimeError as e:
            raise RuntimeError(_guard_message(str(e))) from None
        cls = http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
        conn = cls(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80), timeout=20)
        try:
            path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
            conn.request("GET", path, headers={"Accept": "text/calendar, text/plain;q=0.8, */*;q=0.1",
                                               "User-Agent": "TooPowerInbox-calendar/1"})
            resp = conn.getresponse()
            if resp.status in (301, 302, 303, 307, 308) and resp.getheader("Location"):
                url = urljoin(url, resp.getheader("Location"))
                continue
            if resp.status != 200:
                raise RuntimeError(f"calendar URL returned HTTP {resp.status}")
            raw = resp.read(ics.MAX_BYTES + 1)
            if len(raw) > ics.MAX_BYTES:
                raise RuntimeError("calendar file is larger than 2 MB")
            return raw.decode("utf-8", "replace")
        finally:
            conn.close()
    raise RuntimeError("too many redirects")


def _feed_view(row: dict) -> dict:
    parsed = _parsed(row, UTC)
    return {"id": row["id"], "name": row["name"], "email": row["email"] or "", "url": row["url"] or "",
            "filename": row["filename"] or "", "kind": row["kind"], "allow_private": bool(row["allow_private"]),
            "error": row["error"] or "", "fetched_at": row["fetched_at"] or "", "created_at": row["created_at"],
            "events": len(parsed["events"]) if parsed else 0, "freebusy": len(parsed["freebusy"]) if parsed else 0}


def _parsed(row: dict, floating) -> dict | None:
    text = row.get("ics") or ""
    if not text:
        return None
    key = (row["id"], hashlib.sha1(text.encode("utf-8", "replace")).hexdigest(), ics.tz_name(floating))
    if key not in _PARSED:
        try:
            _PARSED[key] = ics.parse_calendar(text, floating)
        except ics.IcsError:
            _PARSED[key] = None
        if len(_PARSED) > 64:
            _PARSED.pop(next(iter(_PARSED)))
    return _PARSED[key]


def list_feeds() -> list[dict]:
    ensure_tables()
    con = yhbmail.db()
    rows = [dict(r) for r in con.execute("SELECT * FROM cal_feeds ORDER BY id")]
    con.close()
    return [_feed_view(r) for r in rows]


def _feed_row(feed_id) -> dict | None:
    try:
        feed_id = int(feed_id)
    except (TypeError, ValueError):
        return None
    con = yhbmail.db()
    row = con.execute("SELECT * FROM cal_feeds WHERE id=?", (feed_id,)).fetchone()
    con.close()
    return dict(row) if row else None


def add_feed(data: dict, lang: str) -> tuple[dict, int]:
    ensure_tables()
    url = _clip(data.get("url"), 2000).strip()
    text = data.get("ics")
    if not url and not text:
        return _bad("give a url or the ics file content", "請給 ICS 網址或檔案內容", lang)
    allow_private = bool(data.get("allow_private"))
    kind = "url" if url else "file"
    if url:
        if not re.match(r"^(https?|webcal)://", url, re.I):
            return _bad("url must start with https://, http:// or webcal://", "網址要以 https://、http:// 或 webcal:// 開頭", lang)
        try:
            text = fetch_ics(url, allow_private)
        except Exception as e:
            return _bad(f"could not fetch the calendar: {str(e)[:200]}", f"抓不到這個行事曆：{str(e)[:200]}", lang, 502)
    text = str(text)
    try:
        parsed = ics.parse_calendar(text)
    except ics.IcsError as e:
        return _bad(f"not a usable ICS file: {e}", f"不是可用的 ICS 檔：{e}", lang)
    email = _clip(data.get("email"), 300).strip().lower()
    if email and not ADDR_RE.fullmatch(email):
        return _bad("email does not look like an address", "信箱格式不對", lang)
    filename = _clip(data.get("filename"), 200).strip()
    name = _clip(data.get("name"), 120).strip() or parsed["name"] or (filename.rsplit(".", 1)[0] if filename else "") \
        or email or ("同事行事曆" if _zh(lang) else "Colleague calendar")
    now = yhbmail.now_iso()
    con = yhbmail.db()
    feed_id = con.execute(
        "INSERT INTO cal_feeds(name, email, url, filename, kind, allow_private, ics, error, fetched_at, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (name, email, url, filename, kind, 1 if allow_private else 0, text, "", now, now)).lastrowid
    con.commit()
    con.close()
    feed = _feed_view(_feed_row(feed_id))
    return {"ok": True, "feed": feed, "warnings": parsed["errors"],
            "note": ("已匯入；只用來顯示忙碌時段，不會寫進你的行事曆。" if _zh(lang)
                     else "Imported. Used only for free/busy; nothing is added to your calendar.")}, 201


def refresh_feed(feed_id, lang: str) -> tuple[dict, int]:
    row = _feed_row(feed_id)
    if not row:
        return _bad("feed not found", "找不到這個同事行事曆", lang, 404)
    if row["kind"] != "url":
        return _bad("only URL feeds can be refreshed; import the file again", "只有網址訂閱能重新整理；檔案請重新匯入", lang)
    con = yhbmail.db()
    try:
        text = fetch_ics(row["url"], bool(row["allow_private"]))
        ics.parse_calendar(text)
        con.execute("UPDATE cal_feeds SET ics=?, error='', fetched_at=? WHERE id=?", (text, yhbmail.now_iso(), row["id"]))
        status = 200
    except Exception as e:
        con.execute("UPDATE cal_feeds SET error=? WHERE id=?", (str(e)[:300], row["id"]))
        status = 502
    con.commit()
    con.close()
    feed = _feed_view(_feed_row(row["id"]))
    return ({"ok": status == 200, "feed": feed, **({"error": feed["error"]} if status != 200 else {})}, status)


def delete_feed(feed_id, lang: str) -> tuple[dict, int]:
    row = _feed_row(feed_id)
    if not row:
        return _bad("feed not found", "找不到這個同事行事曆", lang, 404)
    con = yhbmail.db()
    con.execute("DELETE FROM cal_feeds WHERE id=?", (row["id"],))
    con.commit()
    con.close()
    return {"ok": True, "deleted": row["id"]}, 200


def import_demo_feeds(lang: str) -> tuple[dict, int]:
    fx = _demo_fixture()
    have = {(f["email"], f["kind"]) for f in list_feeds()}
    added = []
    for c in fx.get("colleagues") or []:
        if (c["email"], "file") in have:
            continue
        path = yhbmail.ROOT / "fixtures" / c["file"]
        if not path.is_file():
            continue
        out, status = add_feed({"name": c["name"], "email": c["email"], "ics": path.read_text(),
                                "filename": path.name}, lang)
        if status == 201:
            added.append(out["feed"])
    return {"ok": True, "added": added, "feeds": list_feeds()}, 200


def import_into_mine(data: dict, lang: str) -> tuple[dict, int]:
    """Add the VEVENTs of an .ics file (an invite you received) to the local calendar; RSVP from PARTSTAT."""
    text = data.get("ics")
    if not text:
        return _bad("ics content is required", "請提供 .ics 內容", lang)
    s = load_settings()
    floating = ics.get_tz(s["tz"]) or UTC
    try:
        parsed = ics.parse_calendar(str(text), floating)
    except ics.IcsError as e:
        return _bad(f"not a usable ICS file: {e}", f"不是可用的 ICS 檔：{e}", lang)
    me = set(me_addresses())
    created, updated, cancelled = [], [], []
    for ev in parsed["events"]:
        if ev.get("recurrence_id") is not None:
            continue
        con = yhbmail.db()
        row = con.execute("SELECT * FROM cal_events WHERE uid=?", (ev["uid"],)).fetchone() if ev["uid"] else None
        con.close()
        if parsed["method"] == "CANCEL" or ev["status"] == "CANCELLED":
            if row:
                con = yhbmail.db()
                con.execute("UPDATE cal_events SET status='CANCELLED', updated_at=? WHERE id=?", (yhbmail.now_iso(), row["id"]))
                con.commit()
                con.close()
                cancelled.append(f"local:{row['id']}")
            continue
        tz_name = ev["tz"] or s["tz"]
        tz = ics.get_tz(tz_name) or floating
        start, end = ev["start"], ev["end"]
        payload = {"title": ev["summary"] or ("（無標題）" if _zh(lang) else "(no title)"), "all_day": ev["all_day"],
                   "start": _local(start, tz) if isinstance(start, datetime) else start.isoformat(),
                   "end": _local(end, tz) if isinstance(end, datetime) else end.isoformat(), "tz": tz_name,
                   "location": ev["location"], "description": ev["description"], "rrule": ev["rrule_raw"] or None,
                   "attendees": ev["attendees"], "organizer": ev["organizer"] or None, "uid": ev["uid"] or None,
                   "make_invite": False}
        if row:
            payload["id"] = f"local:{row['id']}"
        out, status = save_event(payload, lang, source="ics")
        if status not in (200, 201):
            continue
        key = out["event"]["id"]
        my = next((a["status"].lower() for a in ev["attendees"] if a["email"] in me), "")
        con = yhbmail.db()
        con.execute("UPDATE cal_events SET my_status=?, transp=?, exdates_json=? WHERE id=?",
                    ("organizer" if (ev["organizer"] or {}).get("email") in me else my, ev["transp"],
                     json.dumps([_iso(x) for x in ev["exdates"]]), int(key.split(":")[1])))
        con.commit()
        con.close()
        (updated if row else created).append(key)
    return {"ok": True, "created": created, "updated": updated, "cancelled": cancelled, "method": parsed["method"],
            "warnings": parsed["errors"],
            "note": "已加入本機行事曆；不會回覆對方。" if _zh(lang) else "Added to the local calendar; nothing is sent back."}, 200


# ───────────────────────── free / busy ─────────────────────────

def _merge(intervals: list[tuple]) -> list[tuple]:
    out = []
    for s, e in sorted(intervals):
        if out and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def _busy_all_day(title: str, transp: str) -> bool:
    return transp == "OPAQUE" or bool(OOO_RE.search(title or ""))


def busy_me(ws: datetime, we: datetime, tz) -> list[dict]:
    out = []
    for inst in instances(ws, we, tz):
        pub = inst["pub"]
        if pub["my_status"] == "declined" or pub["transp"] == "TRANSPARENT":
            continue
        s, e = inst["s"], inst["e"]
        if not isinstance(s, datetime):
            if not _busy_all_day(pub["title"], pub["transp"]):
                continue
        out.append({"s": ics.as_utc(s, tz), "e": ics.as_utc(e, tz), "title": pub["title"], "id": pub["id"]})
    return out


def busy_feed(row: dict, ws: datetime, we: datetime, tz) -> list[dict]:
    parsed = _parsed(row, tz)
    if not parsed:
        return []
    owner = (row.get("email") or "").lower()
    out = []
    for inst in ics.expand(parsed["events"], ws, we, tz):
        if inst["transp"] == "TRANSPARENT":
            continue
        if owner and any(a["email"] == owner and a["status"] == "DECLINED" for a in inst["attendees"]):
            continue
        if inst["all_day"] and not _busy_all_day(inst["summary"], inst["transp"]):
            continue
        private = inst["class"] in ("PRIVATE", "CONFIDENTIAL")
        out.append({"s": ics.as_utc(inst["start"], tz), "e": ics.as_utc(inst["end"], tz),
                    "title": "" if private else inst["summary"]})
    for s, e, _ in parsed["freebusy"]:
        if e > ws and s < we:
            out.append({"s": s.astimezone(UTC), "e": e.astimezone(UTC), "title": ""})
    return out


def _segments(blocks: list[dict], days: list[date], tz) -> list[list[dict]]:
    rows = []
    for d in days:
        ds, de = _bounds(d, tz)
        segs = []
        for b in blocks:
            if b["e"] > ds and b["s"] < de:
                s, e = max(b["s"], ds), min(b["e"], de)
                segs.append({"from_min": 0 if s == ds else _wall_minutes(s, tz),
                             "to_min": 1440 if e == de else _wall_minutes(e, tz),
                             "start": _local(s, tz), "end": _local(e, tz), "title": b.get("title") or ""})
        rows.append(sorted(segs, key=lambda x: (x["from_min"], x["to_min"])))
    return rows


def free_slots(busy: list[tuple], days: list[date], tz, work_start: int, work_end: int, minutes: int,
               include_weekends: bool = False, after: datetime | None = None, limit: int = 40) -> list[dict]:
    merged = _merge(busy)
    out = []
    for d in days:
        if d.weekday() >= 5 and not include_weekends:
            continue
        cur = datetime.combine(d, time(work_start), tzinfo=tz).astimezone(UTC)
        stop = (datetime.combine(d, time(work_end), tzinfo=tz) if work_end < 24 else
                datetime.combine(d + timedelta(days=1), time(0), tzinfo=tz)).astimezone(UTC)
        if after is not None and after.astimezone(UTC) > cur:
            a = after.astimezone(UTC)
            cur = a + timedelta(minutes=(-a.minute) % 15, seconds=-a.second, microseconds=-a.microsecond)
        for s, e in merged + [(stop, stop)]:
            if e <= cur:
                continue
            gap_end = min(s, stop)
            if gap_end - cur >= timedelta(minutes=minutes):
                out.append({"start": _local(cur, tz), "end": _local(gap_end, tz), "date": d.isoformat(),
                            "start_utc": ics.fmt_utc(cur), "end_utc": ics.fmt_utc(gap_end),
                            "from_min": _wall_minutes(cur, tz), "to_min": _wall_minutes(gap_end, tz) or 1440,
                            "minutes": int((gap_end - cur).total_seconds() // 60)})
                if len(out) >= limit:
                    return out
            cur = max(cur, e)
            if cur >= stop:
                break
    return out


def freebusy(start: date, days_n: int, tz_name: str, feed_ids: list[int] | None, include_me: bool, minutes: int,
             work_start: int, work_end: int, include_weekends: bool, lang: str, after: datetime | None = None) -> dict:
    tz = ics.get_tz(tz_name) or UTC
    days = [start + timedelta(days=i) for i in range(days_n)]
    ws, we = _bounds(days[0], tz)[0], _bounds(days[-1], tz)[1]
    people, union = [], []
    if include_me:
        blocks = busy_me(ws, we, tz)
        me = me_person()
        people.append({"id": "me", "kind": "me", "name": me["name"] or ("我" if _zh(lang) else "Me"),
                       "email": me["email"], "error": "", "days": _segments(blocks, days, tz),
                       "busy_minutes": _minutes(blocks)})
        union += [(b["s"], b["e"]) for b in blocks]
    for feed in list_feeds():
        if feed_ids is not None and feed["id"] not in feed_ids:
            continue
        row = _feed_row(feed["id"])
        blocks = busy_feed(row, ws, we, tz)
        people.append({"id": f"feed:{feed['id']}", "kind": "feed", "name": feed["name"], "email": feed["email"],
                       "error": feed["error"], "days": _segments(blocks, days, tz), "busy_minutes": _minutes(blocks)})
        union += [(b["s"], b["e"]) for b in blocks]
    return {"tz": tz_name, "start": days[0].isoformat(), "days": [
        {"date": d.isoformat(), "weekday": (WD_ZH if _zh(lang) else WD_EN)[d.weekday()], "weekend": d.weekday() >= 5}
        for d in days], "work_start": work_start, "work_end": work_end, "slot_minutes": minutes,
        "people": people, "free_slots": free_slots(union, days, tz, work_start, work_end, minutes, include_weekends, after)}


def _minutes(blocks: list[dict]) -> int:
    return int(sum((e - s).total_seconds() for s, e in _merge([(b["s"], b["e"]) for b in blocks])) // 60)


def feeds_for(emails: list[str]) -> list[int]:
    wanted = {e.lower() for e in emails}
    return [f["id"] for f in list_feeds() if f["email"] and f["email"] in wanted]


def conflicts(start, end, attendee_emails: list[str], exclude_key: str, lang: str) -> list[dict]:
    if not isinstance(start, datetime):
        return []
    s = load_settings()
    tz = ics.get_tz(s["tz"]) or UTC
    su, eu = start.astimezone(UTC), end.astimezone(UTC)
    out = []
    me = me_person()
    for b in busy_me(su, eu, tz):
        if b["id"] != exclude_key and b["e"] > su and b["s"] < eu:
            out.append({"who": me["name"] or ("我" if _zh(lang) else "Me"), "email": me["email"], "title": b["title"],
                        "start": _local(b["s"], tz), "end": _local(b["e"], tz)})
    for fid in feeds_for(attendee_emails):
        row = _feed_row(fid)
        for b in busy_feed(row, su, eu, tz):
            out.append({"who": row["name"], "email": row["email"], "title": b["title"],
                        "start": _local(b["s"], tz), "end": _local(b["e"], tz)})
    return out


# ───────────────────────── AI booking (natural language) ─────────────────────────

ZH_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "兩": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7,
             "八": 8, "九": 9, "十": 10}
EN_WD = {"monday": 0, "mon": 0, "tuesday": 1, "tues": 1, "tue": 1, "wednesday": 2, "wed": 2, "thursday": 3,
         "thurs": 3, "thur": 3, "thu": 3, "friday": 4, "fri": 4, "saturday": 5, "sat": 5, "sunday": 6, "sun": 6}
ZH_WD = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
MONTH_ABBR = {m[:3].lower(): i + 1 for i, m in enumerate(MONTHS_EN)}
CITY_TZ = {
    "taipei": "Asia/Taipei", "台北": "Asia/Taipei", "臺北": "Asia/Taipei", "tokyo": "Asia/Tokyo", "東京": "Asia/Tokyo",
    "seoul": "Asia/Seoul", "首爾": "Asia/Seoul", "singapore": "Asia/Singapore", "新加坡": "Asia/Singapore",
    "hong kong": "Asia/Hong_Kong", "香港": "Asia/Hong_Kong", "shanghai": "Asia/Shanghai", "上海": "Asia/Shanghai",
    "sydney": "Australia/Sydney", "雪梨": "Australia/Sydney", "london": "Europe/London", "倫敦": "Europe/London",
    "berlin": "Europe/Berlin", "柏林": "Europe/Berlin", "paris": "Europe/Paris", "巴黎": "Europe/Paris",
    "new york": "America/New_York", "ny": "America/New_York", "紐約": "America/New_York",
    "chicago": "America/Chicago", "芝加哥": "America/Chicago", "los angeles": "America/Los_Angeles",
    "la": "America/Los_Angeles", "洛杉磯": "America/Los_Angeles", "san francisco": "America/Los_Angeles",
    "sf": "America/Los_Angeles", "舊金山": "America/Los_Angeles",
}
ABBR_TZ = {"est": "America/New_York", "edt": "America/New_York", "pst": "America/Los_Angeles",
           "pdt": "America/Los_Angeles", "jst": "Asia/Tokyo", "kst": "Asia/Seoul", "cet": "Europe/Berlin"}
ZH_NUM = r"[0-9]{1,2}|[零〇一二兩两三四五六七八九十]{1,3}"
RE_TZ_EN = re.compile(r"\b(" + "|".join(re.escape(k) for k in sorted(CITY_TZ, key=len, reverse=True) if k.isascii())
                      + r")\s+time\b", re.I)
RE_TZ_ZH = re.compile("(" + "|".join(k for k in CITY_TZ if not k.isascii()) + r")\s*時間")
RE_TZ_ABBR = re.compile(r"(?<![A-Za-z])(" + "|".join(ABBR_TZ) + r")(?![A-Za-z])", re.I)
RE_TZ_OFF = re.compile(r"\b(?:UTC|GMT)\s*([+-])\s*(\d{1,2})(?::?(\d{2}))?\b", re.I)
RE_TZ_IANA = re.compile(r"\b([A-Z][a-z]+/[A-Z][A-Za-z_]+)\b")
RE_ISO = re.compile(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b")
RE_MD_ZH = re.compile(r"(\d{1,2})\s*月\s*(\d{1,2})\s*[日號号]")
RE_MD_SLASH = re.compile(r"(?<![\d/:])(\d{1,2})/(\d{1,2})(?![\d/])")
RE_MON_D = re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b", re.I)
RE_D_MON = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b", re.I)
RE_REL = re.compile(r"\b(day after tomorrow|tomorrow|today|tonight)\b|(後天|后天|明天|明日|明早|明晚|今天|今日|今晚)", re.I)
RE_IN_DAYS = re.compile(r"\bin\s+(\d{1,2})\s+days?\b|(\d{1,2})\s*天[後后]", re.I)
RE_WD_EN = re.compile(r"\b(?:(next|this|coming)\s+)?(" + "|".join(sorted(EN_WD, key=len, reverse=True)) + r")\b", re.I)
RE_WD_ZH = re.compile(r"(下下|下|這|这|本)?\s*(?:個)?\s*(?:週|周|星期|禮拜|礼拜)([一二三四五六日天])")
RE_TIME_RANGE_EN = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(?:-|–|to)\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)", re.I)
RE_TIME_EN = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)(?![a-z])", re.I)
RE_TIME_24 = re.compile(r"(?<![\d:/.])([01]?\d|2[0-3])[:：]([0-5]\d)(?![\d])")
RE_TIME_ZH = re.compile(r"(凌晨|清晨|早上|上午|中午|下午|傍晚|晚上)?\s*(" + ZH_NUM + r")\s*[點点時时](?!間|间)\s*(半|(" + ZH_NUM + r")\s*分?)?")
RE_NOON = re.compile(r"\bnoon\b", re.I)
RE_RANGE_SEP = re.compile(r"^\s*(?:-|–|—|~|～|to|until|till|到|至)\s*$", re.I)
RE_DUR_H = re.compile(r"(?<![A-Za-z0-9.:])(\d+(?:\.\d+)?|an?|one|two|three)\s*(?:-|\s)?(?:h|hrs?|hours?)\b"
                      r"|(\d+(?:\.\d+)?|[一二兩两三四五六七八九十]+)\s*(?:個|个)?\s*(?:小時|小时|鐘頭|钟头)", re.I)
RE_DUR_M = re.compile(r"(\d+)\s*(?:-|\s)?(?:m|mins?|minutes?)\b|(\d+|[一二三四五六七八九十]+)\s*分鐘|(\d+|[一二三四五六七八九十]+)\s*分钟", re.I)
RE_DUR_HALF = re.compile(r"半小時|半小时|半個小時|half an hour|half hour|半天", re.I)
RE_QUOTED = re.compile(r"[\"“「『]([^\"”」』]{1,80})[\"”」』]")
RE_TOPIC = re.compile(r"(?:\babout\b|\bregarding\b|\bre:|\bto discuss\b|\bon the topic of\b|title\s*[:：]|subject\s*[:：]"
                      r"|主題\s*[:：]?|討論|讨论|關於|关于)\s*([^,，。;；\n]{1,60})", re.I)
RE_LOCATION = re.compile(r"(?:\blocation\b|\bplace\b|\bwhere\b|\bvenue\b|地點|地点|場地)\s*[:：]\s*([^,，。;；\n]{1,80})", re.I)
RE_ROOM = re.compile(r"\b(?:room|rm\.?)\s*([A-Za-z0-9-]{1,12})\b|(會議室\s*[A-Za-z0-9一-龥]{0,8})", re.I)
RE_VIDEO = re.compile(r"\b(zoom|google meet|teams|webex|video call|video)\b|(視訊|线上|線上)", re.I)
FILLER_EN = re.compile(r"\b(please|pls|can you|could you|would you|help me|book|schedule|set up|setup|arrange|create|add|"
                       r"put|a|an|the|meeting|meet|call|sync|with|on|at|for|from|next|this|coming|in|and|me|my|us|our|"
                       r"calendar|invite|event|slot|time|minutes?|mins?|hours?|hrs?|h|m|am|pm|today|tomorrow|tonight|"
                       r"of|to|by|around|about|some|free)\b", re.I)
FILLER_ZH = re.compile(r"(幫我|帮我|請|请|麻煩|麻烦|安排|預約|预约|約一下|约一下|約|约|一個|一个|個|会议|會議|開會|开会|"
                       r"和|跟|與|与|在|的|行程|邀請|邀请|一下|時間|时间|找|空檔|空档|左右|吧|喔|哦|。|，|、)")


def _zh_int(s: str) -> int | None:
    s = (s or "").strip()
    if s.isdigit():
        return int(s)
    if not s or any(c not in ZH_DIGITS for c in s):
        return None
    if s == "十":
        return 10
    if "十" in s:
        a, _, b = s.partition("十")
        return (ZH_DIGITS[a] if a else 1) * 10 + (ZH_DIGITS[b] if b else 0)
    return ZH_DIGITS.get(s)


def _num(s: str) -> float | None:
    s = (s or "").strip().lower()
    if s in ("a", "an", "one"):
        return 1
    if s == "two":
        return 2
    if s == "three":
        return 3
    try:
        return float(s)
    except ValueError:
        v = _zh_int(s)
        return float(v) if v is not None else None


def _next_weekday(today: date, wd: int, mode: str) -> date:
    if mode in ("next", "下"):
        monday = today - timedelta(days=today.weekday()) + timedelta(days=7)
        return monday + timedelta(days=wd)
    if mode == "下下":
        monday = today - timedelta(days=today.weekday()) + timedelta(days=14)
        return monday + timedelta(days=wd)
    if mode in ("this", "這", "这", "本"):
        return today - timedelta(days=today.weekday()) + timedelta(days=wd)
    delta = (wd - today.weekday()) % 7
    return today + timedelta(days=delta or 7)


def _hour(h: int, period: str | None, explicit: bool) -> int:
    period = (period or "").lower().replace(".", "")
    if period in ("pm", "下午", "傍晚", "晚上"):
        return h + 12 if h < 12 else h
    if period == "中午":
        return h + 12 if h < 6 else h
    if period in ("am", "凌晨", "清晨", "早上", "上午"):
        return 0 if h == 12 else h
    if not explicit and 1 <= h <= 7:
        return h + 12
    return h


def parse_ask(ask: str, now: datetime, lang: str) -> dict:
    """Heuristic scheduling parser (en + zh). Returns found fields; nothing is invented."""
    text = ask or ""
    spans: list[tuple[int, int]] = []
    found: dict = {}

    def take(m, group=0):
        spans.append(m.span(group))

    attendees = []
    for m in ADDR_RE.finditer(text):
        attendees.append(m.group(0).lower())
        take(m)
    found["attendees"] = list(dict.fromkeys(attendees))

    tz_name = None
    for rx, fn in ((RE_TZ_IANA, lambda m: m.group(1) if ics.get_tz(m.group(1)) else None),
                   (RE_TZ_EN, lambda m: CITY_TZ.get(m.group(1).lower())),
                   (RE_TZ_ZH, lambda m: CITY_TZ.get(m.group(1))),
                   (RE_TZ_OFF, lambda m: f"UTC{m.group(1)}{int(m.group(2)):02d}:{m.group(3) or '00'}"),
                   (RE_TZ_ABBR, lambda m: ABBR_TZ.get(m.group(1).lower()))):
        m = rx.search(text)
        if m and fn(m):
            tz_name = fn(m)
            take(m)
            break
    found["tz"] = tz_name
    tz = ics.get_tz(tz_name) if tz_name else now.tzinfo
    today = now.astimezone(tz).date()

    day = None
    for rx in (RE_ISO, RE_MD_ZH, RE_MON_D, RE_D_MON, RE_MD_SLASH):
        m = rx.search(text)
        if not m:
            continue
        try:
            if rx is RE_ISO:
                day = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            else:
                if rx is RE_MON_D:
                    mo, dd = MONTH_ABBR[m.group(1)[:3].lower()], int(m.group(2))
                elif rx is RE_D_MON:
                    mo, dd = MONTH_ABBR[m.group(2)[:3].lower()], int(m.group(1))
                else:
                    mo, dd = int(m.group(1)), int(m.group(2))
                day = date(today.year, mo, dd)
                if day < today:
                    day = date(today.year + 1, mo, dd)
        except (ValueError, KeyError):
            day = None
            continue
        take(m)
        break
    if day is None:
        m = RE_REL.search(text)
        if m:
            w = (m.group(1) or m.group(2) or "").lower()
            day = today + timedelta(days=2 if w in ("day after tomorrow", "後天", "后天") else
                                    1 if w in ("tomorrow", "明天", "明日", "明早", "明晚") else 0)
            take(m)
    if day is None:
        m = RE_IN_DAYS.search(text)
        if m:
            day = today + timedelta(days=int(m.group(1) or m.group(2)))
            take(m)
    if day is None:
        m = RE_WD_ZH.search(text)
        if m:
            day = _next_weekday(today, ZH_WD[m.group(2)], m.group(1) or "")
            take(m)
    if day is None:
        m = RE_WD_EN.search(text)
        if m:
            day = _next_weekday(today, EN_WD[m.group(2).lower()], (m.group(1) or "").lower())
            take(m)
    found["date"] = day.isoformat() if day else None

    start_t = end_t = None
    m = RE_TIME_RANGE_EN.search(text)
    if m:
        period = m.group(5)
        h1, h2 = _hour(int(m.group(1)), period, True), _hour(int(m.group(3)), period, True)
        if h1 > h2:
            h1 -= 12
        start_t, end_t = time(h1 % 24, int(m.group(2) or 0)), time(h2 % 24, int(m.group(4) or 0))
        take(m)
    else:
        hits = []
        for rx in (RE_TIME_EN, RE_TIME_24, RE_TIME_ZH):
            for mm in rx.finditer(text):
                if any(a <= mm.start() < b for a, b in spans):
                    continue
                if rx is RE_TIME_EN:
                    h, mi, period, explicit = int(mm.group(1)), int(mm.group(2) or 0), mm.group(3), True
                elif rx is RE_TIME_24:
                    h, mi, period, explicit = int(mm.group(1)), int(mm.group(2)), None, int(mm.group(1)) >= 8 or mm.group(1).startswith("0")
                else:
                    h = _zh_int(mm.group(2))
                    if h is None or h > 24:
                        continue
                    mi = 30 if mm.group(3) == "半" else (_zh_int(mm.group(4)) or 0) if mm.group(4) else 0
                    period, explicit = mm.group(1), bool(mm.group(1)) or h >= 8
                if h > 23 or mi > 59:
                    continue
                hits.append((mm.start(), mm.end(), h, mi, period, explicit))
        hits.sort()
        for mm in RE_NOON.finditer(text):
            hits.append((mm.start(), mm.end(), 12, 0, "中午", True))
        hits.sort()
        if hits:
            a = hits[0]
            start_t = time(_hour(a[2], a[4], a[5]), a[3])
            spans.append((a[0], a[1]))
            if len(hits) > 1 and RE_RANGE_SEP.match(text[a[1]:hits[1][0]]):
                b = hits[1]
                period = b[4] or a[4]
                h2 = _hour(b[2], period, b[5] or bool(period))
                if h2 * 60 + b[3] <= start_t.hour * 60 + start_t.minute and h2 < 12:
                    h2 += 12
                end_t = time(h2 % 24, b[3])
                spans.append((a[1], b[1]))
    found["start_time"] = start_t.strftime("%H:%M") if start_t else None
    found["end_time"] = end_t.strftime("%H:%M") if end_t else None

    minutes = None
    m = RE_DUR_HALF.search(text)
    if m:
        minutes = 240 if m.group(0) == "半天" else 30
        take(m)
    else:
        m = RE_DUR_H.search(text)
        if m:
            v = _num(m.group(1) or m.group(2))
            if v:
                minutes = int(round(v * 60))
                mm = RE_DUR_M.search(text, m.end())
                if mm and mm.start() - m.end() <= 3:
                    minutes += int(_num(mm.group(1) or mm.group(2) or mm.group(3)) or 0)
                    take(mm)
                take(m)
        else:
            m = RE_DUR_M.search(text)
            if m:
                v = _num(m.group(1) or m.group(2) or m.group(3))
                if v:
                    minutes = int(v)
                    take(m)
    found["duration_minutes"] = minutes if minutes and 5 <= minutes <= 24 * 60 else None

    location = None
    m = RE_LOCATION.search(text)
    if m:
        location = m.group(1).strip()
        take(m)
    else:
        m = RE_ROOM.search(text)
        if m:
            location = f"Room {m.group(1)}" if m.group(1) else m.group(2).strip()
            take(m)
        else:
            m = RE_VIDEO.search(text)
            if m:
                word = (m.group(1) or "").lower()
                location = {"zoom": "Zoom", "google meet": "Google Meet", "teams": "Microsoft Teams",
                            "webex": "Webex"}.get(word) or ("視訊會議" if _zh(lang) else "Video call")
                take(m)
    found["location"] = location

    title = None
    m = RE_QUOTED.search(text)
    if m:
        title = m.group(1).strip()
        take(m)
    else:
        m = RE_TOPIC.search(text)
        if m:
            topic = m.group(1).strip()
            sub_spans = [(a - m.start(1), b - m.start(1)) for a, b in spans if m.start(1) <= a < m.end(1)]
            for a, b in sorted(sub_spans, reverse=True):
                topic = topic[:a] + " " + topic[b:]
            topic = re.sub(r"\s+", " ", FILLER_ZH.sub(" ", topic)).strip(" ,.-")
            word = m.group(0)[: m.start(1) - m.start(0)].strip()
            if topic:
                if word in ("討論", "讨论"):
                    title = word + (" " if topic[:1].isascii() else "") + topic
                else:
                    title = topic
                take(m)
    if not title:
        rest = list(text)
        for a, b in spans:
            for i in range(a, min(b, len(rest))):
                rest[i] = " "
        rest = "".join(rest)
        rest = FILLER_ZH.sub(" ", FILLER_EN.sub(" ", rest))
        rest = re.sub(r"[\s,.;:!?()\[\]\-–~～/@]+", " ", rest).strip()
        if 2 <= len(rest) <= 60 and re.search(r"[A-Za-z\u4e00-\u9fff]{2}", rest):
            title = rest[:1].upper() + rest[1:] if rest[:1].isascii() else rest
    found["title"] = title
    return found


CAL_SYSTEM = {
    "zh": "你把排程請求轉成本機行事曆用的 JSON。只輸出一個 JSON 物件，不要其他文字。這只會存成本機草稿，絕不寄出。",
    "en": "You turn a scheduling request into JSON for a local calendar. Output one JSON object and nothing else. "
          "It is only stored as a local draft and never sent.",
}


def ask_agent_json(ask: str, now: datetime, tz_name: str, lang: str) -> tuple[dict | None, str, str | None]:
    cfg = agent_bridge.load_agent_cfg()
    driver = cfg.get("driver") or "local"
    if driver == "local":
        return None, "local", None
    zh = _zh(lang)
    prompt = (f"Today is {now:%Y-%m-%d} ({WD_EN[now.weekday()]}), local time {now:%H:%M} in {tz_name}.\n"
              "Keys: title, date (YYYY-MM-DD), start (HH:MM 24h), end (HH:MM) or duration_minutes, tz (IANA), "
              "attendees (list of email addresses copied from the request), location, description. "
              "Use null for anything the request does not say; never invent people, addresses or times.\n"
              f"Request: {ask}")
    system = CAL_SYSTEM["zh" if zh else "en"]
    try:
        if driver == "openai_compatible":
            block = cfg.get("openai_compatible") or {}
            base = (block.get("base_url") or "").rstrip("/")
            key = os.environ.get(block.get("api_key_env") or "OPENAI_API_KEY") or ""
            body = json.dumps({"model": block.get("model") or "gpt-4.1-mini", "temperature": 0,
                               "messages": [{"role": "system", "content": system},
                                            {"role": "user", "content": prompt}]}).encode()
            data = agent_bridge._post_json(
                f"{base}/chat/completions",
                {"Content-Type": "application/json", **({"Authorization": f"Bearer {key}"} if key else {})},
                body, timeout=90, allow_private=bool(block.get("allow_private")))
            text = data["choices"][0]["message"]["content"] or ""
        elif driver in ("cli", "http"):
            pack = {"ask": system + "\n\n" + prompt, "lang": "zh-Hant" if zh else "en", "mode": "calendar"}
            text = agent_bridge._cli(pack, cfg) if driver == "cli" else agent_bridge._http(pack, cfg)
        else:
            return None, driver, f"unknown agent driver {driver}"
    except Exception as e:
        return None, driver, f"{type(e).__name__}: {e}"[:300]
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None, driver, "agent did not return JSON"
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None, driver, "agent returned invalid JSON"
    return (data if isinstance(data, dict) else None), driver, None if isinstance(data, dict) else "agent JSON is not an object"


def _merge_agent(found: dict, data: dict, ask: str) -> dict:
    out = dict(found)
    if isinstance(data.get("title"), str) and data["title"].strip():
        out["title"] = data["title"].strip()[:200]
    if isinstance(data.get("date"), str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", data["date"].strip()):
        out["date"] = data["date"].strip()
    for k_in, k_out in (("start", "start_time"), ("end", "end_time")):
        v = data.get(k_in)
        if isinstance(v, str):
            mm = re.search(r"(\d{1,2}):(\d{2})", v)
            if mm and int(mm.group(1)) < 24 and int(mm.group(2)) < 60:
                out[k_out] = f"{int(mm.group(1)):02d}:{mm.group(2)}"
            dm = re.match(r"(\d{4}-\d{2}-\d{2})T", v)
            if dm and k_in == "start":
                out["date"] = dm.group(1)
    if isinstance(data.get("duration_minutes"), (int, float)) and 5 <= data["duration_minutes"] <= 1440:
        out["duration_minutes"] = int(data["duration_minutes"])
    if isinstance(data.get("tz"), str) and ics.get_tz(data["tz"]):
        out["tz"] = data["tz"]
    if isinstance(data.get("location"), str) and data["location"].strip():
        out["location"] = data["location"].strip()[:200]
    if isinstance(data.get("description"), str) and data["description"].strip():
        out["description"] = data["description"].strip()[:2000]
    if isinstance(data.get("attendees"), list):
        said = {a.lower() for a in ADDR_RE.findall(ask or "")}
        picked = [str(a).lower() for a in data["attendees"] if str(a).lower() in said]
        out["attendees"] = list(dict.fromkeys(found["attendees"] + picked))
    return out


def propose(ask: str, lang: str, tz_name: str | None = None, now_override=None, use_agent: bool = True) -> dict:
    s = load_settings()
    zh = _zh(lang)
    base_tz = ics.get_tz(tz_name or s["tz"]) or UTC
    now = now_in(base_tz, now_override)
    found = parse_ask(ask, now, lang)
    source, driver, error = "heuristic", "local", None
    if use_agent:
        data, driver, error = ask_agent_json(ask, now, tz_name or s["tz"], lang)
        if data:
            found = _merge_agent(found, data, ask)
            source = "agent"
    tz_used = found.get("tz") or tz_name or s["tz"]
    tz = ics.get_tz(tz_used) or base_tz
    minutes = found.get("duration_minutes")
    if found.get("start_time") and found.get("end_time"):
        h1, m1 = (int(x) for x in found["start_time"].split(":"))
        h2, m2 = (int(x) for x in found["end_time"].split(":"))
        span = (h2 * 60 + m2) - (h1 * 60 + m1)
        minutes = span if span > 0 else minutes
    minutes = minutes or s["slot_minutes"] or DEFAULT_MINUTES
    names = [a.split("@")[0].replace(".", " ").title() for a in found["attendees"]]
    title = found.get("title") or ((f"與 {'、'.join(names)} 開會" if zh else f"Meeting with {', '.join(names)}")
                                   if names else ("會議" if zh else "Meeting"))
    slot, start = None, None
    local_now = now.astimezone(tz)
    if found.get("start_time"):
        hh, mm = (int(x) for x in found["start_time"].split(":"))
        day = date.fromisoformat(found["date"]) if found.get("date") else local_now.date()
        start = datetime.combine(day, time(hh, mm), tzinfo=tz)
        if not found.get("date") and start <= local_now:
            start += timedelta(days=1)
    else:
        if found.get("date"):
            days = [date.fromisoformat(found["date"])]
        else:
            days = [local_now.date() + timedelta(days=i) for i in range(10)]
        fb = freebusy(days[0], (days[-1] - days[0]).days + 1, tz_used, feeds_for(found["attendees"]), True, minutes,
                      s["work_start"], s["work_end"], bool(found.get("date")), lang, after=local_now)
        hit = fb["free_slots"][0] if fb["free_slots"] else None
        if hit:
            start = datetime.fromisoformat(hit["start"]).replace(tzinfo=tz)
            who = [p["name"] for p in fb["people"]]
            slot = {"reason": (f"{'、'.join(who)} 都有空的第一個時段" if zh else f"first slot free for {', '.join(who)}"),
                    "checked": who}
    missing = [] if start else ["start"]
    proposal = {
        "title": title, "tz": tz_used, "all_day": False, "duration_minutes": minutes,
        "start": start.strftime("%Y-%m-%dT%H:%M") if start else "",
        "end": (start + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M") if start else "",
        "attendees": found["attendees"], "location": found.get("location") or "",
        "description": found.get("description") or ("由 AI 代訂（TooPowerInbox）" if zh else "Booked by AI (TooPowerInbox)"),
    }
    clash = conflicts(start, start + timedelta(minutes=minutes), found["attendees"], "", lang) if start else []
    label = (f"AI 解析 · {driver}" if zh else f"AI parse · {driver}") if source == "agent" else \
        ("規則解析（未接 LLM）" if zh else "Heuristic parse (no LLM)")
    return {"proposal": proposal, "found": found, "missing": missing, "slot": slot, "conflicts": clash,
            "source": source, "driver": driver if source == "agent" else ("local" if not error else driver),
            "label": label, "error": error, "sent": False}


def create_event(args: dict, lang: str = "en", source: str = "agent") -> tuple[dict, int]:
    """Agent tool: book on the local calendar and write a .ics invite draft. Never sends."""
    args = dict(args or {})
    zh = _zh(lang)
    ask = _clip(args.get("ask"), 2000).strip()
    proposal = None
    if ask and not (args.get("title") and args.get("start")):
        res = propose(ask, lang, args.get("tz"), args.get("now"), use_agent=bool(args.get("use_agent", True)))
        proposal = res
        p = res["proposal"]
        for k in ("title", "start", "end", "tz", "location", "description"):
            if not args.get(k) and p.get(k):
                args[k] = p[k]
        if not args.get("attendees") and p["attendees"]:
            args["attendees"] = p["attendees"]
        if not args.get("start"):
            return {"error": "找不到可用的時間，請指定開始時間" if zh else "no free slot found; give a start time",
                    "missing": res["missing"], "proposal": p, "sent": False}, 400
    if not args.get("start"):
        return {"error": "start is required (or give ask)" if not zh else "需要 start（或用 ask 描述）", "sent": False}, 400
    if not args.get("title"):
        args["title"] = "會議" if zh else "Meeting"
    if "make_invite" not in args:
        args["make_invite"] = True
    out, status = save_event(args, lang, source=source)
    if proposal and status in (200, 201):
        out["parsed"] = {"source": proposal["source"], "label": proposal["label"], "slot": proposal["slot"]}
    return out, status


# ───────────────────────── agent tools ─────────────────────────

AGENT_TOOLS = [
    {"name": "create_event",
     "description": "Book a meeting on the local calendar and write a .ics invite draft (never sent). "
                    "Args: title, start (ISO, wall time in tz), end or duration_minutes, tz, attendees "
                    "(emails, list or comma string), location, description, all_day, repeat, or ask "
                    "(plain language; fills what is missing and picks the first free slot). "
                    "在本機行事曆建立行程並產生 .ics 邀請草稿，絕不寄出。"},
    {"name": "find_free_time",
     "description": "Common free slots for you and colleagues whose ICS feeds were imported. "
                    "Args: start (YYYY-MM-DD), days, attendees (emails), minutes, tz. 找你和同事都有空的時段。"},
]


def find_free_time(args: dict, lang: str = "en") -> dict:
    s = load_settings()
    tz_name = args.get("tz") if ics.get_tz(args.get("tz")) else s["tz"]
    tz = ics.get_tz(tz_name)
    now = now_in(tz, args.get("now"))
    start = parse_when(args.get("start"), tz, all_day=True) or now.date()
    attendees, _ = parse_people(args.get("attendees") or [])
    ids = feeds_for([a["email"] for a in attendees]) if attendees else None
    return freebusy(start, _int(args.get("days"), 5, 1, 31), tz_name, ids, True,
                    _int(args.get("minutes"), s["slot_minutes"], 15, 480), s["work_start"], s["work_end"],
                    bool(args.get("include_weekends")), lang, after=now)


def _install_agent_tools() -> None:
    have = {t["name"] for t in agent_bridge.TOOLS}
    for tool in AGENT_TOOLS:
        if tool["name"] not in have:
            agent_bridge.TOOLS.append(tool)
    core = agent_bridge.invoke_tool
    if getattr(core, "_tpi_calendar", False):
        return

    def invoke_with_calendar(name: str, args: dict | None = None) -> dict:
        args = args or {}
        lang = args.get("lang") or "en"
        if name == "create_event":
            out, status = create_event(args, lang, source="agent")
            return out if status in (200, 201) else {**out, "status": status}
        if name == "find_free_time":
            return find_free_time(args, lang)
        return core(name, args)

    invoke_with_calendar._tpi_calendar = True
    agent_bridge.invoke_tool = invoke_with_calendar


_install_agent_tools()


# ───────────────────────── routes ─────────────────────────

def _view_params(req) -> tuple[dict, str, list[str]]:
    s = load_settings()
    q = req.query
    tz_name = q.get("tz") if q.get("tz") and ics.get_tz(q.get("tz")) else s["tz"]
    if "extra" in q:
        extras = [z.strip() for z in q["extra"].split(",") if z.strip() and ics.get_tz(z.strip())][:MAX_EXTRA_TZS]
    else:
        extras = s["extra_tzs"]
    return s, tz_name, extras


@get("/api/cal/settings")
def cal_settings(req):
    return settings_view(_lang(req))


@post("/api/cal/settings")
def cal_settings_save(req):
    out, status = save_settings(req.body)
    return (out, status) if status != 200 else settings_view(_lang(req))


@get("/api/cal/view")
def cal_view(req):
    s, tz_name, extras = _view_params(req)
    view = req.query.get("view") or s["view"]
    if view not in VIEWS:
        return {"error": "view must be week or month"}, 400
    raw = req.query.get("date")
    try:
        anchor = date.fromisoformat(raw[:10]) if raw else anchor_date(s)
    except ValueError:
        return {"error": "date must be YYYY-MM-DD"}, 400
    cals = {c for c in (req.query.get("cals") or "").split(",") if c} or None
    week_start = int(req.query["week_start"]) if req.query.get("week_start") in ("0", "1") else s["week_start"]
    return build_view(view, anchor, tz_name, extras, _lang(req), req.query.get("today"), cals, week_start)


@get("/api/cal/events")
def cal_events(req):
    s, tz_name, _ = _view_params(req)
    tz = ics.get_tz(tz_name)
    try:
        start = date.fromisoformat(req.query.get("start") or anchor_date(s).isoformat())
        end = date.fromisoformat(req.query["end"]) if req.query.get("end") else start + timedelta(days=7)
    except ValueError:
        return {"error": "start / end must be YYYY-MM-DD"}, 400
    if end <= start or (end - start).days > 400:
        return {"error": "end must be after start and within 400 days"}, 400
    ws, we = _bounds(start, tz)[0], _bounds(end - timedelta(days=1), tz)[1]
    return {"tz": tz_name, "start": start.isoformat(), "end": end.isoformat(),
            "events": [_inst_view(i, tz) for i in instances(ws, we, tz, _lang(req))]}


@get("/api/cal/event/*")
def cal_event_get(req):
    _, tz_name, extras = _view_params(req)
    out = event_detail(unquote(req.params), _lang(req), tz_name, extras)
    return out if out else ({"error": "event not found"}, 404)


@post("/api/cal/event")
def cal_event_save(req):
    return save_event(req.body, _lang(req), source="local")


@post("/api/cal/event/delete")
def cal_event_delete(req):
    return delete_event(str(req.body.get("id") or ""), _lang(req), req.body.get("make_cancel"))


@post("/api/cal/rsvp")
def cal_rsvp(req):
    b = req.body
    return set_rsvp(str(b.get("id") or ""), str(b.get("status") or ""), _lang(req), bool(b.get("make_reply")))


@get("/api/cal/invites")
def cal_invites(req):
    return {"invites": list_invites(req.query.get("event") or "")}


@get("/api/cal/invite/*")
def cal_invite_get(req):
    name = unquote(req.params)
    raw = name.endswith(".ics")
    try:
        inv = get_invite(int(name[:-4] if raw else name))
    except ValueError:
        return {"error": "bad id"}, 400
    if not inv:
        return {"error": "invite not found"}, 404
    return Raw(inv["ics"].encode(), "text/calendar; charset=utf-8") if raw else inv


@post("/api/cal/agent/propose")
def cal_agent_propose(req):
    ask = _clip(req.body.get("ask"), 2000).strip()
    if not ask:
        return {"error": "ask is required"}, 400
    return propose(ask, _lang(req), req.body.get("tz"), req.body.get("now"), bool(req.body.get("use_agent", True)))


@post("/api/cal/agent/create_event")
def cal_agent_create(req):
    return create_event(req.body, _lang(req), source="agent")


@get("/api/cal/feeds")
def cal_feeds(req):
    return {"feeds": list_feeds()}


def _local_origin(req) -> bool:
    """True for no Origin (curl, scripts) or this server's own UI; any other page is refused."""
    handler = req.handler
    origin = handler.headers.get("Origin") if handler is not None else None
    if origin is None:
        return True
    try:
        port = handler.server.server_address[1]
    except (AttributeError, IndexError, TypeError):
        port = int(os.environ.get("OPENINBOX_PORT", "8770"))
    return origin.strip().lower().rstrip("/") in (f"http://127.0.0.1:{port}", f"http://localhost:{port}")


def _foreign_origin(req) -> tuple[dict, int]:
    return _bad("cross-origin request refused: open the calendar from this app",
                "拒絕跨來源請求：請從本機 App 介面操作", _lang(req), 403)


@post("/api/cal/feeds")
def cal_feeds_add(req):
    if not _local_origin(req):
        return _foreign_origin(req)
    return add_feed(req.body, _lang(req))


@post("/api/cal/feeds/demo")
def cal_feeds_demo(req):
    return import_demo_feeds(_lang(req))


@post("/api/cal/feed/refresh")
def cal_feed_refresh(req):
    if not _local_origin(req):
        return _foreign_origin(req)
    return refresh_feed(req.body.get("id"), _lang(req))


@post("/api/cal/feed/delete")
def cal_feed_delete(req):
    return delete_feed(req.body.get("id"), _lang(req))


@post("/api/cal/import")
def cal_import(req):
    return import_into_mine(req.body, _lang(req))


@get("/api/cal/freebusy")
def cal_freebusy(req):
    s, tz_name, _ = _view_params(req)
    q = req.query
    tz = ics.get_tz(tz_name)
    try:
        raw = q.get("start") or q.get("date")
        start = date.fromisoformat(raw[:10]) if raw else range_for("week", anchor_date(s), s["week_start"])[0]
    except ValueError:
        return {"error": "start must be YYYY-MM-DD"}, 400
    ids = None
    if q.get("feeds") is not None and q.get("feeds") != "":
        try:
            ids = [int(x) for x in q["feeds"].split(",") if x.strip()]
        except ValueError:
            return {"error": "feeds must be ids"}, 400
    work_start = _int(q.get("work_start"), s["work_start"], 0, 23)
    work_end = _int(q.get("work_end"), s["work_end"], 1, 24)
    if work_start >= work_end:
        return {"error": "work_start must be before work_end"}, 400
    after = now_in(tz, q.get("after")) if q.get("after") else None
    return freebusy(start, _int(q.get("days"), 7, 1, 31), tz_name, ids, q.get("me", "1") != "0",
                    _int(q.get("minutes"), s["slot_minutes"], 15, 480), work_start, work_end,
                    q.get("weekends") == "1", _lang(req), after)


@get("/api/cal/timezones")
def cal_timezones(req):
    try:
        from zoneinfo import available_timezones
        every = sorted(z for z in available_timezones() if "/" in z and not z.startswith(("Etc/", "SystemV/")))
    except Exception:
        every = []
    return {"common": [tz_label(z) for z in COMMON_TZS], "all": every}
