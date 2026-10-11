"""F14 Email Brain Fix: a correction is saved, overrides the inference and updates the persona at once."""
from __future__ import annotations

import json
import unittest

import _tpi_server as srv
from _tpi_brain_util import PERSONA, PERSONA_MD, BrainCase, by_key, profile, section


def persona() -> dict:
    return json.loads(PERSONA.read_text())


class ScalarFixTest(BrainCase):
    def test_identity_fix_overrides_inference_and_persona(self):
        r = self.fix({"section": "identity", "key": "role", "value": "Managing partner", "note": "New title"})
        self.assertTrue(r["ok"])
        it = r["item"]
        self.assertEqual((it["value"], it["source"], it["fixed"], it["note"]), ("Managing partner", "fix", True, "New title"))
        self.assertEqual(it["inferred_display"], "Founder")
        self.assertEqual(by_key(r["profile"], "identity")["role"]["value"], "Managing partner")
        self.assertEqual(r["persona"]["identity"]["role"], "Managing partner")
        self.assertIn("role", r["persona"]["identity"]["fixed"])
        p = persona()
        self.assertEqual(p["identity"]["role"], "Managing partner")
        self.assertEqual(p["email_brain"]["identity"]["role"], "Managing partner")
        self.assertIn("identity.role", p["email_brain"]["fixed"])
        md = PERSONA_MD.read_text()
        self.assertIn("## Email Brain / 信件大腦", md)
        self.assertIn("Alex Chen · Managing partner · Quillmark Labs", md)
        self.assertIn("role: Managing partner (corrected by the user)", r["prompt"])
        _, ov = srv.get("/api/persona")
        self.assertEqual(ov["identity"]["role"], "Managing partner")

    def test_enum_hours_and_days_fixes(self):
        r = self.fix({"section": "tone", "key": "formality", "value": "formal"})
        self.assertEqual((r["item"]["value"], r["item"]["display"]), ("formal", "Formal"))
        r = self.fix({"section": "work_patterns", "key": "active_hours", "value": "8:30 - 17:00"})
        self.assertEqual(r["item"]["value"], {"start": 510, "end": 1020})
        self.assertEqual(r["item"]["display"], "08:30–17:00")
        r = self.fix({"section": "work_patterns", "key": "work_days", "value": "週一到週四", "lang": "zh-Hant"})
        self.assertEqual(r["item"]["value"], ["mon", "tue", "wed", "thu"])
        self.assertEqual(r["item"]["display"], "週一–週四")
        r = self.fix({"section": "work_patterns", "key": "work_days", "value": ["sat", "mon"]})
        self.assertEqual(r["item"]["display"], "Mon, Sat")
        self.assertEqual(persona()["email_brain"]["work_patterns"]["active_hours"], "08:30–17:00")
        self.assertEqual(profile()["fixes"], 3)

    def test_validation(self):
        bad = [
            {"section": "nope", "key": "x", "value": "y"},
            {"section": "identity", "key": "shoe_size", "value": "42"},
            {"section": "identity", "key": "role"},
            {"section": "identity", "key": "role", "value": "   "},
            {"section": "tone", "key": "formality", "value": "shouty"},
            {"section": "work_patterns", "key": "active_hours", "value": "late"},
            {"section": "work_patterns", "key": "active_hours", "value": "25:00-26:00"},
            {"section": "work_patterns", "key": "work_days", "value": "someday"},
            {"section": "contacts", "key": "not-an-address", "relationship": "client"},
            {"section": "contacts", "key": "samira@northwind.example"},
            {"section": "projects", "key": "", "note": "no name"},
            {"section": "projects", "key": "northwind", "status": "exploded"},
            {"section": "projects", "key": "BAD KEY!", "name": "x"},
        ]
        for body in bad:
            self.fix(body, 400)
        _, zh = srv.post("/api/brain/fix", {"section": "tone", "key": "formality", "value": "x", "lang": "zh-Hant"})
        self.assertIn("必須是", zh["error"])
        self.assertEqual(profile()["fixes"], 0)

    def test_reset_one_and_all(self):
        self.fix({"section": "identity", "key": "role", "value": "CTO"})
        self.fix({"section": "tone", "key": "signoff", "value": "Cheers,"})
        status, r = srv.post("/api/brain/fix/reset", {"section": "identity", "key": "role"})
        self.assertEqual((status, r["deleted"]), (200, 1))
        self.assertEqual(by_key(r["profile"], "identity")["role"]["value"], "Founder")
        self.assertEqual(persona()["identity"]["role"], "Founder")
        self.assertEqual(r["profile"]["fixes"], 1)
        status, r = srv.post("/api/brain/fix/reset", {"all": True})
        self.assertEqual((status, r["deleted"]), (200, 1))
        self.assertEqual(by_key(r["profile"], "tone")["signoff"]["value"], "Best,")
        self.assertEqual(srv.post("/api/brain/fix/reset", {"section": "tone"})[0], 400)

    def test_fixes_list(self):
        self.fix({"section": "identity", "key": "organization", "value": "Quillmark Holdings"})
        _, data = srv.get("/api/brain/fixes")
        self.assertEqual(data["fixes"], [{"section": "identity", "key": "organization",
                                          "updated_at": data["fixes"][0]["updated_at"],
                                          "value": {"value": "Quillmark Holdings", "note": ""}}])


class ContactFixTest(BrainCase):
    def test_relationship_fix_and_partial_merge(self):
        r = self.fix({"section": "contacts", "key": "Samira@Northwind.example", "relationship": "client",
                      "note": "Runs procurement"})
        c = r["item"]
        self.assertEqual((c["key"], c["relationship"], c["relationship_label"], c["inferred_relationship"]),
                         ("samira@northwind.example", "client", "Client", "investor"))
        r = self.fix({"section": "contacts", "key": "samira@northwind.example", "name": "Samira O."})
        c = r["item"]
        self.assertEqual((c["name"], c["relationship"], c["note"]), ("Samira O.", "client", "Runs procurement"))
        self.assertIn({"name": "Samira O.", "email": "samira@northwind.example", "relationship": "client",
                       "note": "Runs procurement"}, persona()["email_brain"]["contacts"])
        self.assertIn("Samira O. (client)", PERSONA_MD.read_text())

    def test_custom_relationship_hide_unhide_and_add(self):
        r = self.fix({"section": "contacts", "key": "maya@studio.example", "relationship": "Agency lead"})
        self.assertEqual(r["item"]["relationship_label"], "Agency lead")
        r = self.fix({"section": "contacts", "key": "priya@talentloop.example", "hidden": True})
        self.assertTrue(r["item"]["hidden"])
        self.assertNotIn("priya@talentloop.example", [c["email"] for c in persona()["email_brain"]["contacts"]])
        r = self.fix({"section": "contacts", "key": "priya@talentloop.example", "hidden": False})
        self.assertFalse(r["item"]["fixed"], "un-hiding the only fix drops it")
        self.assertEqual(len(srv.get("/api/brain/fixes")[1]["fixes"]), 1)
        r = self.fix({"section": "contacts", "key": "lee@counsel.example", "name": "Lee Park", "relationship": "other",
                      "note": "Outside counsel"})
        added = r["item"]
        self.assertEqual((added["manual"], added["name"], added["note"]), (True, "Lee Park", "Outside counsel"))
        self.assertIn("lee@counsel.example", [c["email"] for c in section(profile(), "contacts")])


class ProjectFixTest(BrainCase):
    def test_rename_status_hide_and_manual_project(self):
        r = self.fix({"section": "projects", "key": "northwind", "name": "Seed round", "status": "active",
                      "note": "Close by end of month"})
        p = r["item"]
        self.assertEqual((p["name"], p["inferred_name"], p["note"]), ("Seed round", "Northwind", "Close by end of month"))
        self.assertTrue(p["threads"], "a renamed project keeps its threads")
        r = self.fix({"section": "projects", "key": "byte-cloud", "status": "done"})
        self.assertEqual((r["item"]["status"], r["item"]["status_label"]), ("done", "Done"))
        self.assertNotIn("Byte Cloud", r["prompt"].split("Active projects:")[1].splitlines()[0])
        r = self.fix({"section": "projects", "key": "contract-designer", "hidden": True})
        self.assertNotIn("Contract designer", [x["name"] for x in persona()["email_brain"]["projects"]])
        r = self.fix({"section": "projects", "name": "Office move", "note": "Lease signed"})
        self.assertEqual((r["key"], r["item"]["manual"], r["item"]["status"]), ("manual-office-move", True, "active"))
        names = [x["name"] for x in persona()["email_brain"]["projects"]]
        self.assertEqual(names, ["Seed round", "Design review", "Byte Cloud", "Office move"])
        self.assertIn("Seed round (active)", PERSONA_MD.read_text())
        zh = profile("zh-Hant")
        self.assertEqual({p["key"]: p["status_label"] for p in section(zh, "projects")}["byte-cloud"], "已完成")


class DurabilityTest(BrainCase):
    def test_fixes_survive_persona_rebuild_sync_and_cache_clear(self):
        self.fix({"section": "identity", "key": "name", "value": "Alexandra Chen"})
        self.fix({"section": "contacts", "key": "maya@studio.example", "relationship": "client"})
        srv.persona.rebuild()
        self.assertEqual(persona()["identity"]["name"], "Alexandra Chen")
        status, out = srv.post("/api/cache/clear", {"reseed": True})
        self.assertEqual(status, 200, out)
        self.assertEqual(persona()["identity"]["name"], "Alexandra Chen")
        self.assertEqual(by_key(profile(), "contacts")["maya@studio.example"]["relationship"], "client")
        self.assertIn("## Email Brain / 信件大腦", PERSONA_MD.read_text())

    def test_voice_section_and_brain_section_coexist_in_persona_md(self):
        _, w = srv.post("/api/compose/write", {"kind": "reply", "item_id": "demo:you@example.com:m1"})
        srv.post("/api/compose/draft", {"kind": "reply", "source_id": "demo:you@example.com:m1",
                                        "text": "Hi Samira,\n\nConfirmed.\n\nThanks,\nAlex", "ai_body": w["text"]})
        self.addCleanup(self._forget_voice)
        self.fix({"section": "tone", "key": "rules", "value": "Never use exclamation marks"})
        md = PERSONA_MD.read_text()
        self.assertEqual(md.count("## Email Brain / 信件大腦"), 1)
        self.assertLess(md.index("## Email Brain"), md.index("## 學到的語氣 / Learned voice"))
        p = persona()
        self.assertEqual(p["voice"]["samples"], 1)
        self.assertEqual(p["email_brain"]["tone"]["rules"], "Never use exclamation marks")
        self.assertTrue(profile()["learned_voice"])

    @staticmethod
    def _forget_voice():
        srv.post("/api/compose/voice/forget", {"all": True})
        con = srv.yhbmail.db()
        con.execute("DELETE FROM drafts")
        con.commit()
        con.close()


if __name__ == "__main__":
    unittest.main()
