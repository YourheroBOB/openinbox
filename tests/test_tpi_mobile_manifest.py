"""PWA manifest: installable on Chrome/Edge (Mac, Windows, Android) and iOS home screen, bilingual."""
from __future__ import annotations

import json
import re
import unittest

import _tpi_server as srv

HTML = (srv.REPO / "ui" / "index.html").read_text()


def manifest(lang: str = ""):
    status, headers, raw = srv.request("GET", "/manifest.webmanifest" + (f"?lang={lang}" if lang else ""))
    return status, headers, json.loads(raw.decode())


class ManifestTest(unittest.TestCase):
    def test_served_with_manifest_type(self):
        status, headers, _ = manifest()
        self.assertEqual(status, 200)
        self.assertTrue(headers["Content-Type"].startswith("application/manifest+json"))

    def test_installability_fields(self):
        _, _, m = manifest()
        self.assertEqual(m["name"], "TooPowerInbox")
        self.assertTrue(m["short_name"] and len(m["short_name"]) <= 12)
        self.assertEqual((m["start_url"], m["scope"], m["id"]), ("/", "/", "/"))
        self.assertEqual(m["display"], "standalone")
        self.assertRegex(m["theme_color"], r"^#[0-9a-f]{6}$")
        self.assertRegex(m["background_color"], r"^#[0-9a-f]{6}$")
        sizes = {(i["sizes"], i.get("purpose", "any"), i["type"]) for i in m["icons"]}
        for need in (("192x192", "any", "image/png"), ("512x512", "any", "image/png"),
                     ("512x512", "maskable", "image/png"), ("any", "any", "image/svg+xml")):
            self.assertIn(need, sizes)

    def test_every_icon_resolves(self):
        _, _, m = manifest()
        srcs = [i["src"] for i in m["icons"]] + [i["src"] for s in m["shortcuts"] for i in s["icons"]]
        for src in set(srcs):
            status, headers, raw = srv.request("GET", src)
            self.assertEqual(status, 200, src)
            self.assertTrue(raw, src)

    def test_shortcuts_open_core_views(self):
        _, _, m = manifest()
        urls = [s["url"] for s in m["shortcuts"]]
        self.assertEqual(urls, ["/#view=mail", "/#view=calendar", "/#view=drafts", "/#copilot=1"])
        self.assertIn('h.get("view")', HTML)
        self.assertIn('h.get("copilot")', HTML)

    def test_both_languages(self):
        _, _, zh = manifest()
        _, _, en = manifest("en")
        self.assertEqual(zh["lang"], "zh-Hant")
        self.assertEqual(en["lang"], "en")
        self.assertRegex(zh["description"], r"[\u4e00-\u9fff]")
        self.assertNotRegex(en["description"], r"[\u4e00-\u9fff]")
        self.assertIn("郵件", [s["name"] for s in zh["shortcuts"]])
        self.assertIn("Mail", [s["name"] for s in en["shortcuts"]])
        self.assertEqual(zh["id"], en["id"], "one app identity across languages")
        _, _, zh2 = manifest("zh-Hant")
        self.assertEqual(zh2, zh)

    def test_index_links_manifest_and_ios_tags(self):
        for tag in ('<link rel="manifest" href="/manifest.webmanifest" />', 'name="theme-color"',
                    'name="apple-mobile-web-app-capable"', 'rel="apple-touch-icon" href="/apple-touch-icon.png"',
                    'viewport-fit=cover', '"beforeinstallprompt"'):
            self.assertIn(tag, HTML)
        head = HTML.split("</head>", 1)[0]
        self.assertIn('rel="manifest"', head)
        self.assertEqual(len(re.findall(r'rel="manifest"', HTML)), 1)

    def test_info_endpoint(self):
        status, info = srv.get("/api/mobile/info")
        self.assertEqual(status, 200)
        self.assertEqual(info["manifest"], "/manifest.webmanifest")
        self.assertEqual(info["service_worker"], "/sw.js")
        self.assertRegex(info["version"], r"^[0-9a-f]{12}$")
        self.assertIn("/api/*", info["never_cached"])
        self.assertFalse([p for p in info["precache"] if p.startswith("/api/")])


if __name__ == "__main__":
    unittest.main()
