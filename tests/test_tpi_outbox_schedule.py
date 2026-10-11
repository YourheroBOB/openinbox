"""F18: Schedule Send queue and the Scheduled folder (change time, edit back to Drafts, cancel)."""
from __future__ import annotations

import time
import unittest
from datetime import datetime, timedelta

import _tpi_server as srv
from _tpi_outbox_util import OutboxCase, at, make_draft
from features import compose, outbox


class ScheduleTest(OutboxCase):
    def test_schedule_moves_the_draft_into_the_scheduled_folder(self):
        draft = make_draft(cc="lee@example.com", bcc="pat@example.com")
        p = self.prepared(draft)
        when = at(20).replace(microsecond=0)
        out, status = outbox.confirm({"id": p["item"]["id"], "token": p["token"], "ack": True, "mode": "schedule",
                                      "send_at": when.isoformat()}, "en")
        self.assertEqual(status, 200, out)
        self.assertEqual(out["item"]["state"], "scheduled")
        self.assertEqual(outbox.parse_when(out["item"]["release_at"]), when)
        self.assertIsNone(compose.get_draft(draft), "a scheduled message leaves Drafts")
        listed = outbox.list_items(["scheduled"], "en")
        self.assertEqual([x["id"] for x in listed], [p["item"]["id"]])
        self.assertEqual(listed[0]["cc"], "lee@example.com")

    def test_wall_clock_time_uses_the_app_timezone(self):
        when = at(48)
        wall = when.astimezone(srv.yhbmail.TZ).strftime("%Y-%m-%dT%H:%M")
        item = self.confirmed("schedule", send_at=wall)
        self.assertEqual(item["release_at"][:16], wall)
        self.assertEqual(outbox.parse_when(wall).utcoffset(), srv.yhbmail.TZ.utcoffset(None))

    def test_schedule_time_limits(self):
        for send_at in ("", "tomorrow-ish", at(-1).isoformat(), (outbox.now_dt() + timedelta(seconds=10)).isoformat(),
                        at(24 * 400).isoformat()):
            p = self.prepared()
            out, status = outbox.confirm({"id": p["item"]["id"], "token": p["token"], "ack": True,
                                          "mode": "schedule", "send_at": send_at}, "en")
            self.assertEqual(status, 400, (send_at, out))
            self.assertEqual(outbox._row(p["item"]["id"])["state"], "awaiting_confirm")

    def test_queue_is_ordered_and_released_when_due(self):
        base = outbox.now_dt()
        late = self.confirmed("schedule", send_at=at(5, base).isoformat(), subject="Later one")
        soon = self.confirmed("schedule", send_at=at(2, base).isoformat(), subject="Sooner one")
        self.assertEqual([x["id"] for x in outbox.list_items(["scheduled"], "en")], [soon["id"], late["id"]])
        self.assertEqual(outbox.release_due(at(1, base)), [])
        first = outbox.release_due(at(3, base))
        self.assertEqual([r["id"] for r in first], [soon["id"]])
        self.assertEqual(outbox._row(late["id"])["state"], "scheduled")
        self.assertEqual([r["id"] for r in outbox.release_due(at(6, base))], [late["id"]])
        self.assertEqual(outbox.release_due(at(7, base)), [], "release is idempotent")
        files = sorted(p.name for p in outbox.outbox_dir().glob("*.eml"))
        self.assertEqual(len(files), 2)
        self.assertTrue(any("sooner-one" in f for f in files))

    def test_reschedule(self):
        item = self.confirmed("schedule", send_at=at(5).isoformat())
        out, status = outbox.reschedule(item["id"], at(30).isoformat(), "zh-Hant")
        self.assertEqual(status, 200, out)
        self.assertEqual(outbox.release_due(at(6)), [])
        self.assertEqual(len(outbox.release_due(at(31))), 1)
        self.assertEqual(outbox.reschedule(item["id"], at(40).isoformat(), "en")[1], 409, "released mail stays put")

    def test_reschedule_validates_and_now_releases(self):
        item = self.confirmed("schedule", send_at=at(5).isoformat())
        self.assertEqual(outbox.reschedule(item["id"], "garbage", "en")[1], 400)
        self.assertEqual(outbox.reschedule(item["id"], at(-2).isoformat(), "en")[1], 400)
        out, status = outbox.reschedule(item["id"], "now", "en")
        self.assertEqual(status, 200, out)
        self.assertEqual(out["item"]["state"], "ready")
        self.assertTrue(out["item"]["eml_path"].startswith("data/outbox/"))

    def test_edit_puts_it_back_in_drafts_with_the_old_time(self):
        draft = make_draft(cc="lee@example.com", subject="Quarterly plan")
        p = self.prepared(draft)
        when = at(10)
        outbox.confirm({"id": p["item"]["id"], "token": p["token"], "ack": True, "mode": "schedule",
                        "send_at": when.isoformat()}, "en")
        out, status = outbox.edit(p["item"]["id"], "en")
        self.assertEqual(status, 200, out)
        self.assertEqual(out["draft_id"], draft, "the draft keeps its id")
        self.assertEqual(outbox.parse_when(out["previous_release_at"]).replace(microsecond=0),
                         when.replace(microsecond=0))
        restored = compose.get_draft(draft)
        self.assertEqual((restored["subject"], restored["cc"], restored["kind"]), ("Quarterly plan", "lee@example.com", "new"))
        self.assertEqual(outbox._row(p["item"]["id"])["state"], "cancelled")
        self.assertEqual(outbox.release_due(at(11)), [])
        again = self.prepared(draft)
        self.assertEqual(again["item"]["subject"], "Quarterly plan")

    def test_cancel_scheduled_restores_the_full_draft(self):
        draft = make_draft(kind="reply", source_id=srv.yhbmail.list_emails(limit=1)[0]["id"],
                           text="Thanks, Friday works.", quote="> original line")
        before = compose.get_draft(draft)
        p = self.prepared(draft)
        outbox.confirm({"id": p["item"]["id"], "token": p["token"], "ack": True, "mode": "schedule",
                        "send_at": at(3).isoformat()}, "en")
        out, status = outbox.cancel(p["item"]["id"], "en")
        self.assertEqual(status, 200, out)
        after = compose.get_draft(out["draft_id"])
        for key in ("kind", "to", "subject", "text", "quote", "source_id", "in_reply_to", "account"):
            self.assertEqual(after[key], before[key], key)

    def test_cancel_without_keeping_the_draft(self):
        item = self.confirmed("schedule", send_at=at(3).isoformat())
        out, status = outbox.cancel(item["id"], "en", keep_draft=False)
        self.assertEqual(status, 200, out)
        self.assertIsNone(out["draft_id"])
        con = srv.yhbmail.db()
        self.assertEqual(con.execute("SELECT COUNT(*) FROM drafts").fetchone()[0], 0)
        con.close()

    def test_ready_message_can_go_back_to_drafts_or_be_marked_done(self):
        a = self.confirmed("now", subject="Alpha")
        b = self.confirmed("now", subject="Beta")
        outbox.release_due(at(1))
        path = srv.yhbmail.ROOT / outbox._row(a["id"])["eml_path"]
        self.assertTrue(path.is_file())
        out, status = outbox.cancel(a["id"], "en")
        self.assertEqual(status, 200, out)
        self.assertFalse(path.exists(), "moving back to Drafts removes the .eml")
        self.assertEqual(compose.get_draft(out["draft_id"])["subject"], "Alpha")
        out, status = outbox.mark_done(b["id"], "en")
        self.assertEqual(status, 200, out)
        self.assertEqual(out["item"]["state"], "done")
        self.assertEqual(outbox.mark_done(b["id"], "en")[1], 409)

    def test_suggestions(self):
        base = datetime(2026, 10, 14, 9, 30, tzinfo=srv.yhbmail.TZ)
        ids = [s["id"] for s in outbox.suggestions(base, "en")]
        self.assertEqual(ids, ["later_today", "tomorrow_morning", "tomorrow_afternoon", "monday_morning"])
        sunday_night = datetime(2026, 10, 18, 22, 0, tzinfo=srv.yhbmail.TZ)
        zh = outbox.suggestions(sunday_night, "zh-Hant")
        self.assertEqual([s["id"] for s in zh], ["tomorrow_morning", "tomorrow_afternoon"])
        self.assertEqual(zh[0]["label"], "明天早上")
        self.assertTrue(zh[0]["at"].startswith("2026-10-19T08:00"))

    def test_ticker_releases_due_mail_in_the_background(self):
        item = self.confirmed("now")
        con = srv.yhbmail.db()
        con.execute("UPDATE outbox SET release_ts=? WHERE id=?", (time.time() - 1, item["id"]))
        con.commit()
        con.close()
        outbox.start_ticker(interval=0.1, enable=True)
        self.addCleanup(outbox.stop_ticker)
        for _ in range(50):
            if outbox._row(item["id"])["state"] == "ready":
                break
            time.sleep(0.1)
        self.assertEqual(outbox._row(item["id"])["state"], "ready")


class ScheduledHttpTest(OutboxCase):
    def test_full_schedule_flow_over_http(self):
        draft = make_draft(subject="Launch checklist")
        status, p = srv.post("/api/outbox/prepare", {"draft_id": draft, "lang": "zh-Hant"})
        self.assertEqual(status, 201, p)
        self.assertEqual(p["item"]["state_label"], "待你確認")
        tomorrow = next(s for s in p["settings"]["suggestions"] if s["id"] == "tomorrow_morning")
        status, c = srv.post("/api/outbox/confirm", {"id": p["item"]["id"], "token": p["token"], "ack": True,
                                                     "mode": "schedule", "send_at": tomorrow["at"], "lang": "zh-Hant"})
        self.assertEqual(status, 200, c)
        self.assertIn("已排程", c["note"])
        status, listed = srv.get("/api/outbox/items?state=scheduled")
        self.assertEqual([x["subject"] for x in listed["items"]], ["Launch checklist"])
        status, summary = srv.get("/api/outbox/summary")
        self.assertEqual(summary["counts"]["scheduled"], 1)
        self.assertEqual(summary["next"]["id"], p["item"]["id"])
        status, r = srv.post("/api/outbox/reschedule", {"id": p["item"]["id"], "send_at": at(50).isoformat()})
        self.assertEqual(status, 200, r)
        status, e = srv.post("/api/outbox/edit", {"id": p["item"]["id"]})
        self.assertEqual(status, 200, e)
        self.assertEqual(e["draft_id"], draft)
        status, drafts = srv.get("/api/compose/drafts")
        self.assertIn(draft, [d["id"] for d in drafts["drafts"]])
        status, detail = srv.get(f"/api/outbox/item/{p['item']['id']}")
        self.assertEqual([h["event"] for h in detail["history"]], ["prepared", "confirmed", "rescheduled", "edit"])

    def test_bad_requests(self):
        self.assertEqual(srv.get("/api/outbox/items?state=bogus")[0], 400)
        self.assertEqual(srv.get("/api/outbox/item/999999")[0], 404)
        self.assertEqual(srv.post("/api/outbox/cancel", {"id": 999999})[0], 404)
        self.assertEqual(srv.post("/api/outbox/settings", {"undo_seconds": 3})[0], 400)


if __name__ == "__main__":
    unittest.main()
