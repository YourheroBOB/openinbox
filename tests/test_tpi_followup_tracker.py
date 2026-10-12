"""F29 follow-up tracker: threads you wrote last surface after N days without a reply."""
from __future__ import annotations

import unittest
from urllib.parse import quote

import _tpi_followup_util as fu
import _tpi_server as srv


def listing(**params) -> dict:
    params.setdefault("now", fu.NOW)
    q = "&".join(f"{k}={quote(str(v))}" for k, v in params.items())
    status, data = srv.get("/api/followup?" + q)
    assert status == 200, data
    return data


def by_subject(data: dict, subject: str) -> dict | None:
    return next((i for i in data["items"] if i["subject"] == subject), None)


class FollowupTrackerTest(unittest.TestCase):
    def setUp(self):
        self.base = fu.Baseline()

    def tearDown(self):
        self.base.restore()

    def test_overdue_waiting_and_answered(self):
        d = listing()
        self.assertEqual(d["days"], 3)
        self.assertEqual(d["counts"]["overdue"], 2)
        self.assertEqual(d["counts"]["waiting"], 5)
        self.assertEqual(d["counts"]["answered"], 2)
        first = d["items"][0]
        self.assertEqual(first["status"], "overdue")
        self.assertEqual(first["subject"], "Byte Cloud renewal on the 20th: switch to annual?")
        self.assertEqual(first["first_name"], "Jordan")
        self.assertTrue(first["asked"])
        self.assertIn("check the balance", first["question"])
        self.assertGreaterEqual(first["waiting_days"], 4)
        for item in d["items"]:
            self.assertTrue(item["to_email"].endswith(".example") or item["to_email"].endswith("example.com"))
        self.assertIsNone(by_subject(d, "Contract designer brief"), "Priya replied to the brief")

    def test_days_threshold(self):
        three = listing()["counts"]["overdue"]
        one = listing(days=1)
        self.assertGreater(one["counts"]["overdue"], three)
        for item in one["items"]:
            if item["status"] == "overdue":
                self.assertGreaterEqual(item["days_waiting"], 1)
            else:
                self.assertLess(item["days_waiting"], 1)
        self.assertEqual(listing(days=30)["counts"]["overdue"], 0)

    def test_saved_setting_is_the_default(self):
        status, s = srv.post("/api/followup/settings", {"days": 1})
        self.assertEqual((status, s["days"]), (200, 1))
        self.assertEqual(listing()["days"], 1)
        self.assertEqual(srv.get("/api/followup/settings")[1]["days"], 1)
        self.assertEqual(srv.post("/api/followup/settings", {"days": 0})[0], 400)
        self.assertEqual(srv.post("/api/followup/settings", {"days": "x"})[0], 400)
        status, _ = fu.post_from("/api/followup/settings", {"days": 9}, "https://evil.example.com")
        self.assertEqual(status, 403)
        self.assertEqual(listing()["days"], 1)

    def test_reply_in_thread_clears_it(self):
        subject = "Byte Cloud renewal on the 20th: switch to annual?"
        self.assertIsNotNone(by_subject(listing(), subject))
        fu.add_email("test:fu:reply1", "Re: " + subject, "Jordan Lee <jordan@quillmark.example>",
                     "2026-09-18 08:00", "Balance is fine, annual it is.", thread_id="s4")
        d = listing()
        self.assertIsNone(by_subject(d, subject))
        self.assertEqual(d["counts"]["answered"], 3)

    def test_reply_matched_by_subject_and_sender(self):
        subject = "Northwind investor call prep"
        self.assertIsNotNone(by_subject(listing(), subject))
        fu.add_email("test:fu:reply2", "RE: " + subject, "Jordan Lee <jordan@quillmark.example>",
                     "2026-09-18 09:30", "On it.", thread_id="other-thread")
        self.assertIsNone(by_subject(listing(), subject))
        fu.add_email("test:fu:reply3", "Re: Design review notes", "Someone Else <else@example.com>",
                     "2026-09-18 19:00", "Not the recipient.", thread_id="unrelated")
        self.assertIsNotNone(by_subject(listing(), "Design review notes"), "only a recipient's reply counts")

    def test_mail_from_your_own_account_counts_as_sent(self):
        fu.add_email("test:fu:own1", "Quote for the spring workshop", fu.ME, "2026-09-12 10:00",
                     "Hi Robin,\n\nCould you send the quote by Friday?\n\nThanks,\nAlex", thread_id="own1",
                     to_addr="Robin Park <robin@example.com>")
        fu.add_email("test:fu:own2", "Unsubscribe me", fu.ME, "2026-09-12 10:00", "Please remove me.",
                     thread_id="own2", to_addr="noreply@example.com")
        d = listing()
        item = by_subject(d, "Quote for the spring workshop")
        self.assertIsNotNone(item)
        self.assertTrue(item["in_db"])
        self.assertEqual((item["status"], item["first_name"], item["to_email"]), ("overdue", "Robin", "robin@example.com"))
        self.assertIsNone(by_subject(d, "Unsubscribe me"), "bulk recipients are not followed up")

    def test_snooze_done_reopen(self):
        thread = listing()["items"][0]["thread"]
        status, out = srv.post("/api/followup/state", {"thread": thread, "action": "snooze", "days": 2, "now": fu.NOW})
        self.assertEqual(status, 200)
        self.assertEqual(out["item"]["status"], "snoozed")
        self.assertEqual(listing()["counts"]["snoozed"], 1)
        later = listing(now="2026-09-22 09:00")
        self.assertEqual(next(i for i in later["items"] if i["thread"] == thread)["status"], "overdue")
        srv.post("/api/followup/state", {"thread": thread, "action": "done", "now": fu.NOW})
        self.assertEqual(next(i for i in listing()["items"] if i["thread"] == thread)["status"], "done")
        self.assertNotIn(thread, [i["thread"] for i in listing(status="open")["items"]])
        srv.post("/api/followup/state", {"thread": thread, "action": "reopen", "now": fu.NOW})
        self.assertEqual(next(i for i in listing()["items"] if i["thread"] == thread)["status"], "overdue")
        self.assertEqual(srv.post("/api/followup/state", {"thread": thread, "action": "send"})[0], 400)
        self.assertEqual(srv.post("/api/followup/state", {"thread": "nope", "action": "done"})[0], 404)

    def test_done_resets_when_you_write_again(self):
        fu.add_email("test:fu:own3", "Venue options", fu.ME, "2026-09-10 10:00", "Can you pick one?",
                     thread_id="venue", to_addr="Robin Park <robin@example.com>")
        thread = by_subject(listing(), "Venue options")["thread"]
        srv.post("/api/followup/state", {"thread": thread, "action": "done", "now": fu.NOW})
        self.assertEqual(by_subject(listing(), "Venue options")["status"], "done")
        fu.add_email("test:fu:own4", "Venue options", fu.ME, "2026-09-14 10:00", "Any thoughts?",
                     thread_id="venue", to_addr="Robin Park <robin@example.com>")
        self.assertEqual(by_subject(listing(), "Venue options")["status"], "overdue")

    def test_nudge_is_a_local_draft_made_once(self):
        item = listing()["items"][0]
        status, out = srv.post("/api/followup/nudge", {"thread": item["thread"], "now": fu.NOW})
        self.assertEqual(status, 201, out)
        self.assertFalse(out["existing"])
        self.assertIn("Hi Jordan,", out["body"])
        self.assertIn("check the balance", out["body"])
        self.assertTrue(out["subject"].startswith("Re: "))
        self.assertIn("Nothing is sent", out["note"])
        drafts = srv.get("/api/drafts")[1]["drafts"]
        self.assertIn(out["draft_id"], [x["id"] for x in drafts])
        again_status, again = srv.post("/api/followup/nudge", {"thread": item["thread"], "now": fu.NOW})
        self.assertEqual((again_status, again["existing"], again["draft_id"]), (200, True, out["draft_id"]))
        self.assertEqual(listing()["items"][0]["nudge_draft_id"], out["draft_id"])
        status, _ = fu.post_from("/api/followup/nudge", {"thread": item["thread"]}, "https://evil.example.com")
        self.assertEqual(status, 403)

    def test_chinese_thread_gets_a_chinese_nudge(self):
        d = listing(now="2026-09-25 09:00")
        item = by_subject(d, "Byte Cloud 續約確認")
        self.assertEqual((item["status"], item["lang"]), ("overdue", "zh"))
        status, out = srv.post("/api/followup/nudge", {"thread": item["thread"], "now": "2026-09-25 09:00",
                                                        "lang": "zh-Hant"})
        self.assertEqual(status, 201)
        self.assertIn("Jordan 你好", out["body"])
        self.assertIn("想跟進一下", out["body"])
        self.assertIn("不會寄出", out["note"])

    def test_only_questions_filter(self):
        d = listing(only_questions=1)
        self.assertTrue(d["items"])
        self.assertTrue(all(i["asked"] for i in d["items"]))


if __name__ == "__main__":
    unittest.main()
