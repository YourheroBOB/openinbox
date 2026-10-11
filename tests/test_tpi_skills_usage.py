"""F35: BYOK token usage is appended to data/usage.jsonl and reported by /api/usage."""
from __future__ import annotations

import json
import os
import secrets
import sys
import threading
import unittest
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import _tpi_server as srv
import features.skills as skills
import features.usage as usage

AGENT_PATH = srv.ROOT / "agent.json"
SECRET = "fake-" + secrets.token_hex(12)


class FakeModel(BaseHTTPRequestHandler):
    mode = {"usage": True, "status": 200}
    seen: list = []

    def log_message(self, *a):
        return

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
        FakeModel.seen.append({"body": body, "auth": self.headers.get("Authorization")})
        if FakeModel.mode["status"] != 200:
            raw = b'{"error":"boom"}'
            self.send_response(FakeModel.mode["status"])
        else:
            out = {"model": "fake-model-v2", "choices": [{"message": {"content": "fake answer"}}]}
            if FakeModel.mode["usage"]:
                out["usage"] = {"prompt_tokens": 123, "completion_tokens": 45, "total_tokens": 168}
            if "messages" not in body:
                out = {"answer": "worker answer"}
            raw = json.dumps(out).encode()
            self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


MODEL = ThreadingHTTPServer(("127.0.0.1", 0), FakeModel)
MODEL_URL = f"http://127.0.0.1:{MODEL.server_address[1]}"
threading.Thread(target=MODEL.serve_forever, daemon=True).start()


def reset() -> None:
    AGENT_PATH.unlink(missing_ok=True)
    skills.settings_path().unlink(missing_ok=True)
    usage.clear()
    FakeModel.mode.update(usage=True, status=200)
    FakeModel.seen.clear()
    os.environ.pop("TPI_FAKE_KEY", None)


def use_openai() -> None:
    os.environ["TPI_FAKE_KEY"] = SECRET
    AGENT_PATH.write_text(json.dumps({"driver": "openai_compatible", "openai_compatible": {
        "base_url": MODEL_URL + "/v1", "model": "fake-model", "api_key_env": "TPI_FAKE_KEY", "allow_private": True}}))


class EstimateTest(unittest.TestCase):
    def test_estimate(self):
        self.assertEqual(usage.estimate_tokens(""), 0)
        self.assertEqual(usage.estimate_tokens("abcd" * 10), 10)
        self.assertEqual(usage.estimate_tokens("需要你"), 3)
        self.assertEqual(usage.estimate_tokens("需要你 abcd"), 3 + 2)
        self.assertGreater(usage.estimate_tokens([{"role": "user", "content": "hi"}]), 0)

    def test_wrappers_installed_once(self):
        import agent_bridge
        self.assertTrue(agent_bridge._post_json.__tpi_usage__)
        self.assertTrue(agent_bridge._cli.__tpi_usage__)
        before = agent_bridge._post_json
        usage.install()
        self.assertIs(agent_bridge._post_json, before)


class RecordTest(unittest.TestCase):
    def setUp(self):
        reset()
        self.addCleanup(reset)

    def lines(self):
        return [json.loads(x) for x in usage.USAGE_PATH.read_text().splitlines() if x.strip()]

    def test_openai_compatible_exact_counts(self):
        use_openai()
        _, out = srv.post("/api/copilot", {"mode": "summarize", "item_id": "demo:you@example.com:m1"})
        self.assertEqual(out["driver"], "openai_compatible")
        self.assertEqual(FakeModel.seen[-1]["auth"], f"Bearer {SECRET}")
        rows = self.lines()
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(usage.USAGE_PATH, srv.ROOT / "data" / "usage.jsonl")
        self.assertEqual((r["driver"], r["model"], r["feature"]), ("openai_compatible", "fake-model-v2", "copilot"))
        self.assertEqual((r["prompt_tokens"], r["completion_tokens"], r["total_tokens"]), (123, 45, 168))
        self.assertFalse(r["estimated"])
        self.assertTrue(r["ok"])
        self.assertEqual(r["host"], "127.0.0.1")
        raw = usage.USAGE_PATH.read_text()
        self.assertNotIn(SECRET, raw)
        self.assertNotIn("Friday scope", raw)
        self.assertNotIn("fake answer", raw)
        self.assertNotIn("/v1/chat", raw)

    def test_estimated_when_no_usage_block(self):
        use_openai()
        FakeModel.mode["usage"] = False
        srv.post("/api/skills/run", {"skill": "morning-brief", "today": "2026-09-17"})
        r = self.lines()[-1]
        self.assertEqual(r["feature"], "skills:morning-brief")
        self.assertTrue(r["estimated"])
        self.assertGreater(r["prompt_tokens"], 50)
        self.assertEqual(r["completion_tokens"], usage.estimate_tokens("fake answer"))

    def test_failures_are_counted(self):
        use_openai()
        FakeModel.mode["status"] = 500
        _, out = srv.post("/api/copilot", {"mode": "chat", "ask": "hi"})
        self.assertTrue(out["fallback"])
        r = self.lines()[-1]
        self.assertFalse(r["ok"])
        self.assertEqual(r["completion_tokens"], 0)
        self.assertIn("HTTP 500", r["error"])

    def test_cli_and_http_drivers(self):
        AGENT_PATH.write_text(json.dumps({"driver": "cli", "cli": {"command": [sys.executable, "-c", "print('ok ' * 8)"],
                                                                   "timeout_sec": 20}}))
        srv.post("/api/triage/summarize", {"ids": ["demo:you@example.com:m3"]})
        r = self.lines()[-1]
        self.assertEqual((r["driver"], r["feature"], r["model"]), ("cli", "triage:summary", os.path.basename(sys.executable)))
        self.assertTrue(r["estimated"])
        self.assertEqual(r["completion_tokens"], usage.estimate_tokens("ok " * 7 + "ok"))
        AGENT_PATH.write_text(json.dumps({"driver": "http", "http": {"url": MODEL_URL + "/agent", "allow_private": True}}))
        _, out = srv.post("/api/v1/agent/run", {"ask": "hello"})
        self.assertEqual(out["answer"], "worker answer")
        r = self.lines()[-1]
        self.assertEqual((r["driver"], r["feature"]), ("http", "agent"))

    def test_local_driver_records_nothing(self):
        srv.post("/api/copilot", {"mode": "summarize"})
        srv.post("/api/skills/run", {"skill": "catch-me-up"})
        self.assertEqual(usage.read_entries(), [])


class ReportTest(unittest.TestCase):
    def setUp(self):
        reset()
        self.addCleanup(reset)

    def test_report_aggregates(self):
        usage.record("openai_compatible", "m-a", 100, 20, False, True, "copilot")
        usage.record("openai_compatible", "m-a", 50, 10, False, True, "skills:find-it")
        usage.record("cli", "claude", 40, 0, True, False, "triage:summary", error="boom")
        status, d = srv.get("/api/usage")
        self.assertEqual(status, 200)
        self.assertEqual(d["file"], "data/usage.jsonl")
        self.assertEqual(d["totals"], {"calls": 3, "prompt_tokens": 190, "completion_tokens": 30,
                                       "total_tokens": 220, "estimated_calls": 1, "errors": 1})
        self.assertEqual([g["key"] for g in d["by_driver"]], ["openai_compatible", "cli"])
        self.assertEqual(d["by_driver"][0]["total_tokens"], 180)
        self.assertEqual([g["key"] for g in d["by_feature"]], ["copilot", "skills:find-it", "triage:summary"])
        self.assertEqual(d["by_model"][0]["key"], "openai_compatible · m-a")
        self.assertEqual(len(d["by_day"]), 1)
        self.assertEqual(d["recent"][0]["driver"], "cli")
        self.assertEqual(d["driver_now"], "local")
        self.assertIn("no model is called", d["note"])
        _, zh = srv.get("/api/usage?lang=zh-Hant")
        self.assertIn("不會呼叫模型", zh["note"])

    def test_window_and_bad_lines(self):
        old = (datetime.now(srv.yhbmail.TZ) - timedelta(days=40)).isoformat(timespec="seconds")
        usage.USAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with usage.USAGE_PATH.open("a") as f:
            f.write(json.dumps({"ts": old, "driver": "cli", "total_tokens": 999, "prompt_tokens": 999}) + "\n")
            f.write("not json\n\n")
        usage.record("cli", "x", 5, 5)
        _, d = srv.get("/api/usage?days=30")
        self.assertEqual(d["totals"]["calls"], 1)
        self.assertEqual(d["all_time"]["calls"], 2)
        _, d = srv.get("/api/usage?days=60&limit=1")
        self.assertEqual(d["totals"]["calls"], 2)
        self.assertEqual(len(d["recent"]), 1)

    def test_clear(self):
        usage.record("cli", "x", 1, 1)
        usage.record("cli", "x", 1, 1)
        status, out = srv.post("/api/usage/clear", {"lang": "zh-Hant"})
        self.assertEqual((status, out["cleared"]), (200, 2))
        self.assertEqual(out["note"], "已清除 2 筆用量紀錄。")
        self.assertEqual(srv.get("/api/usage")[1]["totals"]["calls"], 0)

    def test_survives_cache_clear(self):
        usage.record("cli", "x", 1, 1)
        srv.post("/api/cache/clear", {"reseed": True})
        self.assertEqual(len(usage.read_entries()), 1)


if __name__ == "__main__":
    unittest.main()
