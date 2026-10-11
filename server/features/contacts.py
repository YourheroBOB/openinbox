"""Contacts (F12): everyone in the local mail cache, built from From / To headers.

    GET /api/contacts?q=&sort=frequent|recent|name&people=1&limit=
    GET /api/contacts/<email>          one contact plus their recent mail

Nothing is stored: the list is derived from the `emails` table on demand and
memoised until the cache changes. Your own mailbox addresses are left out, and
automated senders (noreply, newsletter, ...) are flagged so `people=1` can hide them.
"""
from __future__ import annotations

import re
from collections import Counter
from email.utils import getaddresses
from threading import Lock
from urllib.parse import unquote

import yhbmail
from features import get

SORTS = ("frequent", "recent", "name")
_memo: dict = {"sig": None, "contacts": []}
_lock = Lock()


def _int(value, default: int, lo: int = 1, hi: int = 1000) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def parse_addresses(raw: str) -> list[tuple[str, str]]:
    out = []
    for name, addr in getaddresses([raw or ""]):
        addr = (addr or "").strip().strip("<>").lower()
        if "@" not in addr:
            continue
        name = re.sub(r"\s+", " ", (name or "").strip().strip('"')).strip()
        out.append((name if name.lower() != addr else "", addr))
    return out


def own_addresses(con) -> set[str]:
    mine = {(r[0] or "").lower() for r in con.execute("SELECT DISTINCT account FROM emails")}
    for acc in yhbmail.load_cfg().get("accounts") or []:
        if acc.get("email"):
            mine.add(acc["email"].lower())
    return {m for m in mine if m}


def is_automated(addr: str) -> bool:
    return any(x in addr for x in yhbmail.NOISE_FROM)


def signature(con) -> tuple:
    return tuple(con.execute(
        "SELECT COUNT(*), MAX(synced_at), TOTAL(date_ts), TOTAL(LENGTH(from_addr) + LENGTH(to_addr)) FROM emails"
    ).fetchone())


def build(con) -> list[dict]:
    mine = own_addresses(con)
    book: dict[str, dict] = {}

    def entry(addr: str) -> dict:
        c = book.get(addr)
        if c is None:
            c = book[addr] = {
                "email": addr, "domain": addr.split("@", 1)[1], "names": Counter(),
                "received": 0, "cc": 0, "unread": 0, "attachments": 0,
                "first_ts": 0, "last_ts": 0, "last_date": "", "last_subject": "", "last_id": "",
                "categories": Counter(), "accounts": set(),
            }
        return c

    rows = con.execute(
        "SELECT id, account, from_addr, to_addr, date_raw, date_ts, unread, has_attachment, subject, category "
        "FROM emails ORDER BY date_ts")
    for r in rows:
        seen = set()
        for role, raw in (("from", r["from_addr"]), ("to", r["to_addr"])):
            for name, addr in parse_addresses(raw):
                if addr in mine or (addr, role) in seen:
                    continue
                seen.add((addr, role))
                c = entry(addr)
                if name:
                    c["names"][name] += 1
                c["accounts"].add(r["account"])
                if role == "from":
                    c["received"] += 1
                    c["unread"] += 1 if r["unread"] else 0
                    c["attachments"] += 1 if r["has_attachment"] else 0
                    c["categories"][r["category"] or "fyi"] += 1
                else:
                    c["cc"] += 1
                ts = r["date_ts"] or 0
                if ts and (not c["first_ts"] or ts < c["first_ts"]):
                    c["first_ts"] = ts
                if ts >= c["last_ts"]:
                    c["last_ts"], c["last_date"] = ts, r["date_raw"] or ""
                    c["last_subject"], c["last_id"] = r["subject"] or "", r["id"]
    out = []
    for c in book.values():
        names = [n for n, _ in c["names"].most_common()]
        name = names[0] if names else c["email"].split("@", 1)[0]
        out.append({
            "email": c["email"], "name": name, "aliases": names[1:5], "domain": c["domain"],
            "count": c["received"] + c["cc"], "received": c["received"], "cc": c["cc"],
            "unread": c["unread"], "attachments": c["attachments"],
            "first_ts": c["first_ts"], "last_ts": c["last_ts"], "last_date": c["last_date"],
            "last_subject": c["last_subject"], "last_id": c["last_id"],
            "categories": dict(c["categories"]), "accounts": sorted(c["accounts"]),
            "automated": is_automated(c["email"]),
            "search_query": f"from:{c['email']}",
        })
    return out


def all_contacts() -> list[dict]:
    con = yhbmail.db()
    try:
        sig = signature(con)
        with _lock:
            if _memo["sig"] != sig:
                _memo["contacts"] = build(con)
                _memo["sig"] = sig
            return list(_memo["contacts"])
    finally:
        con.close()


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def match_score(c: dict, q: str) -> int:
    """0 = no match. Higher is better: exact > prefix of a name word / address > substring."""
    q = _norm(q)
    if not q:
        return 1
    name, addr = _norm(c["name"]), c["email"]
    local = addr.split("@", 1)[0]
    hay = [name, *(_norm(a) for a in c["aliases"])]
    if q in (name, addr, local):
        return 100
    if any(h.startswith(q) for h in hay) or local.startswith(q) or addr.startswith(q):
        return 80
    if any(w.startswith(q) for h in hay for w in re.split(r"[\s._\-]+", h) if w):
        return 70
    if any(q in h for h in hay) or q in addr:
        return 50
    words = q.split()
    if len(words) > 1 and all(any(w in h for h in hay) or w in addr for w in words):
        return 40
    return 0


def search(q: str = "", sort: str = "frequent", people: bool = False, limit: int = 100) -> dict:
    contacts = all_contacts()
    if people:
        contacts = [c for c in contacts if not c["automated"]]
    scored = [(match_score(c, q), c) for c in contacts]
    scored = [(s, c) for s, c in scored if s > 0]
    if sort == "recent":
        key = lambda sc: (-sc[0] if q else 0, -sc[1]["last_ts"], sc[1]["name"].lower())
    elif sort == "name":
        key = lambda sc: (-sc[0] if q else 0, sc[1]["name"].lower(), sc[1]["email"])
    else:
        key = lambda sc: (-sc[0] if q else 0, -sc[1]["count"], -sc[1]["last_ts"], sc[1]["name"].lower())
    scored.sort(key=key)
    return {"contacts": [dict(c, score=s) for s, c in scored[:limit]], "total": len(scored),
            "q": q, "sort": sort, "people": people}


def resolve(candidate: str, min_score: int = 50, book: list[dict] | None = None) -> list[dict]:
    """Contacts that a sender word like "samira" or "王小明" plausibly refers to."""
    cand = _norm(candidate)
    if len(cand) < 2 and not re.search(r"[\u3400-\u9fff]", cand):
        return []
    hits = [(match_score(c, cand), c) for c in (all_contacts() if book is None else book)]
    return [c for s, c in sorted(hits, key=lambda sc: (-sc[0], -sc[1]["count"])) if s >= min_score]


def detail(addr: str, limit: int = 20) -> dict | None:
    addr = addr.strip().lower()
    c = next((c for c in all_contacts() if c["email"] == addr), None)
    if not c:
        return None
    like = "%" + addr.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    con = yhbmail.db()
    rows = [dict(r) for r in con.execute(
        "SELECT id, account, subject, snippet, from_addr, to_addr, date_raw, date_ts, unread, has_attachment, category "
        "FROM emails WHERE LOWER(from_addr) LIKE ? ESCAPE '\\' OR LOWER(to_addr) LIKE ? ESCAPE '\\' "
        "ORDER BY date_ts DESC LIMIT ?", (like, like, limit))]
    con.close()
    for r in rows:
        r["direction"] = "from" if any(a == addr for _, a in parse_addresses(r["from_addr"])) else "to"
        r["unread"], r["has_attachment"] = bool(r["unread"]), bool(r["has_attachment"])
    return {**c, "emails": rows}


@get("/api/contacts")
def contacts_list(req):
    sort = req.query.get("sort") or "frequent"
    if sort not in SORTS:
        return {"error": f"sort must be one of {', '.join(SORTS)}"}, 400
    people = str(req.query.get("people") or "").lower() in ("1", "true", "yes")
    return search(req.query.get("q") or "", sort, people, _int(req.query.get("limit"), 100))


@get("/api/contacts/*")
def contacts_detail(req):
    item = detail(unquote(req.params), _int(req.query.get("limit"), 20, hi=200))
    if not item:
        return {"error": "contact not found"}, 404
    return item
