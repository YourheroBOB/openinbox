"""Skills + usage UI modules: served by the loader, bilingual, hooked into the core, escaped."""
from __future__ import annotations

import re
import shutil
import subprocess
import unittest
from pathlib import Path

import _tpi_server as srv

REPO = Path(__file__).resolve().parents[1]
SKILLS_JS = REPO / "ui" / "modules" / "skills.js"
USAGE_JS = REPO / "ui" / "modules" / "usage.js"


def _block(src: str, lang: str) -> str:
    m = re.search(rf"\n    {lang}: \{{\n(.*?)\n    \}},", src, re.S)
    assert m, lang
    return m.group(1)


def _keys(block: str) -> set:
    return set(re.findall(r"(?:^|[{,])\s*(\w+):", block, re.M))


class ModulesServedTest(unittest.TestCase):
    def test_listed_and_served(self):
        _, mods = srv.get("/api/ui-modules")
        for name, paths in (("skills.js", (b"/api/skills", b"/api/skills/run", b"/api/skills/settings",
                                           b"/api/skills/slides", b"/api/contacts", b"/api/contacts/update",
                                           b"/api/contacts/delete")),
                            ("usage.js", (b"/api/usage", b"/api/usage/clear"))):
            self.assertIn(f"/ui/modules/{name}", mods["modules"])
            status, headers, raw = srv.request("GET", f"/ui/modules/{name}")
            self.assertEqual(status, 200)
            self.assertIn("javascript", headers.get("Content-Type", ""))
            for p in paths:
                self.assertIn(p, raw, (name, p))

    def test_features_loaded(self):
        _, d = srv.get("/api/features")
        self.assertIn("skills", d["features"])
        self.assertIn("usage", d["features"])
        self.assertEqual(d["errors"], [])


class StringsTest(unittest.TestCase):
    def test_skills_both_languages(self):
        src = SKILLS_JS.read_text()
        zh, en = _block(src, "zh"), _block(src, "en")
        self.assertEqual(_keys(zh), _keys(en))
        for word in ("技能", "已關閉", "開啟投影片", "聯絡人 CRM", "這個人是誰", "轉成投影片"):
            self.assertIn(word, zh)
        for word in ("Skills", "Off", "Open slides", "Contacts CRM", "Brief this person", "Turn into a slide"):
            self.assertIn(word, en)

    def test_usage_both_languages(self):
        src = USAGE_JS.read_text()
        zh, en = _block(src, "zh"), _block(src, "en")
        self.assertEqual(_keys(zh), _keys(en))
        for word in ("用量", "輸入 token", "依功能", "清除紀錄"):
            self.assertIn(word, zh)
        for word in ("Usage", "Prompt tokens", "By feature", "Clear log"):
            self.assertIn(word, en)


class HooksTest(unittest.TestCase):
    def test_hooks_into_core(self):
        html = (REPO / "ui" / "index.html").read_text()
        for anchor in ('id="nav"', 'id="list"', 'id="pane"', 'id="tpi-module-loader"', "function setView",
                       "function mdHtml"):
            self.assertIn(anchor, html)
        sk = SKILLS_JS.read_text()
        for hook in ("window.setView", 'dataset.view = "skills"', 'get("view") === "skills"', "state.selected",
                     "mdHtml", ".actionbar"):
            self.assertIn(hook, sk)
        us = USAGE_JS.read_text()
        for hook in ("window.setView", 'dataset.view = "usage"', 'get("view") === "usage"'):
            self.assertIn(hook, us)

    def test_rendered_values_are_escaped(self):
        for js, fields in ((SKILLS_JS, ("s.name", "s.description", "r.title", "c.name", "c.email", "n.text",
                                        "x.name", "e.title", "r.source_label", "c.last_subject")),
                           (USAGE_JS, ("g.key", "r.feature", "r.model", "r.driver", "d.note", "d.file"))):
            src = js.read_text()
            for field in fields:
                for m in re.finditer(r"\$\{([^{}]*" + re.escape(field) + r"(?!\w)[^{}]*)\}", src):
                    self.assertTrue("h(" in m.group(1) or "n(" in m.group(1), f"{js.name}: unescaped {field}: {m.group(0)}")

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_js_syntax(self):
        for js in (SKILLS_JS, USAGE_JS):
            r = subprocess.run(["node", "--check", str(js)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
