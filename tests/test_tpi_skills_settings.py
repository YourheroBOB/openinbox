"""Skill switches: listed, persisted in data/skills.json, enforced everywhere; BYO agent rewrite."""
from __future__ import annotations

import json
import sys
import unittest
import urllib.error
import urllib.request
from unittest import mock

import _tpi_server as srv
import agent_bridge
import features.skills as skills
import features.triage as triage
import features.usage as usage

AGENT_PATH = srv.ROOT / "agent.json"
ALL = ["morning-brief", "catch-me-up", "organize-inbox", "find-it",
       "meeting-prep", "brief-person", "slide", "crm-contact"]


def reset() -> None:
    skills.settings_path().unlink(missing_ok=True)
    AGENT_PATH.unlink(missing_ok=True)
    srv.reseed()


class SettingsTest(unittest.TestCase):
    def setUp(self):
        reset()
        self.addCleanup(reset)

    def test_listed_all_on_by_default(self):
        _, d = srv.get("/api/skills")
        self.assertEqual([s["slug"] for s in d["skills"]], ALL)
        self.assertTrue(all(s["enabled"] for s in d["skills"]))
        self.assertEqual(d["settings_file"], "data/skills.json")
        self.assertEqual([s["group"] for s in d["skills"]], ["F09"] * 4 + ["F10"] * 4)
        names = {s["slug"]: s["name"] for s in d["skills"]}
        self.assertEqual(names["find-it"], "Find It For Me")
        self.assertEqual(names["slide"], "Turn into a slide")
        self.assertTrue(all(s["prompt"].startswith("skills/") for s in d["skills"]), d["skills"])
        _, zh = srv.get("/api/skills?lang=zh-Hant")
        self.assertEqual({s["slug"]: s["name"] for s in zh["skills"]}["crm-contact"], "加入聯絡人 CRM")

    def test_toggle_persists_to_file(self):
        status, out = srv.post("/api/skills/settings", {"slug": "find-it", "enabled": False})
        self.assertEqual(status, 200)
        self.assertFalse(out["enabled"]["find-it"])
        stored = json.loads(skills.settings_path().read_text())
        self.assertIs(stored["enabled"]["find-it"], False)
        _, d = srv.get("/api/skills")
        self.assertFalse({s["slug"]: s["enabled"] for s in d["skills"]}["find-it"])
        status, out = srv.post("/api/skills/settings", {"enabled": {"find-it": True, "slide": False}})
        self.assertEqual(status, 200)
        self.assertTrue(out["enabled"]["find-it"])
        self.assertFalse(out["enabled"]["slide"])

    def test_bad_settings(self):
        self.assertEqual(srv.post("/api/skills/settings", {"slug": "nope", "enabled": False})[0], 400)
        self.assertEqual(srv.post("/api/skills/settings", {})[0], 400)
        skills.settings_path().parent.mkdir(parents=True, exist_ok=True)
        skills.settings_path().write_text("{not json")
        self.assertTrue(skills.is_enabled("morning-brief"))

    def test_unknown_skill(self):
        status, out = srv.post("/api/skills/run", {"skill": "nope"})
        self.assertEqual(status, 404)
        self.assertIn("morning-brief", out["skills"])

    def test_refusal_message_bilingual(self):
        srv.post("/api/skills/settings", {"slug": "catch-me-up", "enabled": False})
        _, en = srv.post("/api/skills/run", {"skill": "catch-me-up"})
        self.assertIn("switched off", en["message"])
        _, zh = srv.post("/api/skills/run", {"skill": "catch-me-up", "lang": "zh-Hant"})
        self.assertIn("已在設定中關閉", zh["message"])

    def test_run_counter(self):
        srv.post("/api/skills/run", {"skill": "organize-inbox"})
        srv.post("/api/skills/run", {"skill": "organize-inbox"})
        _, d = srv.get("/api/skills")
        s = {x["slug"]: x for x in d["skills"]}["organize-inbox"]
        self.assertEqual(s["runs"], 2)
        self.assertTrue(s["last_run_at"])

    def test_core_agent_route_honours_switch(self):
        _, ok = srv.post("/api/v1/agent/run", {"skill": "morning-brief", "lang": "en"})
        self.assertIn("Needs you", ok["answer"])
        srv.post("/api/skills/settings", {"slug": "morning-brief", "enabled": False})
        _, off = srv.post("/api/v1/agent/run", {"skill": "morning-brief", "lang": "en"})
        self.assertEqual(off["error"], "skill_disabled")
        self.assertTrue(off["disabled"])
        self.assertNotIn("Needs you:", off["answer"])
        srv.post("/api/skills/settings", {"slug": "organize-inbox", "enabled": False})
        _, off = srv.post("/api/v1/agent/run", {"skill": "categorize-inbox", "lang": "zh-Hant"})
        self.assertEqual(off["error"], "skill_disabled")
        _, free = srv.post("/api/v1/agent/run", {"ask": "hello", "lang": "en"})
        self.assertIsNone(free["error"])

    def test_core_agent_route_honours_every_switch(self):
        for meta in skills.SKILLS:
            with self.subTest(skill=meta["slug"], prompt=meta["prompt"]):
                self.assertTrue((srv.ROOT / "skills" / f"{meta['prompt']}.md").exists())
                srv.post("/api/skills/settings", {"enabled": {s: s != meta["slug"] for s in ALL}})
                _, off = srv.post("/api/v1/agent/run", {"skill": meta["prompt"], "lang": "en"})
                self.assertEqual(off["error"], "skill_disabled")
                self.assertTrue(off["disabled"])
                self.assertEqual(off["skill"], meta["prompt"])
                srv.post("/api/skills/settings", {"slug": meta["slug"], "enabled": True})
                _, on = srv.post("/api/v1/agent/run", {"skill": meta["prompt"], "lang": "en"})
                self.assertNotEqual(on.get("error"), "skill_disabled")

    def test_core_agent_route_switch_not_bypassed_by_path_spelling(self):
        srv.post("/api/skills/settings", {"slug": "find-it", "enabled": False})
        for name in ("./find-it-for-me", "../skills/find-it-for-me", "Find-It-For-Me", "x/../find-it-for-me"):
            with self.subTest(skill=name):
                _, off = srv.post("/api/v1/agent/run", {"skill": name, "lang": "en"})
                self.assertEqual(off["error"], "skill_disabled")
        _, other = srv.post("/api/v1/agent/run", {"skill": "../../find-it-for-me", "lang": "en"})
        self.assertNotEqual(other.get("error"), "skill_disabled")
        _, free = srv.post("/api/v1/agent/run", {"skill": "plan-my-week", "lang": "en"})
        self.assertNotEqual(free.get("error"), "skill_disabled")

    def test_slide_of_disabled_skill_refused(self):
        srv.post("/api/skills/settings", {"slug": "morning-brief", "enabled": False})
        status, out = srv.post("/api/skills/run", {"skill": "slide", "from_skill": "morning-brief"})
        self.assertEqual(status, 403)
        self.assertEqual(out["error"], "skill_disabled")
        self.assertEqual(out["skill"], "morning-brief")


class AgentRewriteTest(unittest.TestCase):
    def setUp(self):
        reset()
        self.addCleanup(reset)

    def use_cli(self, script: str) -> None:
        AGENT_PATH.write_text(json.dumps({"driver": "cli", "cli": {"command": [sys.executable, "-c", script],
                                                                   "timeout_sec": 20}}))

    def test_agent_rewrites_text_skills(self):
        self.use_cli("import sys,json; d=json.load(sys.stdin); print('REWRITE ' + str('Northwind' in d['ask']))")
        _, out = srv.post("/api/skills/run", {"skill": "find-it", "query": "northwind"})
        self.assertEqual(out["source"], "agent")
        self.assertEqual(out["agent_text"], "REWRITE True")
        self.assertEqual(out["source_label"], "AI rewrite · cli")
        self.assertIn("# Find it: northwind", out["markdown"])

    def test_agent_off_and_agent_failure(self):
        self.use_cli("print('X')")
        _, out = srv.post("/api/skills/run", {"skill": "catch-me-up", "agent": "off"})
        self.assertEqual(out["source"], "heuristic")
        self.use_cli("import sys; sys.exit(3)")
        _, out = srv.post("/api/skills/run", {"skill": "organize-inbox"})
        self.assertEqual(out["source"], "heuristic")
        self.assertTrue(out["agent_error"])

    def test_agent_false_or_zero_calls_no_model(self):
        usage.clear()
        self.addCleanup(usage.clear)
        for driver in ("cli", "openai_compatible", "http"):
            AGENT_PATH.write_text(json.dumps({
                "driver": driver, "cli": {"command": [sys.executable, "-c", "print('X')"], "timeout_sec": 20},
                "openai_compatible": {"base_url": "http://127.0.0.1:9/v1", "model": "m", "allow_private": True},
                "http": {"url": "http://127.0.0.1:9/agent", "allow_private": True}}))
            for value in (False, 0, 0.0, "off", "OFF", "false", "0", "no", " no "):
                with self.subTest(driver=driver, agent=value), \
                        mock.patch.object(triage, "ask_agent", side_effect=AssertionError("ask_agent")) as ask, \
                        mock.patch.object(agent_bridge, "_post_json", side_effect=AssertionError("_post_json")) as pj, \
                        mock.patch.object(agent_bridge, "_cli", side_effect=AssertionError("_cli")) as cli, \
                        mock.patch.object(agent_bridge, "_http", side_effect=AssertionError("_http")) as http:
                    status, out = srv.post("/api/skills/run", {"skill": "catch-me-up", "agent": value})
                    self.assertEqual(status, 200, out)
                    self.assertEqual((out["source"], out["agent_text"]), ("heuristic", ""))
                    self.assertNotIn("agent_error", out)
                    for m in (ask, pj, cli, http):
                        m.assert_not_called()
        self.assertEqual(usage.read_entries(), [])

    def test_agent_true_or_auto_still_rewrites(self):
        self.use_cli("print('REWRITE')")
        for value in (True, 1, "auto", "", None):
            with self.subTest(agent=value):
                body = {"skill": "catch-me-up"} if value is None else {"skill": "catch-me-up", "agent": value}
                _, out = srv.post("/api/skills/run", body)
                self.assertEqual(out["source"], "agent")
        self.assertTrue(skills.agent_off(False))
        self.assertFalse(skills.agent_off(None))

    def test_slide_and_crm_stay_local(self):
        self.use_cli("print('SHOULD NOT BE USED')")
        _, out = srv.post("/api/skills/run", {"skill": "slide", "markdown": "# A\n- b"})
        self.assertEqual(out["source"], "heuristic")
        self.assertEqual(out["agent_text"], "")


def post_from(path: str, body: dict, origin: str):
    req = urllib.request.Request(srv.BASE + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Origin": origin})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


class OriginTest(unittest.TestCase):
    def setUp(self):
        reset()
        usage.clear()
        skills.contacts_path().unlink(missing_ok=True)
        self.addCleanup(skills.contacts_path().unlink, missing_ok=True)
        self.addCleanup(reset)

    def test_state_changing_routes_refuse_other_origins(self):
        skills.run_skill("crm-contact", {"person": "Samira"})
        email = skills.load_contacts()[0]["email"]
        usage.record("cli", "x", 1, 1)
        routes = [("/api/skills/settings", {"slug": "find-it", "enabled": False}),
                  ("/api/skills/run", {"skill": "slide", "markdown": "# A\n- b"}),
                  ("/api/crm/contacts/update", {"email": email, "stage": "partner"}),
                  ("/api/crm/contacts/delete", {"email": email}),
                  ("/api/usage/clear", {})]
        slides = lambda: len(list(skills.slides_dir().glob("*.html"))) if skills.slides_dir().is_dir() else 0
        before = slides()
        for origin in ("http://evil.example", "http://127.0.0.1:1", "null"):
            for path, body in routes:
                with self.subTest(origin=origin, path=path):
                    status, out = post_from(path, body, origin)
                    self.assertEqual(status, 403, out)
                    self.assertIn("cross-origin", out["error"])
        self.assertTrue(skills.is_enabled("find-it"))
        self.assertEqual(slides(), before)
        self.assertEqual(skills.load_contacts()[0]["stage"], "lead")
        self.assertEqual(len(usage.read_entries()), 1)
        own = srv.BASE
        for path, body in routes:
            with self.subTest(origin=own, path=path):
                status, out = post_from(path, body, own)
                self.assertEqual(status, 200, out)
        self.assertFalse(skills.is_enabled("find-it"))
        self.assertEqual(skills.load_contacts(), [])
        self.assertEqual(usage.read_entries(), [])


if __name__ == "__main__":
    unittest.main()
