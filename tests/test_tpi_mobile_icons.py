"""App icons: real PNGs (any + maskable), an SVG, the iOS touch icon and a favicon, all drawn with the stdlib."""
from __future__ import annotations

import struct
import unittest
import xml.etree.ElementTree as ET
import zlib

import _tpi_server as srv


def decode_png(raw: bytes):
    assert raw[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    pos, idat, ihdr = 8, b"", None
    while pos < len(raw):
        n = struct.unpack(">I", raw[pos:pos + 4])[0]
        tag, data = raw[pos + 4:pos + 8], raw[pos + 8:pos + 8 + n]
        crc = struct.unpack(">I", raw[pos + 8 + n:pos + 12 + n])[0]
        assert zlib.crc32(tag + data) & 0xFFFFFFFF == crc, f"bad CRC in {tag!r}"
        if tag == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", data)
        elif tag == b"IDAT":
            idat += data
        pos += 12 + n
    w, h, depth, color = ihdr[:4]
    assert (depth, color) == (8, 6), "expected 8-bit RGBA"
    pixels = zlib.decompress(idat)
    assert len(pixels) == h * (w * 4 + 1)
    stride = w * 4 + 1

    def px(x, y):
        o = y * stride + 1 + x * 4
        return tuple(pixels[o:o + 4])
    return w, h, px


class IconTest(unittest.TestCase):
    def fetch(self, path):
        status, headers, raw = srv.request("GET", path)
        self.assertEqual(status, 200, path)
        return headers, raw

    def test_png_sizes(self):
        for path, size in (("/icons/tpi-192.png", 192), ("/icons/tpi-512.png", 512),
                           ("/icons/tpi-maskable-192.png", 192), ("/icons/tpi-maskable-512.png", 512),
                           ("/apple-touch-icon.png", 180), ("/apple-touch-icon-precomposed.png", 180),
                           ("/favicon.ico", 48)):
            headers, raw = self.fetch(path)
            self.assertEqual(headers["Content-Type"], "image/png", path)
            w, h, _ = decode_png(raw)
            self.assertEqual((w, h), (size, size), path)

    def test_any_icon_has_rounded_transparent_corners(self):
        _, raw = self.fetch("/icons/tpi-192.png")
        _, _, px = decode_png(raw)
        self.assertEqual(px(0, 0)[3], 0)
        self.assertEqual(px(96, 4)[3], 255)
        self.assertEqual(px(96, 96)[3], 255)

    def test_maskable_and_ios_icons_are_full_bleed(self):
        for path in ("/icons/tpi-maskable-512.png", "/apple-touch-icon.png"):
            _, raw = self.fetch(path)
            w, h, px = decode_png(raw)
            for x, y in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
                self.assertEqual(px(x, y)[3], 255, path)

    def test_glyph_inside_maskable_safe_zone(self):
        _, raw = self.fetch("/icons/tpi-maskable-512.png")
        w, h, px = decode_png(raw)
        ink = [(x, y) for y in range(0, h, 4) for x in range(0, w, 4) if px(x, y)[0] < 60]
        self.assertTrue(ink, "envelope glyph should be drawn")
        radius = max(((x - w / 2) ** 2 + (y - h / 2) ** 2) ** 0.5 for x, y in ink)
        self.assertLess(radius, 0.4 * w, "glyph must stay in the 80% maskable safe zone")

    def test_svg(self):
        headers, raw = self.fetch("/icons/tpi.svg")
        self.assertEqual(headers["Content-Type"], "image/svg+xml")
        svg = ET.fromstring(raw.decode())
        self.assertTrue(svg.tag.endswith("svg"))
        self.assertEqual(svg.get("viewBox"), "0 0 512 512")

    def test_unknown_icon_404(self):
        for path in ("/icons/nope.png", "/icons/../app.py", "/icons/"):
            self.assertEqual(srv.request("GET", path)[0], 404, path)


if __name__ == "__main__":
    unittest.main()
