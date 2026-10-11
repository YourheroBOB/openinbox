"""Per-mail summaries: heuristic without an LLM (and labelled so), BYO agent when wired."""
from __future__ import annotations

import json
import sys
import unittest

import _tpi_server as srv
import features.triage as triage

AGENT_PATH = srv.ROOT / "agent.json"


def use_cli_agent(test: unittest.TestCase, script: str) -> None:
    AGENT_PATH.write_text(json.dumps({"driver": "cli", "cli": {"command": [sys.executable, "-c", script],
                                                               "timeout_sec": 20}}))
    test.addCleanup(lambda: AGENT_PATH.unlink(missing_ok=True))


def all_items(data):
    return [i for lane in data["lanes"] for i in lane["items"]]


def forget_agent_summaries() -> None:
    con = srv.yhbmail.db()
    con.execute("DELETE FROM agent_turns WHERE skill LIKE 'triage:%'")
    con.commit()
    con.close()


class HeuristicSummaryTest(unittest.TestCase):
    def setUp(self):
        AGENT_PATH.unlink(missing_ok=True)
        forget_agent_summaries()
        srv.reseed()

    def test_every_item_has_heuristic_summary(self):
        _, data = srv.get("/api/triage")
        self.assertFalse(data["llm"])
        self.assertEqual(data["agent_driver"], "local")
        items = all_items(data)
        self.assertEqual(len(items), srv.N_EMAILS)
        for it in items:
            self.assertTrue(it["summary"].strip(), it["id"])
            self.assertEqual(it["summary_source"], "heuristic")
            self.assertEqual(it["summary_label"], "Heuristic summary (no LLM)")
        self.assertEqual(data["summary_sources"], {"agent": 0, "heuristic": srv.N_EMAILS})

    def test_label_in_chinese(self):
        _, data = srv.get("/api/triage?lang=zh-Hant")
        self.assertEqual(all_items(data)[0]["summary_label"], "規則摘要（未接 LLM）")

    def test_summary_is_extractive(self):
        by_id = {e["id"]: e for e in srv.FIXTURE["emails"]}
        _, data = srv.get("/api/triage")
        for it in all_items(data):
            body = by_id[it["id"]]["body_text"]
            text = it["summary"].split(": ", 1)[1]
            core = text.split(" (", 1)[0]
            for sentence in core.split(". "):
                self.assertIn(sentence.strip(" ."), body, it["id"])

    def test_deadline_and_amount_copied_verbatim(self):
        _, data = srv.get("/api/triage")
        items = {i["id"].rsplit(":", 1)[-1]: i for i in all_items(data)}
        self.assertIn("deadline: by 17:00 Friday", items["m1"]["summary"])
        self.assertIn("amount: USD 42.00", items["m3"]["summary"])
        self.assertIn("date: 2026-09-20", items["m8"]["summary"])
        self.assertIn("when: Thursday 16:00", items["m4"]["summary"])
        self.assertTrue(items["m1"]["summary"].startswith("Samira Ortiz: "))
        self.assertNotIn("Alex —", items["m1"]["summary"])
        self.assertIn("Can you mark which one you will concede?", items["m7"]["summary"])

    def test_heuristic_handles_edge_cases(self):
        row = {"from_addr": "pat@studio.example", "subject": "Hello", "body_text": "", "snippet": "", "category": "fyi"}
        self.assertEqual(triage.heuristic_summary(row), "pat@studio.example: Hello")
        row = {"from_addr": "Pat <pat@studio.example>", "category": "fyi", "subject": "x",
               "body_text": "Hi Alex,\nThe draft is ready for you.\n> quoted old text that should vanish\n--\nPat"}
        out = triage.heuristic_summary(row)
        self.assertEqual(out, "Pat: The draft is ready for you.")
        row["body_text"] = "您好，\n合約草稿已備妥，請於 10月3日 前回覆。"
        out = triage.heuristic_summary(row, "zh-Hant")
        self.assertTrue(out.startswith("Pat："), out)
        self.assertIn("10月3日", out)
        long_row = {"from_addr": "a@b.example", "category": "fyi", "body_text": "word " * 200}
        self.assertLess(len(triage.heuristic_summary(long_row)), 200)

    def test_summarize_without_llm_says_so(self):
        status, data = srv.post("/api/triage/summarize", {"lang": "en"})
        self.assertEqual(status, 200)
        self.assertTrue(data["heuristic"])
        self.assertEqual(data["driver"], "local")
        self.assertIn("No LLM", data["note"])
        _, zh = srv.post("/api/triage/summarize", {"lang": "zh-Hant"})
        self.assertIn("未接 LLM", zh["note"])

    def test_summaries_endpoint_for_mail_list(self):
        ids = [e["id"] for e in srv.FIXTURE["emails"]][:3] + ["missing"]
        status, data = srv.post("/api/triage/summaries", {"ids": ids})
        self.assertEqual(status, 200)
        self.assertEqual(sorted(data["summaries"]), sorted(ids[:3]))
        one = data["summaries"][ids[2]]
        self.assertTrue(one["has_attachment"])
        self.assertEqual(one["summary_source"], "heuristic")
        self.assertEqual(srv.post("/api/triage/summaries", {"ids": "x"})[0], 400)
        self.assertEqual(srv.post("/api/triage/summaries", {})[1], {"summaries": {}})


class AgentSummaryTest(unittest.TestCase):
    def setUp(self):
        forget_agent_summaries()
        srv.reseed()
        self.addCleanup(forget_agent_summaries)

    def test_byo_agent_summary_replaces_heuristic(self):
        use_cli_agent(self, "import sys; p = sys.stdin.read(); "
                            "print('AGENT says: Northwind wants a yes/no' if 'three slides' in p else 'AGENT other')")
        target = "demo:you@example.com:m1"
        _, before = srv.get("/api/triage")
        self.assertTrue(before["llm"])
        self.assertEqual(before["agent_driver"], "cli")
        status, out = srv.post("/api/triage/summarize", {"ids": [target, "nope"], "lang": "en"})
        self.assertEqual(status, 200)
        self.assertFalse(out["heuristic"])
        self.assertEqual(out["results"][0]["summary"], "AGENT says: Northwind wants a yes/no")
        self.assertEqual(out["results"][1]["error"], "not found")
        self.assertIn("1/2", out["note"])
        _, data = srv.get("/api/triage")
        item = next(i for i in all_items(data) if i["id"] == target)
        self.assertEqual(item["summary"], "AGENT says: Northwind wants a yes/no")
        self.assertEqual(item["summary_source"], "agent")
        self.assertEqual(item["summary_label"], "AI summary · cli")
        others = [i for i in all_items(data) if i["id"] != target]
        self.assertTrue(all(i["summary_source"] == "heuristic" for i in others))
        _, zh = srv.get("/api/triage?lang=zh-Hant")
        self.assertEqual(next(i for i in all_items(zh) if i["id"] == target)["summary_source"], "heuristic",
                         "summaries are cached per language")

    def test_summarize_by_lane(self):
        use_cli_agent(self, "import sys; sys.stdin.read(); print('lane summary')")
        _, out = srv.post("/api/triage/summarize", {"lane": "other", "lang": "en"})
        self.assertEqual(sorted(r["id"].rsplit(":", 1)[-1] for r in out["results"]), ["m5", "m6"])

    def test_agent_failure_keeps_heuristic(self):
        use_cli_agent(self, "import sys; sys.stdin.read(); sys.exit('agent down')")
        _, out = srv.post("/api/triage/summarize", {"ids": ["demo:you@example.com:m2"]})
        self.assertFalse(out["ok"])
        self.assertIn("agent down", out["results"][0]["error"])
        _, data = srv.get("/api/triage")
        item = next(i for i in all_items(data) if i["id"] == "demo:you@example.com:m2")
        self.assertEqual(item["summary_source"], "heuristic")

    def test_agent_summary_cleared_with_local_cache(self):
        use_cli_agent(self, "import sys; sys.stdin.read(); print('cached agent text')")
        srv.post("/api/triage/summarize", {"ids": ["demo:you@example.com:m3"]})
        self.assertIn("demo:you@example.com:m3", triage.cached_agent_summaries(["demo:you@example.com:m3"], "en"))
        srv.post("/api/cache/clear", {"reseed": True})
        self.assertEqual(triage.cached_agent_summaries(["demo:you@example.com:m3"], "en"), {})

    def test_summarize_validates_ids(self):
        self.assertEqual(srv.post("/api/triage/summarize", {"ids": "m1"})[0], 400)


if __name__ == "__main__":
    unittest.main()
