"""Service worker: served at the root scope, versioned by asset hash, caches static assets only.

The behavioural test runs the served sw.js in Node with fake `caches`/`fetch` and checks that
mail data (/api/*), POSTs, other origins and page HTML never land in the cache.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import _tpi_server as srv

import features.mobile as mobile  # noqa: E402

SW_SRC = srv.REPO / "ui" / "pwa" / "sw.js"

HARNESS = r"""
const vm = require("vm");
const fs = require("fs");
const src = fs.readFileSync(process.argv[2], "utf8");
const ORIGIN = "http://127.0.0.1:8770";
const store = new Map();
const fetched = [];
let online = true;
const key = (r) => (typeof r === "string" ? new URL(r, ORIGIN).href : r.url);
const resp = (url) => ({ ok: true, type: "basic", url, body: "net:" + url, clone() { return { ...this, body: "cache:" + url }; } });
function fakeFetch(r) {
  const url = key(r);
  fetched.push(url);
  return online ? Promise.resolve(resp(url)) : Promise.reject(new TypeError("offline"));
}
function openCache(name) {
  if (!store.has(name)) store.set(name, new Map());
  const m = store.get(name);
  return {
    put: async (r, res) => { m.set(key(r), res); },
    match: async (r) => m.get(key(r)),
    addAll: async (list) => { for (const u of list) m.set(key(u), await fakeFetch(u)); },
  };
}
const caches = {
  open: async (n) => openCache(n),
  keys: async () => [...store.keys()],
  delete: async (n) => store.delete(n),
  match: async (r) => { for (const m of store.values()) if (m.has(key(r))) return m.get(key(r)); },
};
const listeners = {};
const self = {
  location: { origin: ORIGIN },
  addEventListener: (t, f) => { listeners[t] = f; },
  skipWaiting: async () => {},
  clients: { claim: async () => {} },
};
vm.runInNewContext(src, { self, caches, fetch: fakeFetch, URL, Promise, console });

async function lifecycle(type) {
  let p = Promise.resolve();
  listeners[type]({ waitUntil: (x) => { p = x; } });
  await p;
}
async function request(url, opts = {}) {
  let responded = null;
  listeners.fetch({ request: { url: new URL(url, ORIGIN).href, method: opts.method || "GET", mode: opts.mode || "cors" },
                    respondWith: (p) => { responded = p; } });
  if (!responded) return { intercepted: false };
  try { const r = await responded; return { intercepted: true, body: r.body }; }
  catch (e) { return { intercepted: true, error: String(e.message || e) }; }
}

(async () => {
  store.set("tpi-static-old", new Map([[ORIGIN + "/icons/tpi.svg", resp("old")]]));
  store.set("someone-else", new Map());
  await lifecycle("install");
  await lifecycle("activate");
  const mine = [...store.keys()].find((k) => k.startsWith("tpi-static-"));
  const out = { cachesAfterActivate: [...store.keys()], precached: [...store.get(mine).keys()] };
  out.api = await request("/api/inbox?limit=5");
  out.apiNav = await request("/api/thread/x", { mode: "navigate" });
  out.post = await request("/ui/modules/mobile.js", { method: "POST" });
  out.cross = await request("https://cdn.example.com/x.js");
  out.print = await request("/mailops/print?id=1");
  out.moduleOnline = await request("/ui/modules/mobile.js");
  out.navOnline = await request("/", { mode: "navigate" });
  online = false;
  out.moduleOffline = await request("/ui/modules/mobile.js");
  out.iconOffline = await request("/icons/tpi-192.png");
  out.navOffline = await request("/", { mode: "navigate" });
  out.unknownModuleOffline = await request("/ui/modules/never-seen.js");
  out.cachedUrls = [...store.values()].flatMap((m) => [...m.keys()]);
  out.fetched = fetched;
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
"""


class ServeTest(unittest.TestCase):
    def test_root_scope_javascript_no_store(self):
        status, headers, raw = srv.request("GET", "/sw.js")
        self.assertEqual(status, 200)
        self.assertIn("javascript", headers["Content-Type"])
        self.assertEqual(headers["Cache-Control"], "no-store", "browsers must always see a new worker")
        src = raw.decode()
        self.assertNotIn("__TPI_", src)
        _, info = srv.get("/api/mobile/info")
        self.assertIn(f'const VERSION = "{info["version"]}";', src)
        self.assertIn("const PRECACHE = " + json.dumps(info["precache"]) + ";", src)

    def test_precache_is_static_and_served(self):
        for path in mobile.PRECACHE:
            self.assertFalse(path.startswith("/api/"), path)
            self.assertEqual(srv.request("GET", path)[0], 200, path)

    def test_source_guards(self):
        src = SW_SRC.read_text()
        self.assertIn('url.pathname.startsWith("/api/")', src)
        self.assertIn('request.method !== "GET"', src)
        self.assertIn("url.origin !== self.location.origin", src)
        self.assertNotRegex(src, r"cache\.put\([^)]*api", "never store API responses")

    def test_offline_page(self):
        status, headers, raw = srv.request("GET", "/offline.html")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["Content-Type"])
        page = raw.decode()
        for word in ("連不到 TooPowerInbox", "不快取任何信件", "重試", "Can't reach TooPowerInbox", "never your mail", "Retry"):
            self.assertIn(word, page)
        self.assertNotRegex(page, r"""(src|href)=["']https?://""", "offline page must be self-contained")
        self.assertIn('localStorage.getItem("tpi-lang")', page)


class VersionTest(unittest.TestCase):
    def test_version_tracks_static_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            ui = Path(tmp) / "ui"
            shutil.copytree(srv.REPO / "ui", ui)
            before = mobile.asset_version(ui)
            self.assertEqual(before, mobile.asset_version(ui))
            (ui / "modules" / "mobile.js").write_text("/* changed */")
            self.assertNotEqual(before, changed := mobile.asset_version(ui))
            (ui / "pwa" / "offline.html").write_text("<p>changed</p>")
            self.assertNotEqual(changed, mobile.asset_version(ui))
        self.assertEqual(mobile.asset_version(), mobile.asset_version(srv.REPO / "ui"))

    def test_version_tracks_manifest_and_icons(self):
        before = mobile.asset_version()
        with mock.patch.dict(mobile.TEXT["en"], description="changed"):
            self.assertNotEqual(before, mobile.asset_version())
        with mock.patch.object(mobile, "STROKE", mobile.STROKE * 2):
            self.assertNotEqual(before, mobile.asset_version())
        self.assertEqual(before, mobile.asset_version())


@unittest.skipUnless(shutil.which("node"), "node not installed")
class BehaviourTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as tmp:
            sw = Path(tmp) / "sw.js"
            sw.write_bytes(srv.request("GET", "/sw.js")[2])
            harness = Path(tmp) / "harness.js"
            harness.write_text(HARNESS)
            r = subprocess.run(["node", str(harness), str(sw)], capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            raise AssertionError("harness failed: " + r.stderr[-800:])
        cls.out = json.loads(r.stdout)
        cls.version = srv.get("/api/mobile/info")[1]["version"]

    def test_syntax(self):
        r = subprocess.run(["node", "--check", str(SW_SRC)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_install_and_activate(self):
        self.assertEqual(sorted(self.out["cachesAfterActivate"]), sorted(["someone-else", "tpi-static-" + self.version]))
        self.assertEqual(sorted(re.sub(r"^https?://[^/]+", "", u) for u in self.out["precached"]), sorted(mobile.PRECACHE))

    def test_never_intercepts_mail_data_or_writes(self):
        for name in ("api", "apiNav", "post", "cross", "print"):
            self.assertEqual(self.out[name], {"intercepted": False}, name)

    def test_static_strategies(self):
        self.assertEqual(self.out["moduleOnline"]["body"], "net:http://127.0.0.1:8770/ui/modules/mobile.js")
        self.assertEqual(self.out["moduleOffline"]["body"], "cache:http://127.0.0.1:8770/ui/modules/mobile.js")
        self.assertTrue(self.out["iconOffline"]["body"].endswith("/icons/tpi-192.png"), "precached icon served offline")
        self.assertEqual(self.out["unknownModuleOffline"]["error"], "offline")

    def test_navigation_falls_back_to_offline_page_without_caching_html(self):
        self.assertEqual(self.out["navOnline"]["body"], "net:http://127.0.0.1:8770/")
        self.assertTrue(self.out["navOffline"]["body"].endswith("/offline.html"))

    def test_cache_holds_static_assets_only(self):
        paths = [re.sub(r"^https?://[^/]+", "", u) for u in self.out["cachedUrls"]]
        self.assertTrue(paths)
        static = re.compile(r"^/(offline\.html|manifest\.webmanifest|icons/[\w.-]+|apple-touch-icon\.png|favicon\.ico|ui/modules/[\w-]+\.js)$")
        for p in paths:
            self.assertRegex(p, static)
        self.assertNotIn("/", paths)
        self.assertFalse([u for u in self.out["fetched"] if "/api/" in u], "the worker itself never fetches /api/")


if __name__ == "__main__":
    unittest.main()
