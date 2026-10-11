"""Installable PWA (F36): web app manifest, a static-only service worker, an offline page and app icons.

The service worker caches the offline page, the manifest, the icons and `ui/modules/*.js`.
It never touches `/api/*`, non-GET requests, other origins or page navigations beyond
falling back to the offline page, so no mail data ever lands in the browser cache.
"""
from __future__ import annotations

import hashlib
import json
import math
import struct
import zlib
from functools import lru_cache
from pathlib import Path

from features import Raw, get

UI = Path(__file__).resolve().parents[2] / "ui"
PWA = UI / "pwa"

NAME = "TooPowerInbox"
SHORT_NAME = "TooPower"
BG = "#14120f"
THEME = "#14120f"
ACCENT = (0xC4, 0xA5, 0x74)
ACCENT_DARK = (0x8F, 0x73, 0x43)
INK = (0x17, 0x13, 0x0C)

PNG_ICONS = {
    "tpi-192.png": (192, False),
    "tpi-512.png": (512, False),
    "tpi-maskable-192.png": (192, True),
    "tpi-maskable-512.png": (512, True),
}
APPLE_ICON = (180, True)
FAVICON = (48, False)

PRECACHE = [
    "/offline.html",
    "/manifest.webmanifest",
    "/icons/tpi.svg",
    "/icons/tpi-192.png",
    "/icons/tpi-512.png",
    "/icons/tpi-maskable-512.png",
    "/apple-touch-icon.png",
]
RUNTIME = ["/ui/modules/*.js"]
NEVER = ["/api/*", "non-GET", "cross-origin", "page HTML (navigations fall back to /offline.html only)"]

TEXT = {
    "zh": {
        "description": "本機 GenMail 式郵件大腦：統一收件匣、分類、Copilot、行事曆。資料留在你的機器，設計上不寄信。",
        "shortcuts": [("郵件", "/#view=mail"), ("日曆", "/#view=calendar"), ("草稿匣", "/#view=drafts"),
                      ("Copilot", "/#copilot=1")],
    },
    "en": {
        "description": "A local GenMail-style inbox brain: unified inbox, triage, Copilot, calendar. "
                       "Your data stays on your machine; it never sends mail by design.",
        "shortcuts": [("Mail", "/#view=mail"), ("Calendar", "/#view=calendar"), ("Drafts", "/#view=drafts"),
                      ("Copilot", "/#copilot=1")],
    },
}


def _lang(req) -> str:
    return "zh" if str(req.query.get("lang") or "zh").lower().startswith("zh") else "en"


def asset_version(ui: Path = UI) -> str:
    """Short hash of every static file the service worker may serve; bumps the cache on any change."""
    h = hashlib.sha256()
    files = [ui / "index.html"] + sorted((ui / "modules").glob("*.js")) + sorted((ui / "pwa").glob("*"))
    for p in files:
        if p.is_file():
            h.update(p.relative_to(ui).as_posix().encode() + b"\0" + p.read_bytes() + b"\0")
    h.update(json.dumps([PRECACHE, sorted(PNG_ICONS)]).encode())
    return h.hexdigest()[:12]


def manifest(lang: str = "zh") -> dict:
    text = TEXT[lang]
    icons = [{"src": "/icons/tpi.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any"}]
    for name, (size, maskable) in PNG_ICONS.items():
        icons.append({"src": f"/icons/{name}", "sizes": f"{size}x{size}", "type": "image/png",
                      "purpose": "maskable" if maskable else "any"})
    small = [{"src": "/icons/tpi-192.png", "sizes": "192x192", "type": "image/png"}]
    return {
        "id": "/",
        "name": NAME,
        "short_name": SHORT_NAME,
        "description": text["description"],
        "lang": "zh-Hant" if lang == "zh" else "en",
        "dir": "ltr",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "any",
        "background_color": BG,
        "theme_color": THEME,
        "categories": ["productivity", "business"],
        "icons": icons,
        "shortcuts": [{"name": n, "short_name": n, "url": u, "icons": small} for n, u in text["shortcuts"]],
    }


def service_worker() -> str:
    src = (PWA / "sw.js").read_text()
    return src.replace('"__TPI_VERSION__"', json.dumps(asset_version())).replace("__TPI_PRECACHE__", json.dumps(PRECACHE))


# ── icons: a gold rounded square with an ink envelope, drawn with signed distances ──

ENV_BOX = (0.5, 0.5, 0.28, 0.20)  # centre x, centre y, half width, half height (unit square)
ENV_TIP = (0.5, 0.535)
STROKE = 0.05
CORNER = 0.22


def _seg(px, py, ax, ay, bx, by) -> float:
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def _box(px, py, cx, cy, hx, hy, r=0.0) -> float:
    qx, qy = abs(px - cx) - hx + r, abs(py - cy) - hy + r
    return math.hypot(max(qx, 0.0), max(qy, 0.0)) + min(max(qx, qy), 0.0) - r


def _png(width: int, height: int, rows: list[bytes]) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    raw = b"".join(b"\0" + r for r in rows)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


@lru_cache(maxsize=None)
def icon_png(size: int, maskable: bool = False) -> bytes:
    cx, cy, hx, hy = ENV_BOX
    left, top, right = cx - hx, cy - hy, cx + hx
    tx, ty = ENV_TIP
    half = STROKE / 2
    rows = []
    for y in range(size):
        v = (y + 0.5) / size
        row = bytearray()
        for x in range(size):
            u = (x + 0.5) / size
            shape = 1.0 if maskable else max(0.0, min(1.0, 0.5 - _box(u, v, 0.5, 0.5, 0.5, 0.5, CORNER) * size))
            if shape <= 0.0:
                row += b"\0\0\0\0"
                continue
            d = min(abs(_box(u, v, cx, cy, hx, hy)), _seg(u, v, left, top, tx, ty), _seg(u, v, right, top, tx, ty))
            ink = max(0.0, min(1.0, (half - d) * size + 0.5))
            g = (u + v) / 2
            px = [round((ACCENT[i] * (1 - g) + ACCENT_DARK[i] * g) * (1 - ink) + INK[i] * ink) for i in range(3)]
            row += bytes(px + [round(255 * shape)])
        rows.append(bytes(row))
    return _png(size, size, rows)


def icon_svg() -> str:
    s = 512
    cx, cy, hx, hy = (n * s for n in ENV_BOX)
    tx, ty = (n * s for n in ENV_TIP)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {s} {s}" width="{s}" height="{s}">'
        '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="#{bytes(ACCENT).hex()}"/><stop offset="1" stop-color="#{bytes(ACCENT_DARK).hex()}"/>'
        '</linearGradient></defs>'
        f'<rect width="{s}" height="{s}" rx="{CORNER * s:g}" fill="url(#g)"/>'
        f'<g fill="none" stroke="#{bytes(INK).hex()}" stroke-width="{STROKE * s:g}" stroke-linejoin="round" stroke-linecap="round">'
        f'<rect x="{cx - hx:g}" y="{cy - hy:g}" width="{2 * hx:g}" height="{2 * hy:g}"/>'
        f'<path d="M{cx - hx:g} {cy - hy:g} L{tx:g} {ty:g} L{cx + hx:g} {cy - hy:g}"/>'
        '</g></svg>'
    )


# ── routes ──

@get("/manifest.webmanifest")
def serve_manifest(req):
    body = json.dumps(manifest(_lang(req)), ensure_ascii=False, indent=1).encode()
    return Raw(body, "application/manifest+json; charset=utf-8")


@get("/sw.js")
def serve_sw(req):
    return Raw(service_worker().encode(), "application/javascript; charset=utf-8")


@get("/offline.html")
def serve_offline(req):
    return Raw((PWA / "offline.html").read_bytes(), "text/html; charset=utf-8")


@get("/icons/*")
def serve_icon(req):
    name = req.params
    if name == "tpi.svg":
        return Raw(icon_svg().encode(), "image/svg+xml")
    if name in PNG_ICONS:
        return Raw(icon_png(*PNG_ICONS[name]), "image/png")
    return {"error": "not found"}, 404


@get("/apple-touch-icon.png")
def serve_apple_icon(req):
    return Raw(icon_png(*APPLE_ICON), "image/png")


@get("/apple-touch-icon-precomposed.png")
def serve_apple_icon_precomposed(req):
    return Raw(icon_png(*APPLE_ICON), "image/png")


@get("/favicon.ico")
def serve_favicon(req):
    return Raw(icon_png(*FAVICON), "image/png")


@get("/api/mobile/info")
def mobile_info(req):
    return {
        "name": NAME,
        "version": asset_version(),
        "manifest": "/manifest.webmanifest",
        "service_worker": "/sw.js",
        "offline": "/offline.html",
        "precache": list(PRECACHE),
        "runtime_cache": list(RUNTIME),
        "never_cached": list(NEVER),
        "breakpoint_px": 760,
    }
