"""Search UI module: served by the loader, bilingual, escaped, hooked into the core list."""
from __future__ import annotations

import re
import shutil
import subprocess
import unittest
from pathlib import Path

import _tpi_server as srv

REPO = Path(__file__).resolve().parents[1]
JS = REPO / "ui" / "modules" / "search.js"


def _block(src: str, lang: str) -> str:
    m = re.search(rf"\n    {lang}: \{{\n(.*?)\n    \}},", src, re.S)
    assert m, lang
    return m.group(1)


class SearchUiTest(unittest.TestCase):
    def test_listed_and_served(self):
        _, mods = srv.get("/api/ui-modules")
        self.assertIn("/ui/modules/search.js", mods["modules"])
        status, headers, raw = srv.request("GET", "/ui/modules/search.js")
        self.assertEqual(status, 200)
        self.assertIn("javascript", headers.get("Content-Type", ""))
        for path in (b"/api/search", b"/api/contacts"):
            self.assertIn(path, raw)

    def test_routes_registered(self):
        _, feats = srv.get("/api/features")
        self.assertIn("search", feats["features"])
        self.assertIn("contacts", feats["features"])
        self.assertEqual(feats["errors"], [])
        paths = {(r["method"], r["path"]) for r in feats["routes"]}
        for route in (("GET", "/api/search"), ("POST", "/api/search"), ("GET", "/api/search/parse"),
                      ("GET", "/api/search/status"), ("POST", "/api/search/reindex"),
                      ("GET", "/api/contacts"), ("GET", "/api/contacts/*")):
            self.assertIn(route, paths)

    def test_strings_in_both_languages(self):
        src = JS.read_text()
        zh, en = _block(src, "zh"), _block(src, "en")
        keys = lambda b: set(re.findall(r"(?:^|[{,])\s*(\w+):", b, re.M))
        self.assertEqual(keys(zh), keys(en))
        for word in ("自然語言搜尋", "解讀為", "Agent 改寫", "聯絡人", "只看真人", "搜尋此人的信"):
            self.assertIn(word, zh)
        for word in ("Natural-language search", "Understood as", "Agent rewrite", "Contacts", "People only",
                     "Search their mail"):
            self.assertIn(word, en)

    def test_hooks_into_core(self):
        src = JS.read_text()
        html = (REPO / "ui" / "index.html").read_text()
        for anchor in ('id="nav"', 'id="list"', 'id="pane"', 'id="q"', 'class="toolbar"', 'id="tpi-module-loader"',
                       "function setView", "function loadInbox"):
            self.assertIn(anchor, html)
        for hook in ("window.loadInbox", "window.setView", "state.emails", "openThread", 'dataset.view = "contacts"',
                     'get("view") === "contacts"', 'get("q")'):
            self.assertIn(hook, src)

    def test_everything_rendered_is_escaped(self):
        src = JS.read_text()
        for field in ("e.subject", "e.highlight", "e.from_addr", "c.name", "c.email", "c.text", "m.subject",
                      "d.canonical", "d.rewrite.note", "e.message"):
            for m in re.finditer(r"\$\{([^{}]*" + re.escape(field) + r"(?!\w)[^{}]*)\}", src):
                self.assertRegex(m.group(1), r"\b(h|marked|avatarHtml)\(", f"unescaped {field}: {m.group(0)}")

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_js_syntax(self):
        r = subprocess.run(["node", "--check", str(JS)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_highlighter_escapes(self):
        src = JS.read_text()
        fn = re.search(r"  function marked\(text, needles\) \{.*?\n  \}\n", src, re.S).group(0)
        h = re.search(r"  const h = .*?;\n", src).group(0)
        script = h + fn + 'console.log(marked("<b>Deck</b> & deck", ["deck"]));'
        r = subprocess.run(["node", "-e", script], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "&lt;b&gt;<mark>Deck</mark>&lt;/b&gt; &amp; <mark>deck</mark>")


if __name__ == "__main__":
    unittest.main()
