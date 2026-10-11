"""Local cache: inspect and clear the mail cache kept on this machine.

Cleared: cached mail, calendar events, agent turns, and everything derived from
them (persona, second-brain index, mail/calendar cards). Kept: local drafts and
the note cards you wrote yourself. Nothing remote is touched.
"""
from __future__ import annotations

import re

import persona
import second_brain
import yhbmail
from features import get, post

CACHE_TABLES = ("emails", "events", "agent_turns")
KIND_LINE = re.compile(r"^- kind:\s*(\S+)\s*$", re.M)


def _derived_files() -> list:
    vault = yhbmail.ROOT / "vault"
    return [vault / "index.json", vault / "persona.json", vault / "persona.md"]


def _derived_cards() -> list:
    cards = []
    if second_brain.CARDS.is_dir():
        for p in sorted(second_brain.CARDS.glob("*.md")):
            m = KIND_LINE.search(p.read_text(errors="replace"))
            if not m or m.group(1) != "note":
                cards.append(p)
    return cards


def _rel(p) -> str:
    try:
        return str(p.relative_to(yhbmail.ROOT))
    except ValueError:
        return str(p)


def stats() -> dict:
    con = yhbmail.db()
    rows = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in CACHE_TABLES + ("drafts",)}
    con.close()
    return {
        "db": _rel(yhbmail.DB),
        "db_bytes": yhbmail.DB.stat().st_size if yhbmail.DB.exists() else 0,
        "cached": {t: rows[t] for t in CACHE_TABLES},
        "kept": {"drafts": rows["drafts"]},
        "derived_files": [_rel(p) for p in _derived_files() if p.exists()],
        "derived_cards": len(_derived_cards()),
    }


def clear(reseed: bool = False) -> dict:
    con = yhbmail.db()
    cleared = {}
    for t in CACHE_TABLES:
        cleared[t] = con.execute(f"DELETE FROM {t}").rowcount
    con.commit()
    con.execute("VACUUM")
    con.close()
    removed = []
    for p in _derived_files() + _derived_cards():
        if p.exists():
            p.unlink()
            removed.append(_rel(p))
    cleared["files"] = removed
    reseeded = False
    if reseed and (yhbmail.load_cfg().get("mode") or "demo") == "demo":
        yhbmail.seed_demo()
        persona.rebuild()
        second_brain.rebuild()
        reseeded = True
    return {"cleared": cleared, "reseeded": reseeded}


@get("/api/cache")
def cache_stats(req):
    return stats()


@post("/api/cache/clear")
def cache_clear(req):
    out = clear(reseed=bool(req.body.get("reseed")))
    if req.lang_zh():
        note = "本機快取已清除；草稿與你自己寫的筆記卡保留。按「同步」重新抓信。"
    else:
        note = "Local cache cleared; drafts and your own note cards are kept. Hit Sync to fetch mail again."
    return {"ok": True, **out, "kept": stats()["kept"], "note": note}
