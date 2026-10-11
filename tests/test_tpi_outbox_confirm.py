"""F20: nothing reaches the outbox without a human confirmation; agents can only propose; no transport."""
from __future__ import annotations

import os
import unittest
from datetime import timedelta
from pathlib import Path

import _tpi_server as srv
from _tpi_outbox_util import OutboxCase, at, make_draft
from features import _outbox_transport as transport
from features import compose, outbox

REPO = Path(__file__).resolve().parents[1]


class ConfirmGateTest(OutboxCase):
    def test_prepare_only_waits_for_confirmation(self):
        draft = make_draft()
        p = self.prepared(draft)
        self.assertEqual(p["item"]["state"], "awaiting_confirm")
        self.assertTrue(p["confirm_required"])
        self.assertTrue(p["token"])
        self.assertIsNotNone(compose.get_draft(draft), "preparing must not consume the draft")
        self.assertEqual(outbox.release_due(at(24 * 400)), [])
        self.assertFalse(outbox.outbox_dir().exists() and any(outbox.outbox_dir().iterdir()))

    def test_confirm_needs_the_token(self):
        p = self.prepared()
        oid = p["item"]["id"]
        for token in ("", "wrong-token"):
            out, status = outbox.confirm({"id": oid, "token": token, "ack": True}, "en")
            self.assertEqual(status, 403, out)
        self.assertEqual(outbox._row(oid)["state"], "awaiting_confirm")

    def test_confirm_needs_explicit_ack(self):
        p = self.prepared()
        for ack in (None, False, "true", 1):
            body = {"id": p["item"]["id"], "token": p["token"], "mode": "now"}
            if ack is not None:
                body["ack"] = ack
            out, status = outbox.confirm(body, "en")
            self.assertEqual(status, 400, (ack, out))
        out, status = outbox.confirm({"id": p["item"]["id"], "token": p["token"], "ack": True}, "en")
        self.assertEqual(status, 200, out)

    def test_token_is_single_use_and_expires(self):
        p = self.prepared()
        body = {"id": p["item"]["id"], "token": p["token"], "ack": True}
        self.assertEqual(outbox.confirm(body, "en")[1], 200)
        self.assertEqual(outbox.confirm(body, "en")[1], 409)
        q = self.prepared()
        late = outbox.now_dt() + timedelta(seconds=outbox.TOKEN_TTL + 5)
        out, status = outbox.confirm({"id": q["item"]["id"], "token": q["token"], "ack": True}, "en", now=late)
        self.assertEqual(status, 403, out)

    def test_content_tampering_after_preview_is_refused(self):
        p = self.prepared()
        con = srv.yhbmail.db()
        con.execute("UPDATE outbox SET to_addr='someone.else@example.com' WHERE id=?", (p["item"]["id"],))
        con.commit()
        con.close()
        out, status = outbox.confirm({"id": p["item"]["id"], "token": p["token"], "ack": True}, "en")
        self.assertEqual(status, 409, out)

    def test_placeholders_block_confirmation(self):
        for text in ("Hi Maya,\n\nThe budget is [TBD].", "Maya 你好：\n\n金額是 [待填]。"):
            p = self.prepared(text=text)
            self.assertTrue(p["item"]["blocking"])
            out, status = outbox.confirm({"id": p["item"]["id"], "token": p["token"], "ack": True}, "en")
            self.assertEqual(status, 409, out)
            self.assertIn("blocking", out)

    def test_placeholder_in_quoted_original_does_not_block(self):
        draft = make_draft(kind="reply", source_id="", text="Thanks, confirmed.", quote="> budget [TBD]")
        p = self.prepared(draft)
        self.assertEqual(p["item"]["blocking"], [])

    def test_addresses_are_validated(self):
        for fields in ({"to": ""}, {"to": "not-an-address"}, {"cc": "maya@"}, {"account": "nobody"}):
            out, status = outbox.prepare({"draft_id": make_draft(**fields)}, "zh-Hant")
            self.assertEqual(status, 400, (fields, out))
            self.assertTrue(out["errors"])

    def test_warnings_for_review(self):
        p = self.prepared(subject="", to="no-reply@example.com", text="Report attached, see 附件.")
        warnings = " ".join(p["item"]["warnings"])
        self.assertIn("subject", warnings.lower())
        self.assertIn("attach", warnings.lower())
        self.assertIn("no-reply", warnings)
        self.assertEqual(p["item"]["blocking"], [])

    def test_unknown_mode_and_missing_draft(self):
        p = self.prepared()
        out, status = outbox.confirm({"id": p["item"]["id"], "token": p["token"], "ack": True, "mode": "deliver"}, "en")
        self.assertEqual(status, 400, out)
        self.assertEqual(outbox.prepare({"draft_id": 999999}, "en")[1], 404)

    def test_discard_keeps_the_draft(self):
        draft = make_draft()
        p = self.prepared(draft)
        out, status = outbox.discard(p["item"]["id"], "en")
        self.assertEqual(status, 200, out)
        self.assertEqual(outbox._row(p["item"]["id"])["state"], "cancelled")
        self.assertIsNotNone(compose.get_draft(draft))
        con = srv.yhbmail.db()
        self.assertEqual(con.execute("SELECT COUNT(*) FROM drafts").fetchone()[0], 1)
        con.close()

    def test_re_prepare_supersedes_the_old_preview(self):
        draft = make_draft()
        first = self.prepared(draft)
        second = self.prepared(draft)
        self.assertEqual(outbox._row(first["item"]["id"])["state"], "cancelled")
        out, status = outbox.confirm({"id": first["item"]["id"], "token": first["token"], "ack": True}, "en")
        self.assertEqual(status, 409, out)
        self.assertEqual(outbox._row(second["item"]["id"])["state"], "awaiting_confirm")


class AgentCannotConfirmTest(OutboxCase):
    def test_agent_tools_are_listed(self):
        names = {t["name"] for t in outbox.agent_bridge.TOOLS}
        self.assertIn("outbox_propose", names)
        self.assertIn("outbox_list", names)
        self.assertFalse({n for n in names if "confirm" in n})

    def test_agent_proposal_waits_without_a_token(self):
        out = outbox.agent_bridge.invoke_tool("outbox_propose", {
            "to": "maya@example.com", "subject": "Follow-up", "body": "Hi Maya,\n\nFollowing up on Friday.",
            "send_at": at(30).isoformat(), "token": "smuggled", "ack": True, "mode": "now"})
        self.assertNotIn("token", out)
        self.assertEqual(out["item"]["state"], "awaiting_confirm")
        self.assertEqual(out["item"]["created_by"], "agent")
        self.assertTrue(out["item"]["proposed_at"])
        self.assertIn("cannot confirm", out["note"])
        self.assertEqual(outbox.release_due(at(24 * 400)), [])

    def test_no_tool_can_confirm_or_release(self):
        for name in ("outbox_confirm", "confirm", "outbox_release", "outbox_tick", "outbox_reschedule"):
            out = outbox.agent_bridge.invoke_tool(name, {"id": 1, "ack": True})
            self.assertIn("unknown tool", out.get("error", ""), name)

    def test_http_tool_route_proposes_only(self):
        status, out = srv.post("/api/v1/tools/outbox_propose", {
            "to": "maya@example.com", "subject": "From the agent", "body": "Short note."})
        self.assertEqual(status, 200, out)
        self.assertNotIn("token", out)
        oid = out["item"]["id"]
        self.assertEqual(outbox._row(oid)["state"], "awaiting_confirm")
        status, listed = srv.post("/api/v1/tools/outbox_list", {"state": "awaiting_confirm"})
        self.assertIn(oid, [x["id"] for x in listed["items"]])
        status, out = srv.post("/api/outbox/confirm", {"id": oid, "ack": True})
        self.assertEqual(status, 403, out)

    def test_user_reviews_then_confirms_an_agent_proposal(self):
        out = outbox.agent_bridge.invoke_tool("outbox_propose", {
            "to": "maya@example.com", "subject": "Agenda", "body": "Agenda for Friday attached below."})
        oid = out["item"]["id"]
        status, r = srv.post("/api/outbox/review", {"id": oid})
        self.assertEqual(status, 200, r)
        status, c = srv.post("/api/outbox/confirm", {"id": oid, "token": r["token"], "ack": True, "mode": "schedule",
                                                     "send_at": at(5).isoformat()})
        self.assertEqual(status, 200, c)
        self.assertEqual(c["item"]["state"], "scheduled")
        self.assertEqual(c["item"]["confirmed_by"], "user")
        events = [e["event"] for e in outbox.history(oid)]
        self.assertEqual(events[:3], ["proposed", "review", "confirmed"])

    def test_agent_discard_does_not_create_a_draft(self):
        out = outbox.agent_bridge.invoke_tool("outbox_propose", {"to": "maya@example.com", "subject": "x", "body": "y"})
        r, status = outbox.discard(out["item"]["id"], "en")
        self.assertEqual(status, 200, r)
        self.assertIsNone(r["draft_id"])


class OriginGuardTest(OutboxCase):
    def post_with(self, path, body, headers):
        req = srv.urllib.request.Request(srv.BASE + path, data=srv.json.dumps(body).encode(), method="POST",
                                         headers={"Content-Type": "application/json", **headers})
        try:
            with srv.urllib.request.urlopen(req, timeout=20) as r:
                return r.status
        except srv.urllib.error.HTTPError as e:
            return e.code

    def test_foreign_pages_are_refused(self):
        draft = make_draft()
        for headers in ({"Origin": "https://evil.example.com"}, {"Sec-Fetch-Site": "cross-site"}):
            self.assertEqual(self.post_with("/api/outbox/prepare", {"draft_id": draft}, headers), 403, headers)
        port = srv.SERVER.server_address[1]
        own = {"Origin": f"http://127.0.0.1:{port}", "Sec-Fetch-Site": "same-origin"}
        self.assertEqual(self.post_with("/api/outbox/prepare", {"draft_id": draft}, own), 201)


class TransportTest(OutboxCase):
    def test_only_the_disabled_transport_exists(self):
        self.assertEqual(transport.names(), ["disabled"])
        t = transport.get()
        self.assertEqual(t.name, "disabled")
        self.assertFalse(t.enabled)
        self.assertFalse(t.deliver(Path("x.eml"), {})["delivered"])
        with self.assertRaises(KeyError):
            transport.get("anything-else")
        with self.assertRaises(NotImplementedError):
            transport.Transport().deliver(Path("x.eml"), {})

    def test_settings_refuse_other_transports(self):
        out, status = outbox.save_settings({"transport": "relay"}, "en")
        self.assertEqual(status, 400, out)
        s = outbox.settings_view("zh-Hant")
        self.assertEqual(s["transport"], "disabled")
        self.assertTrue(s["require_confirm"])
        self.assertIn("自行寄出", s["note"])

    def test_released_message_is_only_a_file(self):
        item = self.confirmed("now")
        released = outbox.release_due(at(1))
        self.assertEqual([r["id"] for r in released], [item["id"]])
        row = outbox._row(item["id"])
        self.assertEqual(row["state"], "ready")
        self.assertEqual(row["transport"], "disabled")
        view = outbox.item_view(row, "zh-Hant")
        self.assertTrue(view["awaiting_user_send"])
        self.assertEqual(view["state_label"], "待使用者自行寄出")

    def test_transport_module_has_no_network_code(self):
        src = (REPO / "server" / "features" / "_outbox_transport.py").read_text()
        for word in ("socket", "http.client", "urllib", "imaplib", "ssl", "subprocess"):
            self.assertNotIn("import " + word, src)
            self.assertNotIn("from " + word, src)
        src = (REPO / "server" / "features" / "outbox.py").read_text()
        for word in ("socket", "http.client", "urllib.request", "subprocess"):
            self.assertNotIn("import " + word, src)

    def test_outbox_survives_a_cache_clear(self):
        self.confirmed("schedule", send_at=at(3).isoformat())
        status, out = srv.post("/api/cache/clear", {})
        self.assertEqual(status, 200, out)
        con = srv.yhbmail.db()
        self.assertEqual(con.execute("SELECT COUNT(*) FROM outbox WHERE state='scheduled'").fetchone()[0], 1)
        con.close()
        srv.reseed()


if __name__ == "__main__":
    unittest.main()
