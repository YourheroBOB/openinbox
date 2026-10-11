"""Contacts list and search (/api/contacts) built from the local mail cache."""
from __future__ import annotations

import unittest
from urllib.parse import quote

import _tpi_server as srv

EXTRA = {
    "id": "test:contacts:zh1", "account": "you@example.com", "platform": "demo",
    "subject": "報價單", "snippet": "附上報價單",
    "from_addr": "王小明 <xiaoming@example.com>",
    "to_addr": "you@example.com, 陳小華 <xiaohua@example.com>",
    "date_raw": "2026-09-12 09:00", "unread": True, "has_attachment": True, "body_text": "附上報價單。",
}


def contacts(query=""):
    status, d = srv.get("/api/contacts" + query)
    assert status == 200, d
    return d


def emails(d):
    return [c["email"] for c in d["contacts"]]


class ContactsTest(unittest.TestCase):
    def setUp(self):
        self._drop()
        srv.reseed()

    @staticmethod
    def _drop():
        con = srv.yhbmail.db()
        con.execute("DELETE FROM emails WHERE id LIKE 'test:contacts:%'")
        con.commit()
        con.close()

    def test_list_from_fixture_senders(self):
        d = contacts()
        self.assertEqual(d["total"], 7)
        self.assertNotIn("you@example.com", emails(d))
        top = d["contacts"][0]
        self.assertEqual((top["email"], top["name"], top["received"], top["count"]),
                         ("samira@northwind.example", "Samira Ortiz", 2, 2))
        self.assertEqual(top["search_query"], "from:samira@northwind.example")
        self.assertEqual(top["last_date"], "2026-09-16 09:12")
        self.assertEqual(top["attachments"], 1)

    def test_search_by_name_address_domain(self):
        self.assertEqual(emails(contacts("?q=maya"))[0], "maya@studio.example")
        self.assertEqual(emails(contacts("?q=ortiz")), ["samira@northwind.example"])
        self.assertEqual(emails(contacts("?q=northwind")), ["samira@northwind.example"])
        self.assertEqual(contacts("?q=" + quote("Samira Ortiz"))["contacts"][0]["score"], 100)
        self.assertEqual(contacts("?q=zzzz")["total"], 0)

    def test_people_filter_and_sorting(self):
        people = contacts("?people=1")
        self.assertEqual(people["total"], 5)
        self.assertFalse(any(c["automated"] for c in people["contacts"]))
        names = [c["name"] for c in contacts("?sort=name")["contacts"]]
        self.assertEqual(names, sorted(names, key=str.lower))
        recent = contacts("?sort=recent")["contacts"]
        self.assertEqual(recent[0]["email"], "samira@northwind.example")
        status, _ = srv.get("/api/contacts?sort=bogus")
        self.assertEqual(status, 400)

    def test_detail(self):
        status, c = srv.get("/api/contacts/" + quote("samira@northwind.example"))
        self.assertEqual(status, 200)
        self.assertEqual([m["id"][-2:] for m in c["emails"]], ["m1", "m7"])
        self.assertTrue(all(m["direction"] == "from" for m in c["emails"]))
        status, _ = srv.get("/api/contacts/nobody@example.com")
        self.assertEqual(status, 404)

    def test_cjk_contacts_and_recipients(self):
        self.addCleanup(self._drop)
        con = srv.yhbmail.db()
        srv.yhbmail.upsert_email(con, EXTRA)
        con.commit()
        con.close()
        d = contacts()
        self.assertEqual(d["total"], 9)
        cc = next(c for c in d["contacts"] if c["email"] == "xiaohua@example.com")
        self.assertEqual((cc["name"], cc["received"], cc["cc"]), ("陳小華", 0, 1))
        self.assertEqual(emails(contacts("?q=" + quote("小明"))), ["xiaoming@example.com"])
        self.assertEqual(emails(contacts("?q=" + quote("王"))), ["xiaoming@example.com"])
        status, c = srv.get("/api/contacts/xiaohua@example.com")
        self.assertEqual([m["direction"] for m in c["emails"]], ["to"])

    def test_contact_feeds_search(self):
        status, d = srv.get("/api/search?q=" + quote("from:samira@northwind.example"))
        self.assertEqual(status, 200)
        self.assertEqual(d["total"], 2)
        status, d = srv.get("/api/search?q=" + quote("from northwind"))
        self.assertEqual(d["parsed"]["contacts"]["northwind"][0]["email"], "samira@northwind.example")
        self.assertEqual(d["total"], 2)


if __name__ == "__main__":
    unittest.main()
