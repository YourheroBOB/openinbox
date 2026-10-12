"""F24 print view: a clean, escaped HTML page for the browser's "Save as PDF"."""
from __future__ import annotations

import unittest

import _tpi_server as srv
from _tpi_mailops_util import add_mail, mid, reset

SIDE = "side@example.com"


def page(path: str):
    status, headers, raw = srv.request("GET", path)
    return status, headers, raw.decode()


class PrintViewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        reset()

    @classmethod
    def tearDownClass(cls):
        reset()

    def test_english_page(self):
        status, headers, html = page("/mailops/print?id=" + mid(1))
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["Content-Type"])
        self.assertIn('<html lang="en">', html)
        subject = srv.FIXTURE["emails"][0]["subject"]
        self.assertIn(subject.replace("'", "&#x27;"), html)
        for label in ("From", "Date", "Account", "Print / Save as PDF", "Save as PDF"):
            self.assertIn(label, html)
        self.assertIn("@media print", html)
        self.assertIn("window.print()", html)
        self.assertNotIn("addEventListener('load'", html, "no auto print unless asked")

    def test_chinese_labels_and_auto_print(self):
        status, _, html = page(f"/mailops/print?id={mid(2)}&lang=zh-Hant&auto=1")
        self.assertEqual(status, 200)
        self.assertIn('<html lang="zh-Hant">', html)
        for label in ("寄件者", "日期", "列印／存成 PDF", "另存為 PDF"):
            self.assertIn(label, html)
        self.assertIn("addEventListener('load'", html)

    def test_body_is_escaped(self):
        add_mail(f"imap:{SIDE}:INBOX:1:31", SIDE, "<script>alert(1)</script> hello",
                 body="Line one\n<img src=x onerror=alert(2)>\nLine three")
        _, _, html = page(f"/mailops/print?id=imap:{SIDE}:INBOX:1:31")
        self.assertNotIn("<script>alert(1)", html)
        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt; hello", html)
        self.assertIn("Line one\n&lt;img", html, "line breaks are kept for pre-wrap")

    def test_thread_prints_every_message(self):
        add_mail(f"imap:{SIDE}:INBOX:1:41", SIDE, "Venue plan", body="first", thread_id="t-venue",
                 date_raw="2026-09-20 09:00")
        add_mail(f"imap:{SIDE}:INBOX:1:42", SIDE, "Re: Venue plan", body="second", thread_id="t-venue",
                 date_raw="2026-09-20 10:00")
        _, _, html = page(f"/mailops/print?id=imap:{SIDE}:INBOX:1:42")
        self.assertEqual(html.count('<article class="msg'), 2)
        self.assertLess(html.index(">first<"), html.index(">second<"))
        self.assertIn("2 message(s)", html)
        _, _, single = page(f"/mailops/print?id=imap:{SIDE}:INBOX:1:42&thread=0")
        self.assertEqual(single.count('<article class="msg'), 1)

    def test_demo_reply_thread_includes_sent_fixture(self):
        _, _, html = page(f"/mailops/print?id={mid(7)}")
        self.assertGreaterEqual(html.count('<article class="msg'), 2)
        self.assertIn("Re: Northwind term sheet comments", html)

    def test_sent_fixture_prints(self):
        _, d = srv.get("/api/mailops/list?folder=sent")
        status, _, html = page("/mailops/print?id=" + d["emails"][0]["id"])
        self.assertEqual(status, 200)
        self.assertIn("To", html)

    def test_missing(self):
        status, headers, html = page("/mailops/print?id=nope&lang=zh-Hant")
        self.assertEqual(status, 404)
        self.assertIn("text/html", headers["Content-Type"])
        self.assertIn("找不到", html)


if __name__ == "__main__":
    unittest.main()
