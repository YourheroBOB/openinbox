"""F23 mark all read across accounts, and F26 new-mail polling via /api/new-since."""
from __future__ import annotations

import unittest

import _tpi_server as srv
from _tpi_mailops_util import DEMO, add_mail, mid, reset

yhbmail = srv.yhbmail
SIDE, TEAM = "side@example.com", "team@example.com"


def unread_ids(account: str = "") -> set[str]:
    _, d = srv.get("/api/inbox?limit=500" + (f"&account={account}" if account else ""))
    return {e["id"] for e in d["emails"] if e["unread"]}


class MarkAllReadTest(unittest.TestCase):
    def setUp(self):
        reset()
        add_mail(f"imap:{SIDE}:INBOX:1:1", SIDE, "Side unread one")
        add_mail(f"imap:{SIDE}:INBOX:1:2", SIDE, "Side unread two")
        add_mail(f"imap:{TEAM}:INBOX:1:1", TEAM, "Team unread")
        add_mail(f"imap:{TEAM}:INBOX:1:2", TEAM, "Team read", unread=False)

    @classmethod
    def tearDownClass(cls):
        reset()

    def test_every_account_at_once(self):
        demo_unread = sum(1 for e in srv.FIXTURE["emails"] if e.get("unread"))
        status, d = srv.post("/api/mailops/mark-all-read", {"lang": "zh-Hant"})
        self.assertEqual(status, 200)
        self.assertEqual(d["marked"], demo_unread + 3)
        self.assertEqual(d["accounts"], {DEMO: demo_unread, SIDE: 2, TEAM: 1})
        self.assertIn("3 個帳號", d["note"])
        self.assertEqual(unread_ids(), set())
        _, f = srv.get("/api/mailops/folders")
        self.assertEqual(f["folders"][0]["unread"], 0)
        _, en = srv.post("/api/mailops/mark-all-read", {})
        self.assertEqual(en["marked"], 0)
        self.assertIn("across 0 account(s)", en["note"])

    def test_one_account_only(self):
        _, d = srv.post("/api/mailops/mark-all-read", {"account": SIDE})
        self.assertEqual(d["accounts"], {SIDE: 2})
        self.assertEqual(unread_ids(SIDE), set())
        self.assertEqual(unread_ids(TEAM), {f"imap:{TEAM}:INBOX:1:1"})
        self.assertTrue(unread_ids(DEMO))

    def test_folder_scope(self):
        srv.post("/api/mailops/action", {"ids": [mid(1)], "action": "archive"})
        _, d = srv.post("/api/mailops/mark-all-read", {"folder": "archive"})
        self.assertEqual(d["marked"], 1)
        self.assertNotIn(mid(1), unread_ids())
        self.assertIn(mid(2), unread_ids())
        status, _ = srv.post("/api/mailops/mark-all-read", {"folder": "spam"})
        self.assertEqual(status, 400)

    def test_local_read_survives_resync(self):
        srv.post("/api/mailops/mark-all-read", {"account": DEMO})
        srv.reseed()  # the fixture copies its unread flags back into the cache
        _, d = srv.get("/api/mailops/list?folder=inbox&account=" + DEMO)
        self.assertFalse(any(e["unread"] for e in d["emails"]))
        self.assertEqual(unread_ids(DEMO), set())

    def test_unread_action_wins_over_earlier_read(self):
        srv.post("/api/mailops/mark-all-read", {})
        status, d = srv.post("/api/mailops/action", {"ids": [mid(2)], "action": "unread"})
        self.assertEqual(status, 200)
        srv.reseed()
        _, f = srv.get("/api/mailops/list?folder=inbox")
        self.assertEqual({e["id"] for e in f["emails"] if e["unread"]}, {mid(2)})
        srv.post("/api/mailops/action", {"ids": [mid(2)], "action": "read"})
        self.assertNotIn(mid(2), unread_ids())


class NewSinceTest(unittest.TestCase):
    def setUp(self):
        reset()

    @classmethod
    def tearDownClass(cls):
        reset()

    def test_baseline_then_new_mail(self):
        status, base = srv.get("/api/new-since")
        self.assertEqual(status, 200)
        self.assertTrue(base["baseline"])
        self.assertEqual((base["count"], base["emails"]), (0, []))
        cursor = base["cursor"]
        self.assertGreaterEqual(cursor, srv.N_EMAILS)
        _, same = srv.get(f"/api/new-since?cursor={cursor}")
        self.assertEqual(same["count"], 0)
        add_mail(f"imap:{SIDE}:INBOX:1:5", SIDE, "Fresh arrival", body="hello")
        add_mail(f"imap:{SIDE}:INBOX:1:6", SIDE, "Already read", unread=False)
        _, d = srv.get(f"/api/new-since?cursor={cursor}")
        self.assertEqual(d["count"], 1)
        self.assertEqual(d["emails"][0]["subject"], "Fresh arrival")
        self.assertEqual(d["emails"][0]["account"], SIDE)
        self.assertEqual(d["cursor"], cursor + 2)
        _, after = srv.get(f"/api/new-since?cursor={d['cursor']}")
        self.assertEqual(after["count"], 0)

    def test_resync_is_not_new(self):
        cursor = srv.get("/api/new-since")[1]["cursor"]
        srv.reseed()
        self.assertEqual(srv.get(f"/api/new-since?cursor={cursor}")[1]["count"], 0)

    def test_archived_or_other_account_skipped(self):
        cursor = srv.get("/api/new-since")[1]["cursor"]
        add_mail(f"imap:{SIDE}:INBOX:1:7", SIDE, "Will be archived")
        add_mail(f"imap:{TEAM}:INBOX:1:7", TEAM, "Team news")
        srv.post("/api/mailops/action", {"ids": [f"imap:{SIDE}:INBOX:1:7"], "action": "archive"})
        _, d = srv.get(f"/api/new-since?cursor={cursor}")
        self.assertEqual([e["subject"] for e in d["emails"]], ["Team news"])
        _, side = srv.get(f"/api/new-since?cursor={cursor}&account={TEAM}")
        self.assertEqual(side["count"], 1)
        _, none = srv.get(f"/api/new-since?cursor={cursor}&account={SIDE}")
        self.assertEqual(none["count"], 0)

    def test_cursor_after_cache_reset(self):
        _, d = srv.get("/api/new-since?cursor=999999")
        self.assertTrue(d["reset"])
        self.assertEqual(d["count"], 0)
        self.assertLess(d["cursor"], 999999)

    def test_since_timestamp(self):
        add_mail(f"imap:{SIDE}:INBOX:1:8", SIDE, "Future dated", date_raw="2030-01-01 08:00")
        ts = yhbmail.parse_date_ts("2029-12-31 00:00")
        _, d = srv.get(f"/api/new-since?since={ts}")
        self.assertEqual([e["subject"] for e in d["emails"]], ["Future dated"])
        self.assertIn("now", d)


if __name__ == "__main__":
    unittest.main()
