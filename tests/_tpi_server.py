"""One in-process TooPowerInbox server shared by the whole unittest run.

It runs against a throwaway OPENINBOX_ROOT seeded only with the fictional
fixtures, so a developer's accounts.json / agent.json / data/ are never read.
"""
from __future__ import annotations

import atexit
import json
import os
import shutil
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROOT = Path(tempfile.mkdtemp(prefix="tpi-test-"))
for _name in ("fixtures", "skills"):
    shutil.copytree(REPO / _name, ROOT / _name)
for _name in ("accounts.example.json", "agent.example.json"):
    shutil.copy(REPO / _name, ROOT / _name)
(ROOT / "vault" / "cards").mkdir(parents=True)

os.environ["OPENINBOX_ROOT"] = str(ROOT)
os.environ["OPENINBOX_NO_BROWSER"] = "1"
sys.path.insert(0, str(REPO / "server"))

import app  # noqa: E402
import features  # noqa: E402
import persona  # noqa: E402
import second_brain  # noqa: E402
import yhbmail  # noqa: E402

assert yhbmail.ROOT == ROOT, "server modules were imported before the test root was set"

FIXTURE = json.loads((REPO / "fixtures" / "demo_inbox.json").read_text())
N_EMAILS = len(FIXTURE["emails"])
N_EVENTS = len(FIXTURE["events"])

app.boot()
SERVER = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
BASE = f"http://127.0.0.1:{SERVER.server_address[1]}"
threading.Thread(target=SERVER.serve_forever, daemon=True).start()


def _stop() -> None:
    SERVER.shutdown()
    SERVER.server_close()
    shutil.rmtree(ROOT, ignore_errors=True)


atexit.register(_stop)


def reseed() -> None:
    yhbmail.seed_demo()
    persona.rebuild()
    second_brain.rebuild()


def request(method: str, path: str, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def call(method: str, path: str, body=None):
    status, _, raw = request(method, path, body)
    return status, json.loads(raw.decode())


def get(path: str):
    return call("GET", path)


def post(path: str, body=None):
    return call("POST", path, body if body is not None else {})


def delete(path: str):
    return call("DELETE", path)
