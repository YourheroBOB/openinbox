"""F10: Meeting Prep, Brief this person, Turn into a slide (HTML file), CRM this contact (contacts.json)."""
from __future__ import annotations

import json
import unittest

import _tpi_server as srv
import features.skills as skills

M1 = "demo:you@example.com:m1"
M7 = "demo:you@example.com:m7"


def reset() -> None:
    skills.settings_path().unlink(missing_ok=True)
    skills.contacts_path().unlink(missing_ok=True)
    (srv.ROOT / "agent.json").unlink(missing_ok=True)
    srv.reseed()


def run(skill: str, **args):
    return srv.post("/api/skills/run", {"skill": skill, **args})


class MeetingPrepTest(unittest.TestCase):
    def setUp(self):
        reset()

    def test_next_event_and_related_mail(self):
        status, out = run("meeting-prep", now="2026-09-18T12:00:00+08:00")
        self.assertEqual(status, 200, out)
        d = out["data"]
        self.assertEqual(d["picked"], "next")
        self.assertEqual(d["event"]["title"], "Design review with Maya")
        self.assertEqual([r["id"].rsplit(":", 1)[-1] for r in d["related"]], ["m4"])
        self.assertEqual(d["people"], [{"name": "Maya Singh", "email": "maya@studio.example", "emails": 1}])
        self.assertIn("- [ ] Re-read", out["markdown"])

    def test_chosen_event_open_questions(self):
        _, out = run("meeting-prep", event_id="cal:demo-cal-1")
        d = out["data"]
        self.assertEqual(d["picked"], "chosen")
        self.assertEqual(sorted(r["id"].rsplit(":", 1)[-1] for r in d["related"]), ["m1", "m7"])
        asks = [a["text"] for a in d["open_questions"]]
        self.assertIn("Can you mark which one you will concede?", asks)
        self.assertIn("by 17:00 Friday", [x["text"] for x in d["deadlines"]])
        self.assertEqual([a["email_id"] for a in d["attachments"]], [M7])

    def test_weak_matches_dropped(self):
        _, out = run("meeting-prep", event_id="demo-cal-3")
        self.assertEqual([r["id"].rsplit(":", 1)[-1] for r in out["data"]["related"]], ["m8"])

    def test_closest_when_nothing_upcoming(self):
        _, out = run("meeting-prep", now="2031-01-01T00:00:00+08:00")
        self.assertEqual(out["data"]["picked"], "closest")

    def test_unknown_event_and_chinese(self):
        status, out = run("meeting-prep", event_id="cal:nope")
        self.assertEqual(status, 404)
        _, zh = run("meeting-prep", event_id="cal:demo-cal-1", lang="zh-Hant")
        self.assertIn("# 會前準備：Northwind investor call", zh["markdown"])
        self.assertIn("## 準備清單", zh["markdown"])

    def test_keywords(self):
        kw = skills.keywords("Design review with Maya")
        self.assertEqual(kw, {"design": 2, "review": 1, "maya": 2})
        self.assertIn("北風", skills.keywords("北風投資人會議"))


class BriefPersonTest(unittest.TestCase):
    def setUp(self):
        reset()

    def test_by_name_address_or_email(self):
        for args in ({"person": "Samira"}, {"person": "samira@northwind.example"},
                     {"person": "Samira Ortiz <samira@northwind.example>"}, {"email_id": M1}):
            with self.subTest(args=args):
                status, out = run("brief-person", **args)
                self.assertEqual(status, 200, out)
                d = out["data"]
                self.assertEqual(d["email"], "samira@northwind.example")
                self.assertEqual(d["name"], "Samira Ortiz")
                self.assertEqual(d["org"], "northwind.example")
                self.assertEqual((d["total"], d["from_them"], d["unread"]), (2, 2, 1))
                self.assertEqual(d["first_seen"], "2026-09-14 16:40")
                self.assertEqual(d["last_seen"], "2026-09-16 09:12")
                self.assertIn("Can you mark which one you will concede?", [a["text"] for a in d["open_asks"]])

    def test_events_and_errors(self):
        _, out = run("brief-person", person="Maya")
        self.assertEqual([e["title"] for e in out["data"]["events"]], ["Design review with Maya"])
        status, out = run("brief-person", person="nobody-here")
        self.assertEqual(status, 404)
        status, out = run("brief-person")
        self.assertEqual(status, 400)
        _, zh = run("brief-person", person="Samira", lang="zh-Hant")
        self.assertIn("## 對方在等你的", zh["markdown"])


class SlideTest(unittest.TestCase):
    def setUp(self):
        reset()

    def test_email_to_html_file(self):
        status, out = run("slide", email_id=M1)
        self.assertEqual(status, 200, out)
        d = out["data"]
        self.assertEqual(d["source"], "email")
        self.assertTrue(d["file"].startswith("data/slides/") and d["file"].endswith(".html"))
        path = srv.ROOT / d["file"]
        self.assertTrue(path.is_file())
        doc = path.read_text()
        self.assertTrue(doc.startswith("<!doctype html>"))
        self.assertIn("Content-Security-Policy", doc)
        self.assertEqual(doc.count('<section class="slide">'), d["slides"])
        self.assertIn("Can you confirm the Friday scope before we send the deck?", doc)
        self.assertNotIn("http://", doc.replace('http-equiv', ''))
        status, headers, raw = srv.request("GET", d["url"])
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["Content-Type"])
        self.assertEqual(raw.decode(), doc)
        _, listing = srv.get("/api/skills/slides")
        self.assertIn(d["name"], [s["name"] for s in listing["slides"]])

    def test_markdown_is_escaped_and_split(self):
        md = "# Deck <script>alert(1)</script>\n\n## Points\n" + "\n".join(f"- point {i} **bold**" for i in range(11))
        _, out = run("slide", markdown=md, title="")
        doc = (srv.ROOT / out["data"]["file"]).read_text()
        self.assertNotIn("<script>alert", doc)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", doc)
        self.assertIn("<strong>bold</strong>", doc)
        self.assertIn("Points (1/2)", doc)
        self.assertIn("Points (2/2)", doc)
        self.assertTrue(out["data"]["name"].startswith("deck-script-alert-1-script-"))

    def test_from_skill_result(self):
        _, out = run("slide", from_skill="morning-brief", today="2026-09-17", lang="zh-Hant")
        self.assertEqual(out["data"]["source"], "skill:morning-brief")
        doc = (srv.ROOT / out["data"]["file"]).read_text()
        self.assertIn("需要你（2）", doc)
        self.assertIn('lang="zh-Hant"', doc)
        self.assertIn("下一張", doc)

    def test_errors_and_safe_serving(self):
        self.assertEqual(run("slide")[0], 400)
        self.assertEqual(run("slide", email_id="nope")[0], 404)
        self.assertEqual(run("slide", from_skill="crm-contact")[0], 400)
        for bad in ("/api/skills/slides/..%2Fskills.json", "/api/skills/slides/missing.html",
                    "/api/skills/slides/Upper.html"):
            self.assertEqual(srv.request("GET", bad)[0], 404, bad)


class CrmTest(unittest.TestCase):
    def setUp(self):
        reset()

    def test_add_then_refresh_contact(self):
        status, out = run("crm-contact", email_id=M1, tags="investor, seed", note="Met at demo day", stage="active")
        self.assertEqual(status, 200, out)
        self.assertTrue(out["data"]["created"])
        self.assertEqual(out["data"]["file"], "data/contacts.json")
        stored = json.loads(skills.contacts_path().read_text())
        self.assertEqual(len(stored["contacts"]), 1)
        c = stored["contacts"][0]
        self.assertEqual(c["email"], "samira@northwind.example")
        self.assertEqual(c["name"], "Samira Ortiz")
        self.assertEqual(c["org"], "northwind.example")
        self.assertEqual(c["emails_total"], 2)
        self.assertEqual(c["stage"], "active")
        self.assertEqual(c["tags"], ["investor", "seed"])
        self.assertEqual([n["text"] for n in c["notes"]], ["Met at demo day"])
        self.assertEqual(c["last_subject"], "Can you confirm the Friday scope before we send the deck?")

        _, again = run("crm-contact", person="Samira", tags="vip")
        self.assertFalse(again["data"]["created"])
        c = again["data"]["contact"]
        self.assertEqual(c["tags"], ["investor", "seed", "vip"])
        self.assertEqual(c["stage"], "active")
        self.assertEqual(len(skills.load_contacts()), 1)

    def test_contacts_api(self):
        run("crm-contact", person="maya@studio.example")
        _, listing = srv.get("/api/crm/contacts")
        self.assertEqual([c["email"] for c in listing["contacts"]], ["maya@studio.example"])
        self.assertEqual(listing["contacts"][0]["stage"], "lead")
        status, out = srv.post("/api/crm/contacts/update", {"email": "maya@studio.example", "stage": "partner",
                                                        "tags": "design", "note": "Contract designer"})
        self.assertEqual(status, 200, out)
        self.assertEqual((out["contact"]["stage"], out["contact"]["tags"]), ("partner", ["design"]))
        self.assertEqual(srv.get("/api/crm/contacts?q=contract")[1]["contacts"][0]["email"], "maya@studio.example")
        self.assertEqual(srv.get("/api/crm/contacts?q=zzz")[1]["contacts"], [])
        self.assertEqual(srv.post("/api/crm/contacts/update", {"email": "maya@studio.example", "stage": "boss"})[0], 400)
        self.assertEqual(srv.post("/api/crm/contacts/update", {"email": "x@nobody.example"})[0], 404)
        self.assertEqual(srv.post("/api/crm/contacts/delete", {"email": "maya@studio.example"})[0], 200)
        self.assertEqual(srv.post("/api/crm/contacts/delete", {"email": "maya@studio.example"})[0], 404)
        self.assertEqual(skills.load_contacts(), [])

    def test_crm_shows_up_in_brief(self):
        run("crm-contact", person="Samira", stage="customer", note="Prefers short replies")
        _, out = run("brief-person", person="Samira")
        self.assertEqual(out["data"]["crm"]["stage"], "customer")
        self.assertIn("Prefers short replies", out["markdown"])

    def test_errors_and_tag_hygiene(self):
        self.assertEqual(run("crm-contact", person="nobody@nowhere.example")[0], 404)
        self.assertEqual(run("crm-contact", person="Samira", stage="boss")[0], 400)
        _, out = run("crm-contact", person="Samira", tags=["ok", "<bad>", "ok", "x" * 40])
        self.assertEqual(out["data"]["contact"]["tags"], ["ok"])

    def test_survives_cache_clear(self):
        run("crm-contact", person="Samira")
        srv.post("/api/cache/clear", {"reseed": True})
        self.assertEqual(len(skills.load_contacts()), 1)


class SwitchOffTest(unittest.TestCase):
    def setUp(self):
        reset()
        self.addCleanup(reset)

    def test_each_f10_skill_refuses_when_off(self):
        args = {"meeting-prep": {}, "brief-person": {"person": "Samira"}, "slide": {"email_id": M1},
                "crm-contact": {"person": "Samira"}}
        count_slides = lambda: len(list(skills.slides_dir().glob("*.html"))) if skills.slides_dir().is_dir() else 0
        slides_before = count_slides()
        for slug, a in args.items():
            with self.subTest(slug=slug):
                srv.post("/api/skills/settings", {"slug": slug, "enabled": False})
                status, out = run(slug, **a)
                self.assertEqual(status, 403)
                self.assertEqual(out["error"], "skill_disabled")
        self.assertFalse(skills.contacts_path().exists())
        self.assertEqual(count_slides(), slides_before)


if __name__ == "__main__":
    unittest.main()
