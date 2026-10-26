"""Same-origin guards for core app routes (mirrors features/outbox policy)."""
from __future__ import annotations

import os
from urllib.parse import urlsplit


def _host_port(handler) -> int:
    host = (handler.headers.get("Host") or "").strip()
    if host.startswith("["):
        end = host.find("]")
        rest = host[end + 1:] if end >= 0 else ""
        if rest.startswith(":") and rest[1:].isdigit():
            return int(rest[1:])
    elif ":" in host:
        maybe = host.rsplit(":", 1)[-1]
        if maybe.isdigit():
            return int(maybe)
    try:
        return handler.server.server_address[1]
    except (AttributeError, IndexError, TypeError):
        return int(os.environ.get("OPENINBOX_PORT", "8770"))


def state_change_ok(handler) -> bool:
    """POST/DELETE: block browser cross-site; allow curl and same-origin UI."""
    site = (handler.headers.get("Sec-Fetch-Site") or "").lower()
    if site and site not in ("same-origin", "none"):
        return False
    origin = handler.headers.get("Origin")
    if origin is None:
        return True
    parts = urlsplit(origin.strip().rstrip("/"))
    if parts.scheme != "http" or parts.hostname not in ("127.0.0.1", "localhost"):
        return False
    origin_port = parts.port or 80
    return origin_port == _host_port(handler)
