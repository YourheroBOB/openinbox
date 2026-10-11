"""Super Agent UI module: served by the loader, bilingual, hooked into the core views."""
from __future__ import annotations

import re
import shutil
import subprocess
import unittest
from pathlib import Path

import _tpi_server as srv

REPO = Path(__file__).resolve().parents[1]
JS = REPO / "ui" / "modules" / "triage.js"


def _block(src: str, lang: str) -> str:
    m = re.search(rf"\n    {lang}: \{{\n(.*?)\n    \}},", src, re.S)
    assert m, lang
    return m.group(1)


class TriageUiTest(unittest.TestCase):
    def test_listed_and_served(self):
        _, mods = srv.get("/api/ui-modules")
        self.assertIn("/ui/modules/triage.js", mods["modules"])
        status, headers, raw = srv.request("GET", "/ui/modules/triage.js")
        self.assertEqual(status, 200)
        self.assertIn("javascript", headers.get("Content-Type", ""))
        for path in (b"/api/triage", b"/api/triage/digest", b"/api/triage/tasks", b"/api/triage/history",
                     b"/api/triage/summarize", b"/api/triage/summaries"):
            self.assertIn(path, raw)

    def test_strings_in_both_languages(self):
        src = JS.read_text()
        zh, en = _block(src, "zh"), _block(src, "en")
        keys = lambda b: set(re.findall(r"(?:^|[{,])\s*(\w+):", b, re.M))
        self.assertEqual(keys(zh), keys(en))
        for word in ("Super Agent 分流", "電子報摘要", "任務歷史", "未接 LLM", "建議後續動作", "附件"):
            self.assertIn(word, zh)
        for word in ("Super Agent", "Newsletter digest", "Task history", "No LLM wired", "Suggested next actions", "Attachment"):
            self.assertIn(word, en)

    def test_hooks_into_core(self):
        src = JS.read_text()
        html = (REPO / "ui" / "index.html").read_text()
        for anchor in ('id="nav"', 'id="list"', 'id="pane"', 'id="tpi-module-loader"', "function setView"):
            self.assertIn(anchor, html)
        for hook in ("window.setView", "window.loadInbox", "window.refreshCounts", 'dataset.view = "super"',
                     "openThread", "cpAction", 'get("view") === "super"'):
            self.assertIn(hook, src)

    def test_everything_rendered_is_escaped(self):
        src = JS.read_text()
        for field in ("it.summary", "it.subject", "it.from_name", "x.subject", "g.sender", "d.markdown"):
            for m in re.finditer(r"\$\{([^{}]*" + re.escape(field) + r"(?!\w)[^{}]*)\}", src):
                self.assertIn("h(", m.group(1), f"unescaped {field}: {m.group(0)}")

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_js_syntax(self):
        r = subprocess.run(["node", "--check", str(JS)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
