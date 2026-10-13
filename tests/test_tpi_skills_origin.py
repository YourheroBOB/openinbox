"""Skills and usage routes refuse other web pages (Origin check) but serve this app's own UI."""
from __future__ import annotations

import json
import unittest
import urllib.error
import urllib.request

import _tpi_server as srv
import features.skills as skills
import features.usage as usage

EVIL = "https://evil.example"
CONTACT = "maya@studio.example"


def reset() -> None:
    skills.settings_path().unlink(missing_ok=True)
    skills.contacts_path().unlink(missing_ok=True)
    usage.USAGE_PATH.unlink(missing_ok=True)
    srv.reseed()


def send(method: str, path: str, origin: str, body=None):
    data = None if body is None else json.dumps(body).encode()
    headers = {"Origin": origin}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(srv.BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def own_origin() -> str:
    return f"http://127.0.0.1:{srv.SERVER.server_address[1]}"


class OriginTest(unittest.TestCase):
    def setUp(self):
        reset()
        self.addCleanup(reset)
        status, out = srv.post("/api/skills/run", {"skill": "crm-contact", "person": CONTACT})
        self.assertEqual(status, 200, out)
        status, out = srv.post("/api/skills/run", {"skill": "slide", "markdown": "# Secret deck\n- item"})
        self.assertEqual(status, 200, out)
        self.slide = out["data"]["name"]

    def routes(self):
        return [
            ("POST", "/api/skills/settings", {"slug": "find-it", "enabled": False}),
            ("POST", "/api/skills/run", {"skill": "organize-inbox"}),
            ("POST", "/api/crm/contacts/update", {"email": CONTACT, "note": "evil note"}),
            ("POST", "/api/crm/contacts/delete", {"email": CONTACT}),
            ("POST", "/api/usage/clear", {}),
            ("GET", "/api/crm/contacts", None),
            ("GET", "/api/skills/slides", None),
            ("GET", f"/api/skills/slides/{self.slide}", None),
            ("GET", "/api/usage", None),
        ]

    def test_cross_origin_refused(self):
        before_settings = srv.get("/api/skills")[1]
        before_contacts = srv.get("/api/crm/contacts")[1]["contacts"]
        for method, path, body in self.routes():
            with self.subTest(method=method, path=path):
                status, raw = send(method, path, EVIL, body)
                self.assertEqual(status, 403, raw)
                self.assertIn(b"cross-origin", raw)
                self.assertNotIn(b"Secret deck", raw)
                self.assertNotIn(CONTACT.encode(), raw)
        status, raw = send("POST", "/api/skills/run", EVIL, {"skill": "organize-inbox", "lang": "zh-Hant"})
        self.assertEqual(status, 403)
        self.assertIn("拒絕跨來源請求", raw.decode())
        self.assertEqual(srv.get("/api/skills")[1]["skills"], before_settings["skills"])
        after_contacts = srv.get("/api/crm/contacts")[1]["contacts"]
        self.assertEqual(after_contacts, before_contacts)
        self.assertTrue(skills.get_contact(CONTACT))
        self.assertNotIn("evil note", json.dumps(after_contacts))

    def test_lookalike_origins_refused(self):
        port = srv.SERVER.server_address[1]
        for origin in ("null", f"http://127.0.0.1:{port + 1}", f"http://127.0.0.1.evil.example:{port}",
                       f"https://127.0.0.1:{port}"):
            with self.subTest(origin=origin):
                self.assertEqual(send("GET", "/api/crm/contacts", origin)[0], 403)
                self.assertEqual(send("POST", "/api/skills/settings", origin,
                                      {"slug": "find-it", "enabled": False})[0], 403)
        self.assertTrue(skills.is_enabled("find-it"))

    def test_own_origin_allowed(self):
        port = srv.SERVER.server_address[1]
        for origin in (own_origin(), f"http://localhost:{port}"):
            for method, path, body in self.routes():
                if path.endswith("/crm/contacts/delete"):
                    continue
                with self.subTest(origin=origin, method=method, path=path):
                    status, raw = send(method, path, origin, body)
                    self.assertEqual(status, 200, raw)
        status, raw = send("GET", f"/api/skills/slides/{self.slide}", own_origin())
        self.assertIn(b"Secret deck", raw)
        self.assertFalse(skills.is_enabled("find-it"))
        status, raw = send("POST", "/api/crm/contacts/delete", own_origin(), {"email": CONTACT})
        self.assertEqual(status, 200, raw)
        self.assertIsNone(skills.get_contact(CONTACT))

    def test_no_origin_still_allowed(self):
        for method, path, body in self.routes():
            with self.subTest(method=method, path=path):
                self.assertEqual(srv.request(method, path, body)[0], 200, path)


class StrictBoolTest(unittest.TestCase):
    def setUp(self):
        reset()
        self.addCleanup(reset)

    def test_string_false_is_rejected_not_enabled(self):
        srv.post("/api/skills/settings", {"slug": "find-it", "enabled": False})
        for value in ("false", "true", 0, 1, None, [], "off"):
            with self.subTest(value=value):
                status, out = srv.post("/api/skills/settings", {"slug": "find-it", "enabled": value})
                self.assertEqual(status, 400, out)
                status, out = srv.post("/api/skills/settings", {"enabled": {"find-it": value}})
                self.assertEqual(status, 400, out)
                self.assertFalse(skills.is_enabled("find-it"))
        self.assertEqual(srv.post("/api/skills/settings", {"slug": "find-it", "enabled": True})[0], 200)
        self.assertTrue(skills.is_enabled("find-it"))

    def test_hand_edited_string_in_file_is_not_on(self):
        skills.settings_path().parent.mkdir(parents=True, exist_ok=True)
        skills.settings_path().write_text(json.dumps({"enabled": {"find-it": "false", "slide": True}}))
        self.assertFalse(skills.is_enabled("find-it"))
        self.assertTrue(skills.is_enabled("slide"))
        self.assertTrue(skills.is_enabled("morning-brief"))
        status, out = srv.post("/api/skills/run", {"skill": "find-it", "query": "northwind"})
        self.assertEqual(status, 403, out)


class CrmRaceTest(unittest.TestCase):
    def setUp(self):
        reset()
        self.addCleanup(reset)

    def test_update_after_concurrent_delete_is_404(self):
        srv.post("/api/skills/run", {"skill": "crm-contact", "person": CONTACT})
        real_get = skills.get_contact
        skills.get_contact = lambda email: {"email": email}
        self.addCleanup(setattr, skills, "get_contact", real_get)
        srv.post("/api/crm/contacts/delete", {"email": CONTACT})
        status, out = srv.post("/api/crm/contacts/update", {"email": CONTACT, "note": "late"})
        self.assertEqual(status, 404, out)
        self.assertEqual(out["error"], "contact not found")


if __name__ == "__main__":
    unittest.main()
