"""Mail-ops UI module: served by the loader, bilingual, hooked into the core views,
and (when Chrome is installed) actually rendering its folder sidebar."""
from __future__ import annotations

import re
import shutil
import subprocess
import unittest
from pathlib import Path

import _tpi_server as srv
from _tpi_mailops_util import reset

REPO = Path(__file__).resolve().parents[1]
JS = REPO / "ui" / "modules" / "mailops.js"
CHROME = next((shutil.which(n) for n in ("google-chrome", "chromium", "chromium-browser") if shutil.which(n)), None)


def _block(src: str, lang: str) -> str:
    m = re.search(rf"\n    {lang}: \{{\n(.*?)\n    \}},", src, re.S)
    assert m, lang
    return m.group(1)


class MailopsUiTest(unittest.TestCase):
    def test_listed_and_served(self):
        _, mods = srv.get("/api/ui-modules")
        self.assertIn("/ui/modules/mailops.js", mods["modules"])
        status, headers, raw = srv.request("GET", "/ui/modules/mailops.js")
        self.assertEqual(status, 200)
        self.assertIn("javascript", headers.get("Content-Type", ""))
        for path in (b"/api/mailops/list", b"/api/mailops/folders", b"/api/mailops/action", b"/api/mailops/mark-all-read",
                     b"/api/mailops/empty-trash", b"/mailops/print", b"/api/mailops/translate", b"/api/new-since",
                     b"/api/mailops/accounts/add", b"/api/mailops/accounts/remove", b"/api/mailops/accounts/reorder",
                     b"/api/mailops/accounts/primary", b"/api/mailops/signature", b"/api/mailops/signature/import"):
            self.assertIn(path, raw)

    def test_strings_in_both_languages(self):
        src = JS.read_text()
        zh, en = _block(src, "zh"), _block(src, "en")
        keys = lambda b: set(re.findall(r"(?:^|[{,])\s*(\w+):", b, re.M))
        self.assertEqual(keys(zh), keys(en))
        for word in ("收件匣", "已加星號", "寄件備份", "封存", "垃圾桶", "全部標為已讀", "列印", "翻譯", "未接 LLM",
                     "新信通知", "帳號設定", "主帳號", "從檔案匯入", "簽名"):
            self.assertIn(word, zh)
        for word in ("Inbox", "Starred", "Sent", "Archive", "Trash", "Mark all read", "Print", "Translate", "No LLM wired",
                     "New-mail alerts", "Account settings", "Primary", "Import from file", "Signature"):
            self.assertIn(word, en)

    def test_hooks_into_core(self):
        src = JS.read_text()
        html = (REPO / "ui" / "index.html").read_text()
        for anchor in ('id="accounts"', 'id="nav"', 'id="list"', 'id="pane"', 'id="tpi-module-loader"'):
            self.assertIn(anchor, html)
        for hook in ("window.loadInbox", "window.openThread", "window.setView", "window.refreshCounts",
                     "window.toggleUnread", "Notification.requestPermission", "new Notification(", "tpiCmpBack"):
            self.assertIn(hook, src)
        self.assertNotIn("mailops", html, "the module needs no edits to ui/index.html")

    def test_no_raw_interpolation_of_mail_fields(self):
        src = JS.read_text()
        for field in ("subject", "from_addr", "to_addr", "body_text", "signature", "label", "note", "text"):
            self.assertIsNone(re.search(rf"\$\{{(?:e|d|a|item)\.{field}\}}", src), f"{field} must go through h()")

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_js_syntax(self):
        r = subprocess.run(["node", "--check", str(JS)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    @unittest.skipUnless(CHROME, "Chrome not installed")
    def test_renders_in_headless_chrome(self):
        reset()
        try:
            r = subprocess.run([CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--virtual-time-budget=6000",
                                "--user-data-dir=" + str(srv.ROOT / "chrome-profile"), "--dump-dom", srv.BASE + "/#folder=sent"],
                               capture_output=True, text=True, timeout=90)
        except subprocess.TimeoutExpired:
            self.skipTest("headless Chrome timed out")
        if r.returncode != 0 or "<body" not in r.stdout:
            self.skipTest("headless Chrome unavailable: " + r.stderr[-200:])
        dom = r.stdout
        self.assertIn('id="tmoFolders"', dom)
        for folder in ("inbox", "starred", "drafts", "sent", "archive", "trash"):
            self.assertIn(f'data-folder="{folder}"', dom)
        self.assertIn('data-folder="sent" class="on"', dom)
        self.assertIn("寄件備份", dom)
        self.assertGreaterEqual(dom.count("tmo-star"), 9, "the nine fictional sent messages are listed")
        self.assertIn('data-view="mailops-accounts"', dom)


if __name__ == "__main__":
    unittest.main()
