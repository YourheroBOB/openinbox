"""Released mail is a standards-shaped .eml under data/outbox/, marked as waiting for the user to send it."""
from __future__ import annotations

import unittest
from datetime import datetime
from email import message_from_bytes
from email.policy import default as default_policy
from unittest import mock

import _tpi_server as srv
from _tpi_outbox_util import OutboxCase, at, make_draft
from features import outbox


class EmlTest(OutboxCase):
    def release(self, **fields):
        item = self.confirmed("now", **fields)
        released = outbox.release_due(at(1))
        self.assertEqual(len(released), 1)
        row = outbox._row(item["id"])
        path = srv.yhbmail.ROOT / row["eml_path"]
        return row, path, message_from_bytes(path.read_bytes(), policy=default_policy)

    def test_file_lands_in_data_outbox(self):
        row, path, _ = self.release(subject="Design review notes")
        self.assertEqual(path.parent, srv.yhbmail.ROOT / "data" / "outbox")
        self.assertTrue(path.name.endswith(f"-{row['id']:04d}-design-review-notes.eml"), path.name)
        self.assertFalse(list(path.parent.glob("*.tmp")))
        self.assertIn(b"\r\n", path.read_bytes())

    def test_headers(self):
        row, _, msg = self.release(to="Maya Lin <maya@example.com>, lee@example.com", cc="pat@example.com",
                                   bcc="alex@example.com", subject="設計審查 · review")
        self.assertEqual(msg["From"], "you@example.com")
        self.assertEqual([a.addr_spec for a in msg["To"].addresses], ["maya@example.com", "lee@example.com"])
        self.assertEqual(msg["To"].addresses[0].display_name, "Maya Lin")
        self.assertEqual(msg["Cc"], "pat@example.com")
        self.assertEqual(msg["Bcc"], "alex@example.com")
        self.assertEqual(msg["Subject"], "設計審查 · review")
        self.assertEqual(msg["X-Unsent"], "1")
        self.assertEqual(msg["X-TooPowerInbox-Status"], "awaiting-user-send")
        self.assertIn("待使用者自行寄出", msg["X-TooPowerInbox-Note"])
        self.assertEqual(msg["X-TooPowerInbox-Outbox-Id"], str(row["id"]))
        self.assertTrue(msg["Message-ID"].endswith("@example.com>"))
        self.assertIsNotNone(msg["Date"].datetime.tzinfo)
        self.assertEqual(msg.get_content_type(), "text/plain")

    def test_body_round_trips(self):
        text = "Maya 你好：\n\n週五的設計審查資料已備妥。\n\n謝謝！"
        _, _, msg = self.release(text=text, subject="資料")
        self.assertEqual(msg.get_content().replace("\r\n", "\n").strip(), text)

    def test_reply_threading_only_with_a_real_message_id(self):
        row = {"id": 7, "account": "you@example.com", "to_addr": "maya@example.com", "cc": "", "bcc": "",
               "subject": "Re: plan", "body": "ok", "in_reply_to": "demo:x"}
        when = datetime(2026, 10, 12, 8, 0, tzinfo=srv.yhbmail.TZ)
        with mock.patch.object(outbox.yhbmail, "get_email", return_value={"thread_id": "<abc.123@example.com>"}):
            msg = message_from_bytes(outbox.build_eml(row, when), policy=default_policy)
        self.assertEqual(msg["In-Reply-To"], "<abc.123@example.com>")
        self.assertEqual(msg["References"], "<abc.123@example.com>")
        with mock.patch.object(outbox.yhbmail, "get_email", return_value={"thread_id": "demo-thread-1"}):
            msg = message_from_bytes(outbox.build_eml(row, when), policy=default_policy)
        self.assertIsNone(msg["In-Reply-To"])

    def test_download_route(self):
        row, path, _ = self.release()
        status, headers, raw = srv.request("GET", f"/api/outbox/eml/{row['id']}.eml")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "message/rfc822")
        self.assertEqual(raw, path.read_bytes())
        path.unlink()
        self.assertEqual(srv.request("GET", f"/api/outbox/eml/{row['id']}.eml")[0], 404)

    def test_no_download_before_release(self):
        item = self.confirmed("schedule", send_at=at(2).isoformat())
        self.assertEqual(srv.request("GET", f"/api/outbox/eml/{item['id']}.eml")[0], 404)

    def test_newline_subject_is_refused_before_confirm(self):
        out, status = outbox.prepare({"draft_id": make_draft(subject="Hello\nBcc: leak@example.com")}, "en")
        self.assertEqual(status, 400, out)
        out, status = outbox.prepare({"draft_id": make_draft(to="\"Bad\nName\" <maya@example.com>")}, "en")
        self.assertEqual(status, 400, out)
        self.assertEqual(outbox.release_due(at(24 * 400)), [])

    def test_newline_subject_blocks_once_and_does_not_retry(self):
        item = self.confirmed("now")
        con = srv.yhbmail.db()
        con.execute("UPDATE outbox SET subject=?, release_ts=? WHERE id=?",
                    ("Hello\nBcc: leak@example.com", outbox.now_dt().timestamp() - 1, item["id"]))
        con.commit()
        con.close()
        with mock.patch("sys.stderr"):
            self.assertEqual(outbox.release_due(), [])
        row = outbox._row(item["id"])
        self.assertEqual(row["state"], "blocked")
        self.assertIsNone(row["release_ts"])
        self.assertEqual(row["note"], "ValueError")
        self.assertNotIn("leak@example.com", row["note"])
        self.assertEqual(outbox.release_due(), [])
        self.assertEqual(list(outbox.outbox_dir().glob("*.eml")) if outbox.outbox_dir().exists() else [], [])

    def test_blocked_message_returns_to_drafts(self):
        item = self.confirmed("now")
        con = srv.yhbmail.db()
        con.execute("UPDATE outbox SET subject=?, release_ts=? WHERE id=?",
                    ("Hello\nBcc: leak@example.com", outbox.now_dt().timestamp() - 1, item["id"]))
        con.commit()
        con.close()
        self.assertEqual(outbox.release_due(), [])
        self.assertEqual(outbox._row(item["id"])["state"], "blocked")
        out, status = outbox.edit(item["id"], "en")
        self.assertEqual(status, 200, out)
        self.assertEqual(outbox._row(item["id"])["state"], "cancelled")
        restored = outbox.compose.get_draft(out["draft_id"])
        self.assertEqual(restored["subject"], "Hello\nBcc: leak@example.com")

    def test_outbox_responses_omit_wildcard_cors(self):
        self.confirmed("now")
        status, headers, raw = srv.request("GET", "/api/outbox/items")
        self.assertEqual(status, 200)
        self.assertNotIn("access-control-allow-origin", {k.lower() for k in headers})
        self.assertIn(b"maya@example.com", raw)
        status, headers, _ = srv.request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertIn("access-control-allow-origin", {k.lower() for k in headers})

    def test_write_failure_keeps_the_message_queued(self):
        item = self.confirmed("now")
        with mock.patch.object(outbox, "build_eml", side_effect=OSError("disk full")), \
                mock.patch("sys.stderr"):
            self.assertEqual(outbox.release_due(at(1)), [])
        row = outbox._row(item["id"])
        self.assertEqual(row["state"], "undo_window")
        self.assertIn("disk full", row["note"])
        self.assertEqual(len(outbox.release_due(at(1))), 1)


if __name__ == "__main__":
    unittest.main()
