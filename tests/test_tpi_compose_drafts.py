"""Composer: new mail, reply and forward prefill, saved and updated as local drafts only."""
from __future__ import annotations

import unittest

import _tpi_server as srv
from _tpi_compose_util import M1, M7, ComposeCase


class StartTest(ComposeCase):
    def test_new_is_blank_with_default_style(self):
        status, d = srv.post("/api/compose/start", {"kind": "new"})
        self.assertEqual(status, 200)
        self.assertEqual((d["kind"], d["to"], d["subject"], d["quote"]), ("new", "", "", ""))
        self.assertEqual(d["style"], "balanced")
        self.assertEqual(d["font"], "system")

    def test_reply_prefills_sender_subject_and_quote(self):
        status, d = srv.post("/api/compose/start", {"kind": "reply", "item_id": M1})
        self.assertEqual(status, 200)
        self.assertEqual(d["to"], "samira@northwind.example")
        self.assertEqual(d["subject"], "Re: Can you confirm the Friday scope before we send the deck?")
        self.assertTrue(d["quote"].startswith("On 2026-09-16 09:12, Samira Ortiz <samira@northwind.example> wrote:\n> "))
        self.assertIn("> Alex — we need a yes/no", d["quote"])
        self.assertEqual(d["in_reply_to"], M1)
        self.assertEqual(d["account"], "you@example.com")

    def test_reply_keeps_existing_re_prefix_and_warns_on_noreply(self):
        _, d = srv.post("/api/compose/start", {"kind": "reply", "item_id": "demo:you@example.com:m2"})
        self.assertTrue(d["subject"].startswith("Re: Action required"))
        self.assertEqual(len(d["warnings"]), 1)
        self.assertIn("no-reply", d["warnings"][0])

    def test_forward_quotes_header_and_warns_about_attachments(self):
        _, d = srv.post("/api/compose/start", {"kind": "forward", "item_id": M7})
        self.assertEqual(d["to"], "")
        self.assertEqual(d["subject"], "Fwd: Northwind term sheet comments")
        self.assertTrue(d["quote"].startswith("---------- Forwarded message ----------\nFrom: Samira Ortiz"))
        self.assertIn("Subject: Northwind term sheet comments", d["quote"])
        self.assertIn("Can you mark which one you will concede?", d["quote"])
        self.assertIn("attachments", d["warnings"][0])

    def test_chinese_prefill(self):
        _, d = srv.post("/api/compose/start", {"kind": "forward", "item_id": M7, "lang": "zh-Hant"})
        self.assertTrue(d["quote"].startswith("---------- 轉寄的郵件 ----------\n寄件者："))
        self.assertIn("附件", d["warnings"][0])
        _, r = srv.post("/api/compose/start", {"kind": "reply", "item_id": M1, "lang": "zh-Hant"})
        self.assertIn("Samira Ortiz <samira@northwind.example> 寫道：", r["quote"])

    def test_validation(self):
        self.assertEqual(srv.post("/api/compose/start", {"kind": "send"})[0], 400)
        self.assertEqual(srv.post("/api/compose/start", {"kind": "reply"})[0], 400)
        self.assertEqual(srv.post("/api/compose/start", {"kind": "forward", "item_id": "nope"})[0], 404)


class SaveTest(ComposeCase):
    def test_save_new_then_update_in_place(self):
        status, r = srv.post("/api/compose/draft", {"kind": "new", "to": "maya@studio.example", "cc": "ops@studio.example",
                                                    "subject": "Design review", "text": "Hi Maya,\n\nCan we move it?"})
        self.assertEqual(status, 201)
        self.assertTrue(r["ok"])
        self.assertIn("Nothing is sent", r["note"])
        d = r["draft"]
        self.assertEqual((d["kind"], d["to"], d["cc"], d["subject"]),
                         ("new", "maya@studio.example", "ops@studio.example", "Design review"))
        status, r2 = srv.post("/api/compose/draft", {"id": d["id"], "kind": "new", "to": "maya@studio.example",
                                                     "subject": "Design review v2", "text": "Hi Maya,\n\nMoved."})
        self.assertEqual(status, 200)
        self.assertEqual(r2["draft"]["id"], d["id"])
        self.assertEqual(r2["draft"]["subject"], "Design review v2")
        _, listing = srv.get("/api/compose/drafts")
        self.assertEqual([x["id"] for x in listing["drafts"]], [d["id"]])
        status, one = srv.get(f"/api/compose/draft/{d['id']}")
        self.assertEqual(status, 200)
        self.assertEqual(one["text"], "Hi Maya,\n\nMoved.")

    def test_reply_with_quote_shows_in_core_drafts_view(self):
        _, start = srv.post("/api/compose/start", {"kind": "reply", "item_id": M1})
        _, r = srv.post("/api/compose/draft", {"kind": "reply", "source_id": M1, "to": start["to"],
                                               "subject": start["subject"], "text": "Confirmed.", "quote": start["quote"]})
        d = r["draft"]
        self.assertEqual(d["body"], "Confirmed.\n\n" + start["quote"])
        self.assertEqual(d["text"], "Confirmed.")
        self.assertEqual(d["in_reply_to"], M1)
        _, core = srv.get("/api/drafts")
        row = next(x for x in core["drafts"] if x["id"] == d["id"])
        self.assertEqual(row["kind"], "reply")
        self.assertEqual(row["to_addr"], "samira@northwind.example")
        self.assertTrue(row["body"].startswith("Confirmed."))

    def test_core_delete_still_works(self):
        _, r = srv.post("/api/compose/draft", {"kind": "forward", "source_id": M7, "text": "FYI", "to": "pat@studio.example"})
        draft_id = r["draft"]["id"]
        self.assertEqual(srv.delete(f"/api/draft?id={draft_id}")[1]["changed"], 1)
        self.assertEqual(srv.get(f"/api/compose/draft/{draft_id}")[0], 404)

    def test_drafts_survive_local_cache_clear(self):
        _, r = srv.post("/api/compose/draft", {"kind": "new", "text": "keep me", "to": "pat@studio.example"})
        srv.post("/api/cache/clear", {"reseed": True})
        self.assertEqual(srv.get(f"/api/compose/draft/{r['draft']['id']}")[1]["text"], "keep me")

    def test_address_warnings_do_not_block_saving(self):
        status, r = srv.post("/api/compose/draft", {"kind": "new", "to": "maya@studio.example, not-an-address",
                                                    "text": "hi"})
        self.assertEqual(status, 201)
        self.assertEqual(len(r["warnings"]), 1)
        self.assertIn("not-an-address", r["warnings"][0])

    def test_validation(self):
        self.assertEqual(srv.post("/api/compose/draft", {"kind": "new"})[0], 400)
        self.assertEqual(srv.post("/api/compose/draft", {"kind": "send", "text": "x"})[0], 400)
        self.assertEqual(srv.post("/api/compose/draft", {"kind": "new", "text": "x", "style": "loud"})[0], 400)
        self.assertEqual(srv.post("/api/compose/draft", {"kind": "new", "text": "x", "font": "comic"})[0], 400)
        self.assertEqual(srv.post("/api/compose/draft", {"id": 99999, "kind": "new", "text": "x"})[0], 404)
        self.assertEqual(srv.post("/api/compose/draft", {"id": "x", "kind": "new", "text": "x"})[0], 400)
        self.assertEqual(srv.post("/api/compose/draft", {"kind": "reply", "source_id": "nope", "text": "x"})[0], 404)
        self.assertEqual(srv.get("/api/compose/draft/abc")[0], 400)


if __name__ == "__main__":
    unittest.main()
