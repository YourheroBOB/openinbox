"""F27 account settings written to accounts.json (add / remove / reorder / primary) and
per-account signatures, typed or imported from a file. Fictional example.com accounts only."""
from __future__ import annotations

import json
import unittest

import _tpi_server as srv
from _tpi_mailops_util import DEMO, request_with_headers, reset

yhbmail = srv.yhbmail
PATH = yhbmail.ACCOUNTS_PATH


def on_disk() -> dict:
    return json.loads(PATH.read_text())


def emails() -> list[str]:
    return [a["email"] for a in on_disk()["accounts"]]


def add(**body):
    return srv.post("/api/mailops/accounts/add", body)


class AccountSettingsTest(unittest.TestCase):
    def setUp(self):
        reset()

    @classmethod
    def tearDownClass(cls):
        reset()

    def test_listing_without_file_uses_example(self):
        self.assertFalse(PATH.exists())
        _, d = srv.get("/api/mailops/accounts")
        self.assertFalse(d["exists"])
        self.assertEqual(d["mode"], "demo")
        self.assertEqual([(a["email"], a["primary"]) for a in d["accounts"]], [(DEMO, True)])
        self.assertEqual(d["drivers"], ["demo", "gog", "gsk", "imap"])

    def test_add_writes_accounts_json(self):
        status, d = add(email="work@example.com", label="Work", driver="gog", lang="zh-Hant")
        self.assertEqual(status, 201)
        self.assertIn("accounts.json", d["note"])
        self.assertIn("live", d["note"])
        cfg = on_disk()
        self.assertEqual(cfg["mode"], "live")
        self.assertEqual(cfg["calendars"], [], "other keys of the example are kept")
        self.assertEqual(cfg["accounts"][1], {"email": "work@example.com", "driver": "gog", "label": "Work", "platform": "gmail"})
        _, core = srv.get("/api/accounts")
        self.assertEqual([a["email"] for a in core["accounts"]], [DEMO, "work@example.com"])
        _, prov = srv.get("/api/providers")
        self.assertIn("work@example.com", [a["email"] for a in prov["accounts"]])

    def test_add_imap_with_password_env_only(self):
        status, d = add(email="box@example.com", driver="imap", host="imap.example.com", port="993",
                        password_env="TPI_IMAP_PASSWORD_BOX", primary=True)
        self.assertEqual(status, 201, d)
        acc = on_disk()["accounts"][0]
        self.assertEqual((acc["email"], acc["port"], acc["password_env"], acc["host"]),
                         ("box@example.com", 993, "TPI_IMAP_PASSWORD_BOX", "imap.example.com"))
        self.assertTrue(d["accounts"][0]["primary"])
        status, d = add(email="pw@example.com", driver="imap", password="hunter2-fake")
        self.assertEqual(status, 400)
        self.assertIn("password_env", d["error"])
        self.assertNotIn("hunter2-fake", PATH.read_text())
        status, d = add(email="env@example.com", driver="imap", password_env="lower case; rm")
        self.assertEqual(status, 400)
        status, d = add(email="port@example.com", driver="imap", port="99999")
        self.assertEqual(status, 400)

    def test_add_validation(self):
        self.assertEqual(add(email="not-an-email")[0], 400)
        self.assertEqual(add(email="x@example.com", driver="pop3")[0], 400)
        add(email="dup@example.com", driver="gsk")
        status, d = add(email="DUP@example.com", driver="gsk", lang="zh-Hant")
        self.assertEqual(status, 409)
        self.assertIn("已有", d["error"])

    def test_remove_reorder_primary(self):
        add(email="a@example.com", driver="gog")
        add(email="b@example.com", driver="gsk")
        self.assertEqual(emails(), [DEMO, "a@example.com", "b@example.com"])
        status, d = srv.post("/api/mailops/accounts/primary", {"email": "b@example.com"})
        self.assertEqual(status, 200)
        self.assertEqual(emails(), ["b@example.com", DEMO, "a@example.com"])
        self.assertEqual([a["primary"] for a in d["accounts"]], [True, False, False])
        status, _ = srv.post("/api/mailops/accounts/reorder", {"order": ["a@example.com", "b@example.com", DEMO]})
        self.assertEqual(status, 200)
        self.assertEqual(emails(), ["a@example.com", "b@example.com", DEMO])
        for bad in (["a@example.com"], ["a@example.com", "a@example.com", DEMO], [], "nope"):
            status, _ = srv.post("/api/mailops/accounts/reorder", {"order": bad})
            self.assertEqual(status, 400, bad)
        self.assertEqual(emails(), ["a@example.com", "b@example.com", DEMO])
        status, d = srv.post("/api/mailops/accounts/remove", {"email": "a@example.com"})
        self.assertEqual(status, 200)
        self.assertEqual(emails(), ["b@example.com", DEMO])
        self.assertEqual(srv.post("/api/mailops/accounts/remove", {"email": "ghost@example.com"})[0], 404)
        srv.post("/api/mailops/accounts/remove", {"email": "b@example.com"})
        self.assertEqual(on_disk()["mode"], "demo", "only demo accounts left -> back to demo mode")

    def test_cross_origin_refused(self):
        status, _, _ = request_with_headers("POST", "/api/mailops/accounts/add",
                                            {"email": "evil@example.com", "driver": "gog"},
                                            {"Origin": "http://evil.example"})
        self.assertEqual(status, 403)
        self.assertFalse(PATH.exists())


class SignatureTest(unittest.TestCase):
    def setUp(self):
        reset()
        add(email="work@example.com", label="Work", driver="gog")

    @classmethod
    def tearDownClass(cls):
        reset()

    def test_save_and_clear(self):
        status, d = srv.post("/api/mailops/signature", {"email": "work@example.com",
                                                        "signature": "Pat Doe\r\nExample Co   \r\n", "lang": "zh-Hant"})
        self.assertEqual(status, 200)
        self.assertEqual(d["signature"], "Pat Doe\nExample Co")
        self.assertIn("簽名已存", d["note"])
        self.assertEqual(on_disk()["accounts"][1]["signature"], "Pat Doe\nExample Co")
        _, g = srv.get("/api/mailops/signature?account=work@example.com")
        self.assertEqual(g["signature"], "Pat Doe\nExample Co")
        _, first = srv.get("/api/mailops/signature")
        self.assertEqual((first["account"], first["signature"]), (DEMO, ""))
        srv.post("/api/mailops/signature", {"email": "work@example.com", "signature": ""})
        self.assertNotIn("signature", on_disk()["accounts"][1])
        self.assertEqual(srv.post("/api/mailops/signature", {"email": "work@example.com", "signature": 5})[0], 400)
        self.assertEqual(srv.post("/api/mailops/signature", {"email": "ghost@example.com", "signature": "x"})[0], 404)

    def test_each_account_has_its_own(self):
        srv.post("/api/mailops/signature", {"email": DEMO, "signature": "Demo person"})
        srv.post("/api/mailops/signature", {"email": "work@example.com", "signature": "Work person"})
        _, d = srv.get("/api/mailops/accounts")
        self.assertEqual({a["email"]: a["signature"] for a in d["accounts"]},
                         {DEMO: "Demo person", "work@example.com": "Work person"})

    def test_import_text_file(self):
        status, d = srv.post("/api/mailops/signature/import", {
            "email": "work@example.com", "filename": "work.sig",
            "content": "\ufeff\n-- \nPat Doe\nOps lead, Example Co\n"})
        self.assertEqual(status, 200, d)
        self.assertEqual(d["signature"], "Pat Doe\nOps lead, Example Co")
        self.assertEqual(d["imported_from"], "work.sig")

    def test_import_html_file(self):
        html = ("<html><head><style>p{color:red}</style></head><body><p>Pat&nbsp;Doe</p>"
                "<p><b>Example Co</b><br>+1 555 0100</p><script>alert(1)</script></body></html>")
        _, d = srv.post("/api/mailops/signature/import", {"email": "work@example.com", "filename": "sig.html", "content": html})
        self.assertEqual(d["signature"], "Pat Doe\nExample Co\n+1 555 0100")
        self.assertNotIn("alert", PATH.read_text())

    def test_import_rejects(self):
        cases = [
            {"filename": "sig.txt", "content": ""},
            {"filename": "sig.exe", "content": "MZ"},
            {"filename": "sig.txt", "content": "a\x00b"},
            {"filename": "sig.txt", "content": "x" * 200_001},
            {"filename": "sig.html", "content": "<p> </p>"},
        ]
        for body in cases:
            status, d = srv.post("/api/mailops/signature/import", {"email": "work@example.com", **body})
            self.assertEqual(status, 400, body["filename"])
        self.assertNotIn("signature", on_disk()["accounts"][1])

    def test_long_signature_is_capped(self):
        _, d = srv.post("/api/mailops/signature", {"email": "work@example.com", "signature": "y" * 9000})
        self.assertEqual(len(d["signature"]), 4000)


if __name__ == "__main__":
    unittest.main()
