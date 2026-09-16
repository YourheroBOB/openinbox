"""Second Brain: durable cards distilled from mail, calendar, and agent runs."""
from __future__ import annotations

import json
import re
from pathlib import Path

from yhbmail import ROOT, brain_board, list_events, now_iso

CARDS = ROOT / "vault" / "cards"
INDEX = ROOT / "vault" / "index.json"


def _slug(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", (text or "card").lower()).strip("-")
    return (s[:48] or "card")


def _write_card(card: dict) -> dict:
    CARDS.mkdir(parents=True, exist_ok=True)
    path = CARDS / f"{card['id']}.md"
    body = [
        f"# {card['title']}",
        f"",
        f"- kind: {card['kind']}",
        f"- category: {card.get('category') or ''}",
        f"- updated: {card['updated_at']}",
        f"",
        card.get("body") or "",
        f"",
    ]
    path.write_text("\n".join(body))
    card["path"] = str(path.relative_to(ROOT))
    return card


def rebuild() -> dict:
    board = brain_board(720)
    cards = []
    for cat in ("needs_you", "worth_a_look", "upcoming"):
        for item in board["todos"].get(cat) or []:
            cid = _slug(item.get("id") or item.get("text"))
            card = {
                "id": cid,
                "title": item.get("text") or cid,
                "kind": item.get("kind") or "mail",
                "category": cat,
                "source_id": item.get("id"),
                "updated_at": now_iso(),
                "body": "\n".join([
                    item.get("summary") or "",
                    f"From: {item.get('from_addr') or ''}",
                    f"Why: {item.get('flag_reason') or ''}",
                ]).strip(),
            }
            cards.append(_write_card(card))
    for ev in list_events():
        cid = _slug(f"cal-{ev.get('id')}")
        cards.append(_write_card({
            "id": cid,
            "title": ev.get("title") or cid,
            "kind": "calendar",
            "category": "upcoming",
            "source_id": ev.get("id"),
            "updated_at": now_iso(),
            "body": f"{ev.get('start_local')} → {ev.get('end_local')}",
        }))
    # de-dupe by id, keep last
    uniq = {c["id"]: c for c in cards}
    cards = list(uniq.values())
    INDEX.write_text(json.dumps({"updated_at": now_iso(), "count": len(cards), "cards": cards},
                                ensure_ascii=False, indent=2))
    return {"updated_at": now_iso(), "count": len(cards), "cards": cards}


def load() -> dict:
    if INDEX.exists():
        return json.loads(INDEX.read_text())
    return rebuild()


def search(q: str) -> list[dict]:
    q = (q or "").lower()
    cards = load().get("cards") or []
    if not q:
        return cards
    hits = []
    for c in cards:
        blob = f"{c.get('title')} {c.get('body')} {c.get('category')}".lower()
        if q in blob:
            hits.append(c)
    return hits


def add_card(title: str, body: str, kind: str = "note") -> dict:
    card = {
        "id": _slug(title),
        "title": title,
        "kind": kind,
        "category": "note",
        "updated_at": now_iso(),
        "body": body,
    }
    card = _write_card(card)
    data = load()
    data["cards"] = [c for c in (data.get("cards") or []) if c["id"] != card["id"]] + [card]
    data["count"] = len(data["cards"])
    data["updated_at"] = now_iso()
    INDEX.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return card
