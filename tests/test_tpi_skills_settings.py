"""Skill switches: listed, persisted in data/skills.json, enforced everywhere; BYO agent rewrite."""
from __future__ import annotations

import json
import sys
import unittest

import _tpi_server as srv
import features.skills as skills

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

    def test_slide_and_crm_stay_local(self):
        self.use_cli("print('SHOULD NOT BE USED')")
        _, out = srv.post("/api/skills/run", {"skill": "slide", "markdown": "# A\n- b"})
        self.assertEqual(out["source"], "heuristic")
        self.assertEqual(out["agent_text"], "")


if __name__ == "__main__":
    unittest.main()
