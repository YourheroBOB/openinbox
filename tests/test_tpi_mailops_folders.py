"""F22 folders: Inbox / Starred / Drafts / Sent / Archive / Trash and star / archive /
trash / move / restore / purge as local state. Fictional demo data only."""
from __future__ import annotations

import unittest

import _tpi_server as srv
from _tpi_mailops_util import DEMO, add_mail, mid, request_with_headers, reset


def ids(folder: str, **q) -> list[str]:
    qs = "&".join(f"{k}={v}" for k, v in q.items())
    status, d = srv.get(f"/api/mailops/list?folder={folder}&{qs}")
    assert status == 200, d
    return [e["id"] for e in d["emails"]]


def counts(account: str = "") -> dict:
    _, d = srv.get("/api/mailops/folders" + (f"?account={account}" if account else ""))
    return {f["id"]: f for f in d["folders"]}


def act(action: str, *item_ids: str, **extra):
    return srv.post("/api/mailops/action", {"ids": list(item_ids), "action": action, **extra})


class FoldersTest(unittest.TestCase):
    def setUp(self):
        reset()

    @classmethod
    def tearDownClass(cls):
        reset()

    def test_folder_list_and_names(self):
        _, en = srv.get("/api/mailops/folders")
        self.assertEqual([f["id"] for f in en["folders"]], ["inbox", "starred", "drafts", "sent", "archive", "trash"])
        self.assertEqual(en["folders"][0]["name"], "Inbox")
        _, zh = srv.get("/api/mailops/folders?lang=zh-Hant")
        self.assertEqual([f["name"] for f in zh["folders"]], ["收件匣", "已加星號", "草稿", "寄件備份", "封存", "垃圾桶"])
        c = counts()
        self.assertEqual(c["inbox"]["total"], srv.N_EMAILS)
        self.assertEqual(c["inbox"]["unread"], sum(1 for e in srv.FIXTURE["emails"] if e.get("unread")))
        self.assertEqual(c["archive"]["total"] + c["trash"]["total"] + c["starred"]["total"], 0)

    def test_sent_shows_demo_fixture_read_only(self):
        sent = ids("sent")
        self.assertEqual(len(sent), 9)
        self.assertNotIn(mid(1), sent)
        status, item = srv.get("/api/mailops/item?id=" + sent[0])
        self.assertEqual(status, 200)
        self.assertEqual((item["folder"], item["source"]), ("sent", "sent_fixture"))
        self.assertTrue(item["body_text"])
        self.assertEqual(counts()["sent"]["total"], 9)

    def test_star_and_unstar(self):
        status, d = act("star", mid(3))
        self.assertEqual((status, d["ok"], d["changed"]), (200, True, [mid(3)]))
        self.assertEqual(ids("starred"), [mid(3)])
        self.assertIn(mid(3), ids("inbox"), "starring keeps the mail in its folder")
        row = next(e for e in srv.get("/api/mailops/list?folder=inbox")[1]["emails"] if e["id"] == mid(3))
        self.assertTrue(row["starred"])
        act("unstar", mid(3))
        self.assertEqual(ids("starred"), [])

    def test_archive_trash_restore_move(self):
        act("archive", mid(1), mid(2))
        self.assertNotIn(mid(1), ids("inbox"))
        self.assertEqual(sorted(ids("archive")), sorted([mid(1), mid(2)]))
        act("trash", mid(2))
        self.assertEqual(ids("archive"), [mid(1)])
        self.assertEqual(ids("trash"), [mid(2)])
        act("restore", mid(2))
        self.assertIn(mid(2), ids("inbox"))
        status, d = act("move", mid(1), folder="trash")
        self.assertEqual(status, 200)
        self.assertEqual(ids("trash"), [mid(1)])
        act("move", mid(1), folder="inbox")
        self.assertIn(mid(1), ids("inbox"))
        c = counts()
        self.assertEqual(c["inbox"]["total"], srv.N_EMAILS)

    def test_starred_hides_trashed_mail(self):
        act("star", mid(4))
        act("trash", mid(4))
        self.assertEqual(ids("starred"), [])
        act("restore", mid(4))
        self.assertEqual(ids("starred"), [mid(4)])

    def test_purge_and_empty_trash(self):
        act("purge", mid(5))
        for f in ("inbox", "starred", "archive", "trash"):
            self.assertNotIn(mid(5), ids(f))
        act("trash", mid(6), mid(7))
        status, d = srv.post("/api/mailops/empty-trash", {"lang": "zh-Hant"})
        self.assertEqual((status, d["purged"]), (200, 2))
        self.assertIn("遠端信箱不變", d["note"])
        self.assertEqual(ids("trash"), [])
        self.assertEqual(counts()["inbox"]["total"], srv.N_EMAILS - 3)
        _, core = srv.get("/api/inbox?limit=200")
        self.assertEqual(len(core["emails"]), srv.N_EMAILS, "the cached mail itself is kept")

    def test_state_survives_resync(self):
        act("archive", mid(1))
        act("star", mid(2))
        srv.reseed()
        self.assertEqual(ids("archive"), [mid(1)])
        self.assertEqual(ids("starred"), [mid(2)])

    def test_sent_fixture_can_be_starred_and_trashed(self):
        sent = ids("sent")
        act("star", sent[0])
        self.assertIn(sent[0], ids("starred"))
        act("trash", sent[0])
        self.assertIn(sent[0], ids("trash"))
        self.assertNotIn(sent[0], ids("sent"))

    def test_labels_pick_default_folder(self):
        add_mail("imap:side@example.com:INBOX:1:7", "side@example.com", "Archived upstream draft", labels=["DRAFT"])
        add_mail("imap:side@example.com:INBOX:1:8", "side@example.com", "Pre-starred", labels=["INBOX", "STARRED"])
        self.assertIn("imap:side@example.com:INBOX:1:7", ids("drafts"))
        self.assertIn("imap:side@example.com:INBOX:1:8", ids("starred"))
        act("unstar", "imap:side@example.com:INBOX:1:8")
        self.assertNotIn("imap:side@example.com:INBOX:1:8", ids("starred"))

    def test_drafts_folder_lists_local_drafts(self):
        srv.post("/api/draft", {"account": DEMO, "to": "lee@example.com", "subject": "Venue follow-up", "body": "Draft body"})
        _, d = srv.get("/api/mailops/list?folder=drafts")
        draft = next(e for e in d["emails"] if e["kind"] == "draft")
        self.assertTrue(draft["id"].startswith("draft:"))
        self.assertEqual((draft["subject"], draft["to_addr"], draft["body"]), ("Venue follow-up", "lee@example.com", "Draft body"))
        self.assertEqual(counts()["drafts"]["total"], 1)

    def test_filters(self):
        add_mail("imap:side@example.com:INBOX:1:9", "side@example.com", "Quarterly venue budget", body="venue numbers")
        self.assertEqual(ids("inbox", account="side@example.com"), ["imap:side@example.com:INBOX:1:9"])
        self.assertIn("imap:side@example.com:INBOX:1:9", ids("inbox", q="venue"))
        self.assertEqual(counts("side@example.com")["inbox"]["total"], 1)
        needs = ids("inbox", category="needs_you")
        self.assertTrue(needs)
        _, d = srv.get("/api/mailops/list?folder=inbox&category=needs_you")
        self.assertTrue(all(e["category"] == "needs_you" for e in d["emails"]))

    def test_bad_requests(self):
        status, _ = srv.get("/api/mailops/list?folder=spam")
        self.assertEqual(status, 400)
        status, d = act("explode", mid(1))
        self.assertEqual(status, 400)
        status, d = act("move", mid(1), folder="sent")
        self.assertEqual(status, 400)
        status, d = act("archive", "demo:you@example.com:nope")
        self.assertEqual((status, d["ok"], d["unknown"]), (404, False, ["demo:you@example.com:nope"]))
        status, _ = srv.post("/api/mailops/action", {"action": "star", "lang": "zh-Hant"})
        self.assertEqual(status, 400)
        status, _ = srv.get("/api/mailops/item?id=missing")
        self.assertEqual(status, 404)

    def test_cross_origin_writes_refused(self):
        for origin in ("http://evil.example", "http://127.0.0.1:1"):
            status, _, raw = request_with_headers(
                "POST", "/api/mailops/action", {"ids": [mid(1)], "action": "archive"}, {"Origin": origin})
            self.assertEqual(status, 403, raw)
        self.assertNotIn(mid(1), ids("archive"))
        port = srv.SERVER.server_address[1]
        status, _, _ = request_with_headers(
            "POST", "/api/mailops/action", {"ids": [mid(1)], "action": "archive"}, {"Origin": f"http://127.0.0.1:{port}"})
        self.assertEqual(status, 200)


if __name__ == "__main__":
    unittest.main()
