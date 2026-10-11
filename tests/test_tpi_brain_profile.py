"""F13 Email Brain: every section of /api/brain/profile is inferred from the demo mail."""
from __future__ import annotations

import json
import unittest

import _tpi_server as srv
from _tpi_brain_util import BrainCase, by_key, profile, section

REPO = srv.REPO


class ProfileShapeTest(BrainCase):
    def test_five_sections_in_order_with_bilingual_names(self):
        en, zh = profile("en"), profile("zh-Hant")
        self.assertEqual([s["id"] for s in en["sections"]],
                         ["identity", "tone", "contacts", "projects", "work_patterns"])
        self.assertEqual([s["name"] for s in en["sections"]],
                         ["Identity & workplace", "Writing tone", "Contacts & relationships", "Active projects",
                          "Work patterns"])
        self.assertEqual([s["name"] for s in zh["sections"]],
                         ["身分與職場", "寫作語氣", "常聯絡人與關係", "進行中專案", "工作模式"])
        self.assertEqual(en["fixes"], 0)
        self.assertEqual(en["sources"]["received"], srv.N_EMAILS)
        self.assertEqual(en["sources"]["sent"], len(json.loads((REPO / "fixtures" / "demo_sent.json").read_text())["sent"]))
        self.assertTrue(en["sources"]["demo_sent"])

    def test_single_section_filter_and_bad_section(self):
        status, data = srv.get("/api/brain/profile?section=projects")
        self.assertEqual(status, 200)
        self.assertEqual([s["id"] for s in data["sections"]], ["projects"])
        status, data = srv.get("/api/brain/profile?section=nope")
        self.assertEqual(status, 400)

    def test_every_item_is_fixable_and_explained(self):
        p = profile()
        for s in p["sections"]:
            for it in s["items"]:
                self.assertEqual(it["section"], s["id"])
                self.assertTrue(it["key"])
                self.assertIn(it["source"], ("mail", "seed", "config", "default", "fix"))
                self.assertFalse(it["fixed"])


class IdentityTest(BrainCase):
    def test_identity_and_workplace_from_signature(self):
        ident = by_key(profile(), "identity")
        self.assertEqual(ident["name"]["value"], "Alex Chen")
        self.assertEqual(ident["name"]["source"], "mail")
        self.assertEqual((ident["role"]["value"], ident["role"]["source"]), ("Founder", "mail"))
        self.assertEqual((ident["organization"]["value"], ident["organization"]["source"]), ("Quillmark Labs", "mail"))
        self.assertEqual(ident["signature"]["value"], "Alex Chen\nFounder, Quillmark Labs")
        self.assertEqual((ident["timezone"]["value"], ident["timezone"]["source"]), ("Asia/Taipei", "seed"))
        sent_subjects = {s["subject"].removeprefix("Re: ")
                         for s in json.loads((REPO / "fixtures" / "demo_sent.json").read_text())["sent"]}
        self.assertTrue(ident["role"]["evidence"])
        self.assertTrue(set(ident["role"]["evidence"]) <= sent_subjects)
        self.assertIn("3 signatures", ident["role"]["basis"])


class ToneTest(BrainCase):
    def test_writing_tone_from_sent_mail(self):
        tone = by_key(profile(), "tone")
        self.assertEqual(tone["formality"]["value"], "balanced")
        self.assertEqual(tone["length"]["value"], "short")
        self.assertEqual(tone["greeting"]["value"], "Hi")
        self.assertEqual(tone["signoff"]["value"], "Best,")
        self.assertEqual(tone["languages"]["value"], "en, zh")
        self.assertEqual(tone["languages"]["display"], "English 89% · Chinese 11%")
        self.assertEqual(tone["exclamations"]["value"], "sometimes")
        self.assertIn("Short paragraphs. Decision first, context second.", tone["rules"]["value"])
        self.assertEqual(tone["formality"]["kind"], "enum")
        self.assertEqual([o["id"] for o in tone["formality"]["options"]], ["formal", "balanced", "casual"])

    def test_tone_labels_in_chinese(self):
        tone = by_key(profile("zh-Hant"), "tone")
        self.assertEqual(tone["formality"]["display"], "平衡")
        self.assertEqual(tone["length"]["display"], "簡短")
        self.assertEqual(tone["languages"]["display"], "英文 89% · 中文 11%")
        self.assertEqual(tone["signoff"]["label"], "結尾")


class ContactsTest(BrainCase):
    def test_frequent_contacts_and_relationships(self):
        contacts = section(profile(), "contacts")
        rel = {c["email"]: c["relationship"] for c in contacts}
        self.assertEqual(rel, {"jordan@quillmark.example": "teammate", "samira@northwind.example": "investor",
                               "maya@studio.example": "collaborator", "priya@talentloop.example": "recruiter"})
        samira = next(c for c in contacts if c["email"] == "samira@northwind.example")
        self.assertEqual((samira["name"], samira["sent"], samira["received"], samira["direction"]),
                         ("Samira Ortiz", 2, 2, "two_way"))
        self.assertIn("Northwind term sheet comments", samira["evidence"])
        jordan = next(c for c in contacts if c["email"] == "jordan@quillmark.example")
        self.assertEqual(jordan["direction"], "outbound")
        self.assertEqual(jordan["basis"], "Same domain / company as you.")

    def test_bulk_senders_and_self_are_not_contacts(self):
        emails = {c["email"] for c in section(profile(), "contacts")}
        for addr in ("noreply@cloud.example", "noreply@bytecloud.example", "team@promo.example",
                     "changelog@updates.example", "you@example.com"):
            self.assertNotIn(addr, emails)

    def test_relationship_labels_in_chinese(self):
        rel = {c["email"]: c["relationship_label"] for c in section(profile("zh-Hant"), "contacts")}
        self.assertEqual(rel["samira@northwind.example"], "投資人")
        self.assertEqual(rel["jordan@quillmark.example"], "同事")


class ProjectsTest(BrainCase):
    def test_active_projects_from_recurring_topics(self):
        projects = {p["name"]: p for p in section(profile(), "projects")}
        self.assertEqual(set(projects), {"Northwind", "Design review", "Byte Cloud", "Contract designer"})
        nw = projects["Northwind"]
        self.assertEqual(nw["status"], "active")
        self.assertEqual(nw["thread_count"], 3)
        self.assertIn("investor call", nw["keywords"])
        self.assertIn("Samira Ortiz", nw["people"])
        self.assertEqual([e["title"] for e in nw["events"]], ["Northwind investor call"])
        inbox_threads = [t for t in nw["threads"] if t["in_inbox"]]
        self.assertTrue(inbox_threads and all(srv.yhbmail.get_email(t["id"]) for t in inbox_threads))
        self.assertEqual([e["title"] for e in projects["Byte Cloud"]["events"]], ["Vendor renewal (Byte Cloud)"])
        self.assertEqual(projects["Contract designer"]["people"], ["Priya Nair"])

    def test_names_and_bulk_mail_do_not_become_projects(self):
        names = {p["name"].lower() for p in section(profile(), "projects")}
        for word in ("samira", "alex", "quillmark", "hiring", "friday", "gemini", "unsubscribe"):
            self.assertFalse(any(word in n for n in names), word)


class WorkPatternsTest(BrainCase):
    def test_active_hours_days_and_reply_speed(self):
        work = by_key(profile(), "work_patterns")
        self.assertEqual(work["active_hours"]["value"], {"start": 9 * 60, "end": 18 * 60})
        self.assertEqual(work["active_hours"]["display"], "09:00–18:00")
        self.assertIn("1 after 22:00", work["active_hours"]["basis"])
        self.assertEqual(work["work_days"]["value"], ["mon", "tue", "wed", "thu", "fri"])
        self.assertEqual(work["work_days"]["display"], "Mon–Fri")
        self.assertEqual(work["peak_hours"]["value"], "10:00, 17:00")
        self.assertEqual(work["reply_speed"]["value"], "within_hours")
        self.assertIn("1 h 12 min", work["reply_speed"]["basis"])

    def test_work_patterns_in_chinese(self):
        work = by_key(profile("zh-Hant"), "work_patterns")
        self.assertEqual(work["work_days"]["display"], "週一–週五")
        self.assertEqual(work["reply_speed"]["display"], "幾小時內")
        self.assertIn("1 小時 12 分", work["reply_speed"]["basis"])


class LiveModeTest(BrainCase):
    def test_live_mode_reads_sent_mail_from_your_own_account_only(self):
        acc = srv.ROOT / "accounts.json"
        acc.write_text(json.dumps({"mode": "live", "accounts": [
            {"email": "you@example.com", "driver": "imap", "label": "Work"}]}))
        self.addCleanup(lambda: acc.unlink(missing_ok=True))
        p = profile()
        self.assertEqual(p["sources"]["sent"], 0)
        self.assertFalse(p["sources"]["demo_sent"])
        ident = by_key(p, "identity")
        self.assertEqual(ident["role"]["source"], "default")
        self.addCleanup(self._drop_live_row)
        con = srv.yhbmail.db()
        srv.yhbmail.upsert_email(con, {
            "id": "live:you@example.com:x1", "account": "you@example.com", "thread_id": "m7",
            "subject": "Re: Northwind term sheet comments", "from_addr": "Alex Chen <you@example.com>",
            "to_addr": "samira@northwind.example", "date_raw": "2026-09-14 18:10",
            "body_text": "Hi Samira,\n\nAgreed.\n\nBest,\nAlex\n--\nAlex Chen\nCEO, Quillmark Labs"})
        con.commit()
        con.close()
        p = profile()
        self.assertEqual(p["sources"]["sent"], 1)
        ident = by_key(p, "identity")
        self.assertEqual((ident["role"]["value"], ident["organization"]["value"]), ("CEO", "Quillmark Labs"))
        self.assertEqual(by_key(p, "work_patterns")["reply_speed"]["value"], "within_hours")

    @staticmethod
    def _drop_live_row():
        con = srv.yhbmail.db()
        con.execute("DELETE FROM emails WHERE id LIKE 'live:%'")
        con.commit()
        con.close()


if __name__ == "__main__":
    unittest.main()
