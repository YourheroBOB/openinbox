"""F25 inline translation through the BYO agent; without an LLM a clear notice, never a fake."""
from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import _tpi_server as srv
from _tpi_mailops_util import mid, reset

yhbmail = srv.yhbmail
AGENT = yhbmail.ROOT / "agent.json"


class FakeAgent(BaseHTTPRequestHandler):
    """Loopback stand-in for the user's own agent worker (agent.json driver: http)."""
    seen: list = []
    reply = {"answer": "主旨：週五範圍確認\n\n請在週五前確認範圍。"}
    status = 200

    def log_message(self, *a):
        return

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        FakeAgent.seen.append(json.loads(self.rfile.read(n).decode()))
        raw = json.dumps(FakeAgent.reply, ensure_ascii=False).encode()
        self.send_response(FakeAgent.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class TranslateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        reset()
        cls.agent = ThreadingHTTPServer(("127.0.0.1", 0), FakeAgent)
        threading.Thread(target=cls.agent.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.agent.shutdown()
        cls.agent.server_close()
        reset()

    def setUp(self):
        AGENT.unlink(missing_ok=True)
        FakeAgent.seen.clear()
        FakeAgent.status = 200

    def wire_agent(self, **extra):
        port = self.agent.server_address[1]
        AGENT.write_text(json.dumps({"driver": "http", "http": {
            "url": f"http://127.0.0.1:{port}/agent", "timeout_sec": 10, "allow_private": True, **extra}}))

    def test_no_llm_gives_clear_notice(self):
        status, d = srv.post("/api/mailops/translate", {"id": mid(1), "lang": "zh-Hant"})
        self.assertEqual(status, 200)
        self.assertFalse(d["ok"])
        self.assertTrue(d["needs_agent"])
        self.assertEqual((d["driver"], d["target"]), ("local", "zh-Hant"))
        self.assertIn("未接 LLM", d["note"])
        self.assertIn("agent.json", d["note"])
        self.assertNotIn("text", d, "no fake translation without a model")
        _, en = srv.post("/api/mailops/translate", {"id": mid(1), "target": "ja"})
        self.assertIn("No LLM is wired", en["note"])
        self.assertEqual(en["target"], "ja")
        self.assertEqual(FakeAgent.seen, [])

    def test_translates_through_agent(self):
        self.wire_agent()
        status, d = srv.post("/api/mailops/translate", {"id": mid(1), "target": "zh-TW", "lang": "zh-Hant"})
        self.assertEqual(status, 200, d)
        self.assertTrue(d["ok"], d)
        self.assertEqual((d["driver"], d["target"], d["target_name"]), ("http", "zh-Hant", "繁體中文"))
        self.assertEqual(d["subject"], "週五範圍確認")
        self.assertEqual(d["text"], "請在週五前確認範圍。")
        self.assertIn("機器翻譯", d["note"])
        pack = FakeAgent.seen[-1]
        self.assertEqual(pack["mode"], "translate")
        self.assertIn("Traditional Chinese", pack["ask"])
        self.assertIn(srv.FIXTURE["emails"][0]["subject"], pack["ask"])
        self.assertIn("Keep names, numbers", pack["ask"])

    def test_plain_answer_without_subject_line(self):
        self.wire_agent()
        FakeAgent.reply = {"answer": "```\nPlease confirm the scope by Friday.\n```"}
        try:
            _, d = srv.post("/api/mailops/translate", {"id": mid(1), "target": "en"})
        finally:
            FakeAgent.reply = {"answer": "主旨：週五範圍確認\n\n請在週五前確認範圍。"}
        self.assertTrue(d["ok"])
        self.assertEqual(d["text"], "Please confirm the scope by Friday.")
        self.assertNotIn("subject", d)

    def test_agent_failure_keeps_original(self):
        self.wire_agent()
        FakeAgent.status = 500
        _, d = srv.post("/api/mailops/translate", {"id": mid(2), "lang": "zh-Hant"})
        self.assertFalse(d["ok"])
        self.assertIn("HTTP 500", d["error"])
        self.assertIn("原文未變動", d["note"])

    def test_sent_fixture_translates(self):
        self.wire_agent()
        _, sent = srv.get("/api/mailops/list?folder=sent")
        _, d = srv.post("/api/mailops/translate", {"id": sent["emails"][0]["id"], "target": "zh-Hant"})
        self.assertTrue(d["ok"])

    def test_bad_input(self):
        status, _ = srv.post("/api/mailops/translate", {"id": "nope"})
        self.assertEqual(status, 404)
        status, d = srv.post("/api/mailops/translate", {"id": mid(1), "target": "klingon"})
        self.assertEqual(status, 400)

    def test_languages(self):
        _, zh = srv.get("/api/mailops/languages?lang=zh-Hant")
        names = {x["id"]: x["name"] for x in zh["languages"]}
        self.assertEqual((names["zh-Hant"], names["en"]), ("繁體中文", "英文"))
        _, en = srv.get("/api/mailops/languages")
        self.assertEqual({x["id"]: x["name"] for x in en["languages"]}["ja"], "Japanese")


if __name__ == "__main__":
    unittest.main()
