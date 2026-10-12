"""F32: research and meeting-prep tasks run through the BYO agent bridge; deliverables are saved and read back."""
from __future__ import annotations

import json
import unittest
from unittest import mock

import _tpi_server as srv
from features import agents as A


class TaskRunTest(unittest.TestCase):
    def setUp(self):
        self.cfg = {"driver": "local"}

    def test_build_pack_uses_only_local_sources_and_persona(self):
        pack = A.build_pack("research_person", "Samira Ortiz", "", "en")
        self.assertEqual(pack["task"], "research_person")
        self.assertEqual(pack["target"], "Samira Ortiz")
        self.assertTrue(pack["sources"], "fixture mail for Samira should be found in the local cache")
        for s in pack["sources"]:
            self.assertTrue(s["id"].startswith("demo:"), "sources come from the local cache only")
        self.assertIn("identity", pack["persona"])
        self.assertTrue(any("Read only" in r for r in pack["rules"]))

    def test_build_pack_rejects_unknown_kind(self):
        with self.assertRaises(ValueError):
            A.build_pack("outbound_mail", "x")

    def test_local_brief_marks_missing_facts_instead_of_inventing(self):
        pack = A.build_pack("research_company", "Northwind", "", "en")
        text = A._local_brief(pack)
        self.assertIn("[missing]", text)
        self.assertIn("Company brief", text)
        zh = A._local_brief(A.build_pack("research_company", "Northwind", "", "zh-Hant"))
        self.assertIn("[待填]", zh)

    def test_meeting_prep_brief_has_its_own_sections(self):
        en = A._local_brief(A.build_pack("meeting_prep", "Investor call", "", "en"))
        self.assertIn("Meeting prep", en)
        self.assertIn("Decisions needed", en)

    def test_run_task_local_driver_is_marked_as_fallback_free(self):
        with mock.patch("agent_bridge.load_agent_cfg", return_value=self.cfg):
            res = A.run_task("research_person", "Samira Ortiz", "", "en")
        self.assertEqual(res["driver"], "local")
        self.assertTrue(res["fallback"])
        self.assertIsNone(res["error"])
        self.assertTrue(res["text"].strip())

    def test_external_driver_text_is_used_when_it_answers(self):
        cfg = {"driver": "cli", "cli": {"command": ["cat"]}}
        with mock.patch("agent_bridge.load_agent_cfg", return_value=cfg), \
                mock.patch("agent_bridge._cli", return_value="外部 agent 的回答"):
            res = A.run_task("research_company", "Northwind", "", "zh-Hant")
        self.assertEqual(res["driver"], "cli")
        self.assertFalse(res["fallback"])
        self.assertEqual(res["text"], "外部 agent 的回答")

    def test_external_driver_failure_falls_back_to_local_with_error(self):
        cfg = {"driver": "http", "http": {"url": "https://agent.example.com/x"}}
        with mock.patch("agent_bridge.load_agent_cfg", return_value=cfg), \
                mock.patch("agent_bridge._http", side_effect=RuntimeError("worker down")):
            res = A.run_task("meeting_prep", "Investor call", "", "en")
        self.assertEqual(res["driver"], "local")
        self.assertTrue(res["fallback"])
        self.assertIn("worker down", res["error"])
        self.assertIn("Meeting prep", res["text"])

    def test_empty_external_answer_falls_back(self):
        cfg = {"driver": "cli", "cli": {"command": ["cat"]}}
        with mock.patch("agent_bridge.load_agent_cfg", return_value=cfg), \
                mock.patch("agent_bridge._cli", return_value="   "):
            res = A.run_task("research_person", "Samira Ortiz", "", "en")
        self.assertTrue(res["fallback"])
        self.assertEqual(res["driver"], "local")


class DeliverableTest(unittest.TestCase):
    def _result(self, **kw):
        base = {"kind": "research_person", "target": "Samira Ortiz", "text": "# Hi\n\n- point one\n\nplain",
                "driver": "local", "fallback": True, "error": None, "sources": []}
        base.update(kw)
        return base

    def test_save_writes_md_html_and_json_under_deliverables(self):
        card = A.save_deliverable(self._result(), lang="en")
        did = card["id"]
        self.assertTrue(A.ID_RE.match(did))
        for ext in ("md", "html", "json"):
            self.assertTrue((A.DELIV_DIR / f"{did}.{ext}").is_file(), ext)
        self.assertEqual(card["kind"], "research_person")
        self.assertEqual(card["lang"], "en")

    def test_html_card_escapes_and_has_no_script(self):
        evil = "<script>alert(1)</script> <img src=x onerror=alert(2)>"
        card = A.save_deliverable(self._result(text=evil, target="<b>X</b>"), lang="en")
        html_text = (A.DELIV_DIR / f"{card['id']}.html").read_text()
        self.assertNotIn("<script>alert", html_text)
        self.assertNotIn("<img src=x", html_text)
        self.assertIn("&lt;script&gt;", html_text)
        self.assertNotIn("<script", html_text.lower())

    def test_html_card_renders_headings_and_list_items(self):
        card = A.save_deliverable(self._result(text="## 人物概況\n- 職務：[待填]\nplain line"), lang="zh-Hant")
        html_text = (A.DELIV_DIR / f"{card['id']}.html").read_text()
        self.assertIn('lang="zh-Hant"', html_text)
        self.assertIn("<h2>人物概況</h2>", html_text)
        self.assertIn("<li>職務：[待填]</li>", html_text)
        self.assertIn("<p>plain line</p>", html_text)

    def test_md_card_carries_metadata_and_fallback_flag(self):
        card = A.save_deliverable(self._result(), lang="en")
        md = (A.DELIV_DIR / f"{card['id']}.md").read_text()
        self.assertTrue(md.startswith("# Person research: Samira Ortiz"))
        self.assertIn("Fell back to local", md)

    def test_read_rejects_traversal_and_bad_format(self):
        self.assertIsNone(A.read_deliverable("../../etc/passwd", "md"))
        self.assertIsNone(A.read_deliverable("..%2F..", "md"))
        self.assertIsNone(A.read_deliverable("x", "exe"))
        self.assertIsNone(A.read_deliverable("research-person-missing-0000", "md"))

    def test_save_rejects_bad_generated_id(self):
        with mock.patch.object(A, "_slug", return_value="../../x"):
            card = A.save_deliverable(self._result(), lang="en")
        self.assertRegex(card["id"], A.ID_RE.pattern)
        self.assertNotIn("..", card["id"])

    def test_list_is_newest_first_and_skips_junk_files(self):
        A.DELIV_DIR.mkdir(parents=True, exist_ok=True)
        (A.DELIV_DIR / "not-valid!.json").write_text("{}")
        (A.DELIV_DIR / "broken-card-0001.json").write_text("{not json")
        ids = [c["id"] for c in A.list_deliverables()]
        self.assertFalse(any("not-valid" in i or "broken" in i for i in ids))


class CoreHttpTest(unittest.TestCase):
    def setUp(self):
        srv.reseed()

    def test_task_endpoint_returns_card_and_text(self):
        status, body = srv.call("POST", "/api/agents/task",
                                {"kind": "research_person", "target": "Samira Ortiz", "lang": "en"})
        self.assertEqual(status, 200)
        self.assertEqual(body["deliverable"]["kind"], "research_person")
        self.assertEqual(body["driver"], "local")
        self.assertTrue(body["fallback"])
        self.assertIn("Local sources", body["text"])
        self.assertTrue(body["sources"])

    def test_task_endpoint_meeting_prep_in_chinese(self):
        status, body = srv.call("POST", "/api/agents/task",
                                {"kind": "meeting_prep", "target": "Northwind 投資會議", "lang": "zh-Hant"})
        self.assertEqual(status, 200)
        self.assertIn("會議準備", body["text"])
        self.assertIn("[待填]", body["text"])

    def test_task_endpoint_validates_input(self):
        self.assertEqual(srv.call("POST", "/api/agents/task", {"kind": "outbound_mail", "target": "x"})[0], 400)
        self.assertEqual(srv.call("POST", "/api/agents/task", {"kind": "research_person"})[0], 400)

    def test_deliverable_preview_endpoints(self):
        status, body = srv.call("POST", "/api/agents/task",
                                {"kind": "research_company", "target": "Northwind", "lang": "en"})
        did = body["deliverable"]["id"]
        s_md, h_md, raw_md = srv.request("GET", f"/api/agents/deliverables/{did}.md")
        self.assertEqual(s_md, 200)
        self.assertIn("text/markdown", h_md["Content-Type"])
        self.assertIn(b"Company research", raw_md)
        s_html, h_html, raw_html = srv.request("GET", f"/api/agents/deliverables/{did}.html")
        self.assertEqual(s_html, 200)
        self.assertIn("text/html", h_html["Content-Type"])
        self.assertNotIn(b"<script", raw_html.lower())

    def test_deliverable_list_and_unknown_id(self):
        srv.call("POST", "/api/agents/task", {"kind": "research_person", "target": "Priya Nair", "lang": "en"})
        status, body = srv.call("GET", "/api/agents/deliverables")
        self.assertEqual(status, 200)
        self.assertTrue(body["deliverables"])
        self.assertEqual(body["alias"], A.ALIAS)
        self.assertEqual(srv.request("GET", "/api/agents/deliverables/nope-nope-0000.md")[0], 404)
        self.assertEqual(srv.request("GET", "/api/agents/deliverables/..%2Fsecret.md")[0], 404)

    def test_state_changing_post_refuses_cross_origin(self):
        import urllib.request
        req = urllib.request.Request(
            srv.BASE + "/api/agents/task",
            data=json.dumps({"kind": "research_person", "target": "x"}).encode(),
            headers={"Content-Type": "application/json", "Origin": "https://evil.example"},
            method="POST")
        import urllib.error
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req, timeout=10)
        self.assertEqual(cm.exception.code, 403)
        req2 = urllib.request.Request(
            srv.BASE + "/api/agents/mention",
            data=json.dumps({"text": "@agent x"}).encode(),
            headers={"Content-Type": "application/json", "Origin": "https://evil.example"},
            method="POST")
        with self.assertRaises(urllib.error.HTTPError) as cm2:
            urllib.request.urlopen(req2, timeout=10)
        self.assertEqual(cm2.exception.code, 403)


if __name__ == "__main__":
    unittest.main()
