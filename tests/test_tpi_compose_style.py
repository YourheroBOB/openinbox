"""Draft style setting: Professional / Balanced / Casual, persisted and used by AI Write."""
from __future__ import annotations

import unittest

import _tpi_server as srv
from _tpi_compose_util import M1, ComposeCase


class StyleSettingTest(ComposeCase):
    def test_defaults_and_choices(self):
        status, s = srv.get("/api/compose/settings")
        self.assertEqual(status, 200)
        self.assertEqual(s["style"], "balanced")
        self.assertEqual([x["id"] for x in s["styles"]], ["professional", "balanced", "casual"])
        self.assertEqual([x["name"] for x in s["styles"]], ["Professional", "Balanced", "Casual"])
        self.assertTrue(all(x["description"] and x["sample"] for x in s["styles"]))
        _, zh = srv.get("/api/compose/settings?lang=zh-Hant")
        self.assertEqual([x["name"] for x in zh["styles"]], ["專業", "平衡", "輕鬆"])
        self.assertIn("Maya 您好：", zh["styles"][0]["sample"])

    def test_set_persist_and_survive_cache_clear(self):
        status, s = srv.post("/api/compose/settings", {"style": "casual"})
        self.assertEqual((status, s["style"]), (200, "casual"))
        self.assertEqual(srv.get("/api/compose/settings")[1]["style"], "casual")
        srv.post("/api/cache/clear", {"reseed": True})
        self.assertEqual(srv.get("/api/compose/settings")[1]["style"], "casual")
        _, start = srv.post("/api/compose/start", {"kind": "new"})
        self.assertEqual(start["style"], "casual")

    def test_rejects_unknown_style(self):
        status, r = srv.post("/api/compose/settings", {"style": "pirate"})
        self.assertEqual(status, 400)
        self.assertIn("professional", r["error"])
        self.assertEqual(srv.get("/api/compose/settings")[1]["style"], "balanced")

    def test_style_shapes_greeting_and_sign_off(self):
        expect = {"professional": ("Dear Samira,", "Best regards,\nAlex Chen", "Thank you for your email regarding"),
                  "balanced": ("Hi Samira,", "Best,\nAlex", "Thanks for your note about"),
                  "casual": ("Hey Samira,", "Cheers,\nAlex", "Thanks for the note!")}
        for style, (greet, close, thanks) in expect.items():
            _, r = srv.post("/api/compose/write", {"kind": "reply", "item_id": M1, "style": style})
            self.assertTrue(r["text"].startswith(greet), (style, r["text"]))
            self.assertTrue(r["text"].endswith(close), (style, r["text"]))
            self.assertIn(thanks, r["text"])
            self.assertEqual(r["style"], style)

    def test_saved_style_is_the_default_for_ai_write(self):
        srv.post("/api/compose/settings", {"style": "professional"})
        _, r = srv.post("/api/compose/write", {"kind": "reply", "item_id": M1, "lang": "zh-Hant"})
        self.assertEqual(r["style"], "professional")
        self.assertTrue(r["text"].startswith("Samira 您好："))
        self.assertIn("敬祝 順心", r["text"])
        _, c = srv.post("/api/compose/write", {"kind": "reply", "item_id": M1, "lang": "zh-Hant", "style": "casual"})
        self.assertTrue(c["text"].startswith("嗨 Samira，"))
        self.assertIn("先這樣，再聊！", c["text"])


if __name__ == "__main__":
    unittest.main()
