"""Mobile UI module: served by the loader, bilingual, hooked into the core views, and (with Chrome + Node)
driven end to end at phone size: drawer, list ↔ detail, back gesture, Copilot, service worker, installability."""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

import _tpi_server as srv

JS = srv.REPO / "ui" / "modules" / "mobile.js"
CDP = srv.REPO / "tests" / "_tpi_mobile_cdp.js"
CHROME = next((shutil.which(n) for n in ("google-chrome", "chromium", "chromium-browser") if shutil.which(n)), None)


def _node_can_drive_cdp() -> bool:
    if not shutil.which("node"):
        return False
    r = subprocess.run(["node", "-e", "process.exit(typeof WebSocket === 'function' && typeof fetch === 'function' ? 0 : 1)"],
                       capture_output=True)
    return r.returncode == 0


E2E = bool(CHROME) and _node_can_drive_cdp()


def _block(src: str, lang: str) -> str:
    m = re.search(rf"\n    {lang}: \{{\n(.*?)\n    \}},", src, re.S)
    assert m, lang
    return m.group(1)


class MobileModuleTest(unittest.TestCase):
    def test_listed_and_served(self):
        _, mods = srv.get("/api/ui-modules")
        self.assertIn("/ui/modules/mobile.js", mods["modules"])
        status, headers, raw = srv.request("GET", "/ui/modules/mobile.js")
        self.assertEqual(status, 200)
        self.assertIn("javascript", headers["Content-Type"])
        for needle in (b'register("/sw.js"', b"beforeinstallprompt", b"appinstalled", b"/manifest.webmanifest", b"/api/health"):
            self.assertIn(needle, raw)

    def test_strings_in_both_languages(self):
        src = JS.read_text()
        zh, en = _block(src, "zh"), _block(src, "en")
        keys = lambda b: set(re.findall(r"^\s*(\w+):", b, re.M))
        self.assertEqual(keys(zh), keys(en))
        for word in ("安裝 App", "加入主畫面", "郵件", "日曆", "草稿", "選單", "返回", "離線中", "不離線保存信件", "重試"):
            self.assertIn(word, zh)
        for word in ("Install app", "Add to Home Screen", "Mail", "Calendar", "Drafts", "Menu", "Back", "Offline",
                     "never your mail", "Retry"):
            self.assertIn(word, en)

    def test_hooks_into_core(self):
        src = JS.read_text()
        html = (srv.REPO / "ui" / "index.html").read_text()
        for anchor in ('id="app"', 'id="nav"', 'id="list"', 'id="pane"', 'id="copilot"', 'class="sidefoot"', 'id="tpi-module-loader"'):
            self.assertIn(anchor, html)
        for hook in ("window.setView", "window.openThread", "toggleCopilot", "history.pushState", "popstate",
                     "matchMedia", "@media (max-width: ${BREAKPOINT}px)", "safe-area-inset-bottom"):
            self.assertIn(hook, src)
        self.assertNotIn("mobile.js", html, "the module needs no script tag in ui/index.html")

    def test_layout_breakpoint_matches_server(self):
        _, info = srv.get("/api/mobile/info")
        self.assertIn(f"const BREAKPOINT = {info['breakpoint_px']};", JS.read_text())

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_js_syntax(self):
        for path in (JS, CDP):
            r = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)


class ReadmeTest(unittest.TestCase):
    def test_install_section_both_languages(self):
        for name, heading, words in (
            ("README.md", "## Install as an app (Mac, Windows, iOS, Android)", ("Add to Home Screen", "Install app", "/api/*")),
            ("README.zh-Hant.md", "## 安裝成 App（Mac、Windows、iOS、Android）", ("加入主畫面", "安裝 App", "/api/*")),
        ):
            text = (srv.REPO / name).read_text()
            self.assertIn(heading, text, name)
            section = text.split(heading, 1)[1].split("\n## ", 1)[0]
            for word in words:
                self.assertIn(word, section, name)
            self.assertNotIn("0.0.0.0", section, name)


@unittest.skipUnless(E2E, "needs Chrome and Node 22+ (global WebSocket)")
class PhoneEndToEndTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        profile = tempfile.mkdtemp(prefix="tpi-mobile-chrome-")
        try:
            r = subprocess.run(["node", str(CDP), CHROME, srv.BASE, profile], capture_output=True, text=True, timeout=150)
        except subprocess.TimeoutExpired:
            raise unittest.SkipTest("headless Chrome timed out")
        finally:
            shutil.rmtree(profile, ignore_errors=True)
        if r.returncode != 0:
            if "DevTools port" in r.stderr:
                raise unittest.SkipTest("headless Chrome unavailable")
            raise AssertionError("CDP run failed: " + r.stderr[-1500:])
        cls.out = json.loads(r.stdout)

    def test_narrow_layout(self):
        o = self.out
        self.assertTrue(o["narrow"])
        self.assertEqual(o["tabbar"], "flex")
        self.assertEqual(o["tabs"], ["mail", "calendar", "drafts", "copilot", "menu"])
        self.assertEqual((o["asideHidden"], o["sectionHidden"]), ("hidden", "hidden"))
        self.assertEqual(o["mainWidth"], 390)
        self.assertFalse(o["docOverflowX"], "no sideways scrolling on a phone")

    def test_list_to_detail_and_back(self):
        o = self.out
        self.assertEqual(o["detailLeft"], 0)
        self.assertTrue(o["detailTitle"])
        self.assertEqual(o["tabbarInDetail"], "none")
        self.assertEqual(o["backLabel"], "‹ 返回")
        self.assertEqual(o["afterBackLayers"], [])
        self.assertIsNone(o["afterBackButtonHistory"], "the back button consumes its history entry")

    def test_drawer_and_tabs(self):
        o = self.out
        self.assertEqual(o["drawerLeft"], 0)
        self.assertEqual(o["activeTab"], "drafts")
        self.assertTrue(o["calendarWide"])
        self.assertEqual(o["calendarMainWidth"], 390, "calendar's wide grid class must not break the phone layout")

    def test_copilot_full_screen(self):
        self.assertEqual(self.out["copilotRect"], [0, 390])
        self.assertEqual(self.out["layersEnd"], [])

    def test_compose_full_screen(self):
        if self.out["composeRect"] is None:
            self.skipTest("compose module not present")
        self.assertEqual(self.out["composeRect"], [0, 0, 390, 844])

    def test_language_switch(self):
        self.assertEqual(self.out["enLabels"], ["Mail", "Calendar", "Drafts", "Copilot", "Menu"])
        self.assertEqual(self.out["zhLabels"], ["郵件", "日曆", "草稿", "Copilot", "選單"])
        self.assertEqual(self.out["enManifest"], "/manifest.webmanifest?lang=en")

    def test_service_worker_controls_and_caches_static_only(self):
        o = self.out
        self.assertTrue(o["controlled"])
        _, info = srv.get("/api/mobile/info")
        self.assertEqual(o["cacheNames"], ["tpi-static-" + info["version"]])
        self.assertTrue(set(info["precache"]) <= set(o["cached"]))
        self.assertIn("/ui/modules/mobile.js", o["cached"])
        self.assertFalse([p for p in o["cached"] if p.startswith("/api/") or p == "/"], o["cached"])

    def test_chrome_says_installable(self):
        self.assertEqual(self.out["installErrors"], [])
        self.assertEqual(self.out["manifestErrors"], [])
        self.assertTrue(self.out["manifestUrl"].endswith("/manifest.webmanifest"))

    def test_desktop_width_unchanged(self):
        o = self.out
        self.assertFalse(o["wideNarrow"])
        self.assertEqual(o["wideTabbar"], "none")
        self.assertEqual(o["wideSection"], "visible")

    def test_no_page_errors(self):
        self.assertEqual(self.out["exceptions"], [])


@unittest.skipUnless(E2E, "needs Chrome and Node 22+ (global WebSocket)")
class OfflineEndToEndTest(unittest.TestCase):
    """A separate throwaway server that the browser can lose: banner while open, offline page on reload."""

    @classmethod
    def setUpClass(cls):
        root = Path(tempfile.mkdtemp(prefix="tpi-mobile-offline-"))
        for name in ("fixtures", "skills"):
            shutil.copytree(srv.REPO / name, root / name)
        for name in ("accounts.example.json", "agent.example.json"):
            shutil.copy(srv.REPO / name, root / name)
        (root / "vault" / "cards").mkdir(parents=True)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        env = {**os.environ, "OPENINBOX_ROOT": str(root), "OPENINBOX_PORT": str(port), "OPENINBOX_NO_BROWSER": "1"}
        server = subprocess.Popen([sys.executable, str(srv.REPO / "server" / "app.py")], env=env,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        base = f"http://127.0.0.1:{port}"
        profile = root / "chrome-profile"
        try:
            for _ in range(100):
                try:
                    urllib.request.urlopen(base + "/api/health", timeout=1).read()
                    break
                except OSError:
                    time.sleep(0.1)
            r = subprocess.run(["node", str(CDP), CHROME, base, str(profile), "offline", str(server.pid)],
                               capture_output=True, text=True, timeout=150)
        except subprocess.TimeoutExpired:
            raise unittest.SkipTest("headless Chrome timed out")
        finally:
            server.terminate()
            server.wait(timeout=10)
            shutil.rmtree(root, ignore_errors=True)
        if r.returncode != 0:
            if "DevTools port" in r.stderr:
                raise unittest.SkipTest("headless Chrome unavailable")
            raise AssertionError("CDP run failed: " + r.stderr[-1500:])
        cls.out = json.loads(r.stdout)

    def test_banner_when_server_goes_away(self):
        self.assertEqual(self.out["banner"], "flex")
        self.assertIn("離線中", self.out["bannerText"])

    def test_offline_page_served_from_cache(self):
        self.assertEqual(self.out["offlinePath"], "/", "the worker answers the navigation in place")
        self.assertEqual(self.out["offlineH1"], "連不到 TooPowerInbox")
        self.assertIn("不快取任何信件", self.out["offlineBody"])


if __name__ == "__main__":
    unittest.main()
