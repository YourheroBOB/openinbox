"""Attachment flag, suggested next actions, tasks and task history."""
from __future__ import annotations

import unittest

import _tpi_server as srv
import features.triage as triage

M = "demo:you@example.com:"


def items_by_short_id(lang="en"):
    _, data = srv.get(f"/api/triage?lang={lang}")
    return {i["id"].rsplit(":", 1)[-1]: i for lane in data["lanes"] for i in lane["items"]}


class AttachmentAndActionsTest(unittest.TestCase):
    def setUp(self):
        srv.reseed()

    def test_attachment_flags(self):
        items = items_by_short_id()
        self.assertTrue(items["m3"]["has_attachment"])
        self.assertTrue(items["m3"]["attachment"]["flagged"])
        self.assertTrue(items["m7"]["attachment"]["flagged"])
        self.assertTrue(items["m4"]["has_attachment"], "body says 'Calendar invite attached'")
        self.assertFalse(items["m4"]["attachment"]["flagged"])
        self.assertTrue(items["m4"]["attachment"]["mentioned"])
        self.assertFalse(items["m1"]["has_attachment"])
        info = triage.attachment_info({"body_text": "See budget-2026.xlsx and notes.pdf, then notes.pdf again."})
        self.assertEqual(info["names"], ["budget-2026.xlsx", "notes.pdf"])
        self.assertTrue(info["has"])

    def test_suggested_actions(self):
        items = items_by_short_id()
        kinds = {k: [a["kind"] for a in v["suggested_actions"]] for k, v in items.items()}
        self.assertEqual(kinds["m1"][0], "reply")
        self.assertEqual(kinds["m2"][0], "review", "automated sender: review, not reply")
        self.assertNotIn("reply", kinds["m2"])
        self.assertIn("read_attachment", kinds["m3"])
        self.assertIn("pay_or_file", kinds["m3"])
        self.assertIn("rsvp", kinds["m4"])
        self.assertIn("read_attachment", kinds["m4"])
        self.assertIn("unsubscribe", kinds["m6"])
        self.assertIn("mark_read", kinds["m6"])
        self.assertIn("reply", kinds["m7"])
        for it in items.values():
            acts = it["suggested_actions"]
            self.assertTrue(acts)
            self.assertEqual([a["primary"] for a in acts], [True] + [False] * (len(acts) - 1))
            for a in acts:
                self.assertIn(a["ui"], {"draft", "open", "calendar", "task", "mark_read"})
                self.assertTrue(a["label"] and a["reason"])

    def test_action_labels_in_chinese(self):
        items = items_by_short_id("zh-Hant")
        self.assertEqual(items["m1"]["suggested_actions"][0]["label"], "起草回覆")
        self.assertEqual(items["m1"]["suggested_actions"][0]["reason"], "對方在等你回覆。")

    def test_fallback_action(self):
        acts = triage.suggested_actions({"category": "fyi", "from_addr": "Pat <pat@studio.example>",
                                         "body_text": "Shipped.", "unread": 0})
        self.assertEqual([a["kind"] for a in acts], ["follow_up"])

    def test_item_endpoint(self):
        status, it = srv.get("/api/triage/item/" + M + "m4")
        self.assertEqual(status, 200)
        self.assertEqual(it["lane"], "upcoming_today")
        self.assertIn("tasks", it)
        self.assertIn("history", it)
        self.assertEqual(srv.get("/api/triage/item/nope")[0], 404)


class TasksAndHistoryTest(unittest.TestCase):
    def setUp(self):
        srv.reseed()

    def test_task_lifecycle_and_history(self):
        status, task = srv.post("/api/triage/tasks", {"email_id": M + "m1", "action": "reply", "note": "after lunch"})
        self.assertEqual(status, 201)
        self.assertEqual(task["status"], "open")
        self.assertEqual(task["label"], "Draft a reply")
        self.assertEqual(task["subject"], "Can you confirm the Friday scope before we send the deck?")
        self.assertEqual(task["note"], "after lunch")

        items = items_by_short_id()
        self.assertGreaterEqual(items["m1"]["open_tasks"], 1)
        _, listing = srv.get("/api/triage/tasks?status=open&email_id=" + M + "m1")
        self.assertIn(task["id"], [t["id"] for t in listing["tasks"]])

        status, done = srv.post("/api/triage/tasks/update", {"id": task["id"], "status": "done"})
        self.assertEqual(status, 200)
        self.assertEqual(done["status"], "done")
        _, listing = srv.get("/api/triage/tasks?status=open&email_id=" + M + "m1")
        self.assertNotIn(task["id"], [t["id"] for t in listing["tasks"]])

        _, hist = srv.get("/api/triage/history?email_id=" + M + "m1")
        events = [h["event"] for h in hist["history"] if h["task_id"] == task["id"]]
        self.assertEqual(events[:2], ["task_done", "task_created"])
        self.assertEqual(hist["history"][0]["text"], "Task done · Draft a reply")
        _, zh = srv.get("/api/triage/history?lang=zh-Hant&email_id=" + M + "m1")
        self.assertEqual(zh["history"][0]["text"], "任務完成 · 起草回覆")

        _, it = srv.get("/api/triage/item/" + M + "m1")
        self.assertIn(task["id"], [t["id"] for t in it["tasks"]])
        self.assertTrue(it["history"])

    def test_digest_task_without_email(self):
        status, task = srv.post("/api/triage/tasks", {"action": "review_digest"})
        self.assertEqual(status, 201)
        self.assertEqual(task["email_id"], "")
        self.assertEqual(task["subject"], "")

    def test_task_validation(self):
        self.assertEqual(srv.post("/api/triage/tasks", {"email_id": M + "m1", "action": "send"})[0], 400)
        self.assertEqual(srv.post("/api/triage/tasks", {"email_id": "nope", "action": "reply"})[0], 404)
        self.assertEqual(srv.post("/api/triage/tasks/update", {"id": "x", "status": "done"})[0], 400)
        self.assertEqual(srv.post("/api/triage/tasks/update", {"id": 999999, "status": "done"})[0], 404)
        _, task = srv.post("/api/triage/tasks", {"email_id": M + "m2", "action": "review"})
        self.assertEqual(srv.post("/api/triage/tasks/update", {"id": task["id"], "status": "sent"})[0], 400)
        self.assertEqual(srv.get("/api/triage/tasks?status=weird")[0], 400)

    def test_note_update_keeps_status(self):
        _, task = srv.post("/api/triage/tasks", {"email_id": M + "m8", "action": "pay_or_file"})
        _, upd = srv.post("/api/triage/tasks/update", {"id": task["id"], "note": "check card"})
        self.assertEqual(upd["status"], "open")
        self.assertEqual(upd["note"], "check card")
        _, hist = srv.get("/api/triage/history?email_id=" + M + "m8")
        self.assertEqual(hist["history"][0]["event"], "task_updated")

    def test_log_ui_events(self):
        status, entry = srv.post("/api/triage/history", {"event": "reply_draft", "email_id": M + "m1",
                                                         "action": "reply", "lang": "zh-Hant"})
        self.assertEqual(status, 201)
        self.assertEqual(entry["text"], "請 Copilot 起草回覆（只存本機） · 起草回覆")
        self.assertEqual(srv.post("/api/triage/history", {"event": "DROP TABLE"})[0], 400)
        self.assertEqual(srv.post("/api/triage/history", {"event": "opened", "email_id": "nope"})[0], 404)

    def test_tasks_survive_cache_clear(self):
        _, task = srv.post("/api/triage/tasks", {"email_id": M + "m7", "action": "reply"})
        srv.post("/api/cache/clear", {})
        _, listing = srv.get("/api/triage/tasks")
        kept = next(t for t in listing["tasks"] if t["id"] == task["id"])
        self.assertEqual(kept["subject"], "", "mail content is gone with the cache")
        self.assertEqual(kept["action"], "reply")
        srv.reseed()
        _, listing = srv.get("/api/triage/tasks")
        kept = next(t for t in listing["tasks"] if t["id"] == task["id"])
        self.assertEqual(kept["subject"], "Northwind term sheet comments")


if __name__ == "__main__":
    unittest.main()
