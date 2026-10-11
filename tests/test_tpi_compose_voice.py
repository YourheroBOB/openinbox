"""Learn the user's voice from edited AI drafts; samples are stored in the persona."""
from __future__ import annotations

import json
import unittest

import _tpi_server as srv
import features.compose as compose
from _tpi_compose_util import M1, M4, M7, ComposeCase, use_cli_agent

PERSONA = srv.ROOT / "vault" / "persona.json"


def ai_then_edit(item_id: str, final: str, draft_id=None):
    _, w = srv.post("/api/compose/write", {"kind": "reply", "item_id": item_id})
    body = {"kind": "reply", "source_id": item_id, "to": "samira@northwind.example", "text": final, "ai_body": w["text"]}
    if draft_id:
        body["id"] = draft_id
    return srv.post("/api/compose/draft", body)[1]


class LearnTest(ComposeCase):
    def test_edited_ai_draft_becomes_a_voice_sample(self):
        r = ai_then_edit(M1, "Hi Samira,\n\nConfirmed: keep all three slides.\n\nThanks,\nAlex")
        self.assertTrue(r["learned"]["learned"])
        self.assertEqual(r["learned"]["samples"], 1)
        _, v = srv.get("/api/compose/voice")
        self.assertEqual(v["samples"], 1)
        en = v["by_lang"]["en"]
        self.assertEqual((en["greeting"], en["signoff"], en["length_bias"]), ("", "Thanks,", "shorter"),
                         "the kept 'Hi' opening is not a habit; the changed sign-off is")
        self.assertEqual(v["recent"][0]["final"], "Hi Samira,\n\nConfirmed: keep all three slides.\n\nThanks,\nAlex")
        self.assertIn("Signs off with “Thanks,”.", v["traits_en"])
        self.assertIn("結尾習慣用「Thanks,」（英文信）。", v["traits_zh"])

    def test_unchanged_or_missing_ai_text_is_not_a_sample(self):
        _, w = srv.post("/api/compose/write", {"kind": "reply", "item_id": M1})
        _, r = srv.post("/api/compose/draft", {"kind": "reply", "source_id": M1, "text": w["text"], "ai_body": w["text"]})
        self.assertEqual(r["learned"], {"learned": False, "reason": "unchanged", "ratio": 1.0})
        _, r = srv.post("/api/compose/draft", {"kind": "new", "text": "my own words", "to": "pat@studio.example"})
        self.assertFalse(r["learned"]["learned"])
        self.assertEqual(srv.get("/api/compose/voice")[1]["samples"], 0)

    def test_resaving_a_draft_updates_its_sample(self):
        r = ai_then_edit(M1, "Hi Samira,\n\nYes.\n\nThanks,\nAlex")
        r2 = ai_then_edit(M1, "Hi Samira,\n\nYes, all three.\n\nThanks,\nAlex", draft_id=r["draft"]["id"])
        self.assertTrue(r2["learned"]["updated"])
        self.assertEqual(r2["learned"]["sample_id"], r["learned"]["sample_id"])
        self.assertEqual(srv.get("/api/compose/voice")[1]["samples"], 1)

    def test_samples_are_written_into_persona_and_survive_rebuild_and_cache_clear(self):
        ai_then_edit(M1, "Hi Samira,\n\nConfirmed.\n\nThanks,\nAlex")
        p = json.loads(PERSONA.read_text())
        self.assertEqual(p["voice"]["samples"], 1)
        learned = [x for x in p["how_you_write"] if x.startswith("Learned from your edits: ")]
        self.assertIn("Learned from your edits: Signs off with “Thanks,”.", learned)
        self.assertIn("Short paragraphs. Decision first, context second.", p["how_you_write"])
        self.assertIn("## 學到的語氣 / Learned voice", (srv.ROOT / "vault" / "persona.md").read_text())
        srv.persona.rebuild()
        self.assertEqual(json.loads(PERSONA.read_text())["voice"]["samples"], 1)
        srv.post("/api/cache/clear", {"reseed": True})
        p = json.loads(PERSONA.read_text())
        self.assertEqual(p["voice"]["samples"], 1)
        self.assertEqual(len([x for x in p["how_you_write"] if x.startswith("Learned")]), len(learned))
        _, overview = srv.get("/api/overview")
        self.assertEqual(overview["persona"]["voice"]["samples"], 1)

    def test_learned_voice_shapes_the_next_draft(self):
        ai_then_edit(M1, "Hello Samira,\n\nConfirmed.\n\nTalk soon,\nAlex")
        ai_then_edit(M7, "Hello Samira,\n\nI'll concede the information right.\n\nTalk soon,\nAlex")
        _, r = srv.post("/api/compose/write", {"kind": "reply", "item_id": M4})
        self.assertTrue(r["text"].startswith("Hello Maya,"), r["text"])
        self.assertIn("\nTalk soon,\nAlex", r["text"])
        self.assertNotIn("Thanks for your note", r["text"], "shorter voice drops the thank-you opener")

    def test_kept_opening_does_not_override_the_chosen_style(self):
        compose.learn("Hi Maya,\n\nCopilot text about Thursday.", "Hi Maya,\n\nSee you Thursday, and I will bring the notes.")
        self.assertEqual(srv.get("/api/compose/voice")[1]["by_lang"]["en"]["greeting"], "")
        srv.post("/api/compose/settings", {"style": "casual"})
        _, r = srv.post("/api/compose/write", {"kind": "new", "to": "maya@studio.example",
                                               "instruction": "can we move the design review to next Tuesday?"})
        self.assertTrue(r["text"].startswith("Hey Maya,"), r["text"])

    def test_template_phrase_cut_twice_is_avoided(self):
        compose.learn("Hi Samira,\n\nI hope this email finds you well. Confirmed.\n\nBest,\nAlex",
                      "Hi Samira,\n\nConfirmed.\n\nBest,\nAlex")
        _, v = srv.get("/api/compose/voice")
        self.assertIn("i hope this email finds you well.", v["by_lang"]["en"]["avoid_phrases"])
        self.assertIn("Cuts phrases like “I hope this email finds you well.”.", v["traits_en"])

    def test_placeholder_lines_are_not_avoid_phrases(self):
        ai_then_edit(M1, "Hi Samira,\n\nConfirmed.\n\nThanks,\nAlex")
        self.assertEqual(srv.get("/api/compose/voice")[1]["by_lang"]["en"]["avoid_phrases"], [])

    def test_chinese_samples_are_profiled_separately(self):
        _, w = srv.post("/api/compose/write", {"kind": "reply", "item_id": M1, "lang": "zh-Hant"})
        srv.post("/api/compose/draft", {"kind": "reply", "source_id": M1, "text": "Samira 您好：\n\n三張都保留。\n\n敬祝 順心\nAlex",
                                        "ai_body": w["text"], "lang": "zh-Hant"})
        _, v = srv.get("/api/compose/voice")
        self.assertEqual(list(v["by_lang"]), ["zh"])
        self.assertEqual((v["by_lang"]["zh"]["greeting"], v["by_lang"]["zh"]["signoff"]), ("您好", "敬祝 順心"))
        _, r = srv.post("/api/compose/write", {"kind": "reply", "item_id": M4, "lang": "zh-Hant"})
        self.assertTrue(r["text"].startswith("Maya 您好："), r["text"])
        _, en = srv.post("/api/compose/write", {"kind": "reply", "item_id": M4})
        self.assertTrue(en["text"].startswith("Hi Maya,"), "English drafts are not affected by Chinese samples")

    def test_agent_prompt_carries_learned_voice(self):
        ai_then_edit(M1, "Hello Samira,\n\nConfirmed.\n\nTalk soon,\nAlex")
        use_cli_agent(self, "import sys, json; p = json.load(sys.stdin)['ask']; "
                            "print('VOICE OK' if 'Voice learned from the user' in p and 'Talk soon,' in p "
                            "and 'The user changed it to' in p else 'NO VOICE')")
        _, r = srv.post("/api/compose/write", {"kind": "reply", "item_id": M4})
        self.assertEqual(r["text"], "VOICE OK")

    def test_explicit_learn_and_forget(self):
        status, r = srv.post("/api/compose/learn", {"ai_body": "Hi,\n\nOK!\n\nBest,\nA", "body": "Hi,\n\nOK.\n\nThanks,\nA"})
        self.assertEqual(status, 200)
        self.assertTrue(r["learned"])
        self.assertEqual(srv.post("/api/compose/learn", {"ai_body": "x"})[0], 400)
        sid = r["sample_id"]
        _, f = srv.post("/api/compose/voice/forget", {"id": sid})
        self.assertEqual((f["deleted"], f["voice"]["samples"]), (1, 0))
        ai_then_edit(M1, "Hi Samira,\n\nYes.\n\nThanks,\nAlex")
        _, f = srv.post("/api/compose/voice/forget", {"all": True})
        self.assertEqual(f["deleted"], 1)
        p = json.loads(PERSONA.read_text())
        self.assertEqual(p["voice"]["samples"], 0)
        self.assertFalse([x for x in p["how_you_write"] if x.startswith("Learned")])
        self.assertEqual(srv.post("/api/compose/voice/forget", {})[0], 400)


if __name__ == "__main__":
    unittest.main()
