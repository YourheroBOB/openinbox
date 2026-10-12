"""F14 Email Brain → drafts: fixes reach the AI Write prompt and the rule-based draft right away."""
from __future__ import annotations

import unittest

import _tpi_server as srv
import features.compose as compose
from _tpi_brain_util import M1, M4, BrainCase, use_echo_agent


def prompt(**q) -> str:
    qs = "&".join(f"{k}={v}" for k, v in q.items())
    status, data = srv.get("/api/brain/prompt?" + qs)
    assert status == 200, data
    return data["text"]


class PromptBlockTest(BrainCase):
    def test_inferred_block_names_recipient_and_project(self):
        text = prompt(item_id=M1)
        self.assertTrue(text.startswith("About the user (Email Brain;"))
        self.assertIn("name: Alex Chen; role: Founder; organization: Quillmark Labs; timezone: Asia/Taipei", text)
        self.assertIn("opening: “Hi”; sign-off: “Best,”", text)
        self.assertIn("- Recipient: Samira Ortiz <samira@northwind.example>, relationship: Investor", text)
        self.assertIn("- Related project: Northwind (Active)", text)
        self.assertIn("- Working hours: 09:00–18:00 Mon–Fri", text)
        self.assertNotIn("corrected by the user", text)
        self.assertEqual(srv.get("/api/brain/prompt?item_id=nope")[0], 404)

    def test_chinese_block_drops_english_only_opening(self):
        text = prompt(item_id=M1, lang="zh-Hant")
        self.assertTrue(text.startswith("關於使用者（Email Brain；"))
        self.assertIn("收件者：Samira Ortiz <samira@northwind.example>，關係：投資人", text)
        self.assertIn("相關專案：Northwind（進行中）", text)
        self.assertNotIn("「Hi」", text)

    def test_fixes_are_marked_in_the_block(self):
        self.fix({"section": "contacts", "key": "samira@northwind.example", "relationship": "client",
                  "note": "Prefers bullet points"})
        self.fix({"section": "projects", "key": "northwind", "name": "Seed round"})
        self.fix({"section": "work_patterns", "key": "active_hours", "value": "10:00-16:00"})
        self.fix({"section": "tone", "key": "rules", "value": "No exclamation marks\nOne question per email"})
        text = prompt(item_id=M1)
        self.assertIn("relationship: Client (corrected by the user). Note: Prefers bullet points", text)
        self.assertIn("- Related project: Seed round (Active) (corrected by the user)", text)
        self.assertIn("10:00–16:00 (corrected by the user)", text)
        self.assertIn("Writing rules (corrected by the user): No exclamation marks / One question per email", text)
        zh = prompt(item_id=M1, lang="zh-Hant")
        self.assertIn("關係：客戶（使用者已修正）", zh)

    def test_hidden_contact_is_left_out(self):
        self.fix({"section": "contacts", "key": "samira@northwind.example", "hidden": True})
        text = prompt(item_id=M1)
        self.assertNotIn("Samira", text)


class AiWriteTest(BrainCase):
    def test_write_prompt_carries_the_fix_immediately(self):
        before = compose.write_prompt("reply", M1, "", "balanced", "en", "", "", "")
        self.assertIn("relationship: Investor", before)
        self.assertTrue(before.endswith("Reply with the email body only."))
        self.fix({"section": "contacts", "key": "samira@northwind.example", "relationship": "client"})
        after = compose.write_prompt("reply", M1, "", "balanced", "en", "", "", "")
        self.assertIn("relationship: Client (corrected by the user)", after)
        self.assertNotIn("relationship: Investor", after)
        self.assertTrue(after.endswith("Reply with the email body only."))

    def test_byo_agent_receives_the_corrected_profile(self):
        use_echo_agent(self)
        self.fix({"section": "identity", "key": "role", "value": "Chief operator"})
        self.fix({"section": "tone", "key": "formality", "value": "formal"})
        status, w = srv.post("/api/compose/write", {"kind": "reply", "item_id": M4})
        self.assertEqual((status, w["source"]), (200, "agent"))
        self.assertIn("role: Chief operator (corrected by the user)", w["text"])
        self.assertIn("formality: Formal (corrected by the user)", w["text"])
        self.assertIn("- Recipient: Maya Singh <maya@studio.example>, relationship: Collaborator", w["text"])
        self.assertIn("- Related project: Design review (Active)", w["text"])

    def test_rule_based_draft_uses_fixed_signoff_greeting_and_name(self):
        _, w = srv.post("/api/compose/write", {"kind": "reply", "item_id": M1, "style": "balanced"})
        self.assertEqual(w["source"], "heuristic")
        self.assertTrue(w["text"].startswith("Hi Samira,"), w["text"])
        self.assertTrue(w["text"].rstrip().endswith("Best,\nAlex"), w["text"])
        self.fix({"section": "tone", "key": "signoff", "value": "Warm regards,"})
        self.fix({"section": "tone", "key": "greeting", "value": "Hello"})
        self.fix({"section": "identity", "key": "name", "value": "Sasha Chen"})
        _, w = srv.post("/api/compose/write", {"kind": "reply", "item_id": M1, "style": "balanced"})
        self.assertTrue(w["text"].startswith("Hello Samira,"), w["text"])
        self.assertTrue(w["text"].rstrip().endswith("Warm regards,\nSasha"), w["text"])
        _, zh = srv.post("/api/compose/write", {"kind": "reply", "item_id": M1, "style": "balanced", "lang": "zh-Hant"})
        self.assertNotIn("Warm regards", zh["text"], "an English sign-off fix leaves Chinese drafts alone")
        self.assertNotIn("Hello", zh["text"])

    def test_new_mail_to_a_fixed_contact(self):
        self.fix({"section": "contacts", "key": "jordan@quillmark.example", "relationship": "teammate",
                  "note": "Handles finance"})
        text = compose.write_prompt("new", "", "Ask about the renewal", "balanced", "en",
                                    "Jordan Lee <jordan@quillmark.example>", "Byte Cloud renewal", "")
        self.assertIn("Recipient: Jordan Lee <jordan@quillmark.example>, relationship: Teammate (corrected by the user). "
                      "Note: Handles finance", text)
        self.assertIn("- Related project: Byte Cloud (Active)", text)


if __name__ == "__main__":
    unittest.main()
