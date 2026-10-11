"""Outbox UI module: served by the loader, bilingual, hooked into the composer and views, output escaped."""
from __future__ import annotations

import re
import shutil
import subprocess
import unittest
from pathlib import Path

import _tpi_server as srv

REPO = Path(__file__).resolve().parents[1]
JS = REPO / "ui" / "modules" / "outbox.js"


def _block(src: str, lang: str) -> str:
    m = re.search(rf"\n    {lang}: \{{\n(.*?)\n    \}},", src, re.S)
    assert m, lang
    return m.group(1)


class OutboxUiTest(unittest.TestCase):
    def test_listed_and_served(self):
        _, mods = srv.get("/api/ui-modules")
        self.assertIn("/ui/modules/outbox.js", mods["modules"])
        status, headers, raw = srv.request("GET", "/ui/modules/outbox.js")
        self.assertEqual(status, 200)
        self.assertIn("javascript", headers.get("Content-Type", ""))
        for path in (b"/api/outbox/prepare", b"/api/outbox/confirm", b"/api/outbox/undo", b"/api/outbox/discard",
                     b"/api/outbox/review", b"/api/outbox/reschedule", b"/api/outbox/edit", b"/api/outbox/cancel",
                     b"/api/outbox/done", b"/api/outbox/tick", b"/api/outbox/items", b"/api/outbox/summary",
                     b"/api/outbox/settings"):
            self.assertIn(path, raw)

    def test_feature_registered(self):
        _, info = srv.get("/api/features")
        self.assertIn("outbox", info["features"])
        self.assertFalse([e for e in info["errors"] if e["feature"] == "outbox"])
        paths = {r["path"] for r in info["routes"] if r["feature"] == "outbox"}
        self.assertIn("/api/outbox/confirm", paths)

    def test_strings_in_both_languages(self):
        src = JS.read_text()
        zh, en = _block(src, "zh"), _block(src, "en")
        keys = lambda b: set(re.findall(r"(?:^|[{,])\s*(\w+):", b, re.M))
        self.assertEqual(keys(zh), keys(en))
        for word in ("已排程", "寄件匣", "寄出前確認", "我已確認收件者與內容", "撤回", "待你自行寄出", "排程", "取消排程",
                     "變更時間", "編輯", "移回草稿", "標記為我已自行寄出", "寄出前一律人工確認", "不會真的寄信"):
            self.assertIn(word, zh)
        for word in ("Scheduled", "Outbox", "Confirm before release", "I checked the recipients and content", "Undo",
                     "send it yourself", "Schedule", "Cancel schedule", "Change time", "Edit", "Move back to Drafts",
                     "Mark as sent by me", "Always confirm before release", "never sends mail"):
            self.assertIn(word, en)

    def test_hooks(self):
        src = JS.read_text()
        cmp = (REPO / "ui" / "modules" / "compose.js").read_text()
        html = (REPO / "ui" / "index.html").read_text()
        for anchor in ('id="nav"', 'data-view="drafts"', 'id="list"', 'id="pane"', 'id="tpi-module-loader"',
                       "function setView", "function toast"):
            self.assertIn(anchor, html)
        for hook in ("window.tpiComposer", "isOpen:", "save:", "close:", "open: openComposer", 'id = "tpiCmpBack"',
                     "tpi-cmp-foot", "return r.draft"):
            self.assertIn(hook, cmp)
        for hook in ("window.tpiComposer.save()", "window.tpiComposer.close()", "window.tpiComposer.open",
                     "window.setView", "tpiCmpBack", ".tpi-cmp-foot", 'attributeFilter: ["lang"]', "ack: dlg.ack === true",
                     'window.addEventListener("keydown"', 'ev.key !== "z"'):
            self.assertIn(hook, src)

    def test_confirm_button_needs_ack_and_no_blocking(self):
        src = JS.read_text()
        self.assertIn("const canConfirm = dlg.ack && !blocked", src)
        self.assertIn('data-ob="confirm" ${canConfirm ? "" : "disabled"}', src)

    def test_everything_rendered_is_escaped(self):
        src = JS.read_text()
        for field in ("it.to", "it.cc", "it.bcc", "it.subject", "it.body", "it.account", "it.eml_path", "it.eml_name",
                      "it.state_label", "it.eml_url", "p.label", "u.item.subject", "x)", "s.note", "s.outbox_dir"):
            hits = list(re.finditer(r"\$\{([^{}]*" + re.escape(field) + r"(?!\w)[^{}]*)\}", src))
            self.assertTrue(hits, field)
            for m in hits:
                expr = m.group(1)
                self.assertTrue(expr.lstrip("!(").startswith(("h(", "it.cc ?", "it.bcc ?", "it.release_at ?",
                                                             "it.released_at ?", "it.eml_path ?")) or "h(" in expr,
                                f"unescaped: {expr}")

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_parses(self):
        for name in ("outbox.js", "compose.js"):
            r = subprocess.run(["node", "--check", str(REPO / "ui" / "modules" / name)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
