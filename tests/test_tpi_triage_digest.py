"""Other lane rolled into a newsletter / promotion digest."""
from __future__ import annotations

import json
import sys
import unittest

import _tpi_server as srv

AGENT_PATH = srv.ROOT / "agent.json"


class DigestTest(unittest.TestCase):
    def setUp(self):
        AGENT_PATH.unlink(missing_ok=True)
        srv.reseed()

    def test_digest_groups_other_lane(self):
        status, d = srv.get("/api/triage/digest?lang=en")
        self.assertEqual(status, 200)
        self.assertEqual(d["total"], 2)
        self.assertEqual(d["senders"], 2)
        kinds = {g["sender"]: g["kind"] for g in d["groups"]}
        self.assertEqual(kinds, {"Kickstart Go": "promotion", "Linear Changelog": "newsletter"})
        self.assertEqual((d["newsletters"], d["promotions"], d["unread"]), (1, 1, 1))
        self.assertEqual(d["headline"], "2 bulk emails from 2 senders (1 newsletter, 1 promotion; 1 unread)")
        self.assertEqual(d["source"], "heuristic")
        self.assertEqual(d["source_label"], "Heuristic summary (no LLM)")
        self.assertTrue(d["markdown"].startswith("# Newsletter digest"))
        self.assertIn("## Linear Changelog · newsletter · 1", d["markdown"])
        self.assertIn("- Weekly product changelog — Loops for product management.", d["markdown"])
        _, lanes = srv.get("/api/triage")
        other = next(lane for lane in lanes["lanes"] if lane["id"] == "other")
        self.assertEqual(sorted(i["id"] for g in d["groups"] for i in g["items"]),
                         sorted(i["id"] for i in other["items"]))

    def test_digest_in_chinese(self):
        _, d = srv.get("/api/triage/digest?lang=zh-Hant")
        self.assertEqual(d["headline"], "2 封電子報／廣告，來自 2 個寄件者（電子報 1、廣告 1；未讀 1）")
        self.assertTrue(d["markdown"].startswith("# 電子報摘要"))
        self.assertIn("· 廣告 ·", d["markdown"])

    def test_same_sender_grouped(self):
        con = srv.yhbmail.db()
        srv.yhbmail.upsert_email(con, {
            "id": "demo:you@example.com:t-news2", "account": "you@example.com",
            "subject": "Weekly product changelog #2", "from_addr": "Linear Changelog <changelog@updates.example>",
            "body_text": "Two more features shipped. Unsubscribe at the bottom.", "date_raw": "2026-09-17 11:00",
            "unread": True})
        con.commit()
        con.close()
        try:
            _, d = srv.get("/api/triage/digest")
            group = next(g for g in d["groups"] if g["sender_email"] == "changelog@updates.example")
            self.assertEqual(group["count"], 2)
            self.assertEqual(d["groups"][0]["sender"], "Linear Changelog", "largest group first")
        finally:
            con = srv.yhbmail.db()
            con.execute("DELETE FROM emails WHERE id='demo:you@example.com:t-news2'")
            con.commit()
            con.close()

    def test_empty_digest(self):
        _, d = srv.get("/api/triage/digest?account=nobody@example.com")
        self.assertEqual(d["total"], 0)
        self.assertEqual(d["groups"], [])
        self.assertEqual(d["headline"], "Nothing in Other right now.")

    def test_post_digest_logs_history(self):
        status, d = srv.post("/api/triage/digest", {"lang": "en"})
        self.assertEqual(status, 200)
        self.assertEqual(d["source"], "heuristic")
        _, hist = srv.get("/api/triage/history?limit=1")
        self.assertEqual(hist["history"][0]["event"], "digest")
        self.assertEqual(hist["history"][0]["text"], "Digest generated · heuristic 2")

    def test_digest_with_byo_agent(self):
        AGENT_PATH.write_text(json.dumps({"driver": "cli", "cli": {"command": [
            sys.executable, "-c", "import sys; p = sys.stdin.read(); print('- agent bullet' if 'Kickstart Go' in p else 'x')"]}}))
        self.addCleanup(lambda: AGENT_PATH.unlink(missing_ok=True))
        _, d = srv.post("/api/triage/digest", {"lang": "en"})
        self.assertEqual(d["source"], "agent")
        self.assertEqual(d["agent_text"], "- agent bullet")
        self.assertEqual(d["source_label"], "AI summary · cli")
        self.assertEqual(d["total"], 2)


if __name__ == "__main__":
    unittest.main()
