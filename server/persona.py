"""Know-you-better persona: built from mail + optional seed, stored in the vault."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from yhbmail import FIXTURE, ROOT, brain_board, list_emails, load_cfg, now_iso

PERSONA_PATH = ROOT / "vault" / "persona.json"


def _seed() -> dict:
    if FIXTURE.exists():
        data = json.loads(FIXTURE.read_text())
        return data.get("persona_seed") or {}
    return {}


def rebuild() -> dict:
    emails = list_emails(limit=200)
    board = brain_board(720)
    senders = Counter()
    cats = Counter()
    for e in emails:
        senders[(e.get("from_addr") or "unknown").split("<")[-1].strip("> ")] += 1
        cats[e.get("category") or "fyi"] += 1
    seed = _seed()
    cfg = load_cfg()
    persona = {
        "updated_at": now_iso(),
        "mode": cfg.get("mode") or "demo",
        "identity": {
            "name": seed.get("name") or "You",
            "role": seed.get("role") or "Inbox owner",
            "timezone": seed.get("timezone") or "local",
            "accounts": [a.get("email") for a in (cfg.get("accounts") or [])],
        },
        "how_you_write": seed.get("how_you_write") or [
            "Learned from sent mail once a live driver is connected.",
        ],
        "how_you_run_inbox": seed.get("how_you_run_inbox") or [
            "Needs-you items first, then money, then the rest.",
        ],
        "attention_now": seed.get("attention_now") or [
            t["text"] for t in (board["todos"].get("needs_you") or [])[:4]
        ],
        "inbox_priorities": [
            {"category": k, "count": cats.get(k, 0)}
            for k in ("needs_you", "upcoming", "worth_a_look", "fyi", "other")
        ],
        "top_senders": [{"email": e, "count": n} for e, n in senders.most_common(8)],
        "facts_learned": len(emails) + len(seed.get("how_you_write") or []),
        "source": "demo-seed+local-mail" if seed else "local-mail",
    }
    PERSONA_PATH.parent.mkdir(parents=True, exist_ok=True)
    PERSONA_PATH.write_text(json.dumps(persona, ensure_ascii=False, indent=2))
    md = [
        f"# Know you better",
        f"",
        f"Updated {persona['updated_at']}",
        f"",
        f"## Identity",
        f"- {persona['identity']['name']} · {persona['identity']['role']}",
        f"",
        f"## How you write",
        *[f"- {x}" for x in persona["how_you_write"]],
        f"",
        f"## How you run the inbox",
        *[f"- {x}" for x in persona["how_you_run_inbox"]],
        f"",
        f"## Attention now",
        *[f"- {x}" for x in persona["attention_now"]],
        f"",
        f"## Top senders",
        *[f"- {s['email']} ({s['count']})" for s in persona["top_senders"]],
        f"",
    ]
    (ROOT / "vault" / "persona.md").write_text("\n".join(md))
    return persona


def load() -> dict:
    if PERSONA_PATH.exists():
        return json.loads(PERSONA_PATH.read_text())
    return rebuild()
