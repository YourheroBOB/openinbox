"""iCalendar (RFC 5545) subset for the calendar feature: parse, expand recurrences, build drafts.

Parsing handles line folding, quoted parameters, TEXT escapes, VEVENT / VFREEBUSY / VTIMEZONE,
DATE and DATE-TIME (UTC, TZID, floating), DURATION, RRULE (DAILY / WEEKLY / MONTHLY / YEARLY with
INTERVAL, COUNT, UNTIL, BYDAY, BYMONTHDAY, BYMONTH), EXDATE, RDATE and RECURRENCE-ID overrides.
A TZID that zoneinfo does not know falls back to a Windows-name map, then to the fixed offset of
the file's own VTIMEZONE STANDARD block.

Building writes METHOD REQUEST / CANCEL / REPLY drafts with CRLF line ends and 75-octet folding.
The underscore keeps the plug-in loader from treating this file as a feature.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone, tzinfo

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python < 3.9
    ZoneInfo = None

MAX_BYTES = 2_000_000
MAX_OCCURRENCES = 3000
MAX_STEPS = 200_000
UTC = timezone.utc

WINDOWS_TZ = {
    "taipei standard time": "Asia/Taipei", "china standard time": "Asia/Shanghai",
    "tokyo standard time": "Asia/Tokyo", "korea standard time": "Asia/Seoul",
    "singapore standard time": "Asia/Singapore", "india standard time": "Asia/Kolkata",
    "eastern standard time": "America/New_York", "central standard time": "America/Chicago",
    "mountain standard time": "America/Denver", "pacific standard time": "America/Los_Angeles",
    "gmt standard time": "Europe/London", "w. europe standard time": "Europe/Berlin",
    "romance standard time": "Europe/Paris", "aus eastern standard time": "Australia/Sydney",
    "utc": "UTC", "coordinated universal time": "UTC",
}
WEEKDAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
FREQS = ("DAILY", "WEEKLY", "MONTHLY", "YEARLY")
PARTSTATS = ("NEEDS-ACTION", "ACCEPTED", "DECLINED", "TENTATIVE", "DELEGATED")

OFFSET_RE = re.compile(r"^(?:UTC|GMT)?\s*([+-])(\d{1,2})(?::?(\d{2}))?$", re.I)
DT_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})(?:T(\d{2})(\d{2})(\d{2})?(Z)?)?$")
DUR_RE = re.compile(r"^([+-])?P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")
BYDAY_RE = re.compile(r"^([+-]?\d{1,2})?(MO|TU|WE|TH|FR|SA|SU)$")


class IcsError(ValueError):
    pass


# ───────────────────────── time zones ─────────────────────────

def fixed_offset(sign: str, hours: str, minutes: str | None) -> timezone:
    delta = timedelta(hours=int(hours), minutes=int(minutes or 0))
    if delta > timedelta(hours=14):
        raise IcsError("offset out of range")
    delta = -delta if sign == "-" else delta
    return timezone(delta, "UTC" + format_offset(delta))


def format_offset(delta: timedelta | None) -> str:
    if delta is None:
        return ""
    total = int(delta.total_seconds() // 60)
    sign = "+" if total >= 0 else "−"
    h, m = divmod(abs(total), 60)
    return f"{sign}{h}" + (f":{m:02d}" if m else "")


def get_tz(name) -> tzinfo | None:
    """IANA name, Windows name, UTC/GMT, or a fixed offset like UTC+08:00. None when unknown."""
    name = str(name or "").strip().strip('"')
    if not name or len(name) > 64:
        return None
    if name.upper() in ("UTC", "Z", "GMT", "ETC/UTC", "ETC/GMT"):
        return UTC
    m = OFFSET_RE.match(name)
    if m:
        try:
            return fixed_offset(*m.groups())
        except IcsError:
            return None
    if ZoneInfo is not None:
        for key in (name, WINDOWS_TZ.get(name.lower())):
            if not key:
                continue
            if key == "UTC":
                return UTC
            try:
                return ZoneInfo(key)
            except Exception:
                continue
    return None


def tz_name(tz: tzinfo | None) -> str:
    if tz is None:
        return ""
    if tz is UTC:
        return "UTC"
    return getattr(tz, "key", None) or str(tz)


# ───────────────────────── parsing ─────────────────────────

def unfold(text: str) -> list[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines: list[str] = []
    for raw in text.split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        elif raw.strip():
            lines.append(raw)
    return lines


def _split_unquoted(s: str, sep: str) -> list[str]:
    out, cur, quoted = [], [], False
    for ch in s:
        if ch == '"':
            quoted = not quoted
            cur.append(ch)
        elif ch == sep and not quoted:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur))
    return out


def parse_line(line: str):
    quoted, colon = False, -1
    for i, ch in enumerate(line):
        if ch == '"':
            quoted = not quoted
        elif ch == ":" and not quoted:
            colon = i
            break
    if colon <= 0:
        return None
    head, value = line[:colon], line[colon + 1:]
    parts = _split_unquoted(head, ";")
    params = {}
    for p in parts[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            params[k.strip().upper()] = v.strip().strip('"')
    return parts[0].strip().upper(), params, value


def unescape(value: str) -> str:
    return re.sub(r"\\([\\;,nN])", lambda m: "\n" if m.group(1) in "nN" else m.group(1), value or "")


def parse_components(text: str) -> dict:
    if len(text.encode("utf-8", "replace")) > MAX_BYTES:
        raise IcsError("calendar file is larger than 2 MB")
    if "BEGIN:VCALENDAR" not in text.upper():
        raise IcsError("not an iCalendar file (no BEGIN:VCALENDAR)")
    root = {"name": "ROOT", "props": [], "children": []}
    stack = [root]
    for line in unfold(text):
        parsed = parse_line(line)
        if not parsed:
            continue
        name, params, value = parsed
        if name == "BEGIN":
            comp = {"name": value.strip().upper(), "props": [], "children": []}
            stack[-1]["children"].append(comp)
            stack.append(comp)
        elif name == "END":
            if len(stack) > 1:
                stack.pop()
        else:
            stack[-1]["props"].append((name, params, value))
    cals = [c for c in root["children"] if c["name"] == "VCALENDAR"]
    if not cals:
        raise IcsError("no VCALENDAR component")
    return cals[0]


def _prop(comp: dict, name: str):
    for n, params, value in comp["props"]:
        if n == name:
            return params, value
    return None


def _props(comp: dict, name: str):
    return [(p, v) for n, p, v in comp["props"] if n == name]


def _vtimezone_fallback(comp: dict) -> tzinfo | None:
    for child in comp["children"]:
        if child["name"] == "STANDARD":
            hit = _prop(child, "TZOFFSETTO")
            if hit:
                m = re.match(r"^([+-])(\d{2})(\d{2})", hit[1].strip())
                if m:
                    try:
                        return fixed_offset(*m.groups())
                    except IcsError:
                        return None
    return None


def parse_dt(value: str, params: dict, tzmap: dict, floating: tzinfo):
    v = value.strip()
    m = DT_RE.match(v)
    if not m:
        raise IcsError(f"bad date value {v[:40]!r}")
    y, mo, d, hh, mi, ss, z = m.groups()
    if hh is None or params.get("VALUE", "").upper() == "DATE":
        return date(int(y), int(mo), int(d))
    naive = datetime(int(y), int(mo), int(d), int(hh), int(mi), int(ss or 0))
    if z:
        return naive.replace(tzinfo=UTC)
    tzid = params.get("TZID")
    if tzid:
        tz = tzmap.get(tzid) or get_tz(tzid)
        if tz is not None:
            return naive.replace(tzinfo=tz)
    return naive.replace(tzinfo=floating)


def parse_dt_list(value: str, params: dict, tzmap: dict, floating: tzinfo) -> list:
    out = []
    for part in value.split(","):
        part = part.strip()
        if part and "/" not in part:
            try:
                out.append(parse_dt(part, params, tzmap, floating))
            except IcsError:
                continue
    return out


def parse_duration(value: str) -> timedelta:
    m = DUR_RE.match((value or "").strip().upper())
    if not m or not any(m.groups()[1:]):
        raise IcsError(f"bad duration {value[:30]!r}")
    sign, w, d, h, mi, s = m.groups()
    delta = timedelta(weeks=int(w or 0), days=int(d or 0), hours=int(h or 0), minutes=int(mi or 0),
                      seconds=int(s or 0))
    return -delta if sign == "-" else delta


def parse_rrule(value: str) -> dict:
    rule: dict = {}
    for part in (value or "").strip().split(";"):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        rule[k.strip().upper()] = v.strip()
    freq = rule.get("FREQ", "").upper()
    if freq not in FREQS:
        raise IcsError(f"unsupported FREQ {freq or '(missing)'}")
    out = {"freq": freq, "interval": 1, "count": None, "until": None, "byday": [], "bymonthday": [], "bymonth": []}
    try:
        out["interval"] = max(1, int(rule.get("INTERVAL") or 1))
        if rule.get("COUNT"):
            out["count"] = max(1, int(rule["COUNT"]))
        out["bymonthday"] = [int(x) for x in rule.get("BYMONTHDAY", "").split(",") if x.strip()]
        out["bymonth"] = [int(x) for x in rule.get("BYMONTH", "").split(",") if x.strip()]
    except ValueError:
        raise IcsError("bad number in RRULE")
    for tok in rule.get("BYDAY", "").upper().split(","):
        tok = tok.strip()
        if not tok:
            continue
        m = BYDAY_RE.match(tok)
        if not m:
            raise IcsError(f"bad BYDAY {tok}")
        out["byday"].append((int(m.group(1)) if m.group(1) else 0, WEEKDAYS.index(m.group(2))))
    if rule.get("UNTIL"):
        out["until_raw"] = rule["UNTIL"]
    return out


def _addr(value: str) -> str:
    v = (value or "").strip()
    return v[7:] if v.lower().startswith("mailto:") else v


def _person(params: dict, value: str) -> dict:
    return {"email": _addr(value).lower(), "name": params.get("CN", "").strip(),
            "status": params.get("PARTSTAT", "NEEDS-ACTION").upper(),
            "role": params.get("ROLE", "REQ-PARTICIPANT").upper()}


def _event(comp: dict, tzmap: dict, floating: tzinfo, method: str) -> dict | None:
    hit = _prop(comp, "DTSTART")
    if not hit:
        return None
    start = parse_dt(hit[1], hit[0], tzmap, floating)
    all_day = not isinstance(start, datetime)
    end = None
    hit_end = _prop(comp, "DTEND")
    if hit_end:
        try:
            end = parse_dt(hit_end[1], hit_end[0], tzmap, floating)
        except IcsError:
            end = None
        if end is not None and isinstance(end, datetime) != isinstance(start, datetime):
            end = None
    if end is None:
        dur = _prop(comp, "DURATION")
        if dur:
            try:
                end = start + parse_duration(dur[1])
            except IcsError:
                end = None
    if end is None or end <= start:
        end = start + (timedelta(days=1) if all_day else timedelta(0))
    rrule = None
    hit_rr = _prop(comp, "RRULE")
    if hit_rr:
        try:
            rrule = parse_rrule(hit_rr[1])
            if rrule.get("until_raw"):
                rrule["until"] = parse_dt(rrule["until_raw"], {}, tzmap, start.tzinfo if not all_day else floating)
        except IcsError:
            rrule = None
    exdates = []
    for params, value in _props(comp, "EXDATE"):
        exdates += parse_dt_list(value, params, tzmap, start.tzinfo if not all_day else floating)
    rdates = []
    for params, value in _props(comp, "RDATE"):
        rdates += parse_dt_list(value, params, tzmap, start.tzinfo if not all_day else floating)
    rid = None
    hit_rid = _prop(comp, "RECURRENCE-ID")
    if hit_rid:
        try:
            rid = parse_dt(hit_rid[1], hit_rid[0], tzmap, start.tzinfo if not all_day else floating)
        except IcsError:
            rid = None
    text = lambda name: unescape(_prop(comp, name)[1]).strip() if _prop(comp, name) else ""
    org = _prop(comp, "ORGANIZER")
    seq = text("SEQUENCE")
    return {
        "uid": text("UID"), "summary": text("SUMMARY"), "description": text("DESCRIPTION"),
        "location": text("LOCATION"), "status": text("STATUS").upper(), "transp": text("TRANSP").upper(),
        "class": text("CLASS").upper(), "start": start, "end": end, "all_day": all_day,
        "tz": tz_name(start.tzinfo) if not all_day else "", "rrule": rrule,
        "rrule_raw": hit_rr[1].strip() if hit_rr and rrule else "",
        "exdates": exdates, "rdates": rdates, "recurrence_id": rid,
        "organizer": _person(org[0], org[1]) if org else None,
        "attendees": [_person(p, v) for p, v in _props(comp, "ATTENDEE")],
        "sequence": int(seq) if seq.isdigit() else 0, "method": method,
    }


def _freebusy(comp: dict, tzmap: dict, floating: tzinfo) -> list[tuple]:
    out = []
    for params, value in _props(comp, "FREEBUSY"):
        fbtype = params.get("FBTYPE", "BUSY").upper()
        if fbtype == "FREE":
            continue
        for period in value.split(","):
            if "/" not in period:
                continue
            a, b = period.strip().split("/", 1)
            try:
                start = parse_dt(a, {}, tzmap, floating)
                end = start + parse_duration(b) if b.upper().startswith(("P", "+P", "-P")) else parse_dt(b, {}, tzmap, floating)
            except IcsError:
                continue
            if isinstance(start, datetime) and isinstance(end, datetime) and end > start:
                out.append((start, end, fbtype))
    return out


def parse_calendar(text: str, floating: tzinfo = UTC) -> dict:
    """{name, method, events, freebusy, errors}. Raises IcsError when it is not a calendar at all."""
    cal = parse_components(text)
    method = (_prop(cal, "METHOD") or ({}, ""))[1].strip().upper()
    name = unescape((_prop(cal, "X-WR-CALNAME") or ({}, ""))[1]).strip()
    tzmap: dict = {}
    for comp in cal["children"]:
        if comp["name"] == "VTIMEZONE":
            hit = _prop(comp, "TZID")
            if hit:
                tzid = hit[1].strip()
                tzmap[tzid] = get_tz(tzid) or _vtimezone_fallback(comp)
    tzmap = {k: v for k, v in tzmap.items() if v is not None}
    events, freebusy, errors = [], [], []
    for comp in cal["children"]:
        try:
            if comp["name"] == "VEVENT":
                ev = _event(comp, tzmap, floating, method)
                if ev:
                    events.append(ev)
            elif comp["name"] == "VFREEBUSY":
                freebusy += _freebusy(comp, tzmap, floating)
        except IcsError as e:
            errors.append(str(e))
    return {"name": name, "method": method, "events": events, "freebusy": freebusy, "errors": errors[:20]}


# ───────────────────────── recurrence ─────────────────────────

def as_utc(value, day_tz: tzinfo) -> datetime:
    """Aware UTC instant for a DATE-TIME, or for a DATE at midnight in `day_tz`."""
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    return datetime.combine(value, time(0), tzinfo=day_tz).astimezone(UTC)


def _month_days(y: int, m: int) -> int:
    nxt = date(y + (m == 12), m % 12 + 1, 1)
    return (nxt - date(y, m, 1)).days


def _nth_weekdays(y: int, m: int, byday: list) -> list[int]:
    n_days = _month_days(y, m)
    out = []
    for n, wd in byday:
        days = [d for d in range(1, n_days + 1) if date(y, m, d).weekday() == wd]
        if n == 0:
            out += days
        elif -len(days) <= n <= len(days) and n != 0:
            out.append(days[n - 1] if n > 0 else days[n])
    return sorted(set(out))


def _candidates(start, rule: dict):
    """Yield wall-clock occurrence starts (naive datetime or date), in order, from `start` on."""
    is_dt = isinstance(start, datetime)
    base = start.replace(tzinfo=None) if is_dt else start
    clock = base.time() if is_dt else None
    base_day = base.date() if is_dt else base
    interval, freq = rule["interval"], rule["freq"]
    byday = rule["byday"]
    wd_set = {wd for _, wd in byday}

    def mk(d: date):
        return datetime.combine(d, clock) if is_dt else d

    k = 0
    while k < MAX_STEPS:
        if freq == "DAILY":
            d = base_day + timedelta(days=interval * k)
            if (not wd_set or d.weekday() in wd_set) and (not rule["bymonth"] or d.month in rule["bymonth"]):
                yield mk(d)
        elif freq == "WEEKLY":
            week0 = base_day - timedelta(days=base_day.weekday()) + timedelta(weeks=interval * k)
            days = sorted(wd_set) if wd_set else [base_day.weekday()]
            for wd in days:
                d = week0 + timedelta(days=wd)
                if d >= base_day:
                    yield mk(d)
        elif freq == "MONTHLY":
            idx = base_day.month - 1 + interval * k
            y, m = base_day.year + idx // 12, idx % 12 + 1
            if not rule["bymonth"] or m in rule["bymonth"]:
                n_days = _month_days(y, m)
                if rule["bymonthday"]:
                    days = sorted({(x if x > 0 else n_days + x + 1) for x in rule["bymonthday"]
                                   if 1 <= (x if x > 0 else n_days + x + 1) <= n_days})
                elif byday:
                    days = _nth_weekdays(y, m, byday)
                else:
                    days = [base_day.day] if base_day.day <= n_days else []
                for dd in days:
                    d = date(y, m, dd)
                    if d >= base_day:
                        yield mk(d)
        else:  # YEARLY
            y = base_day.year + interval * k
            for m in sorted(rule["bymonth"] or [base_day.month]):
                n_days = _month_days(y, m)
                days = sorted(x for x in (rule["bymonthday"] or [base_day.day]) if 1 <= x <= n_days)
                for dd in days:
                    d = date(y, m, dd)
                    if d >= base_day:
                        yield mk(d)
        k += 1


def _key(value, day_tz: tzinfo):
    return as_utc(value, day_tz) if isinstance(value, datetime) else value


def occurrences(ev: dict, win_start: datetime, win_end: datetime, day_tz: tzinfo) -> list[tuple]:
    """(start, end) pairs of `ev` that overlap [win_start, win_end); starts keep the event's own tz."""
    start, end = ev["start"], ev["end"]
    length = end - start
    tz = start.tzinfo if isinstance(start, datetime) else None
    exkeys = {_key(x, day_tz) for x in ev.get("exdates") or []}
    out = []

    def consider(s) -> None:
        if _key(s, day_tz) in exkeys:
            return
        e = s + length
        if as_utc(e, day_tz) > win_start and as_utc(s, day_tz) < win_end:
            out.append((s, e))

    rule = ev.get("rrule")
    if not rule:
        consider(start)
    else:
        until = rule.get("until")
        n = 0
        for cand in _candidates(start, rule):
            s = cand.replace(tzinfo=tz) if isinstance(cand, datetime) else cand
            if until is not None:
                if isinstance(s, datetime) and isinstance(until, datetime) and s.astimezone(UTC) > until.astimezone(UTC):
                    break
                if isinstance(s, datetime) and not isinstance(until, datetime) and s.date() > until:
                    break
                if not isinstance(s, datetime) and (until.date() if isinstance(until, datetime) else until) < s:
                    break
            n += 1
            if rule.get("count") and n > rule["count"]:
                break
            if as_utc(s, day_tz) >= win_end:
                break
            consider(s)
            if len(out) >= MAX_OCCURRENCES:
                break
    seen = {_key(s, day_tz) for s, _ in out}
    for rd in ev.get("rdates") or []:
        if isinstance(rd, datetime) == isinstance(start, datetime) and _key(rd, day_tz) not in seen:
            consider(rd)
    out.sort(key=lambda p: as_utc(p[0], day_tz))
    return out


def expand(events: list[dict], win_start: datetime, win_end: datetime, day_tz: tzinfo) -> list[dict]:
    """Every instance in the window: masters expanded, RECURRENCE-ID overrides applied, CANCELLED dropped."""
    overrides: dict = {}
    for ev in events:
        if ev.get("recurrence_id") is not None and ev.get("uid"):
            overrides.setdefault(ev["uid"], {})[_key(ev["recurrence_id"], day_tz)] = ev
    out = []
    for ev in events:
        if ev.get("recurrence_id") is not None:
            continue
        mine = overrides.get(ev.get("uid") or "", {})
        for s, e in occurrences(ev, win_start, win_end, day_tz):
            k = _key(s, day_tz)
            if k in mine:
                continue
            if ev.get("status") != "CANCELLED":
                out.append({**ev, "start": s, "end": e, "instance": k})
    for uid, by_key in overrides.items():
        for k, ov in by_key.items():
            if ov.get("status") == "CANCELLED":
                continue
            if as_utc(ov["end"], day_tz) > win_start and as_utc(ov["start"], day_tz) < win_end:
                out.append({**ov, "instance": k})
    out.sort(key=lambda x: as_utc(x["start"], day_tz))
    return out


# ───────────────────────── building ─────────────────────────

def escape(value) -> str:
    s = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _param(value: str) -> str:
    v = re.sub(r'[\x00-\x1f"]', "", str(value or "")).strip()
    return f'"{v}"' if re.search(r"[:;,]", v) else v


def fold(line: str) -> str:
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    parts, cur, size = [], "", 0
    for ch in line:
        n = len(ch.encode("utf-8"))
        if size + n > (75 if not parts else 74):
            parts.append(cur)
            cur, size = "", 0
        cur += ch
        size += n
    parts.append(cur)
    return "\r\n ".join(parts)


def fmt_utc(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def fmt_date(value: date) -> str:
    return value.strftime("%Y%m%d")


def person_line(kind: str, person: dict, partstat: str | None = None, rsvp: bool = False) -> str:
    params = []
    if person.get("name"):
        params.append("CN=" + _param(person["name"]))
    if kind == "ATTENDEE":
        params.append("ROLE=" + (person.get("role") or "REQ-PARTICIPANT"))
        params.append("PARTSTAT=" + (partstat or person.get("status") or "NEEDS-ACTION"))
        if rsvp:
            params.append("RSVP=TRUE")
    head = kind + "".join(";" + p for p in params)
    return f"{head}:mailto:{person['email']}"


def build(method: str, ev: dict, dtstamp: datetime, prodid: str = "-//TooPowerInbox//Calendar//EN") -> str:
    """One VEVENT in a VCALENDAR. ev: uid, sequence, title, start, end, all_day, location, description,
    organizer {email, name}, attendees [{email, name, status, role}], rrule_raw, reply_as (REPLY only)."""
    method = method.upper()
    if method not in ("REQUEST", "CANCEL", "REPLY", "PUBLISH"):
        raise IcsError("method must be REQUEST, CANCEL, REPLY or PUBLISH")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{prodid}", "CALSCALE:GREGORIAN", f"METHOD:{method}",
             "BEGIN:VEVENT", f"UID:{ev['uid']}", f"DTSTAMP:{fmt_utc(dtstamp)}", f"SEQUENCE:{int(ev.get('sequence') or 0)}"]
    if ev.get("all_day"):
        lines += [f"DTSTART;VALUE=DATE:{fmt_date(ev['start'])}", f"DTEND;VALUE=DATE:{fmt_date(ev['end'])}"]
    else:
        lines += [f"DTSTART:{fmt_utc(ev['start'])}", f"DTEND:{fmt_utc(ev['end'])}"]
    if ev.get("rrule_raw") and method != "REPLY":
        lines.append("RRULE:" + re.sub(r"[^A-Z0-9=;,+\-]", "", ev["rrule_raw"].upper()))
    lines.append("SUMMARY:" + escape(ev.get("title") or ""))
    if ev.get("location"):
        lines.append("LOCATION:" + escape(ev["location"]))
    if ev.get("description") and method != "REPLY":
        lines.append("DESCRIPTION:" + escape(ev["description"]))
    if ev.get("organizer") and ev["organizer"].get("email"):
        lines.append(person_line("ORGANIZER", ev["organizer"]))
    if method == "REPLY":
        me = ev["reply_as"]
        lines.append(person_line("ATTENDEE", me, partstat=me["status"]))
    else:
        for a in ev.get("attendees") or []:
            lines.append(person_line("ATTENDEE", a, rsvp=method == "REQUEST"))
    lines.append("STATUS:" + ("CANCELLED" if method == "CANCEL" else "CONFIRMED"))
    lines.append("TRANSP:" + ("TRANSPARENT" if ev.get("transp") == "TRANSPARENT" else "OPAQUE"))
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(fold(ln) for ln in lines) + "\r\n"
