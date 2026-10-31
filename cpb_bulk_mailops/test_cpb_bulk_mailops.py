"""Isolated batch API regressions and real browser interaction tests (stdlib only)."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tests"))

import _tpi_server as srv
from _tpi_mailops_util import add_mail, request_with_headers, reset

MODULE = REPO / "ui" / "modules" / "cpb_bulk_mailops.js"
CHROME = next((shutil.which(name) for name in ("google-chrome", "chromium", "chromium-browser")
               if shutil.which(name)), None)


class BatchApiTest(unittest.TestCase):
    def setUp(self):
        reset()
        self.ids = ["cpb:batch:1", "cpb:batch:2"]
        for item_id, account in zip(self.ids, ("one@example.com", "two@example.com")):
            add_mail(item_id, account, "Synthetic batch fixture", body="")

    @classmethod
    def tearDownClass(cls):
        reset()

    def action(self, action, **extra):
        return srv.post("/api/mailops/action", {"ids": self.ids, "action": action, **extra})

    def items(self):
        return [srv.get("/api/mailops/item?id=" + item_id)[1] for item_id in self.ids]

    def test_cross_account_archive_trash_and_move(self):
        for action, folder in (("archive", "archive"), ("trash", "trash")):
            status, data = self.action(action)
            self.assertEqual((status, data["changed"], data["unknown"]), (200, self.ids, []))
            self.assertEqual([item["folder"] for item in self.items()], [folder, folder])
        status, _ = self.action("move", folder="inbox")
        self.assertEqual(status, 200)
        self.assertTrue(all(item["folder"] == "inbox" for item in self.items()))

    def test_read_unread_and_star_unstar(self):
        for action, field, value in (("read", "unread", False), ("unread", "unread", True),
                                     ("star", "starred", True), ("unstar", "starred", False)):
            with self.subTest(action=action):
                self.assertEqual(self.action(action)[0], 200)
                self.assertEqual([item[field] for item in self.items()], [value, value])

    def test_partial_result_reports_missing_ids(self):
        self.ids.append("cpb:missing")
        status, data = self.action("archive")
        self.assertEqual((status, data["ok"]), (200, True))
        self.assertEqual(data["changed"], self.ids[:2])
        self.assertEqual(data["unknown"], ["cpb:missing"])

    def test_all_missing_is_an_explicit_failure(self):
        self.ids = ["cpb:missing"]
        status, data = self.action("star")
        self.assertEqual((status, data["ok"], data["changed"]), (404, False, []))
        self.assertTrue(data["error"])

    def test_cross_origin_write_is_refused(self):
        status, _, _ = request_with_headers(
            "POST", "/api/mailops/action", {"ids": self.ids, "action": "archive"},
            {"Origin": "https://untrusted.example.com"})
        self.assertEqual(status, 403)
        self.assertTrue(all(item["folder"] == "inbox" for item in self.items()))

    def test_actions_preserve_cached_messages_and_drafts(self):
        srv.post("/api/draft", {"account": "one@example.com", "to": "two@example.com",
                               "subject": "Synthetic draft", "body": ""})
        con = srv.yhbmail.db()
        before = [tuple(row) for row in con.execute("SELECT * FROM emails ORDER BY id")]
        drafts = [tuple(row) for row in con.execute("SELECT * FROM drafts ORDER BY id")]
        con.close()
        self.action("trash")
        con = srv.yhbmail.db()
        self.assertEqual(before, [tuple(row) for row in con.execute("SELECT * FROM emails ORDER BY id")])
        self.assertEqual(drafts, [tuple(row) for row in con.execute("SELECT * FROM drafts ORDER BY id")])
        con.close()

    def test_local_state_survives_resync(self):
        self.action("archive")
        srv.reseed()
        self.assertTrue(all(item["folder"] == "archive" for item in self.items()))


class BulkUiTest(unittest.TestCase):
    def test_automatically_listed_and_served(self):
        status, data = srv.get("/api/ui-modules")
        self.assertEqual(status, 200)
        self.assertIn("/ui/modules/cpb_bulk_mailops.js", data["modules"])
        status, headers, raw = srv.request("GET", "/ui/modules/cpb_bulk_mailops.js")
        self.assertEqual(status, 200)
        self.assertIn("javascript", headers["Content-Type"])
        self.assertEqual(raw, MODULE.read_bytes())

    def test_both_locales_have_matching_keys(self):
        source = MODULE.read_text()
        blocks = [re.search(rf"\n    {lang}: \{{\n(.*?)\n    \}},", source, re.S).group(1)
                  for lang in ("zh", "en")]
        keys = [set(re.findall(r"(?:^|[{,])\s*(\w+):", block, re.M)) for block in blocks]
        self.assertEqual(keys[0], keys[1])
        self.assertGreater(len(keys[0]), 20)

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for JavaScript checks")
    def test_javascript_syntax(self):
        for path in (MODULE, Path(__file__).with_name("cpb_browser_test.js")):
            with self.subTest(path=path.name):
                result = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(CHROME and shutil.which("node"), "Chrome and Node.js are required for browser interactions")
    def test_real_browser_interactions(self):
        reset()
        for i in range(125):
            add_mail(f"cpb:display:{i}", "one@example.com", "Synthetic batch fixture", body="")
        srv.post("/api/draft", {"account": "you@example.com", "to": "two@example.com",
                               "subject": "Synthetic draft", "body": ""})
        try:
            result = subprocess.run(
                ["node", str(Path(__file__).with_name("cpb_browser_test.js")), CHROME, srv.BASE,
                 str(srv.ROOT / "cpb-browser-profile")],
                capture_output=True, text=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertGreaterEqual(len(report["checks"]), 25)
            self.assertEqual(report["exceptions"], [])
            print(f"CPB Chrome: {len(report['checks'])} interaction checks passed; no runtime exceptions.")
        finally:
            reset()


if __name__ == "__main__":
    unittest.main()
