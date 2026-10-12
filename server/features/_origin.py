"""Same-origin guard for routes that change local state (rules file, applied actions, overnight runs).

A request with no Origin header (curl, scripts, tests) or from this server's own UI is
accepted; any other web page is refused, so a site you visit cannot drive the local app.
"""
from __future__ import annotations

import os


def local_origin(req) -> bool:
    handler = req.handler
    origin = handler.headers.get("Origin") if handler is not None else None
    if origin is None:
        return True
    try:
        port = handler.server.server_address[1]
    except (AttributeError, IndexError, TypeError):
        port = int(os.environ.get("OPENINBOX_PORT", "8770"))
    return origin.strip().lower().rstrip("/") in (f"http://127.0.0.1:{port}", f"http://localhost:{port}")


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
