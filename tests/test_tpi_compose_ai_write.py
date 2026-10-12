"""AI Write: drafts from thread context and style; heuristic without an LLM, BYO agent when wired."""
from __future__ import annotations

import json
import unittest

import _tpi_server as srv
from _tpi_compose_util import M1, M4, M7, ComposeCase, use_cli_agent


class HeuristicWriteTest(ComposeCase):
    def test_reply_uses_context_and_never_invents(self):
        status, r = srv.post("/api/compose/write", {"kind": "reply", "item_id": M1})
        self.assertEqual(status, 200)
        self.assertEqual((r["source"], r["driver"], r["label"]), ("heuristic", "local", "Heuristic draft (no LLM)"))
        text = r["text"]
        self.assertTrue(text.startswith("Hi Samira,"), text)
        self.assertIn("Noted the deadline: by 17:00 Friday.", text)
        self.assertIn("[TBD]", text)
        self.assertIn("“Reply with confirm or the two lines you want cut.”", text)
        self.assertTrue(text.rstrip().endswith("Best,\nAlex"), text)

    def test_instruction_becomes_the_core_point(self):
        _, r = srv.post("/api/compose/write", {"kind": "reply", "item_id": M1,
                                               "instruction": "confirm all three slides stay"})
        self.assertIn("Confirm all three slides stay.", r["text"])
        self.assertNotIn("[TBD]", r["text"])

    def test_chinese_reply(self):
        _, r = srv.post("/api/compose/write", {"kind": "reply", "item_id": M1, "lang": "zh-Hant"})
        self.assertEqual(r["label"], "規則草稿（未接 LLM）")
        self.assertTrue(r["text"].startswith("Samira 你好："), r["text"])
        self.assertIn("[待填]", r["text"])
        self.assertIn("已注意到期限：by 17:00 Friday。", r["text"])

    def test_new_mail_greets_recipient_and_suggests_subject(self):
        _, r = srv.post("/api/compose/write", {"kind": "new", "to": "maya@studio.example",
                                               "instruction": "can we move the design review to next Tuesday?"})
        self.assertEqual(r["text"], "Hi Maya,\n\nCan we move the design review to next Tuesday?\n\nBest,\nAlex")
        self.assertEqual(r["subject_suggestion"], "Can we move the design review to next Tuesday?")
        _, blank = srv.post("/api/compose/write", {"kind": "new"})
        self.assertIn("[TBD]", blank["text"])
        self.assertNotIn("subject_suggestion", blank)

    def test_forward_note(self):
        _, r = srv.post("/api/compose/write", {"kind": "forward", "item_id": M7, "to": "pat@studio.example",
                                               "lang": "zh-Hant", "instruction": "請幫忙看 pro-rata 條款"})
        self.assertIn("轉寄 Samira Ortiz 的「Northwind term sheet comments」給你參考。", r["text"])
        self.assertIn("請幫忙看 pro-rata 條款。", r["text"])
        self.assertTrue(r["text"].startswith("Pat 你好："))

    def test_validation(self):
        self.assertEqual(srv.post("/api/compose/write", {"kind": "reply"})[0], 400)
        self.assertEqual(srv.post("/api/compose/write", {"kind": "reply", "item_id": "nope"})[0], 404)
        self.assertEqual(srv.post("/api/compose/write", {"kind": "tweet"})[0], 400)
        self.assertEqual(srv.post("/api/compose/write", {"kind": "new", "style": "shouty"})[0], 400)


class AgentWriteTest(ComposeCase):
    def test_agent_gets_thread_style_and_persona(self):
        script = ("import sys, json; p = json.load(sys.stdin)['ask']; "
                  "ok = all(k in p for k in ('three slides', 'Professional', 'Decision first', 'move it to Monday')); "
                  "print('```\\nSubject: ignored\\n\\nDear Samira,\\n\\nAGENT ' + ('OK' if ok else 'MISSING') + '\\n```')")
        use_cli_agent(self, script)
        _, r = srv.post("/api/compose/write", {"kind": "reply", "item_id": M1, "style": "professional",
                                               "instruction": "move it to Monday"})
        self.assertEqual((r["source"], r["driver"], r["label"]), ("agent", "cli", "AI draft · cli"))
        self.assertEqual(r["text"], "Dear Samira,\n\nAGENT OK")

    def test_agent_failure_falls_back_to_heuristic(self):
        use_cli_agent(self, "import sys; sys.stdin.read(); sys.exit('agent down')")
        _, r = srv.post("/api/compose/write", {"kind": "reply", "item_id": M4})
        self.assertEqual(r["source"], "heuristic")
        self.assertIn("agent down", r["error"])
        self.assertTrue(r["text"].startswith("Hi Maya,"))

    def test_agent_prompt_is_chinese_for_zh(self):
        use_cli_agent(self, "import sys, json; p = json.load(sys.stdin)['ask']; "
                            "print('中文提示' if '請用繁體中文' in p and '[待填]' in p else 'english')")
        _, r = srv.post("/api/compose/write", {"kind": "new", "lang": "zh-Hant", "instruction": "約下週開會"})
        self.assertEqual(r["text"], "中文提示")

    def test_agent_turn_recorded_for_cache_clear(self):
        use_cli_agent(self, "import sys; sys.stdin.read(); print('hello')")
        srv.post("/api/compose/write", {"kind": "new", "instruction": "say hi"})
        con = srv.yhbmail.db()
        n = con.execute("SELECT COUNT(*) FROM agent_turns WHERE skill='compose:write'").fetchone()[0]
        con.close()
        self.assertEqual(n, 1)


if __name__ == "__main__":
    unittest.main()
