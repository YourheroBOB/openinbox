"""BYO agent query rewrite: optional, labelled, and never required for search to work."""
from __future__ import annotations

import json
import sys
import unittest

import _tpi_server as srv

AGENT_PATH = srv.ROOT / "agent.json"
M = "demo:you@example.com:"


def use_cli_agent(test: unittest.TestCase, script: str) -> None:
    AGENT_PATH.write_text(json.dumps({"driver": "cli", "cli": {"command": [sys.executable, "-c", script],
                                                               "timeout_sec": 20}}))
    test.addCleanup(lambda: AGENT_PATH.unlink(missing_ok=True))


def ids(data):
    return [e["id"].removeprefix(M) for e in data["emails"]]


class AgentRewriteTest(unittest.TestCase):
    def setUp(self):
        AGENT_PATH.unlink(missing_ok=True)
        srv.reseed()

    def test_local_driver_keeps_builtin_parser(self):
        status, d = srv.post("/api/search", {"q": "term sheet", "agent": True, "lang": "en"})
        self.assertEqual(status, 200)
        self.assertEqual(d["rewrite"]["driver"], "local")
        self.assertFalse(d["rewrite"]["used"])
        self.assertIn("No LLM wired", d["rewrite"]["note"])
        self.assertEqual(ids(d), ["m7"])
        _, zh = srv.post("/api/search", {"q": "term sheet", "agent": True, "lang": "zh-Hant"})
        self.assertIn("未接 LLM", zh["rewrite"]["note"])

    def test_no_rewrite_unless_asked(self):
        _, d = srv.post("/api/search", {"q": "term sheet"})
        self.assertNotIn("rewrite", d)

    def test_agent_rewrite_drives_the_search(self):
        use_cli_agent(self, (
            "import json, sys\n"
            "pack = json.loads(sys.stdin.read())\n"
            "ok = '2026-09-16' in pack['ask'] and 'design stuff Maya sent' in pack['ask'] and pack['mode'] == 'search_rewrite'\n"
            "print('```\\nquery: from:maya has:attachment\\n```' if ok else 'bad prompt')\n"))
        status, d = srv.post("/api/search", {"q": "design stuff Maya sent", "agent": True, "lang": "en"})
        self.assertEqual(status, 200)
        rw = d["rewrite"]
        self.assertTrue(rw["used"], rw)
        self.assertEqual((rw["driver"], rw["query"]), ("cli", "from:maya has:attachment"))
        self.assertIn("design", rw["heuristic"])
        self.assertEqual(d["canonical"], "from:maya has:attachment")
        self.assertEqual(ids(d), ["m4"])

    def test_agent_failure_falls_back(self):
        use_cli_agent(self, "import sys; sys.stdin.read(); sys.exit('agent down')")
        _, d = srv.post("/api/search", {"q": "term sheet", "agent": True, "lang": "zh-Hant"})
        self.assertFalse(d["rewrite"]["used"])
        self.assertIn("agent down", d["rewrite"]["error"])
        self.assertIn("改用內建規則解析", d["rewrite"]["note"])
        self.assertEqual(ids(d), ["m7"])

    def test_agent_empty_answer_is_an_error(self):
        use_cli_agent(self, "import sys; sys.stdin.read(); print('   ')")
        _, d = srv.post("/api/search", {"q": "term sheet", "agent": True})
        self.assertFalse(d["rewrite"]["used"])
        self.assertIn("empty", d["rewrite"]["error"])
        self.assertEqual(ids(d), ["m7"])

    def test_get_with_agent_flag(self):
        use_cli_agent(self, "import sys; sys.stdin.read(); print('newsletter -cables')")
        status, d = srv.get("/api/search?q=promo%20stuff&agent=1")
        self.assertEqual(status, 200)
        self.assertTrue(d["rewrite"]["used"])
        self.assertEqual(ids(d), ["m5"])


if __name__ == "__main__":
    unittest.main()
