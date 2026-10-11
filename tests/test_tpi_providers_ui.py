"""Account filter UI module: served by the loader, bilingual, wired to the core sidebar."""
from __future__ import annotations

import re
import shutil
import subprocess
import unittest
from pathlib import Path

import _tpi_server as srv

JS = Path(__file__).resolve().parents[1] / "ui" / "modules" / "providers.js"


def _block(src: str, lang: str) -> str:
    m = re.search(rf"\n    {lang}: \{{\n(.*?)\n    \}},", src, re.S)
    assert m, lang
    return m.group(1)


class ProvidersUiTest(unittest.TestCase):
    def test_listed_and_served(self):
        _, mods = srv.get("/api/ui-modules")
        self.assertIn("/ui/modules/providers.js", mods["modules"])
        status, headers, raw = srv.request("GET", "/ui/modules/providers.js")
        self.assertEqual(status, 200)
        self.assertIn("javascript", headers.get("Content-Type", ""))
        self.assertIn(b"/api/providers", raw)

    def test_strings_in_both_languages(self):
        src = JS.read_text()
        zh, en = _block(src, "zh"), _block(src, "en")
        keys = lambda b: set(re.findall(r"(?:^|[{,])\s*(\w+):", b, re.M))
        self.assertEqual(keys(zh), keys(en))
        self.assertIn("所有收件匣", zh)
        self.assertIn("All inboxes", en)
        self.assertIn("測試連線", zh)
        self.assertIn("Test connection", en)

    def test_hooks_into_core_sidebar(self):
        src = JS.read_text()
        html = (Path(__file__).resolve().parents[1] / "ui" / "index.html").read_text()
        self.assertIn('id="accounts"', html)
        self.assertIn('id="tpi-module-loader"', html)
        for hook in ("window.renderAccounts", "window.loadInbox", "window.refreshCounts", "state.account"):
            self.assertIn(hook, src)
        self.assertNotIn("innerHTML = `", src, "account labels must be set via textContent")

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_js_syntax(self):
        r = subprocess.run(["node", "--check", str(JS)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
