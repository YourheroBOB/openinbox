"""FMB integration tests: the real HTTP server, end to end.

Every run builds a throwaway root (a temp dir), copies only the static inputs the server needs
(`fixtures/`, `skills/`, `ui/`), writes an obviously fake `agent.json` pinned to the `local`
driver, and boots `server/app.py` as a separate process on 127.0.0.1 with a random port. The
tests then drive it over HTTP with the standard library and inspect the files it writes.

Covered: health, dashboard shell, feature / UI-module registry, tool API, the agent task and
@agent mention flows (including the deliverable files on disk), cache clear + reseed, and the
error paths (bad task kind, empty request, cross-origin write, unknown route, malformed JSON).

No network beyond loopback, no real mailbox, no credentials: `agent.json` only carries
"FAKE_VALUE_FOR_TEST" style placeholders and the `local` driver never leaves the machine.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = REPO_ROOT / "server"

# Obviously fake BYO-agent config. The driver stays `local`, so nothing here is ever dialled.
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

CARD_ID_RE = r"^[a-z0-9][a-z0-9-]{2,80}$"


def _tail(blob, limit=400):
    try:
        return blob[:limit].decode("utf-8", "replace")
    except Exception:  # pragma: no cover - defensive
        return repr(blob[:limit])


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _build_root():
    root = Path(tempfile.mkdtemp(prefix="fmb-integration-"))
    (root / "data").mkdir(parents=True, exist_ok=True)
    (root / "vault" / "cards").mkdir(parents=True, exist_ok=True)
    for name in ("fixtures", "skills", "ui"):
        src = REPO_ROOT / name
        if src.is_dir():
            shutil.copytree(src, root / name)
    (root / "accounts.json").write_text(json.dumps(ACCOUNTS_CFG, indent=2), encoding="utf-8")
    (root / "agent.json").write_text(json.dumps(AGENT_CFG, indent=2), encoding="utf-8")
    return root


def _server_env(root, port):
    env = dict(os.environ)
    for key in list(env):
        if key.startswith("TPI_IMAP_") or key == "OPENINBOX_TODAY":
            env.pop(key, None)
    env["OPENINBOX_ROOT"] = str(root)
    env["OPENINBOX_PORT"] = str(port)
    env["OPENINBOX_NO_BROWSER"] = "1"
    env["PYTHONPATH"] = os.pathsep.join([str(SERVER_DIR), env.get("PYTHONPATH") or ""]).strip(os.pathsep)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _wait_health(port, proc, timeout=30.0):
    url = "http://127.0.0.1:%d/api/health" % int(port)
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        if proc.poll() is not None:
            try:
                err = (proc.stderr.read() or "")[-2000:]
            except Exception:  # pragma: no cover - defensive
                err = ""
            raise RuntimeError(
                "server exited (code %s) before it answered /api/health; "
                "check OPENINBOX_PORT support and stderr: %s" % (proc.returncode, err)
            )
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if getattr(resp, "status", 0) == 200:
                    return
        except Exception as exc:  # server still starting
            last = exc
        time.sleep(0.2)
    raise RuntimeError("server did not answer %s within %.0fs (last error: %r)" % (url, timeout, last))


def _stop(proc):
    if proc is None:
        return
    if proc.poll() is None:
        try:
            if os.name == "posix":
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            else:  # pragma: no cover - Windows
                proc.terminate()
        except Exception:  # pragma: no cover - defensive
            try:
                proc.terminate()
            except Exception:
                pass
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:  # pragma: no cover - defensive
        try:
            proc.kill()
            proc.wait(timeout=5)
        except Exception:
            pass
    for stream in (proc.stdout, proc.stderr):
        try:
            stream.close()
        except Exception:  # pragma: no cover - defensive
            pass


class RealServerE2E(unittest.TestCase):
    """Boot the real server once, then exercise it like a client would."""

    maxDiff = None
    root = None
    port = None
    proc = None

    @classmethod
    def setUpClass(cls):
        cls.root = _build_root()
        cls.port = _free_port()
        cls.proc = subprocess.Popen(
            [sys.executable, str(SERVER_DIR / "app.py")],
            cwd=str(cls.root),
            env=_server_env(cls.root, cls.port),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            text=True,
        )
        try:
            _wait_health(cls.port, cls.proc)
        except Exception:
            _stop(cls.proc)
            shutil.rmtree(cls.root, ignore_errors=True)
            raise

    @classmethod
    def tearDownClass(cls):
        _stop(cls.proc)
        if cls.root is not None:
            shutil.rmtree(cls.root, ignore_errors=True)

    # ── plumbing ───────────────────────────────────────────────
    def _url(self, path):
        return "http://127.0.0.1:%d%s" % (int(self.port), path)

    def _request(self, path, method="GET", body=None, headers=None, raw=None):
        data = raw
        hdrs = dict(headers or {})
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            hdrs.setdefault("Content-Type", "application/json")
        req = urllib.request.Request(self._url(path), data=data, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return getattr(resp, "status", 200), dict(resp.headers), resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers), exc.read()
        except urllib.error.URLError:
            return 0, {}, b""

    def _json(self, path, **kwargs):
        status, headers, body = self._request(path, **kwargs)
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception:
            payload = None
        return status, payload, body

    def _deliv_dir(self):
        return self.root / "data" / "deliverables"

    # ── scenarios ──────────────────────────────────────────────
    def test_health_and_dashboard_shell(self):
        status, payload, body = self._json("/api/health")
        self.assertEqual(status, 200, _tail(body))
        self.assertIsInstance(payload, dict, _tail(body))

        status, headers, body = self._request("/")
        self.assertEqual(status, 200, _tail(body))
        self.assertIn("html", (headers.get("Content-Type") or "").lower())
        self.assertIn(b"<html", body.lower())

        status, payload, body = self._json("/api/ui-modules")
        self.assertEqual(status, 200, _tail(body))
        self.assertIn("agents.js", body.decode("utf-8", "replace"))

    def test_feature_registry_and_tool_api(self):
        status, payload, body = self._json("/api/features")
        self.assertEqual(status, 200, _tail(body))
        self.assertIsInstance(payload, dict, _tail(body))
        self.assertIn("agents", body.decode("utf-8", "replace"))

        status, payload, body = self._json("/api/v1/tools")
        self.assertEqual(status, 200, _tail(body))
        self.assertIn("list_inbox", body.decode("utf-8", "replace"))

        for path in ("/api/v1/context?lang=zh-Hant", "/api/inbox", "/api/triage"):
            status, payload, body = self._json(path)
            self.assertEqual(status, 200, "%s -> %s %s" % (path, status, _tail(body)))

    def test_agent_task_writes_local_deliverable(self):
        status, payload, body = self._json(
            "/api/agents/task",
            method="POST",
            body={"kind": "research_person", "target": "Samira Ortiz", "lang": "zh-Hant"},
        )
        self.assertEqual(status, 200, _tail(body))
        self.assertIsInstance(payload, dict, _tail(body))

        card = payload.get("deliverable") or {}
        did = card.get("id") or ""
        self.assertRegex(did, CARD_ID_RE)
        self.assertEqual(card.get("kind"), "research_person")
        self.assertEqual(payload.get("driver"), "local", _tail(body))
        self.assertIn("Samira Ortiz", payload.get("text") or "")

        base = self._deliv_dir()
        for ext in ("md", "html", "json"):
            path = base / ("%s.%s" % (did, ext))
            self.assertTrue(path.is_file(), "missing deliverable file %s" % path)

        html_text = (base / ("%s.html" % did)).read_text(encoding="utf-8")
        self.assertNotIn("<script", html_text.lower())
        self.assertNotIn("onerror=", html_text.lower())

        status, payload, body = self._json("/api/agents/deliverables?limit=50")
        self.assertEqual(status, 200, _tail(body))
        ids = [c.get("id") for c in (payload.get("deliverables") or [])]
        self.assertIn(did, ids)

        status, headers, body = self._request("/api/agents/deliverables/%s.md" % did)
        self.assertEqual(status, 200, _tail(body))
        self.assertIn("markdown", (headers.get("Content-Type") or "").lower())
        self.assertEqual(body, (base / ("%s.md" % did)).read_bytes())

    def test_agent_task_error_paths(self):
        status, payload, body = self._json(
            "/api/agents/task", method="POST", body={"kind": "no_such_kind", "target": "x"}
        )
        self.assertEqual(status, 400, _tail(body))

        status, payload, body = self._json(
            "/api/agents/task",
            method="POST",
            body={"kind": "research_person", "target": "", "ask": ""},
        )
        self.assertEqual(status, 400, _tail(body))

        status, payload, body = self._json(
            "/api/agents/task",
            method="POST",
            body={"kind": "research_person", "target": "Samira Ortiz"},
            headers={"Origin": "http://fmb-evil.example"},
        )
        self.assertEqual(status, 403, _tail(body))

        status, payload, body = self._json("/api/agents/deliverables/no-such-card-here.md")
        self.assertEqual(status, 404, _tail(body))

        status, payload, body = self._json("/api/agents/deliverables/..%2F..%2Fserver%2Fapp.py.md")
        self.assertIn(status, (400, 404), _tail(body))
        self.assertLess(len(body), 500, "traversal answer looks like file content: %s" % _tail(body))

    def test_mention_routing(self):
        status, payload, body = self._json(
            "/api/agents/mention", method="POST", body={"text": "just a note to a human", "lang": "en"}
        )
        self.assertEqual(status, 200, _tail(body))
        self.assertFalse(payload.get("triggered"), _tail(body))

        status, payload, body = self._json(
            "/api/agents/mention",
            method="POST",
            body={"text": "@research Samira Ortiz recent threads", "lang": "en"},
        )
        self.assertEqual(status, 200, _tail(body))
        self.assertTrue(payload.get("triggered"), _tail(body))
        self.assertEqual((payload.get("mention") or {}).get("kind"), "research_person")

        did = (payload.get("deliverable") or {}).get("id") or ""
        self.assertRegex(did, CARD_ID_RE)
        self.assertTrue((self._deliv_dir() / ("%s.md" % did)).is_file())

        status, payload, body = self._json(
            "/api/agents/mention", method="POST", body={"email_id": "fmb-no-such-email"}
        )
        self.assertEqual(status, 404, _tail(body))

    def test_cache_clear_and_reseed(self):
        status, payload, body = self._json("/api/cache")
        self.assertEqual(status, 200, _tail(body))
        self.assertIsInstance(payload, dict, _tail(body))

        status, payload, body = self._json("/api/cache/clear", method="POST", body={"reseed": True})
        self.assertEqual(status, 200, _tail(body))

        status, payload, body = self._json("/api/health")
        self.assertEqual(status, 200, _tail(body))
        status, payload, body = self._json("/api/inbox")
        self.assertEqual(status, 200, _tail(body))

    def test_bad_input_does_not_kill_the_server(self):
        status, headers, body = self._request(
            "/api/agents/task",
            method="POST",
            raw=b"{this is not json",
            headers={"Content-Type": "application/json"},
        )
        self.assertNotEqual(status, 200, "malformed JSON must not be accepted: %s" % _tail(body))

        status, payload, body = self._json("/api/health")
        self.assertEqual(status, 200, "server stopped serving /api/health: %s" % _tail(body))

        status, payload, body = self._json("/api/fmb-integration-no-such-route")
        self.assertEqual(status, 404, _tail(body))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
