"""Same-origin guards for core app routes (mirrors features/outbox policy)."""
from __future__ import annotations

import os
from urllib.parse import urlsplit

_LOCAL_HOST_ALIASES = frozenset({"localhost", "127.0.0.1", "::1"})


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


def _server_hostname(handler) -> str:
    host = (handler.headers.get("Host") or "").strip()
    if not host:
        return "127.0.0.1"
    if host.startswith("["):
        end = host.find("]")
        return host[1:end] if end > 0 else host
    return host.rsplit(":", 1)[0]


def _hosts_equivalent(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    na = a.lower().strip("[]")
    nb = b.lower().strip("[]")
    if na == nb:
        return True
    return na in _LOCAL_HOST_ALIASES and nb in _LOCAL_HOST_ALIASES


def state_change_ok(handler) -> bool:
    """POST/DELETE: block browser cross-site; allow curl and same-origin UI."""
    site = (handler.headers.get("Sec-Fetch-Site") or "").lower()
    if site and site not in ("same-origin", "none"):
        return False
    origin = handler.headers.get("Origin")
    if origin is None:
        return True
    parts = urlsplit(origin.strip().rstrip("/"))
    if parts.scheme not in ("http", "https"):
        return False
    if not _hosts_equivalent(parts.hostname, _server_hostname(handler)):
        return False
    try:
        origin_port = parts.port
        if origin_port is None:
            origin_port = 443 if parts.scheme == "https" else 80
    except ValueError:
        return False
    return origin_port == _host_port(handler)
