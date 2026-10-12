"""CJK font choice: local font stacks for Traditional / Simplified Chinese, Japanese and Korean."""
from __future__ import annotations

import re
import unittest

import _tpi_server as srv
from _tpi_compose_util import ComposeCase

SAFE_STACK = re.compile(r'^[\w\s",.-]*$')


class FontTest(ComposeCase):
    def test_choices_cover_cjk(self):
        _, s = srv.get("/api/compose/settings")
        fonts = {f["id"]: f for f in s["fonts"]}
        self.assertEqual(s["font"], "system")
        self.assertEqual(s["font_stack"], "")
        langs = {f["lang"] for f in s["fonts"]}
        self.assertTrue({"zh-Hant", "zh-Hans", "ja", "ko"} <= langs)
        self.assertIn("Noto Sans TC", fonts["sans_tc"]["stack"])
        self.assertIn("Noto Serif JP", fonts["serif_jp"]["stack"])
        self.assertIn("Noto Sans KR", fonts["sans_kr"]["stack"])
        for f in s["fonts"]:
            self.assertRegex(f["stack"], SAFE_STACK, f["id"])
            self.assertNotIn("url(", f["stack"])
            if f["stack"]:
                self.assertRegex(f["stack"], r"(sans-serif|serif|monospace)$", f["id"])
        _, zh = srv.get("/api/compose/settings?lang=zh-Hant")
        self.assertEqual({f["id"]: f["name"] for f in zh["fonts"]}["serif_tc"], "明體 · 繁中（思源宋體 TC）")

    def test_set_font_scope_and_size(self):
        status, s = srv.post("/api/compose/settings", {"font": "serif_tc", "font_scope": "app", "font_size": 30})
        self.assertEqual(status, 200)
        self.assertEqual((s["font"], s["font_scope"], s["font_size"], s["font_lang"]), ("serif_tc", "app", 24, "zh-Hant"))
        self.assertTrue(s["font_stack"].startswith('"Noto Serif TC"'))
        again = srv.get("/api/compose/settings")[1]
        self.assertEqual((again["font"], again["font_scope"], again["font_size"]), ("serif_tc", "app", 24))
        self.assertEqual(srv.post("/api/compose/settings", {"font_size": 2})[1]["font_size"], 12)

    def test_font_is_stored_with_the_draft(self):
        _, r = srv.post("/api/compose/draft", {"kind": "new", "text": "日本語のメール", "font": "sans_jp",
                                               "to": "pat@studio.example"})
        self.assertEqual(r["draft"]["font"], "sans_jp")

    def test_rejects_unknown_values(self):
        self.assertEqual(srv.post("/api/compose/settings", {"font": "comic-sans; color:red"})[0], 400)
        self.assertEqual(srv.post("/api/compose/settings", {"font_scope": "everywhere"})[0], 400)
        self.assertEqual(srv.post("/api/compose/settings", {"font_size": "big"})[0], 400)
        self.assertEqual(srv.get("/api/compose/settings")[1]["font"], "system")


if __name__ == "__main__":
    unittest.main()
