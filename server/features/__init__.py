"""Feature plug-ins: drop `server/features/<name>.py` and its routes register themselves.

    from features import get, post

    @get("/api/hello")
    def hello(req):
        return {"hello": req.query.get("name") or "world"}

    @post("/api/hello")
    def hello_post(req):
        return {"echo": req.body}, 201

A handler gets a `Request` and returns a dict (JSON, 200), a `(dict, status)`
tuple, or a `Raw` response. A path ending in `*` matches by prefix. Feature
routes are tried before the core routes in `app.py`, so never reuse a core path.
Modules whose name starts with `_` are skipped. A module that fails to import
is reported on `/api/features` instead of taking the server down.
"""
from __future__ import annotations

import importlib
import json
import pkgutil
import sys
import traceback
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import parse_qs, urlparse

METHODS = ("GET", "POST")
ROUTES: dict[str, dict[str, tuple[str, Callable]]] = {m: {} for m in METHODS}
LOADED: list[str] = []
ERRORS: list[dict] = []
_state = {"loaded": False}


@dataclass
class Request:
    method: str
    path: str
    query: dict = field(default_factory=dict)
    body: dict = field(default_factory=dict)
    handler: object = None
    params: str = ""

    def lang_zh(self) -> bool:
        lang = self.body.get("lang") if isinstance(self.body, dict) else None
        return str(lang or self.query.get("lang") or "").lower().startswith("zh")


@dataclass
class Raw:
    body: bytes
    content_type: str = "application/octet-stream"
    status: int = 200


def _owner(fn: Callable) -> str:
    mod = getattr(fn, "__module__", "") or ""
    return mod.split(".", 1)[1] if mod.startswith("features.") else mod


def route(method: str, path: str) -> Callable:
    method = method.upper()
    if method not in METHODS:
        raise ValueError(f"unsupported method {method}")
    if not path.startswith("/"):
        raise ValueError(f"route path must start with '/': {path}")

    def deco(fn: Callable) -> Callable:
        table = ROUTES[method]
        owner = _owner(fn)
        if path in table and table[path][0] != owner:
            ERRORS.append({"feature": owner, "error": f"{method} {path} already owned by {table[path][0]}"})
            return fn
        table[path] = (owner, fn)
        return fn
    return deco


def get(path: str) -> Callable:
    return route("GET", path)


def post(path: str) -> Callable:
    return route("POST", path)


def load_all() -> list[str]:
    if _state["loaded"]:
        return LOADED
    _state["loaded"] = True
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda i: i.name):
        if info.name.startswith("_"):
            continue
        try:
            importlib.import_module(f"{__name__}.{info.name}")
            LOADED.append(info.name)
        except Exception as e:
            ERRORS.append({"feature": info.name, "error": f"{type(e).__name__}: {e}"[:300]})
            traceback.print_exc(file=sys.stderr)
    return LOADED


def match(method: str, path: str) -> tuple[Callable, str] | None:
    table = ROUTES.get(method.upper()) or {}
    hit = table.get(path)
    if hit and not path.endswith("*"):
        return hit[1], ""
    best = None
    for pattern, (_, fn) in table.items():
        if pattern.endswith("*") and path.startswith(pattern[:-1]):
            if best is None or len(pattern) > len(best[0]):
                best = (pattern, fn)
    if best:
        return best[1], path[len(best[0]) - 1:]
    return None


def routes() -> list[dict]:
    return [
        {"method": m, "path": p, "feature": owner}
        for m in METHODS for p, (owner, _) in sorted(ROUTES[m].items())
    ]


def _read_body(handler) -> dict:
    n = int(handler.headers.get("Content-Length") or 0)
    if n <= 0:
        return {}
    try:
        data = json.loads(handler.rfile.read(n).decode())
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write(handler, body: bytes, content_type: str, status: int) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def dispatch(handler, method: str) -> bool:
    parsed = urlparse(handler.path)
    hit = match(method, parsed.path)
    if not hit:
        return False
    fn, params = hit
    req = Request(
        method=method, path=parsed.path, params=params, handler=handler,
        query={k: v[0] for k, v in parse_qs(parsed.query).items()},
        body=_read_body(handler) if method == "POST" else {},
    )
    try:
        out = fn(req)
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        out = ({"error": f"{type(e).__name__}: {e}"[:300]}, 500)
    status = 200
    if isinstance(out, tuple):
        out, status = out
    if isinstance(out, Raw):
        _write(handler, out.body, out.content_type, out.status)
    else:
        raw = json.dumps(out, ensure_ascii=False).encode()
        _write(handler, raw, "application/json; charset=utf-8", status)
    return True


def mount(base: type) -> type:
    """Wrap the core HTTP handler so feature routes are served first."""
    load_all()

    class FeatureHandler(base):
        def do_GET(self):
            if not dispatch(self, "GET"):
                super().do_GET()

        def do_POST(self):
            if not dispatch(self, "POST"):
                super().do_POST()

    FeatureHandler.__name__ = FeatureHandler.__qualname__ = base.__name__
    return FeatureHandler
