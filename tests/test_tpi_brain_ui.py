"""Email Brain UI module: served by the loader, bilingual, Fix buttons wired to the API."""
from __future__ import annotations

import re
import shutil
import subprocess
import unittest
from pathlib import Path

import _tpi_server as srv

REPO = Path(__file__).resolve().parents[1]
JS = REPO / "ui" / "modules" / "email_brain.js"


def _block(src: str, lang: str) -> str:
    m = re.search(rf"\n    {lang}: \{{\n(.*?)\n    \}},", src, re.S)
    assert m, lang
    return m.group(1)


class EmailBrainUiTest(unittest.TestCase):
    def test_listed_and_served(self):
        _, mods = srv.get("/api/ui-modules")
        self.assertIn("/ui/modules/email_brain.js", mods["modules"])
        status, headers, raw = srv.request("GET", "/ui/modules/email_brain.js")
        self.assertEqual(status, 200)
        self.assertIn("javascript", headers.get("Content-Type", ""))
        for path in (b"/api/brain/profile", b"/api/brain/fix", b"/api/brain/fix/reset", b"/api/brain/prompt",
                     b"/api/brain/fixes"):
            self.assertIn(path, raw)

    def test_routes_registered_by_the_feature(self):
        _, data = srv.get("/api/features")
        self.assertIn("email_brain", data["features"])
        owned = {(r["method"], r["path"]) for r in data["routes"] if r["feature"] == "email_brain"}
        self.assertEqual(owned, {("GET", "/api/brain/profile"), ("GET", "/api/brain/fixes"),
                                 ("POST", "/api/brain/fix"), ("POST", "/api/brain/fix/reset"),
                                 ("GET", "/api/brain/prompt")})
        self.assertFalse([e for e in data["errors"] if e["feature"] == "email_brain"])
        status, board = srv.get("/api/brain?hours=168")
        self.assertEqual(status, 200)
        self.assertIn("taxonomy", board, "the core triage board route is untouched")

    def test_strings_in_both_languages(self):
        src = JS.read_text()
        zh, en = _block(src, "zh"), _block(src, "en")
        keys = lambda b: set(re.findall(r"(?:^|[{,])\s*(\w+):", b, re.M))
        self.assertEqual(keys(zh), keys(en))
        for word in ("信件大腦", "修正", "還原推論", "這些會怎麼影響 AI 草稿", "新增聯絡人", "新增專案"):
            self.assertIn(word, zh)
        for word in ("Email Brain", "Fix", "Reset to inferred", "How this shapes AI drafts", "Add contact", "Add project"):
            self.assertIn(word, en)

    def test_every_item_kind_has_a_fix_button(self):
        src = JS.read_text()
        for fn in ("function scalarItem", "function contactItem", "function projectItem"):
            body = src.split(fn, 1)[1].split("\n  function ", 1)[0]
            self.assertIn('data-fix="${h(id)}"', body, fn)
            self.assertIn('data-reset="${h(id)}"', body, fn)

    def test_hooks_into_core(self):
        src = JS.read_text()
        html = (REPO / "ui" / "index.html").read_text()
        for anchor in ('id="nav"', 'id="list"', 'id="pane"', 'id="tpi-module-loader"', 'data-view="brain2"'):
            self.assertIn(anchor, html)
        for hook in ("window.setView", 'dataset.view = "ebrain"', 'get("view") === "ebrain"', "openThread",
                     "MutationObserver"):
            self.assertIn(hook, src)

    def test_everything_rendered_is_escaped(self):
        src = JS.read_text()
        for field in ("it.display", "it.basis", "it.note", "c.name", "c.email", "c.note", "c.basis", "p.name",
                      "p.note", "x.subject", "view.prompt", "s.name", "e.title"):
            for m in re.finditer(r"\$\{([^{}]*" + re.escape(field) + r"(?!\w)[^{}]*)\}", src):
                self.assertIn("h(", m.group(1), f"unescaped {field}: {m.group(0)}")

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_js_syntax(self):
        r = subprocess.run(["node", "--check", str(JS)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
