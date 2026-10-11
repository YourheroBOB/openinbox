"""Read-only IMAP driver: config, credentials from env only, parsing, read-only wire behaviour.

Runs against tests/_tpi_imap_fake.py on 127.0.0.1; no real mailbox is contacted.
"""
from __future__ import annotations

import os
import re
import unittest
from pathlib import Path
from unittest import mock

import _tpi_server as srv  # noqa: F401  (sets OPENINBOX_ROOT, loads features)
from _tpi_imap_fake import FakeIMAP

from features import imap

PW_ENV = "TPI_TEST_IMAP_PW"
PW = "fake-app-pass"


def fake_acc(fake: FakeIMAP, **extra) -> dict:
    acc = {"email": "you@example.com", "driver": "imap", "label": "Fake IMAP",
           "host": "127.0.0.1", "port": fake.port, "security": "none", "password_env": PW_ENV}
    acc.update(extra)
    return acc


class SettingsTest(unittest.TestCase):
    def test_icloud_preset(self):
        cfg = imap.settings({"email": "you@example.com", "driver": "imap", "provider": "icloud",
                             "password_env": PW_ENV})
        self.assertEqual((cfg["host"], cfg["port"], cfg["security"]), ("imap.mail.me.com", 993, "ssl"))
        self.assertEqual(cfg["username"], "you@example.com")
        self.assertEqual(cfg["mailbox"], "INBOX")

    def test_icloud_detected_from_domain(self):
        addr = "someone" + "@" + "icloud.com"
        self.assertEqual(imap.provider_of({"email": addr}), "icloud")
        self.assertEqual(imap.provider_of({"email": "you@example.com"}), "custom")
        self.assertEqual(imap.provider_of({"email": "you@example.com", "provider": "nope"}), "custom")

    def test_custom_needs_host(self):
        with self.assertRaisesRegex(imap.ConfigError, "host"):
            imap.settings({"email": "you@example.com", "driver": "imap"})

    def test_plaintext_password_refused(self):
        for key in ("password", "app_password"):
            acc = {"email": "you@example.com", "provider": "icloud", key: "hunter2-fake"}
            with self.assertRaises(imap.ConfigError) as cm:
                imap.settings(acc)
            self.assertNotIn("hunter2-fake", str(cm.exception))
            self.assertIn("password_env", str(cm.exception))
            self.assertEqual(imap.credential_status(acc), "plaintext_rejected")

    def test_plaintext_transport_only_on_loopback(self):
        with self.assertRaisesRegex(imap.ConfigError, "loopback"):
            imap.settings({"email": "you@example.com", "host": "imap.example.com", "security": "none"})
        self.assertEqual(imap.settings({"email": "you@example.com", "host": "127.0.0.1",
                                        "security": "none"})["port"], 143)
        with self.assertRaisesRegex(imap.ConfigError, "security"):
            imap.settings({"email": "you@example.com", "host": "imap.example.com", "security": "tls9"})

    def test_password_env_names(self):
        self.assertEqual(imap.default_password_env({"email": "you.box@example.com"}),
                         "TPI_IMAP_PASSWORD_YOU_BOX_EXAMPLE_COM")
        self.assertEqual(imap.password_env_name({"email": "you@example.com", "password_env": " MY_PW "}), "MY_PW")
        acc = {"email": "you@example.com", "password_env": PW_ENV}
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(PW_ENV, None)
            self.assertEqual(imap.credential_status(acc), "missing")
            with self.assertRaisesRegex(imap.ConfigError, PW_ENV):
                imap._password(imap.settings({**acc, "host": "127.0.0.1", "security": "none"}))
        with mock.patch.dict(os.environ, {PW_ENV: PW}):
            self.assertEqual(imap.credential_status(acc), "env")

    def test_username_env(self):
        with mock.patch.dict(os.environ, {"TPI_TEST_IMAP_USER": "alias@example.com"}):
            cfg = imap.settings({"email": "you@example.com", "provider": "fastmail",
                                 "username_env": "TPI_TEST_IMAP_USER"})
        self.assertEqual(cfg["username"], "alias@example.com")

    def test_ssl_connection_uses_verified_context(self):
        seen = {}

        class FakeSSL:
            def __init__(self, host, port, ssl_context=None, timeout=None):
                seen.update(host=host, port=port, ctx=ssl_context, timeout=timeout)

        with mock.patch.object(imap.imaplib, "IMAP4_SSL", FakeSSL):
            imap.open_connection(imap.settings({"email": "you@example.com", "provider": "icloud"}))
        self.assertEqual((seen["host"], seen["port"]), ("imap.mail.me.com", 993))
        self.assertTrue(seen["ctx"].check_hostname)


class ParseTest(unittest.TestCase):
    def test_quote_mailbox(self):
        self.assertEqual(imap.quote_mailbox('Work "A"'), '"Work \\"A\\""')

    def test_garbage_does_not_crash(self):
        row = imap.parse_message(b"\x00\xff not mail", account="you@example.com", mailbox="INBOX",
                                 uidvalidity="1", uid="9", flags=[], provider="custom")
        self.assertEqual(row["id"], "imap:you@example.com:INBOX:1:9")
        self.assertTrue(row["unread"])


class FakeServerTest(unittest.TestCase):
    def setUp(self):
        self.fake = FakeIMAP(password=PW)
        self.env = mock.patch.dict(os.environ, {PW_ENV: PW})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.fake.close()

    def test_fetch_rows(self):
        rows = imap.fetch(fake_acc(self.fake), limit=25)
        self.assertEqual(len(rows), 3)
        by_uid = {r["id"].rsplit(":", 1)[1]: r for r in rows}
        r1, r2, r3 = by_uid["101"], by_uid["102"], by_uid["105"]
        for r in rows:
            self.assertEqual(r["account"], "you@example.com")
            self.assertEqual(r["platform"], "imap")
            self.assertTrue(r["id"].startswith("imap:you@example.com:INBOX:7:"))
            self.assertIn("INBOX", r["labels"])
        self.assertFalse(r1["unread"])
        self.assertTrue(r2["unread"] and r3["unread"])
        self.assertEqual(r1["subject"], "Can you confirm the venue by Thursday?")
        self.assertEqual(r1["from_addr"], "Rina Park <rina@harbor.example>")
        self.assertIn("Thursday 17:00", r1["body_text"])
        self.assertEqual(r1["date_raw"], "2026-09-20 09:00")
        self.assertEqual(r1["thread_id"], "<m1@harbor.example>")
        self.assertEqual(r2["subject"], "季度報告：請審閱附件")
        self.assertTrue(r2["has_attachment"])
        self.assertIn("FLAGGED", r2["labels"])
        self.assertEqual(r2["thread_id"], "<root2@lantern.example>")
        self.assertFalse(r1["has_attachment"])
        self.assertIn("Hello & welcome", r3["snippet"])
        self.assertNotIn("<p>", r3["body_text"])
        self.assertNotIn("p{}", r3["body_text"])

    def test_limit_keeps_newest(self):
        rows = imap.fetch(fake_acc(self.fake), limit=2)
        self.assertEqual(sorted(r["id"].rsplit(":", 1)[1] for r in rows), ["102", "105"])

    def test_icloud_platform(self):
        rows = imap.fetch(fake_acc(self.fake, provider="icloud"), limit=1)
        self.assertEqual(rows[0]["platform"], "icloud")

    def test_wire_is_read_only(self):
        imap.fetch(fake_acc(self.fake), limit=25)
        verbs = self.fake.verbs()
        self.assertIn("EXAMINE", verbs)
        self.assertNotIn("SELECT", verbs)
        for bad in ("STORE", "UID STORE", "EXPUNGE", "UID EXPUNGE", "APPEND", "COPY", "UID COPY",
                    "MOVE", "UID MOVE", "DELETE", "CREATE", "RENAME"):
            self.assertNotIn(bad, verbs)
        fetches = [c for c in self.fake.commands if c.upper().startswith("UID FETCH")]
        self.assertTrue(fetches)
        for c in fetches:
            self.assertIn("BODY.PEEK[]", c)
        self.assertEqual(verbs[-1], "LOGOUT")
        self.assertEqual([m["flags"] for m in self.fake.mail], [[r"\Seen"], [r"\Flagged"], []])

    def test_bad_password_is_scrubbed(self):
        with mock.patch.dict(os.environ, {PW_ENV: "wrong-fake-pass"}):
            with self.assertRaises(RuntimeError) as cm:
                imap.fetch(fake_acc(self.fake))
        self.assertIn("AUTHENTICATIONFAILED", str(cm.exception))
        self.assertNotIn("wrong-fake-pass", str(cm.exception))
        self.assertNotIn("EXAMINE", self.fake.verbs())

    def test_check(self):
        out = imap.check(fake_acc(self.fake))
        self.assertEqual(out, {"ok": True, "host": "127.0.0.1", "mailbox": "INBOX", "exists": 3})
        self.assertNotIn("UID FETCH", self.fake.verbs())


class SourceGuardTest(unittest.TestCase):
    SRC = (Path(__file__).resolve().parents[1] / "server" / "features" / "imap.py").read_text()

    def test_no_mutating_imap_calls(self):
        used = set(re.findall(r"\bconn\.(\w+)\(", self.SRC))
        self.assertTrue(used)
        self.assertLessEqual(used, {"login", "select", "uid", "response", "logout", "starttls"})
        self.assertEqual(set(re.findall(r'\bconn\.uid\("(\w+)"', self.SRC)), {"SEARCH", "FETCH"})
        self.assertNotIn("readonly=False", self.SRC)
        self.assertIn("readonly=True", self.SRC)
        self.assertNotRegex(self.SRC, r'"\(?(UID )?(STORE|EXPUNGE|COPY|MOVE)')
        self.assertNotRegex(self.SRC, r"BODY\[\]")

    def test_registered_as_driver(self):
        self.assertIs(srv.yhbmail.DRIVERS.get("imap"), imap.fetch)


if __name__ == "__main__":
    unittest.main()
