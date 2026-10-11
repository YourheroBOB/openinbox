"""Follow-ups & automation UI module: served by the loader, bilingual, escaped, hooked into the core views."""
from __future__ import annotations

import re
import shutil
import subprocess
import unittest
from pathlib import Path

import _tpi_server as srv

REPO = Path(__file__).resolve().parents[1]
JS = REPO / "ui" / "modules" / "followup.js"


def _block(src: str, lang: str) -> str:
    m = re.search(rf"\n    {lang}: \{{\n(.*?)\n    \}},", src, re.S)
    assert m, lang
    return m.group(1)


class FollowupUiTest(unittest.TestCase):
    def test_listed_and_served(self):
        _, mods = srv.get("/api/ui-modules")
        self.assertIn("/ui/modules/followup.js", mods["modules"])
        status, headers, raw = srv.request("GET", "/ui/modules/followup.js")
        self.assertEqual(status, 200)
        self.assertIn("javascript", headers.get("Content-Type", ""))
        for path in (b"/api/followup", b"/api/followup/nudge", b"/api/followup/state", b"/api/followup/settings",
                     b"/api/rules", b"/api/rules/run", b"/api/rules/validate", b"/api/rules/marks",
                     b"/api/overnight/run", b"/api/overnight/latest", b"/api/overnight/runs"):
            self.assertIn(path, raw)

    def test_routes_registered(self):
        _, data = srv.get("/api/features")
        self.assertEqual(data["errors"], [])
        for name in ("followup", "rules", "overnight"):
            self.assertIn(name, data["features"])
        owners = {(r["method"], r["path"]): r["feature"] for r in data["routes"]}
        self.assertEqual(owners[("GET", "/api/followup")], "followup")
        self.assertEqual(owners[("POST", "/api/rules/run")], "rules")
        self.assertEqual(owners[("POST", "/api/overnight/run")], "overnight")

    def test_strings_in_both_languages(self):
        src = JS.read_text()
        zh, en = _block(src, "zh"), _block(src, "en")
        keys = lambda b: set(re.findall(r"(?:^|[{,])\s*(\w+):", b, re.M))
        self.assertEqual(keys(zh), keys(en))
        for word in ("追蹤與自動化", "待回覆追蹤", "自動化規則", "夜班交接", "Dry-run", "寫追蹤草稿", "不會寄出", "已封存（本機）"):
            self.assertIn(word, zh)
        for word in ("Follow-ups", "Automation rules", "Overnight brief", "Dry run", "Draft a nudge", "nothing is sent",
                     "Archived (local)"):
            self.assertIn(word, en)

    def test_hooks_into_core(self):
        src = JS.read_text()
        html = (REPO / "ui" / "index.html").read_text()
        for anchor in ('id="nav"', 'id="list"', 'id="pane"', 'id="tpi-module-loader"', "function setView"):
            self.assertIn(anchor, html)
        for hook in ("window.setView", "window.refreshCounts", 'dataset.view = "followup"', "openThread",
                     'get("view") === "followup"', "confirm(t(\"applyConfirm\"))"):
            self.assertIn(hook, src)

    def test_everything_rendered_is_escaped(self):
        src = JS.read_text()
        for field in ("it.subject", "it.to_name", "it.question", "it.excerpt", "it.to_email", "m.subject",
                      "m.rule_name", "a.label", "latest.markdown", "e.message", "r.path"):
            for m in re.finditer(r"\$\{([^{}]*" + re.escape(field) + r"(?!\w)[^{}]*)\}", src):
                self.assertIn("h(", m.group(1), f"unescaped {field}: {m.group(0)}")

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_js_syntax(self):
        r = subprocess.run(["node", "--check", str(JS)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
