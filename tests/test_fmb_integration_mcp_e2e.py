"""End-to-end tests for the MCP stdio server (server/mcp_server.py).

These tests drive the real server as a subprocess against a throwaway copy of the
repository and speak JSON-RPC 2.0 over stdin/stdout, one message per line:

- happy paths: the initialize handshake, tools/list discovery, ping, and a
  read-only tools/call (list_inbox);
- error paths: an unknown method, an unknown tool, a malformed (non-JSON) line,
  a tools/call with no tool name, and save_draft with empty / dummy arguments.
  In every error case the server must answer (or at least stay alive and keep
  answering ping) instead of dying.

The throwaway copy deliberately excludes the operator's real local state
(data/, vault/, accounts.json, agent.json, rules.json, .env*), so nothing from
a real inbox can leak into a test run and no test writes into the checkout.
No network, no pip, stdlib only. No credential-shaped value is used anywhere;
the only fake marker is the literal string FAKE_VALUE_FOR_TEST.
"""
from __future__ import annotations

import itertools
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FAKE = "FAKE_VALUE_FOR_TEST"
FORBIDDEN_SECRET_PREFIXES = ("sk-", "ghp_", "gho_", "xox")

_IGNORED = {".git", ".github", "__pycache__", "data", "vault", "state",
            "accounts.json", "agent.json", "rules.json", ".idea", ".vscode",
            ".pr-review"}


def _copy_ignore(_dirpath, names):
    out = []
    for n in names:
        if (n in _IGNORED
                or n.endswith((".pyc", ".log", ".db", ".db-wal", ".db-shm"))
                or n.startswith(".env")):
            out.append(n)
    return out


def make_throwaway_root(base: Path) -> Path:
    """A clean, offline copy of the repo, seeded the way a fresh install.sh would."""
    root = base / "openinbox"
    shutil.copytree(REPO, root, ignore=_copy_ignore)
    shutil.copy(REPO / "accounts.example.json", root / "accounts.json")
    shutil.copy(REPO / "agent.example.json", root / "agent.json")
    (root / "vault" / "cards").mkdir(parents=True, exist_ok=True)
    return root


class McpStdioClient:
    """Minimal line-based MCP stdio client driving a real server subprocess."""

    def __init__(self, root: Path, timeout: float = 30.0):
        self.timeout = timeout
        env = dict(os.environ)
        env["OPENINBOX_ROOT"] = str(root)
        env.pop("PYTHONPATH", None)
        self.proc = subprocess.Popen(
            [sys.executable, "-u", str(root / "server" / "mcp_server.py")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=str(root), env=env, text=True)
        self._out = queue.Queue()
        self._err = []
        self.all_lines = []
        threading.Thread(target=self._pump_out, daemon=True).start()
        threading.Thread(target=self._pump_err, daemon=True).start()

    def _pump_out(self):
        for line in self.proc.stdout:
            line = line.rstrip("\r\n")
            self.all_lines.append(line)
            self._out.put(line)
        self._out.put(None)  # EOF sentinel

    def _pump_err(self):
        for line in self.proc.stderr:
            self._err.append(line)

    def stderr_text(self) -> str:
        return "".join(self._err[-40:])

    def send(self, payload) -> None:
        self.proc.stdin.write(json.dumps(payload) + "\n")
        self.proc.stdin.flush()

    def send_raw(self, text: str) -> None:
        self.proc.stdin.write(text + "\n")
        self.proc.stdin.flush()

    def notify(self, payload) -> None:
        """Send a notification (no id, no response expected)."""
        self.send(payload)

    def recv(self, want_id):
        deadline = time.monotonic() + self.timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AssertionError(
                    "timed out waiting for id=%s; server stderr tail:\n%s"
                    % (want_id, self.stderr_text()))
            try:
                line = self._out.get(timeout=remaining)
            except queue.Empty:
                continue
            if line is None:
                raise AssertionError(
                    "server closed stdout early (rc=%s); stderr tail:\n%s"
                    % (self.proc.poll(), self.stderr_text()))
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                continue  # tolerate non-JSON banner noise on stdout
            if not isinstance(msg, dict):
                continue
            if want_id is not None and msg.get("id") != want_id:
                continue  # a late error for a notification or another id
            return msg

    def call(self, payload):
        pid = payload.get("id")
        self.send(payload)
        return self.recv(pid)

    def close(self):
        proc = self.proc
        try:
            if proc.poll() is None:
                try:
                    if proc.stdin:
                        proc.stdin.close()
                except Exception:
                    pass
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=5)
        except Exception:
            pass


@unittest.skipIf(not (REPO / "server" / "mcp_server.py").is_file(),
                 "server/mcp_server.py not present")
class McpStdioEndToEnd(unittest.TestCase):
    EXPECTED_TOOLS = {"list_inbox", "brain_board", "search_brain", "persona", "save_draft"}

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="fmb_mcp_e2e_")
        cls.root = make_throwaway_root(Path(cls._tmp.name))
        cls.client = McpStdioClient(cls.root)
        cls._ids = itertools.count(1)
        cls.init_resp = cls.client.call({
            "jsonrpc": "2.0", "id": next(cls._ids), "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {}}})
        cls.client.notify({"jsonrpc": "2.0", "method": "notifications/initialized"})

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        cls._tmp.cleanup()

    def _call(self, method, params=None):
        payload = {"jsonrpc": "2.0", "id": next(self._ids), "method": method}
        if params is not None:
            payload["params"] = params
        return self.client.call(payload)

    # ── happy paths ──────────────────────────────────────────────

    def test_initialize_returns_result(self):
        r = self.init_resp
        self.assertIsNotNone(r.get("result"),
                             "initialize returned an error: %r" % (r,))

    def test_ping(self):
        r = self._call("ping")
        self.assertNotIn("error", r, "ping errored: %r" % (r,))
        self.assertIn("result", r)

    def test_tools_list_exposes_documented_tools(self):
        r = self._call("tools/list")
        self.assertNotIn("error", r, "tools/list errored: %r" % (r,))
        res = r.get("result") or {}
        self.assertIsInstance(res, dict, "unexpected tools/list result: %r" % (res,))
        tools = res.get("tools")
        self.assertIsInstance(tools, list, "tools/list result has no tool list: %r" % (res,))
        names = {t.get("name") for t in tools if isinstance(t, dict)}
        missing = self.EXPECTED_TOOLS - names
        self.assertFalse(missing, "documented tools missing from tools/list: %s" % sorted(missing))

    def test_list_inbox_call_returns_result(self):
        r = self._call("tools/call", {"name": "list_inbox", "arguments": {}})
        self.assertNotIn("error", r, "list_inbox errored: %r" % (r,))
        self.assertIsNotNone(r.get("result"), "list_inbox returned no result: %r" % (r,))

    # ── error paths ──────────────────────────────────────────────

    def test_malformed_line_does_not_kill_server(self):
        self.client.send_raw("{ this is not json")
        r = self._call("ping")
        self.assertIn("result", r, "server stopped answering after a malformed line: %r" % (r,))
        self.assertIsNone(self.client.proc.poll(), "server died after a malformed line")

    def test_unknown_method_is_an_error(self):
        r = self._call("no/such/method")
        self.assertIn("error", r, "unknown method was not reported as an error: %r" % (r,))
        code = (r.get("error") or {}).get("code")
        self.assertTrue(isinstance(code, int) and code < 0,
                        "unexpected error code for unknown method: %r" % (r,))

    def test_unknown_tool_is_an_error(self):
        r = self._call("tools/call", {"name": "no_such_tool", "arguments": {}})
        self.assertIn("error", r, "unknown tool was not reported as an error: %r" % (r,))

    def test_tools_call_without_name_is_survived(self):
        r = self._call("tools/call", {})
        self.assertIsInstance(r, dict, "no response for a nameless tools/call")
        r2 = self._call("ping")
        self.assertIn("result", r2, "server stopped answering after a nameless tools/call")
        self.assertIsNone(self.client.proc.poll(), "server died after a nameless tools/call")

    def test_save_draft_bad_args_keep_server_responsive(self):
        # Empty arguments and dummy fake-marker arguments: whatever the server
        # answers, it must answer and keep serving. No real data is written
        # anywhere outside the throwaway root.
        r1 = self._call("tools/call", {"name": "save_draft", "arguments": {}})
        self.assertIsInstance(r1, dict, "no response for save_draft with empty arguments")
        r2 = self._call("tools/call", {"name": "save_draft",
                                       "arguments": {"to": FAKE, "subject": FAKE, "body": FAKE}})
        self.assertIsInstance(r2, dict, "no response for save_draft with dummy arguments")
        r3 = self._call("ping")
        self.assertIn("result", r3, "server stopped answering after save_draft calls")
        self.assertIsNone(self.client.proc.poll(), "server died after save_draft calls")

    def test_zzz_stdout_never_carries_secret_shaped_strings(self):
        # Runs last (alphabetical) so it sees everything emitted during this
        # run. A credential-shaped prefix must never appear on stdout.
        blob = "\n".join(self.client.all_lines)
        for prefix in FORBIDDEN_SECRET_PREFIXES:
            self.assertNotIn(prefix, blob,
                             "secret-shaped prefix %r appeared on MCP stdout" % prefix)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
