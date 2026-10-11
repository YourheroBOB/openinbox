"""/api/cache and /api/cache/clear: wipe the local mail cache, keep drafts and notes."""
from __future__ import annotations

import unittest

import _tpi_server as srv


class CacheClearTest(unittest.TestCase):
    def setUp(self):
        srv.reseed()

    def tearDown(self):
        srv.reseed()

    def test_stats(self):
        status, s = srv.get("/api/cache")
        self.assertEqual(status, 200)
        self.assertEqual(s["cached"]["emails"], srv.N_EMAILS)
        self.assertEqual(s["cached"]["events"], srv.N_EVENTS)
        self.assertEqual(s["db"], "data/openinbox.db")
        self.assertGreater(s["db_bytes"], 0)
        self.assertIn("vault/index.json", s["derived_files"])
        self.assertGreater(s["derived_cards"], 0)

    def test_clear_wipes_cache_and_keeps_drafts_and_notes(self):
        _, draft = srv.post("/api/draft", {"to": "pat@example.com", "subject": "keep me", "body": "fictional"})
        srv.post("/api/second-brain", {"title": "my own note", "body": "fictional note", "kind": "note"})
        srv.post("/api/v1/agent/run", {"skill": "morning-brief"})
        note_card = srv.ROOT / "vault" / "cards" / "my-own-note.md"
        self.assertTrue(note_card.exists())

        status, r = srv.post("/api/cache/clear", {"lang": "en"})
        self.assertEqual(status, 200)
        self.assertTrue(r["ok"])
        self.assertFalse(r["reseeded"])
        self.assertEqual(r["cleared"]["emails"], srv.N_EMAILS)
        self.assertEqual(r["cleared"]["events"], srv.N_EVENTS)
        self.assertGreaterEqual(r["cleared"]["agent_turns"], 1)
        self.assertIn("vault/index.json", r["cleared"]["files"])
        self.assertIn("vault/persona.json", r["cleared"]["files"])
        self.assertIn("drafts", r["note"])
        self.assertGreaterEqual(r["kept"]["drafts"], 1)

        self.assertEqual(srv.get("/api/inbox")[1]["emails"], [])
        self.assertEqual(srv.get("/api/calendar")[1]["events"], [])
        self.assertEqual(srv.get("/api/health")[1]["counts"]["emails"], 0)
        _, s = srv.get("/api/cache")
        self.assertEqual(s["cached"], {"emails": 0, "events": 0, "agent_turns": 0})
        self.assertEqual(s["derived_cards"], 0)
        self.assertTrue(note_card.exists())
        self.assertIn(draft["id"], [d["id"] for d in srv.get("/api/drafts")[1]["drafts"]])
        srv.delete(f"/api/draft?id={draft['id']}")
        note_card.unlink()

    def test_clear_zh_note(self):
        _, r = srv.post("/api/cache/clear", {"lang": "zh-Hant"})
        self.assertIn("本機快取已清除", r["note"])

    def test_clear_is_idempotent(self):
        srv.post("/api/cache/clear")
        status, r = srv.post("/api/cache/clear")
        self.assertEqual(status, 200)
        self.assertEqual(r["cleared"]["emails"], 0)
        self.assertEqual(r["cleared"]["files"], [])

    def test_reseed_in_demo_mode(self):
        status, r = srv.post("/api/cache/clear", {"reseed": True})
        self.assertEqual(status, 200)
        self.assertTrue(r["reseeded"])
        self.assertEqual(len(srv.get("/api/inbox")[1]["emails"]), srv.N_EMAILS)

    def test_get_is_not_clear(self):
        self.assertEqual(srv.get("/api/cache/clear")[0], 404)
        self.assertEqual(srv.get("/api/cache")[1]["cached"]["emails"], srv.N_EMAILS)


if __name__ == "__main__":
    unittest.main()
