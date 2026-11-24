"""Unified inbox: IMAP boxes sync next to other drivers, tagged by account, filterable,
listed on /api/providers without leaking secrets. Fake loopback IMAP only.
"""
from __future__ import annotations

import json
import os
import time
import unittest
from unittest import mock

import _tpi_server as srv
from _tpi_imap_fake import FakeIMAP, fictional_mail

yhbmail = srv.yhbmail
PW1, PW2 = "fake-pass-box", "fake-pass-side"
ENV = {"TPI_TEST_BOX_PW": PW1, "TPI_IMAP_PASSWORD_SIDE_EXAMPLE_COM": PW2}


def _imap(fake, email, label, **extra):
    return {"email": email, "driver": "imap", "label": label, "host": "127.0.0.1",
            "port": fake.port, "security": "none", **extra}


class UnifiedInboxTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.box = FakeIMAP(user="box@example.com", password=PW1)
        cls.side = FakeIMAP(user="side@example.com", password=PW2, mail=fictional_mail()[:1], uidvalidity=3)
        cls.env = mock.patch.dict(os.environ, ENV)
        cls.env.start()
        os.environ.pop("TPI_IMAP_PASSWORD_NOPW_EXAMPLE_COM", None)
        cfg = {"mode": "live", "accounts": [
            _imap(cls.box, "box@example.com", "Fake iCloud", provider="icloud", password_env="TPI_TEST_BOX_PW"),
            _imap(cls.side, "side@example.com", "Side box"),
            _imap(cls.side, "nopw@example.com", "No password"),
            _imap(cls.side, "plain@example.com", "Plaintext", password="should-never-be-used"),
            {"email": "team@example.com", "driver": "gsk", "label": "Outlook"},
        ]}
        yhbmail.ACCOUNTS_PATH.write_text(json.dumps(cfg))
        with mock.patch.dict(os.environ, {"PATH": "/nonexistent"}):
            cls.report = yhbmail.sync_all(25)

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()
        cls.box.close()
        cls.side.close()
        yhbmail.ACCOUNTS_PATH.unlink(missing_ok=True)
        con = yhbmail.db()
        con.execute("DELETE FROM emails WHERE platform != 'demo'")
        con.commit()
        con.close()
        yhbmail.LAST_SYNC.clear()
        srv.reseed()

    def test_sync_report_isolates_failures(self):
        acc = {a["email"]: a for a in self.report["accounts"]}
        self.assertEqual(self.report["mode"], "live")
        self.assertEqual(acc["box@example.com"]["count"], 3)
        self.assertEqual(acc["side@example.com"]["count"], 1)
        self.assertIn("TPI_IMAP_PASSWORD_NOPW_EXAMPLE_COM", acc["nopw@example.com"]["error"])
        self.assertIn("password_env", acc["plain@example.com"]["error"])
        self.assertIn("error", acc["team@example.com"])
        self.assertNotIn("should-never-be-used", json.dumps(self.report))

    def test_one_inbox_tagged_by_account(self):
        _, every = srv.get("/api/inbox?limit=200")
        accounts = {e["account"] for e in every["emails"]}
        self.assertLessEqual({"box@example.com", "side@example.com"}, accounts)
        _, box = srv.get("/api/inbox?account=box@example.com")
        self.assertEqual(len(box["emails"]), 3)
        self.assertTrue(all(e["account"] == "box@example.com" and e["platform"] == "icloud" for e in box["emails"]))
        _, side = srv.get("/api/inbox?account=side@example.com")
        self.assertEqual([e["platform"] for e in side["emails"]], ["imap"])
        self.assertEqual(side["emails"][0]["id"], "imap:side@example.com:INBOX:3:101")
        _, needs = srv.get("/api/inbox?account=box@example.com&category=needs_you")
        self.assertIn("Can you confirm the venue by Thursday?", [e["subject"] for e in needs["emails"]])
        _, hit = srv.get("/api/inbox?q=" + "venue")
        self.assertTrue({"box@example.com", "side@example.com"} <= {e["account"] for e in hit["emails"]})

    def test_thread_opens(self):
        status, item = srv.get("/api/thread/" + "imap:side@example.com:INBOX:3:101")
        self.assertEqual(status, 200)
        self.assertIn("Thursday 17:00", item["body_text"])

    def test_resync_is_idempotent(self):
        before = srv.get("/api/inbox?account=box@example.com")[1]["emails"]
        yhbmail.sync_all(25)
        after = srv.get("/api/inbox?account=box@example.com")[1]["emails"]
        self.assertEqual(sorted(e["id"] for e in before), sorted(e["id"] for e in after))

    def test_providers_endpoint(self):
        status, d = srv.get("/api/providers?lang=zh-Hant")
        self.assertEqual(status, 200)
        self.assertEqual(d["mode"], "live")
        self.assertIn({"id": "imap", "name": "IMAP 唯讀"}, d["drivers"])
        self.assertIn("icloud", [p["id"] for p in d["imap_presets"]])
        acc = {a["email"]: a for a in d["accounts"]}
        box = acc["box@example.com"]
        self.assertEqual((box["label"], box["driver"], box["provider"], box["platform"]),
                         ("Fake iCloud", "imap", "icloud", "icloud"))
        self.assertEqual((box["total"], box["credentials"], box["password_env"]), (3, "env", "TPI_TEST_BOX_PW"))
        self.assertEqual(box["unread"], 2)
        self.assertEqual(box["last_sync"]["count"], 3)
        self.assertEqual(acc["side@example.com"]["password_env"], "TPI_IMAP_PASSWORD_SIDE_EXAMPLE_COM")
        self.assertEqual(acc["nopw@example.com"]["credentials"], "missing")
        self.assertIn("error", acc["nopw@example.com"]["last_sync"])
        self.assertEqual(acc["plain@example.com"]["credentials"], "plaintext_rejected")
        self.assertEqual(acc["team@example.com"]["driver"], "gsk")
        self.assertNotIn("credentials", acc["team@example.com"])
        self.assertNotIn("you@example.com", acc)
        _, en = srv.get("/api/providers")
        self.assertIn({"id": "imap", "name": "IMAP read-only"}, en["drivers"])

    def test_no_secret_leaves_the_server(self):
        for path in ("/api/providers", "/api/accounts", "/api/health", "/api/features"):
            _, _, raw = srv.request("GET", path)
            text = raw.decode()
            for secret in (PW1, PW2, "should-never-be-used"):
                self.assertNotIn(secret, text, path)

    def test_check_endpoint(self):
        status, ok = srv.post("/api/providers/check", {"email": "box@example.com", "lang": "zh-Hant"})
        self.assertEqual(status, 200)
        self.assertTrue(ok["ok"])
        self.assertEqual(ok["exists"], 3)
        self.assertIn("唯讀", ok["note"])
        status, en = srv.post("/api/providers/check", {"email": "side@example.com"})
        self.assertIn("read-only", en["note"])
        _, bad = srv.post("/api/providers/check", {"email": "nopw@example.com"})
        self.assertFalse(bad["ok"])
        self.assertIn("TPI_IMAP_PASSWORD_NOPW_EXAMPLE_COM", bad["error"])
        status, _ = srv.post("/api/providers/check", {"email": "ghost@example.com"})
        self.assertEqual(status, 404)
        status, _ = srv.post("/api/providers/check", {"email": "team@example.com"})
        self.assertEqual(status, 400)

    def test_sync_over_http(self):
        yhbmail.LAST_SYNC.clear()
        with mock.patch.dict(os.environ, {"PATH": "/nonexistent"}):
            status, r = srv.post("/api/sync", {"limit": 10})
            self.assertEqual((status, r["started"]), (200, True))
            for _ in range(100):
                time.sleep(0.1)
                h = srv.get("/api/health")[1]
                if yhbmail.LAST_SYNC and not h["sync"]["running"]:
                    break
        self.assertIsNotNone(h["sync"]["error"])
        _, d = srv.get("/api/providers")
        box = next(a for a in d["accounts"] if a["email"] == "box@example.com")
        self.assertEqual(box["last_sync"]["count"], 3)


if __name__ == "__main__":
    unittest.main()
