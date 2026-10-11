"""Core HTTP API: health, inbox, thread, copilot, agent/run, drafts."""
from __future__ import annotations

import unittest
from urllib.parse import quote

import _tpi_server as srv

FIRST = srv.FIXTURE["emails"][0]


class HealthTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        srv.reseed()

    def test_health(self):
        status, h = srv.get("/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(h["ok"])
        self.assertEqual(h["name"], "TooPowerInbox")
        self.assertEqual(h["mode"], "demo")
        self.assertEqual(h["agent"], "local")
        self.assertEqual(h["counts"]["emails"], srv.N_EMAILS)
        self.assertEqual(h["counts"]["events"], srv.N_EVENTS)
        self.assertIn("running", h["sync"])

    def test_index_html_bilingual_with_module_loader(self):
        status, headers, raw = srv.request("GET", "/")
        html = raw.decode()
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["Content-Type"])
        self.assertIn("TooPowerInbox", html)
        self.assertIn("繁中", html)
        self.assertIn("English", html)
        self.assertEqual(html.count('id="tpi-module-loader"'), 1)
        self.assertIn("/api/ui-modules", html)

    def test_unknown_routes_404(self):
        self.assertEqual(srv.get("/api/nope")[0], 404)
        self.assertEqual(srv.post("/api/nope")[0], 404)
        self.assertEqual(srv.delete("/api/nope")[0], 404)

    def test_overview_and_accounts(self):
        status, ov = srv.get("/api/overview")
        self.assertEqual(status, 200)
        self.assertEqual(ov["agent"]["driver"], "local")
        self.assertTrue(any(s["slug"] == "morning-brief" for s in ov["skills"]))
        status, acc = srv.get("/api/accounts")
        self.assertEqual(status, 200)
        for a in acc["accounts"]:
            self.assertTrue(a["email"].endswith("@example.com"))


class InboxTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        srv.reseed()

    def test_list_all(self):
        status, data = srv.get("/api/inbox")
        self.assertEqual(status, 200)
        emails = data["emails"]
        self.assertEqual(len(emails), srv.N_EMAILS)
        ts = [e["date_ts"] for e in emails]
        self.assertEqual(ts, sorted(ts, reverse=True))
        self.assertIsInstance(emails[0]["labels"], list)
        self.assertNotIn("labels_json", emails[0])

    def test_limit(self):
        _, data = srv.get("/api/inbox?limit=2")
        self.assertEqual(len(data["emails"]), 2)

    def test_category_filter(self):
        _, data = srv.get("/api/inbox?category=needs_you")
        self.assertTrue(data["emails"])
        self.assertTrue(all(e["category"] == "needs_you" for e in data["emails"]))
        _, every = srv.get("/api/inbox?category=all")
        self.assertEqual(len(every["emails"]), srv.N_EMAILS)

    def test_search(self):
        word = FIRST["subject"].split()[2]
        _, data = srv.get("/api/inbox?q=" + quote(word))
        self.assertIn(FIRST["id"], [e["id"] for e in data["emails"]])
        _, none = srv.get("/api/inbox?q=" + quote("zz-no-such-text-zz"))
        self.assertEqual(none["emails"], [])

    def test_account_filter(self):
        _, data = srv.get("/api/inbox?account=" + quote(FIRST["account"]))
        self.assertTrue(data["emails"])
        _, none = srv.get("/api/inbox?account=" + quote("nobody@example.com"))
        self.assertEqual(none["emails"], [])

    def test_thread(self):
        status, item = srv.get("/api/thread/" + quote(FIRST["id"], safe=""))
        self.assertEqual(status, 200)
        self.assertEqual(item["subject"], FIRST["subject"])
        self.assertEqual(srv.get("/api/thread/missing")[0], 404)

    def test_read_toggle(self):
        status, r = srv.post("/api/read", {"id": FIRST["id"], "unread": False})
        self.assertEqual((status, r["changed"]), (200, 1))
        _, item = srv.get("/api/thread/" + quote(FIRST["id"], safe=""))
        self.assertEqual(item["unread"], 0)
        srv.post("/api/read", {"id": FIRST["id"], "unread": True})
        self.assertEqual(srv.post("/api/read", {})[0], 400)

    def test_brain_board(self):
        status, b = srv.get("/api/brain?hours=168")
        self.assertEqual(status, 200)
        self.assertEqual([t["id"] for t in b["taxonomy"]],
                         ["needs_you", "upcoming", "worth_a_look", "fyi", "other"])


class CopilotTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        srv.reseed()

    def copilot(self, **body):
        status, data = srv.post("/api/copilot", body)
        self.assertEqual(status, 200)
        self.assertEqual(data["driver"], "local")
        self.assertTrue(data["fallback"])
        return data

    def test_summarize_digest(self):
        co = self.copilot(mode="summarize", lang="en")
        self.assertEqual(co["mode"], "summarize")
        self.assertGreater(len(co["text"]), 10)

    def test_summarize_selected_email(self):
        en = self.copilot(mode="summarize", item_id=FIRST["id"], lang="en")
        self.assertIn(FIRST["subject"], en["text"])
        self.assertIn("local heuristic", en["text"])
        zh = self.copilot(mode="summarize", item_id=FIRST["id"], lang="zh-Hant")
        self.assertIn("本機啟發式", zh["text"])

    def test_todos_and_draft(self):
        todos = self.copilot(mode="todos", item_id=FIRST["id"], lang="en")
        self.assertTrue(todos["text"].strip())
        draft = self.copilot(mode="draft", item_id=FIRST["id"], lang="zh-Hant")
        self.assertIn("您好", draft["text"])

    def test_chat_with_history(self):
        co = self.copilot(mode="chat", ask="morning brief", lang="en",
                          history=[{"role": "user", "text": "hi"}, {"role": "model", "text": "hello"}, "junk"])
        self.assertIn("Needs you", co["text"])
        co = self.copilot(mode="chat", ask="晨間", lang="zh-Hant", history="not-a-list")
        self.assertIn("需要你", co["text"])


class AgentRunTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        srv.reseed()

    def test_morning_brief_bilingual(self):
        status, en = srv.post("/api/v1/agent/run", {"skill": "morning-brief", "lang": "en"})
        self.assertEqual(status, 200)
        self.assertEqual(en["driver"], "local")
        self.assertEqual(en["skill"], "morning-brief")
        self.assertIn("Needs you", en["answer"])
        self.assertIsNone(en["error"])
        _, zh = srv.post("/api/v1/agent/run", {"skill": "morning-brief", "lang": "zh-Hant"})
        self.assertIn("需要你", zh["answer"])

    def test_legacy_alias_and_freeform(self):
        status, r = srv.post("/api/agent", {"ask": "what is new?"})
        self.assertEqual(status, 200)
        self.assertEqual(r["skill"], "freeform")
        self.assertTrue(r["answer"])

    def test_tools(self):
        _, t = srv.get("/api/v1/tools")
        names = {x["name"] for x in t["tools"]}
        self.assertTrue({"list_inbox", "save_draft"} <= names)
        _, inbox = srv.post("/api/v1/tools/list_inbox", {"limit": 3})
        self.assertEqual(len(inbox["emails"]), 3)
        _, bad = srv.post("/api/v1/tools/no_such_tool", {})
        self.assertIn("error", bad)

    def test_context_pack(self):
        status, ctx = srv.get("/api/v1/context?lang=zh-Hant&skill=morning-brief")
        self.assertEqual(status, 200)
        self.assertEqual(ctx["lang"], "zh-Hant")
        self.assertTrue(ctx["skill_body"])
        self.assertTrue(any("不要寄信" in r for r in ctx["rules"]))


class DraftsTest(unittest.TestCase):
    def test_save_list_delete(self):
        body = {"account": "you@example.com", "to": "pat@example.com",
                "subject": "Re: test", "body": "Fictional draft body.", "lang": "en"}
        status, saved = srv.post("/api/draft", body)
        self.assertEqual(status, 200)
        self.assertIsInstance(saved["id"], int)
        self.assertIn("Local draft only", saved["note"])
        _, listing = srv.get("/api/drafts")
        mine = [d for d in listing["drafts"] if d["id"] == saved["id"]]
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0]["to_addr"], "pat@example.com")
        self.assertEqual(mine[0]["body"], "Fictional draft body.")
        status, gone = srv.delete(f"/api/draft?id={saved['id']}")
        self.assertEqual((status, gone["changed"]), (200, 1))
        _, listing = srv.get("/api/drafts")
        self.assertNotIn(saved["id"], [d["id"] for d in listing["drafts"]])

    def test_zh_note(self):
        _, saved = srv.post("/api/draft", {"to": "pat@example.com", "subject": "測試", "body": "虛構草稿", "lang": "zh-Hant"})
        self.assertIn("草稿只留本機", saved["note"])
        srv.delete(f"/api/draft?id={saved['id']}")

    def test_delete_validation(self):
        self.assertEqual(srv.delete("/api/draft?id=abc")[0], 400)
        self.assertEqual(srv.delete("/api/draft")[0], 400)
        status, r = srv.delete("/api/draft?id=999999")
        self.assertEqual((status, r["changed"]), (200, 0))


if __name__ == "__main__":
    unittest.main()
