"""Same-origin guard for routes that change local state (rules file, applied actions, overnight runs).

A request with no Origin header (curl, scripts, tests) or from this server's own UI is
accepted; any other web page is refused, so a site you visit cannot drive the local app.
"""
from __future__ import annotations

import os


def _host_port(handler) -> int | None:
    """Port from a loopback Host header (an ssh -L forward keeps the browser's port there)."""
    host = (handler.headers.get("Host") or "").strip().lower()
    name, _, port = host.rpartition(":")
    if name in ("127.0.0.1", "localhost") and port.isdigit():
        return int(port)
    return None


def local_origin(req) -> bool:
    handler = req.handler
    origin = handler.headers.get("Origin") if handler is not None else None
    if origin is None:
        return True
    ports = set()
    try:
        ports.add(int(handler.server.server_address[1]))
    except (AttributeError, IndexError, TypeError, ValueError):
        ports.add(int(os.environ.get("OPENINBOX_PORT", "8770")))
    host_port = _host_port(handler)
    if host_port is not None:
        ports.add(host_port)
    allowed = {f"http://{h}:{p}" for h in ("127.0.0.1", "localhost") for p in ports}
    return origin.strip().lower().rstrip("/") in allowed


def local_read(req) -> bool:
    """Same as local_origin, and a browser cross-site fetch is refused even when Origin is absent."""
    handler = getattr(req, "handler", None)
    if handler is not None:
        site = handler.headers.get("Sec-Fetch-Site")
        if site and site.lower() == "cross-site":
            return False
    return local_origin(req)


def refuse(zh: bool) -> tuple[dict, int]:
    msg = "拒絕跨來源請求：請從本機 App 介面操作" if zh else "cross-origin request refused: use this app's own UI"
    return {"error": msg}, 403
