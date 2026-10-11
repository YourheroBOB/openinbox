"""Shared helpers for the compose tests: a clean slate and a fake BYO agent."""
from __future__ import annotations

import json
import sys
import unittest

import _tpi_server as srv

AGENT_PATH = srv.ROOT / "agent.json"
M1 = "demo:you@example.com:m1"
M4 = "demo:you@example.com:m4"
M7 = "demo:you@example.com:m7"


def reset() -> None:
    AGENT_PATH.unlink(missing_ok=True)
    con = srv.yhbmail.db()
    for table in ("drafts", "compose_settings", "compose_voice_samples"):
        con.execute(f"DELETE FROM {table}")
    con.execute("DELETE FROM agent_turns WHERE skill LIKE 'compose:%'")
    con.commit()
    con.close()
    srv.reseed()


def use_cli_agent(test: unittest.TestCase, script: str) -> None:
    AGENT_PATH.write_text(json.dumps({"driver": "cli", "cli": {"command": [sys.executable, "-c", script],
                                                               "timeout_sec": 20}}))
    test.addCleanup(lambda: AGENT_PATH.unlink(missing_ok=True))


class ComposeCase(unittest.TestCase):
    def setUp(self):
        srv.get("/api/compose/settings")
        reset()
