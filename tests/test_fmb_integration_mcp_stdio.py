"""FMB integration tests: the stdio MCP entry point plus the deliverable files it shares.

The first tests run `server/mcp_server.py` as a real subprocess and speak JSON-RPC 2.0 over
stdin/stdout, exactly like the README's `printf | python3 server/mcp_server.py` example. That
covers initialize, ping, tools/list, tools/call, a notification (no reply expected), an unknown
method (-32601) and a malformed line (-32700).

The last test imports the features package in a subprocess with OPENINBOX_ROOT pointed at a
temp dir and writes a card through the same code path the HTTP route uses, then checks the
files on disk: Markdown/HTML/JSON written, HTML escaped (no `<script`), deliverable ids
validated (bad ids and bad formats rejected), and listing finds the card.

Offline only: loopback subprocesses, a fake agent config pinned to the `local` driver, no real
mailbox, no credentials, and nothing written outside the temp dir.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = REPO_ROOT / "server"
MCP_ENTRY = SERVER_DIR / "mcp_server.py"

MCP_TOOLS = ("list_inbox", "brain_board", "search_brain", "persona", "save_draft")
CARD_ID_RE = r"^[a-z0-9][a-z0-9-]{2,80}$"
MARKER = "@@FMB@@"

ACCOUNTS_CFG = {
    "mode": "demo",
    "accounts": [
        {
            "email": "you@example.com",
            "platform": "gmail",
            "driver": "demo",
            "label": "Demo inbox",
        }
    ],
    "calendars": [],
}

AGENT_CFG = {
    "driver": "local",
    "openai_compatible": {
        "base_url": "http://127.0.0.1:11434/v1",
        "model": "FAKE_VALUE_FOR_TEST",
        "api_key_env": "FMB_FAKE_API_KEY_ENV",
    },
    "cli": {"command": ["true"], "timeout_sec": 10},
    "http": {"url": "http://127.0.0.1:9/agent", "timeout_sec": 5},
}

_CARD_SCRIPT = r'''
import json
import os
import sys

marker = os.environ["FMB_MARKER"]
root = os.environ["OPENINBOX_ROOT"]
sys.path.insert(0, os.environ["FMB_SERVER_DIR"])

import yhbmail

out = {
    "data_dir": str(yhbmail.DATA),
    "isolated": os.path.abspath(str(yhbmail.DATA)).startswith(os.path.abspath(root)),
}
if not out["isolated"]:
    print(marker + json.dumps(out))
    raise SystemExit(0)

import features.agents as agents

PAYLOAD = "<script>alert('FAKE_VALUE_FOR_TEST')</script>"
card = agents.save_deliverable({
    "kind": "meeting_prep",
    "target": PAYLOAD,
    "text": "## Agenda\n- " + PAYLOAD + "\n- budget",
    "driver": "local",
    "fallback": True,
    "sources": [],
}, lang="zh-Hant")

base = agents.DELIV_DIR
out["card"] = card
out["files"] = sorted(p.name for p in base.iterdir() if p.is_file())
out["md"] = (base / (card["id"] + ".md")).read_text(encoding="utf-8")
out["html"] = (base / (card["id"] + ".html")).read_text(encoding="utf-8")
out["md_ok"] = agents.read_deliverable(card["id"], "md") is not None
out["html_ok"] = agents.read_deliverable(card["id"], "html") is not None
out["bad_fmt_rejected"] = agents.read_deliverable(card["id"], "exe") is None
out["bad_ids_rejected"] = all(
    agents.read_deliverable(bad, "md") is None
    for bad in ("../server/app.py", "..%2Fserver%2Fapp.py", "a" * 200, "", "-nope", "UPPER", "ok.dot")
)
out["listed"] = [c.get("id") for c in agents.list_deliverables(10)]
print(marker + json.dumps(out, ensure_ascii=False))
'''


def _build_root():
    root = Path(tempfile.mkdtemp(prefix="fmb-mcp-"))
    (root / "data").mkdir(parents=True, exist_ok=True)
    (root / "vault" / "cards").mkdir(parents=True, exist_ok=True)
    for name in ("fixtures", "skills"):
        src = REPO_ROOT / name
        if src.is_dir():
            shutil.copytree(src, root / name)
    (root / "accounts.json").write_text(json.dumps(ACCOUNTS_CFG, indent=2), encoding="utf-8")
    (root / "agent.json").write_text(json.dumps(AGENT_CFG, indent=2), encoding="utf-8")
    return root


def _env(root):
    env = dict(os.environ)
    for key in list(env):
        if key.startswith("TPI_IMAP_") or key == "OPENINBOX_TODAY":
            env.pop(key, None)
    env["OPENINBOX_ROOT"] = str(root)
    env["OPENINBOX_NO_BROWSER"] = "1"
    env["FMB_SERVER_DIR"] = str(SERVER_DIR)
    env["FMB_MARKER"] = MARKER
    env["PYTHONPATH"] = os.pathsep.join([str(SERVER_DIR), env.get("PYTHONPATH") or ""]).strip(os.pathsep)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    return env


class McpStdioE2E(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        cls.root = _build_root()

    @classmethod
    def tearDownClass(cls):
        if cls.root is not None:
            shutil.rmtree(cls.root, ignore_errors=True)

    # ── plumbing ───────────────────────────────────────────────
    def _run_mcp(self, payload, timeout=90):
        proc = subprocess.run(
            [sys.executable, str(MCP_ENTRY)],
            input=payload,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(self.root),
            env=_env(self.root),
        )
        replies = []
        for line in (proc.stdout or "").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                replies.append(json.loads(line))
            except json.JSONDecodeError:
                self.fail(
                    "non-JSON line on stdout: %r (stderr tail: %r)"
                    % (line[:200], (proc.stderr or "")[-500:])
                )
        return proc, replies

    def _payload(self, messages):
        return "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in messages)

    # ── scenarios ──────────────────────────────────────────────
    def test_initialize_ping_tools_list_and_call(self):
        payload = self._payload(
            [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"protocolVersion": "2025-06-18", "capabilities": {}},
                },
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "ping"},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {"name": "list_inbox", "arguments": {}},
                },
                {"jsonrpc": "2.0", "id": 5, "method": "no/such/method"},
            ]
        )
        proc, replies = self._run_mcp(payload)
        self.assertEqual(proc.returncode, 0, (proc.stderr or "")[-1000:])
        # Five id-bearing requests, one notification: the notification must stay silent.
        self.assertEqual(len(replies), 5, replies)

        by_id = {r.get("id"): r for r in replies}
        self.assertIn("result", by_id.get(1) or {}, replies)
        self.assertIsInstance(by_id[1]["result"].get("protocolVersion"), str)

        self.assertIn("result", by_id.get(2) or {}, replies)

        tools = by_id[3]["result"]["tools"]
        names = {t.get("name") for t in tools}
        for expected in MCP_TOOLS:
            self.assertIn(expected, names)

        self.assertNotIn("error", by_id.get(4) or {}, by_id.get(4))
        self.assertIn("content", by_id[4]["result"])

        self.assertEqual(by_id[5]["error"]["code"], -32601, by_id[5])

    def test_parse_error_and_unknown_tool(self):
        payload = (
            "{this is not json}\n"
            + json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "fmb_no_such_tool", "arguments": {}},
                }
            )
            + "\n"
        )
        proc, replies = self._run_mcp(payload)
        self.assertEqual(proc.returncode, 0, (proc.stderr or "")[-1000:])

        codes = [(r.get("error") or {}).get("code") for r in replies]
        self.assertIn(-32700, codes, replies)

        bad_tool = [r for r in replies if r.get("id") == 2]
        self.assertEqual(len(bad_tool), 1, replies)
        reply = bad_tool[0]
        rejected = ("error" in reply) or bool((reply.get("result") or {}).get("isError"))
        self.assertTrue(rejected, reply)

    def test_deliverable_files_and_id_guards(self):
        root = Path(tempfile.mkdtemp(prefix="fmb-deliv-"))
        (root / "data").mkdir(parents=True, exist_ok=True)
        (root / "vault" / "cards").mkdir(parents=True, exist_ok=True)
        for name in ("fixtures", "skills"):
            src = REPO_ROOT / name
            if src.is_dir():
                shutil.copytree(src, root / name)
        (root / "accounts.json").write_text(json.dumps(ACCOUNTS_CFG, indent=2), encoding="utf-8")
        (root / "agent.json").write_text(json.dumps(AGENT_CFG, indent=2), encoding="utf-8")
        self.addCleanup(shutil.rmtree, root, True)

        proc = subprocess.run(
            [sys.executable, "-c", _CARD_SCRIPT],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(root),
            env=_env(root),
        )
        self.assertEqual(proc.returncode, 0, (proc.stderr or "")[-2000:])

        lines = [ln for ln in (proc.stdout or "").splitlines() if ln.startswith(MARKER)]
        self.assertTrue(lines, "script produced no result line; stdout=%r" % (proc.stdout or "")[:500])
        out = json.loads(lines[-1][len(MARKER):])

        self.assertTrue(out.get("isolated"), "OPENINBOX_ROOT was not honoured: %s" % out.get("data_dir"))
        self.assertTrue(str(out["data_dir"]).startswith(str(root)))

        card = out["card"]
        did = card.get("id") or ""
        self.assertRegex(did, CARD_ID_RE)
        self.assertEqual(card.get("kind"), "meeting_prep")

        for ext in ("md", "html", "json"):
            self.assertIn("%s.%s" % (did, ext), out["files"])

        self.assertIn("FAKE_VALUE_FOR_TEST", out["md"])

        html_text = out["html"]
        self.assertIn("&lt;script&gt;", html_text)
        self.assertNotIn("<script", html_text.lower())
        self.assertNotIn("onerror=", html_text.lower())

        self.assertTrue(out["md_ok"])
        self.assertTrue(out["html_ok"])
        self.assertTrue(out["bad_fmt_rejected"], "unknown format should be refused")
        self.assertTrue(out["bad_ids_rejected"], "unsafe deliverable ids should be refused")
        self.assertIn(did, out["listed"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
