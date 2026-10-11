"""Shared helpers for the Email Brain tests: a clean slate before and after every test."""
from __future__ import annotations

import json
import sys
import unittest

import _tpi_server as srv

AGENT_PATH = srv.ROOT / "agent.json"
PERSONA = srv.ROOT / "vault" / "persona.json"
PERSONA_MD = srv.ROOT / "vault" / "persona.md"
M1 = "demo:you@example.com:m1"
M4 = "demo:you@example.com:m4"
M7 = "demo:you@example.com:m7"


def reset() -> None:
    AGENT_PATH.unlink(missing_ok=True)
    srv.get("/api/brain/fixes")
    con = srv.yhbmail.db()
    con.execute("DELETE FROM brain_fixes")
    con.commit()
    con.close()
    srv.reseed()


def use_echo_agent(test: unittest.TestCase) -> None:
    """A BYO CLI agent that answers with the prompt it was given."""
    script = "import json,sys; print(json.loads(sys.stdin.read())['ask'])"
    AGENT_PATH.write_text(json.dumps({"driver": "cli", "cli": {"command": [sys.executable, "-c", script],
                                                               "timeout_sec": 20}}))
    test.addCleanup(lambda: AGENT_PATH.unlink(missing_ok=True))


def section(profile: dict, sid: str) -> list[dict]:
    return next(s["items"] for s in profile["sections"] if s["id"] == sid)


def by_key(profile: dict, sid: str) -> dict:
    return {i["key"]: i for i in section(profile, sid)}


def profile(lang: str = "en") -> dict:
    status, data = srv.get(f"/api/brain/profile?lang={lang}")
    assert status == 200, data
    return data


class BrainCase(unittest.TestCase):
    def setUp(self):
        reset()
        self.addCleanup(reset)

    def fix(self, body: dict, status: int = 200) -> dict:
        got, data = srv.post("/api/brain/fix", body)
        self.assertEqual(got, status, data)
        return data
