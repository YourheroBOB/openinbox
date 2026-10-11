"""Drive server/mcp_server.py over real stdio, the way an MCP client does."""
from __future__ import annotations

import ast
import json
import os
import queue
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SERVER = REPO / "server" / "mcp_server.py"
TIMEOUT = 20


def bridge_tool_names() -> list[str]:
    tree = ast.parse((REPO / "server" / "agent_bridge.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "TOOLS" for t in node.targets):
            return [d["name"] for d in ast.literal_eval(node.value)]
    raise AssertionError("TOOLS not found in agent_bridge.py")


def make_root() -> Path:
    root = Path(tempfile.mkdtemp(prefix="tpi-mcp-"))
    for d in ("fixtures", "skills"):
        shutil.copytree(REPO / d, root / d)
    for f in ("accounts.example.json", "agent.example.json"):
        shutil.copy(REPO / f, root / f)
    return root


class McpProc:
    def __init__(self, root: Path):
        env = {**os.environ, "OPENINBOX_ROOT": str(root), "PYTHONIOENCODING": "utf-8"}
        self.p = subprocess.Popen(
            [sys.executable, str(SERVER)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env=env, cwd=str(root))
        self.lines: queue.Queue = queue.Queue()
        self.raw: list[bytes] = []
        threading.Thread(target=self._pump, daemon=True).start()
        threading.Thread(target=self.p.stderr.read, daemon=True).start()
        self._id = 0

    def _pump(self):
        for line in self.p.stdout:
            self.raw.append(line)
            self.lines.put(line)

    def send_raw(self, text: str):
        self.p.stdin.write(text.encode("utf-8") + b"\n")
        self.p.stdin.flush()

    def recv(self):
        return json.loads(self.lines.get(timeout=TIMEOUT).decode("utf-8"))

    def request(self, method: str, params=None):
        self._id += 1
        msg = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params is not None:
            msg["params"] = params
        self.send_raw(json.dumps(msg, ensure_ascii=False))
        resp = self.recv()
        assert resp.get("id") == self._id, resp
        return resp

    def notify(self, method: str, params=None):
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self.send_raw(json.dumps(msg))

    def call(self, name: str, arguments=None):
        params = {"name": name}
        if arguments is not None:
            params["arguments"] = arguments
        return self.request("tools/call", params)

    def close(self):
        try:
            self.p.stdin.close()
        except Exception:
            pass
        try:
            self.p.wait(timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            self.p.kill()
            self.p.wait()
        for s in (self.p.stdout, self.p.stderr):
            try:
                s.close()
            except Exception:
                pass


class McpStdioTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = make_root()
        cls.mcp = McpProc(cls.root)
        cls.init = cls.mcp.request("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "unittest", "version": "0"},
        })
        cls.mcp.notify("notifications/initialized")

    @classmethod
    def tearDownClass(cls):
        cls.mcp.close()
        shutil.rmtree(cls.root, ignore_errors=True)

    def payload(self, resp) -> dict:
        self.assertNotIn("error", resp)
        result = resp["result"]
        self.assertFalse(result["isError"], result)
        self.assertEqual(result["content"][0]["type"], "text")
        data = json.loads(result["content"][0]["text"])
        self.assertEqual(data, result["structuredContent"])
        return data

    def test_initialize(self):
        r = self.init["result"]
        self.assertEqual(self.init["jsonrpc"], "2.0")
        self.assertEqual(r["protocolVersion"], "2025-06-18")
        self.assertIn("tools", r["capabilities"])
        self.assertEqual(r["serverInfo"]["name"], "toopowerinbox")
        self.assertIn("save_draft", r["instructions"])
        self.assertIn("絕不寄出", r["instructions"])

    def test_initialize_negotiates_unknown_version(self):
        r = self.mcp.request("initialize", {"protocolVersion": "1999-01-01", "capabilities": {}})["result"]
        self.assertEqual(r["protocolVersion"], "2025-06-18")
        r = self.mcp.request("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}})["result"]
        self.assertEqual(r["protocolVersion"], "2024-11-05")

    def test_notification_gets_no_reply_and_ping_works(self):
        self.mcp.notify("notifications/initialized")
        self.mcp.notify("notifications/cancelled", {"requestId": 999})
        self.assertEqual(self.mcp.request("ping")["result"], {})

    def test_tools_list_matches_agent_bridge(self):
        tools = self.mcp.request("tools/list")["result"]["tools"]
        self.assertEqual([t["name"] for t in tools], bridge_tool_names())
        self.assertEqual({t["name"] for t in tools},
                         {"list_inbox", "brain_board", "search_brain", "persona", "save_draft"})
        for t in tools:
            self.assertEqual(t["inputSchema"]["type"], "object", t["name"])
            self.assertRegex(t["description"], r"[\u4e00-\u9fff]", t["name"])
            self.assertRegex(t["description"], r"[A-Za-z]{4}", t["name"])
        by = {t["name"]: t for t in tools}
        self.assertTrue(by["list_inbox"]["annotations"]["readOnlyHint"])
        self.assertFalse(by["save_draft"]["annotations"]["readOnlyHint"])
        self.assertFalse(by["save_draft"]["annotations"]["openWorldHint"])
        self.assertIn("Never sends", by["save_draft"]["description"])

    def test_list_inbox(self):
        data = self.payload(self.mcp.call("list_inbox", {"limit": 3}))
        self.assertEqual(len(data["emails"]), 3)
        for e in data["emails"]:
            self.assertTrue(e["account"].endswith("example.com"))
        hits = self.payload(self.mcp.call("list_inbox", {"q": "Northwind"}))["emails"]
        self.assertTrue(hits)
        self.assertTrue(all("northwind" in json.dumps(e).lower() for e in hits))
        everything = self.payload(self.mcp.call("list_inbox"))["emails"]
        self.assertEqual(len(everything), 8)

    def test_list_inbox_category_and_clamp(self):
        all_mail = self.payload(self.mcp.call("list_inbox", {"limit": 500}))["emails"]
        cats = {e["category"] for e in all_mail}
        cat = sorted(cats)[0]
        got = self.payload(self.mcp.call("list_inbox", {"category": cat}))["emails"]
        self.assertTrue(got)
        self.assertTrue(all(e["category"] == cat for e in got))
        self.assertEqual(len(self.payload(self.mcp.call("list_inbox", {"limit": "2"}))["emails"]), 2)
        self.assertEqual(len(self.payload(self.mcp.call("list_inbox", {"limit": 2.0}))["emails"]), 2)
        self.assertTrue(self.mcp.call("list_inbox", {"limit": 2.5})["result"]["isError"])

    def test_brain_board(self):
        data = self.payload(self.mcp.call("brain_board", {"hours": 24 * 365}))
        ids = [t["id"] for t in data["taxonomy"]]
        self.assertIn("needs_you", ids)
        self.assertEqual(set(data["counts"]), set(data["todos"]))
        self.assertEqual(data["window_hours"], 24 * 365)

    def test_search_brain(self):
        cards = self.payload(self.mcp.call("search_brain", {"q": ""}))["cards"]
        self.assertTrue(cards)
        word = cards[0]["title"].split()[0]
        hits = self.payload(self.mcp.call("search_brain", {"q": word}))["cards"]
        self.assertTrue(any(c["id"] == cards[0]["id"] for c in hits))
        self.assertEqual(self.payload(self.mcp.call("search_brain", {"q": "zzz-no-such-card-zzz"}))["cards"], [])
        self.assertTrue((self.root / "vault" / "index.json").exists())

    def test_persona(self):
        data = self.payload(self.mcp.call("persona", {}))
        self.assertIn("identity", data)
        self.assertIn("top_senders", data)
        self.assertEqual(data["mode"], "demo")

    def test_save_draft_is_local_only(self):
        data = self.payload(self.mcp.call("save_draft", {
            "to": "client@example.com", "subject": "Re: scope", "body": "Confirmed, thanks.",
        }))
        self.assertIs(data["sent"], False)
        self.assertIn("Local draft only", data["note"])
        zh = self.payload(self.mcp.call("save_draft", {
            "subject": "回覆：範圍", "body": "已確認，謝謝。", "lang": "zh-Hant",
        }))
        self.assertIn("草稿只留本機", zh["note"])
        con = sqlite3.connect(self.root / "data" / "openinbox.db")
        rows = con.execute("SELECT id, account, to_addr, subject, body FROM drafts ORDER BY id").fetchall()
        con.close()
        by_id = {r[0]: r for r in rows}
        self.assertEqual(by_id[data["id"]][1:], ("you@example.com", "client@example.com",
                                                 "Re: scope", "Confirmed, thanks."))
        self.assertEqual(by_id[zh["id"]][3:], ("回覆：範圍", "已確認，謝謝。"))

    def test_bad_arguments_are_tool_errors(self):
        for name, args in [
            ("list_inbox", {"limit": "many"}),
            ("list_inbox", {"category": "nope"}),
            ("list_inbox", {"bogus": 1}),
            ("save_draft", {"subject": "x"}),
            ("save_draft", {"subject": "x", "body": 5}),
            ("persona", ["not", "an", "object"]),
        ]:
            resp = self.mcp.call(name, args)
            self.assertNotIn("error", resp, (name, args))
            self.assertTrue(resp["result"]["isError"], (name, args))
            self.assertTrue(resp["result"]["content"][0]["text"])

    def test_protocol_errors(self):
        self.assertEqual(self.mcp.call("send_everything", {})["error"]["code"], -32602)
        self.assertEqual(self.mcp.request("tools/call", {})["error"]["code"], -32602)
        self.assertEqual(self.mcp.request("resources/list")["error"]["code"], -32601)
        self.mcp.send_raw("{not json")
        resp = self.mcp.recv()
        self.assertEqual(resp["error"]["code"], -32700)
        self.assertIsNone(resp["id"])
        self.mcp.send_raw(json.dumps({"jsonrpc": "1.0", "id": "x", "method": "ping"}))
        resp = self.mcp.recv()
        self.assertEqual((resp["id"], resp["error"]["code"]), ("x", -32600))
        self.assertEqual(self.mcp.request("ping")["result"], {})

    def test_batch(self):
        self.mcp.send_raw(json.dumps([
            {"jsonrpc": "2.0", "id": "a", "method": "ping"},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": "b", "method": "tools/list"},
        ]))
        resp = self.mcp.recv()
        self.assertIsInstance(resp, list)
        self.assertEqual([r["id"] for r in resp], ["a", "b"])

    def test_stdout_is_pure_json_rpc(self):
        self.mcp.request("ping")
        for line in list(self.mcp.raw):
            self.assertTrue(line.endswith(b"\n"))
            msg = json.loads(line.decode("utf-8"))
            for m in msg if isinstance(msg, list) else [msg]:
                self.assertEqual(m["jsonrpc"], "2.0")

    def test_uses_isolated_root(self):
        self.assertTrue((self.root / "data" / "openinbox.db").exists())


class McpLifecycleTest(unittest.TestCase):
    def test_exits_cleanly_on_eof(self):
        root = make_root()
        try:
            env = {**os.environ, "OPENINBOX_ROOT": str(root)}
            msgs = [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                 "params": {"protocolVersion": "2025-03-26", "capabilities": {}}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                 "params": {"name": "list_inbox", "arguments": {"limit": 1}}},
            ]
            p = subprocess.run([sys.executable, str(SERVER)],
                               input="".join(json.dumps(m) + "\n" for m in msgs).encode(),
                               capture_output=True, env=env, timeout=TIMEOUT)
            self.assertEqual(p.returncode, 0, p.stderr.decode())
            out = [json.loads(x) for x in p.stdout.decode().splitlines()]
            self.assertEqual([m["id"] for m in out], [1, 2])
            self.assertEqual(out[0]["result"]["protocolVersion"], "2025-03-26")
            self.assertEqual(len(json.loads(out[1]["result"]["content"][0]["text"])["emails"]), 1)
            self.assertIn(b"MCP server ready", p.stderr)
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
