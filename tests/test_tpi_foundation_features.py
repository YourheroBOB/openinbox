"""Feature plug-in mechanism: server/features/*.py routes and ui/modules/*.js loader."""
from __future__ import annotations

import contextlib
import io
import re
import unittest

import _tpi_server as srv
from _tpi_server import features

FEATURES_DIR = srv.REPO / "server" / "features"
MODULES_DIR = srv.REPO / "ui" / "modules"


class RegistryTest(unittest.TestCase):
    def setUp(self):
        self._routes = {m: dict(t) for m, t in features.ROUTES.items()}
        self._errors = list(features.ERRORS)

    def tearDown(self):
        for m, t in self._routes.items():
            features.ROUTES[m].clear()
            features.ROUTES[m].update(t)
        features.ERRORS[:] = self._errors

    def test_every_feature_file_is_loaded(self):
        on_disk = sorted(p.stem for p in FEATURES_DIR.glob("*.py") if not p.stem.startswith("_"))
        self.assertEqual(sorted(features.LOADED), on_disk)
        self.assertEqual(features.ERRORS, [])

    def test_app_hook_is_mounted_once(self):
        src = (srv.REPO / "server" / "app.py").read_text()
        self.assertEqual(src.count("features.mount("), 1)
        self.assertTrue(issubclass(srv.app.Handler, srv.app.BaseHTTPRequestHandler))

    def test_feature_paths_do_not_shadow_core(self):
        core = set(re.findall(r'"(/(?:api/|index\.html)[^"]*)"', (srv.REPO / "server" / "app.py").read_text()))
        self.assertIn("/api/health", core)
        prefixes = [c for c in core if c.endswith("/")]
        for r in features.routes():
            path = r["path"].rstrip("*")
            self.assertNotIn(path, core, f"{r['feature']} shadows a core route")
            self.assertFalse(any(path.startswith(p) for p in prefixes), f"{r['feature']} sits under a core prefix")

    def test_runtime_registration_get_post_and_prefix(self):
        @features.get("/api/_t/echo")
        def echo(req):
            return {"q": req.query.get("x"), "zh": req.lang_zh()}

        @features.post("/api/_t/echo")
        def echo_post(req):
            return {"body": req.body}, 201

        @features.get("/api/_t/items/*")
        def item(req):
            return {"id": req.params}

        @features.get("/api/_t/boom")
        def boom(req):
            raise RuntimeError("kaboom")

        self.assertEqual(srv.get("/api/_t/echo?x=1&lang=zh-Hant"), (200, {"q": "1", "zh": True}))
        self.assertEqual(srv.post("/api/_t/echo", {"a": [1, 2]}), (201, {"body": {"a": [1, 2]}}))
        self.assertEqual(srv.get("/api/_t/items/abc"), (200, {"id": "abc"}))
        with contextlib.redirect_stderr(io.StringIO()):
            status, err = srv.get("/api/_t/boom")
        self.assertEqual(status, 500)
        self.assertIn("kaboom", err["error"])
        self.assertEqual(srv.call("DELETE", "/api/_t/echo")[0], 404)

    def test_non_dict_json_body_is_empty(self):
        @features.post("/api/_t/body")
        def body(req):
            return {"body": req.body}

        status, headers, raw = srv.request("POST", "/api/_t/body", [1, 2, 3])
        self.assertEqual((status, raw), (200, b'{"body": {}}'))

    def test_duplicate_route_keeps_first_owner(self):
        def first(req):
            return {"who": "first"}
        first.__module__ = "features.alpha"

        def second(req):
            return {"who": "second"}
        second.__module__ = "features.beta"

        features.get("/api/_t/dup")(first)
        features.get("/api/_t/dup")(second)
        self.assertEqual(srv.get("/api/_t/dup"), (200, {"who": "first"}))
        self.assertTrue(any("already owned by alpha" in e["error"] for e in features.ERRORS))

    def test_bad_route_definitions(self):
        with self.assertRaises(ValueError):
            features.route("PUT", "/api/x")
        with self.assertRaises(ValueError):
            features.get("api/x")

    def test_core_routes_still_work_through_mount(self):
        self.assertEqual(srv.get("/api/health")[0], 200)
        self.assertEqual(srv.post("/api/read", {})[0], 400)


class FeaturesEndpointTest(unittest.TestCase):
    def test_api_features(self):
        status, data = srv.get("/api/features")
        self.assertEqual(status, 200)
        self.assertIn("plugins", data["features"])
        self.assertIn("cache", data["features"])
        pairs = {(r["method"], r["path"]) for r in data["routes"]}
        self.assertTrue({("GET", "/api/features"), ("GET", "/api/ui-modules"),
                         ("GET", "/api/cache"), ("POST", "/api/cache/clear")} <= pairs)
        self.assertEqual(data["errors"], [])


class UiModulesTest(unittest.TestCase):
    def test_lists_every_module(self):
        on_disk = sorted(f"/ui/modules/{p.name}" for p in MODULES_DIR.glob("*.js"))
        status, data = srv.get("/api/ui-modules")
        self.assertEqual(status, 200)
        self.assertEqual(data["modules"], on_disk)
        self.assertIn("/ui/modules/cache.js", data["modules"])

    def test_serves_module_as_javascript(self):
        status, headers, raw = srv.request("GET", "/ui/modules/cache.js")
        self.assertEqual(status, 200)
        self.assertIn("javascript", headers["Content-Type"])
        self.assertEqual(raw, (MODULES_DIR / "cache.js").read_bytes())

    def test_rejects_traversal_and_unknown(self):
        for path in ("/ui/modules/nope.js", "/ui/modules/..%2Fapp.py", "/ui/modules/../index.html",
                     "/ui/modules/", "/ui/modules/.hidden.js", "/ui/modules/cache.js/x"):
            self.assertEqual(srv.request("GET", path)[0], 404, path)

    def test_modules_ship_zh_and_en_strings(self):
        for p in MODULES_DIR.glob("*.js"):
            src = p.read_text()
            self.assertRegex(src, r"\bzh:\s*\{", p.name)
            self.assertRegex(src, r"\ben:\s*\{", p.name)
            self.assertRegex(src, r"[\u4e00-\u9fff]", p.name)


if __name__ == "__main__":
    unittest.main()
