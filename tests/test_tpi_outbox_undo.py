"""F19: Undo Send countdown; undo inside the window returns the message to Drafts."""
from __future__ import annotations

import threading
import unittest
from datetime import timedelta

import _tpi_server as srv
from _tpi_outbox_util import OutboxCase, make_draft
from features import compose, outbox


class UndoTest(OutboxCase):
    def test_now_opens_the_undo_window(self):
        now = outbox.now_dt()
        item = self.confirmed("now", now=now)
        self.assertEqual(item["state"], "undo_window")
        self.assertEqual(item["seconds_left"], 10.0)
        self.assertEqual(outbox.release_due(now + timedelta(seconds=9)), [])
        self.assertEqual(len(outbox.release_due(now + timedelta(seconds=10))), 1)

    def test_undo_seconds_setting(self):
        out, status = outbox.save_settings({"undo_seconds": 30}, "en")
        self.assertEqual(status, 200, out)
        self.assertEqual(out["undo_seconds"], 30)
        now = outbox.now_dt()
        item = self.confirmed("now", now=now)
        self.assertEqual(item["seconds_left"], 30.0)
        self.assertEqual(outbox.release_due(now + timedelta(seconds=29)), [])
        for bad in (0, 3, 60, "ten"):
            self.assertEqual(outbox.save_settings({"undo_seconds": bad}, "en")[1], 400, bad)
        self.assertEqual(outbox.settings_view("en")["undo_choices"], [5, 10, 20, 30])

    def test_undo_inside_the_window_restores_the_draft(self):
        draft = make_draft(subject="Oops, wrong person", to="lee@example.com")
        p = self.prepared(draft)
        now = outbox.now_dt()
        outbox.confirm({"id": p["item"]["id"], "token": p["token"], "ack": True, "mode": "now"}, "en", now=now)
        self.assertIsNone(compose.get_draft(draft))
        out, status = outbox.undo(p["item"]["id"], "zh-Hant")
        self.assertEqual(status, 200, out)
        self.assertEqual(out["draft_id"], draft)
        self.assertIn("撤回", out["note"])
        self.assertEqual(compose.get_draft(draft)["subject"], "Oops, wrong person")
        self.assertEqual(outbox._row(p["item"]["id"])["cancel_reason"], "undo")
        self.assertEqual(outbox.release_due(now + timedelta(minutes=5)), [])
        self.assertFalse(list(outbox.outbox_dir().glob("*.eml")) if outbox.outbox_dir().exists() else [])

    def test_undo_after_the_window_is_too_late(self):
        now = outbox.now_dt()
        item = self.confirmed("now", now=now)
        outbox.release_due(now + timedelta(seconds=11))
        out, status = outbox.undo(item["id"], "en")
        self.assertEqual(status, 409, out)
        self.assertIn("Too late", out["error"])
        self.assertEqual(out["state"], "ready")

    def test_scheduled_mail_cannot_be_undone_only_cancelled(self):
        item = self.confirmed("schedule", send_at=(outbox.now_dt() + timedelta(hours=2)).isoformat())
        self.assertEqual(outbox.undo(item["id"], "en")[1], 409)
        self.assertEqual(outbox.cancel(item["id"], "en")[1], 200)

    def test_undo_and_release_race_only_one_wins(self):
        for _ in range(5):
            now = outbox.now_dt()
            item = self.confirmed("now", now=now)
            results = {}

            def do_undo():
                results["undo"] = outbox.undo(item["id"], "en")[1]

            def do_release():
                results["release"] = len(outbox.release_due(now + timedelta(seconds=11)))

            threads = [threading.Thread(target=do_undo), threading.Thread(target=do_release)]
            for th in threads:
                th.start()
            for th in threads:
                th.join()
            state = outbox._row(item["id"])["state"]
            if results["undo"] == 200:
                self.assertEqual((state, results["release"]), ("cancelled", 0))
            else:
                self.assertEqual((state, results["release"], results["undo"]), ("ready", 1, 409))
            files = list(outbox.outbox_dir().glob(f"*-{item['id']:04d}-*.eml")) if outbox.outbox_dir().exists() else []
            self.assertEqual(len(files), 1 if state == "ready" else 0)

    def test_undo_over_http(self):
        draft = make_draft()
        status, p = srv.post("/api/outbox/prepare", {"draft_id": draft})
        status, c = srv.post("/api/outbox/confirm", {"id": p["item"]["id"], "token": p["token"], "ack": True,
                                                     "mode": "now"})
        self.assertEqual(status, 200, c)
        self.assertEqual(c["item"]["state"], "undo_window")
        self.assertGreater(c["item"]["seconds_left"], 5)
        status, u = srv.post("/api/outbox/undo", {"id": p["item"]["id"]})
        self.assertEqual(status, 200, u)
        self.assertEqual(srv.post("/api/outbox/undo", {"id": p["item"]["id"]})[0], 409)
        status, d = srv.get(f"/api/compose/draft/{draft}")
        self.assertEqual(status, 200, d)

    def test_tick_route_releases_expired_windows(self):
        item = self.confirmed("now")
        con = srv.yhbmail.db()
        con.execute("UPDATE outbox SET release_ts=release_ts-60 WHERE id=?", (item["id"],))
        con.commit()
        con.close()
        status, out = srv.post("/api/outbox/tick", {"lang": "zh-Hant"})
        self.assertEqual(status, 200, out)
        self.assertEqual([r["id"] for r in out["released"]], [item["id"]])
        self.assertEqual(out["released"][0]["state_label"], "待使用者自行寄出")
        self.assertEqual(out["summary"]["counts"]["ready"], 1)


if __name__ == "__main__":
    unittest.main()
