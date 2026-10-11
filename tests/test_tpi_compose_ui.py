"""Composer UI module: served by the loader, bilingual, hooked into the core views, output escaped."""
from __future__ import annotations

import re
import shutil
import subprocess
import unittest
from pathlib import Path

import _tpi_server as srv

REPO = Path(__file__).resolve().parents[1]
JS = REPO / "ui" / "modules" / "compose.js"


def _block(src: str, lang: str) -> str:
    m = re.search(rf"\n    {lang}: \{{\n(.*?)\n    \}},", src, re.S)
    assert m, lang
    return m.group(1)


class ComposeUiTest(unittest.TestCase):
    def test_listed_and_served(self):
        _, mods = srv.get("/api/ui-modules")
        self.assertIn("/ui/modules/compose.js", mods["modules"])
        status, headers, raw = srv.request("GET", "/ui/modules/compose.js")
        self.assertEqual(status, 200)
        self.assertIn("javascript", headers.get("Content-Type", ""))
        for path in (b"/api/compose/start", b"/api/compose/draft", b"/api/compose/write", b"/api/compose/rewrite",
                     b"/api/compose/settings", b"/api/compose/voice", b"/api/compose/voice/forget"):
            self.assertIn(path, raw)

    def test_strings_in_both_languages(self):
        src = JS.read_text()
        zh, en = _block(src, "zh"), _block(src, "en")
        keys = lambda b: set(re.findall(r"(?:^|[{,])\s*(\w+):", b, re.M))
        self.assertEqual(keys(zh), keys(en))
        for word in ("新郵件", "回覆", "轉寄", "AI 起草", "更正式", "更短", "更友善", "草稿風格", "中日韓字型", "學到的語氣", "只存本機草稿"):
            self.assertIn(word, zh)
        for word in ("New mail", "Reply", "Forward", "AI draft", "More formal", "Shorter", "Friendlier", "Draft style",
                     "CJK font", "Learned voice", "local draft only"):
            self.assertIn(word, en)

    def test_hooks_into_core(self):
        src = JS.read_text()
        html = (REPO / "ui" / "index.html").read_text()
        for anchor in ('class="toolbar"', 'id="cpBtn"', 'class="sidefoot"', 'id="langBtn"', 'id="pane"',
                       'id="tpi-module-loader"', "function openThread", "window.showDraftEditor", "window.openDraftModal"):
            self.assertIn(anchor, html)
        for hook in ("window.openThread", "window.showDraftEditor", "window.openDraftModal", "window.openComposer",
                     "refreshCounts", "loadDrafts", 'attributeFilter: ["lang"]', 'hash.get("compose")'):
            self.assertIn(hook, src)

    def test_everything_rendered_is_escaped(self):
        src = JS.read_text()
        for field in ("cmp.to", "cmp.cc", "cmp.bcc", "cmp.subject", "cmp.quote", "cmp.label", "s.name", "s.description",
                      "s.sample", "f.name", "x.ai", "x.final", "(w)", "(title)"):
            hits = list(re.finditer(r"\$\{([^{}]*" + re.escape(field) + r"(?!\w)[^{}]*)\}", src))
            self.assertTrue(hits, field)
            for m in hits:
                self.assertIn("h(", m.group(1), f"unescaped {field}: {m.group(0)}")
        self.assertIn("ta.value = cmp.text", src, "the body goes in via .value, never as HTML")

    def test_font_stack_is_checked_before_injecting_css(self):
        src = JS.read_text()
        self.assertIn("SAFE_STACK.test(cfg.font_stack", src)
        self.assertIn("SAFE_STACK.test(font.stack", src)

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_js_syntax(self):
        r = subprocess.run(["node", "--check", str(JS)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
