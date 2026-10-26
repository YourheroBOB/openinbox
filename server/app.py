#!/usr/bin/env python3
"""TooPowerInbox HTTP app: dashboard + mail + second brain + BYO agent."""
from __future__ import annotations

import json
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
os.environ.setdefault("OPENINBOX_ROOT", str(ROOT))
sys.path.insert(0, str(HERE))

import agent_bridge  # noqa: E402
import features  # noqa: E402
import http_guard  # noqa: E402
import persona  # noqa: E402
import second_brain  # noqa: E402
import yhbmail  # noqa: E402

PORT = int(os.environ.get("OPENINBOX_PORT", "8770"))
UI = ROOT / "ui"
MAX_JSON_BODY = 1 * 1024 * 1024
_sync = {"running": False, "last": None, "error": None}
_sync_lock = threading.Lock()


def json_ok(handler, payload, status=200):
    raw = json.dumps(payload, ensure_ascii=False).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


def read_json(handler) -> tuple[dict | None, int | None]:
    raw_len = handler.headers.get("Content-Length")
    try:
        n = int(raw_len) if raw_len not in (None, "") else 0
    except ValueError:
        return None, 400
    if n < 0 or n > MAX_JSON_BODY:
        return None, 413
    if n <= 0:
        return {}, None
    try:
        data = json.loads(handler.rfile.read(n).decode())
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, 400
    if not isinstance(data, dict):
        return None, 400
    return data, None


def boot() -> None:
    yhbmail.init_db()
    cfg = yhbmail.load_cfg()
    if (cfg.get("mode") or "demo") == "demo":
        yhbmail.seed_demo()
    persona.rebuild()
    second_brain.rebuild()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def do_OPTIONS(self):
        self.send_response(405)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        q = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        if path in ("/", "/index.html"):
            html = (UI / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
            return
        if path == "/api/health":
            cfg_err = None
            try:
                cfg = yhbmail.load_cfg()
                agent_driver = agent_bridge.load_agent_cfg().get("driver")
                ok = True
            except Exception:
                cfg = {"mode": "unknown"}
                agent_driver = None
                ok = False
                cfg_err = "configuration unreadable"
            payload = {
                "ok": ok, "name": "TooPowerInbox", "port": PORT,
                "mode": cfg.get("mode") or "demo",
                "sync": _sync, "counts": yhbmail.counts(),
                "agent": agent_driver,
            }
            if cfg_err:
                payload["config_error"] = cfg_err
            return json_ok(self, payload, 503 if not ok else 200)
        if path == "/api/overview":
            cfg = agent_bridge.load_agent_cfg()
            return json_ok(self, {
                "counts": yhbmail.counts(),
                "board": yhbmail.brain_board(168),
                "persona": persona.load(),
                "brain": second_brain.load(),
                "skills": agent_bridge.list_skills(),
                "tools": agent_bridge.TOOLS,
                "agent": {"driver": cfg.get("driver") or "local"},
            })
        if path == "/api/inbox":
            try:
                lim = int(q.get("limit") or 80)
            except (TypeError, ValueError):
                return json_ok(self, {"error": "bad limit"}, 400)
            lim = max(1, min(lim, 200))
            return json_ok(self, {"emails": yhbmail.list_emails(
                account=q.get("account"), category=q.get("category"),
                q=q.get("q"), limit=lim)})
        if path == "/api/accounts":
            cfg = yhbmail.load_cfg()
            return json_ok(self, {
                "mode": cfg.get("mode") or "demo",
                "accounts": [
                    {"label": a.get("label") or (a.get("email") or "").split("@")[0],
                     "email": a.get("email") or "", "driver": a.get("driver") or "demo"}
                    for a in (cfg.get("accounts") or [])
                ],
            })
        if path == "/api/drafts":
            return json_ok(self, {"drafts": yhbmail.list_drafts()})
        if path.startswith("/api/thread/"):
            item = yhbmail.get_email(unquote(path[len("/api/thread/"):]))
            return json_ok(self, item or {"error": "not found"}, 200 if item else 404)
        if path == "/api/brain":
            try:
                hours = int(q.get("hours") or 168)
            except (TypeError, ValueError):
                return json_ok(self, {"error": "bad hours"}, 400)
            hours = max(1, min(hours, 24 * 365))
            return json_ok(self, yhbmail.brain_board(hours))
        if path == "/api/calendar":
            return json_ok(self, {"events": yhbmail.list_events()})
        if path == "/api/persona":
            return json_ok(self, persona.load())
        if path == "/api/second-brain":
            return json_ok(self, {"cards": second_brain.search(q.get("q") or "")})
        if path == "/api/v1/tools":
            return json_ok(self, {"tools": agent_bridge.TOOLS, "skills": agent_bridge.list_skills()})
        if path == "/api/v1/context":
            return json_ok(self, agent_bridge.context_pack(
                ask=q.get("ask") or "", skill=q.get("skill") or "", lang=q.get("lang") or "en"))
        return json_ok(self, {"error": "not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        if not http_guard.state_change_ok(self):
            return json_ok(self, {"error": "cross-origin request refused"}, 403)
        body, body_err = read_json(self)
        if body_err:
            return json_ok(self, {"error": "bad request body"}, body_err)
        if path == "/api/sync":
            with _sync_lock:
                if _sync["running"]:
                    return json_ok(
                        self, {"ok": False, "started": False, "error": "sync already running"}, 409,
                    )
                _sync["running"] = True
            try:
                limit = int(body.get("limit") or 25)
            except (TypeError, ValueError):
                with _sync_lock:
                    _sync["running"] = False
                return json_ok(self, {"error": "bad limit"}, 400)
            limit = max(1, min(limit, 100))

            def job():
                try:
                    report = yhbmail.sync_all(limit)
                    persona.rebuild()
                    second_brain.rebuild()
                    errs = [
                        f"{a.get('email') or '?'}: {a.get('error')}"
                        for a in (report.get("accounts") or []) if a.get("error")
                    ]
                    with _sync_lock:
                        if errs or not report.get("ok", True):
                            _sync["error"] = ("; ".join(errs) or "sync failed")[:300]
                        else:
                            _sync["last"] = yhbmail.now_iso()
                            _sync["error"] = None
                except Exception as e:
                    with _sync_lock:
                        _sync["error"] = str(e)[:300]
                finally:
                    with _sync_lock:
                        _sync["running"] = False

            threading.Thread(target=job, daemon=True).start()
            return json_ok(self, {"ok": True, "started": True})
        if path in ("/api/agent", "/api/v1/agent/run"):
            return json_ok(self, agent_bridge.run_agent(
                ask=body.get("ask") or "", skill=body.get("skill") or "",
                driver=body.get("driver"), lang=body.get("lang") or "en"))
        if path.startswith("/api/v1/tools/"):
            name = path[len("/api/v1/tools/"):]
            return json_ok(self, agent_bridge.invoke_tool(name, body))
        if path == "/api/second-brain":
            return json_ok(self, second_brain.add_card(
                body.get("title") or "note", body.get("body") or "", body.get("kind") or "note"))
        if path == "/api/copilot":
            history = body.get("history") or []
            if not isinstance(history, list):
                history = []
            history = [
                {"role": h.get("role") or "user", "text": str(h.get("text") or "")[:2000]}
                for h in history if isinstance(h, dict) and (h.get("text") or "").strip()
            ][-8:]
            return json_ok(self, agent_bridge.run_copilot(
                mode=(body.get("mode") or "chat").strip(),
                ask=(body.get("ask") or "").strip(),
                item_id=(body.get("item_id") or "").strip(),
                history=history,
                lang=body.get("lang") or "en"))
        if path == "/api/read":
            item_id = (body.get("id") or "").strip()
            if not item_id:
                return json_ok(self, {"error": "missing id"}, 400)
            changed = yhbmail.set_unread(item_id, bool(body.get("unread")))
            return json_ok(self, {"ok": True, "id": item_id, "unread": bool(body.get("unread")), "changed": changed})
        if path == "/api/draft":
            return json_ok(self, yhbmail.save_draft(
                body.get("account") or "you@example.com", body.get("to") or "",
                body.get("subject") or "", body.get("body") or "",
                lang=body.get("lang") or "en"))
        if path == "/api/rebuild":
            persona.rebuild()
            return json_ok(self, second_brain.rebuild())
        return json_ok(self, {"error": "not found"}, 404)

    def do_DELETE(self):
        if not http_guard.state_change_ok(self):
            return json_ok(self, {"error": "cross-origin request refused"}, 403)
        parsed = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        if parsed.path == "/api/draft":
            try:
                draft_id = int(q.get("id") or 0)
            except ValueError:
                return json_ok(self, {"error": "bad id"}, 400)
            if not draft_id:
                return json_ok(self, {"error": "missing id"}, 400)
            return json_ok(self, {"ok": True, "deleted": draft_id, "changed": yhbmail.delete_draft(draft_id)})
        return json_ok(self, {"error": "not found"}, 404)


Handler = features.mount(Handler)


def start_background() -> None:
    """Server start, not import. Tests call stop_ticker(); OPENINBOX_OUTBOX_TICK=0 keeps it off."""
    from features import outbox
    outbox.start_ticker()


def main() -> None:
    boot()
    start_background()
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://127.0.0.1:{PORT}/"
    print(f"TooPowerInbox  {url}", flush=True)
    if os.environ.get("OPENINBOX_NO_BROWSER") != "1":
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    httpd.serve_forever()


if __name__ == "__main__":
    main()
