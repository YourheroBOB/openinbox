"""F09: Morning Brief, Catch Me Up, Organize Inbox, Find It For Me run, and refuse to run when off."""
from __future__ import annotations

import unittest

import _tpi_server as srv
import features.skills as skills

F09 = ("morning-brief", "catch-me-up", "organize-inbox", "find-it")


def reset() -> None:
    skills.settings_path().unlink(missing_ok=True)
    (srv.ROOT / "agent.json").unlink(missing_ok=True)
    srv.reseed()


def run(skill: str, **args):
    return srv.post("/api/skills/run", {"skill": skill, **args})


class MorningBriefTest(unittest.TestCase):
    def setUp(self):
        reset()

    def test_needs_you_spelled_out(self):
        status, out = run("morning-brief", today="2026-09-17")
        self.assertEqual(status, 200, out)
        self.assertEqual(out["source"], "heuristic")
        self.assertEqual(out["source_label"], "Local rule-based result (no LLM)")
        d = out["data"]
        self.assertEqual(d["since"], "2026-09-16")
        self.assertEqual(d["new_count"], 3)
        self.assertEqual([i["id"].rsplit(":", 1)[-1] for i in d["needs_you"]], ["m1", "m2"])
        self.assertIn("## Needs you (2)", out["markdown"])
        self.assertIn("by 17:00 Friday", out["markdown"])
        self.assertIn("Next: Draft a reply", out["markdown"])

    def test_monday_looks_back_to_friday(self):
        _, out = run("morning-brief", today="2026-09-21")
        self.assertEqual(out["data"]["since"], "2026-09-18")

    def test_today_calendar(self):
        _, out = run("morning-brief", today="2026-09-18")
        self.assertEqual([e["title"] for e in out["data"]["events_today"]], ["Design review with Maya"])
        self.assertIn("16:00 Design review with Maya", out["markdown"])

    def test_chinese(self):
        _, out = run("morning-brief", today="2026-09-17", lang="zh-Hant")
        self.assertEqual(out["name"], "晨間簡報")
        self.assertIn("## 需要你（2）", out["markdown"])
        self.assertIn("下一步：起草回覆", out["markdown"])
        self.assertEqual(out["source_label"], "本機規則結果（未接 LLM）")


class CatchMeUpTest(unittest.TestCase):
    def setUp(self):
        reset()

    def test_groups_by_sender_reply_first(self):
        _, out = run("catch-me-up", hours=72, now="2026-09-16T12:00:00+08:00")
        d = out["data"]
        self.assertFalse(d["fallback"])
        self.assertEqual(d["emails"], 8)
        first = d["reply_needed"][0]
        self.assertEqual(first["email"], "samira@northwind.example")
        self.assertEqual(first["count"], 2)
        skim = {g["email"] for g in d["skimmable"]}
        self.assertIn("team@promo.example", skim)
        self.assertNotIn("samira@northwind.example", skim)
        self.assertLess(out["markdown"].index("## Reply needed"), out["markdown"].index("## Skimmable"))

    def test_window_and_fallback(self):
        _, out = run("catch-me-up", hours=12, now="2026-09-16T12:00:00+08:00")
        self.assertEqual(out["data"]["emails"], 3)
        _, out = run("catch-me-up", hours=1, now="2030-01-01T00:00:00+08:00")
        self.assertTrue(out["data"]["fallback"])
        self.assertIn("No mail in the last 1 hours", out["markdown"])
        _, zh = run("catch-me-up", hours=1, now="2030-01-01T00:00:00+08:00", lang="zh-Hant")
        self.assertIn("## 要回的", zh["markdown"])


class OrganizeInboxTest(unittest.TestCase):
    def setUp(self):
        reset()

    def test_folders_rules_noise(self):
        _, out = run("organize-inbox")
        d = out["data"]
        self.assertTrue(d["read_only"])
        folders = {f["folder"]: [i["id"].rsplit(":", 1)[-1] for i in f["items"]] for f in d["folders"]}
        self.assertEqual(folders["action"], ["m1", "m2"])
        self.assertEqual(folders["calendar"], ["m4"])
        self.assertEqual(sorted(folders["receipts"]), ["m3", "m8"])
        self.assertEqual(folders["promotions"], ["m6"])
        self.assertEqual(folders["newsletters"], ["m5"])
        self.assertEqual(sum(f["count"] for f in d["folders"]), srv.N_EMAILS)
        self.assertIn({"match": "from:@promo.example", "folder": "promotions", "folder_name": "Promotions"}, d["rules"])
        self.assertTrue(all(n["unsubscribe"] for n in d["noise"]))
        self.assertIn("nothing was moved", out["markdown"])

    def test_nothing_is_changed(self):
        before = srv.yhbmail.list_emails(limit=100)
        run("organize-inbox")
        self.assertEqual(before, srv.yhbmail.list_emails(limit=100))

    def test_chinese(self):
        _, out = run("organize-inbox", lang="zh-Hant")
        self.assertIn("待處理", out["markdown"])
        self.assertIn("沒有搬動或貼標任何信", out["markdown"])


class FindItTest(unittest.TestCase):
    def setUp(self):
        reset()

    def ids(self, out):
        return [m["id"].rsplit(":", 1)[-1] for m in out["data"]["mails"]]

    def test_keyword_across_mail_calendar_brain(self):
        _, out = run("find-it", query="northwind")
        self.assertEqual(self.ids(out), ["m7", "m1"])
        self.assertEqual([e["title"] for e in out["data"]["events"]], ["Northwind investor call"])
        self.assertTrue(out["data"]["cards"])

    def test_operators(self):
        _, out = run("find-it", query="has:attachment")
        self.assertEqual(sorted(self.ids(out)), ["m3", "m4", "m7"])
        _, out = run("find-it", query="from:samira is:unread")
        self.assertEqual(self.ids(out), ["m1"])
        _, out = run("find-it", query="after:2026-09-16")
        self.assertEqual(sorted(self.ids(out)), ["m1", "m2", "m3"])
        _, out = run("find-it", query="before:2026-09-15")
        self.assertEqual(sorted(self.ids(out)), ["m7", "m8"])
        _, out = run("find-it", query='"term sheet"')
        self.assertEqual(self.ids(out), ["m7"])

    def test_any_word_fallback_and_nothing(self):
        _, out = run("find-it", query="receipt zzzunknown")
        self.assertEqual(out["data"]["mode"], "any")
        self.assertIn("m3", self.ids(out))
        _, out = run("find-it", query="zzzunknown")
        self.assertEqual(out["data"]["total"], 0)
        self.assertIn("Nothing found", out["markdown"])

    def test_missing_query(self):
        status, out = run("find-it", query="  ")
        self.assertEqual(status, 400)
        self.assertEqual(out["error"], "missing query")
        status, out = run("find-it", lang="zh-Hant")
        self.assertEqual(out["message"], "請輸入要找的關鍵字。")


class SwitchOffTest(unittest.TestCase):
    def setUp(self):
        reset()
        self.addCleanup(reset)

    def test_each_f09_skill_refuses_when_off(self):
        for slug in F09:
            with self.subTest(slug=slug):
                status, _ = srv.post("/api/skills/settings", {"slug": slug, "enabled": False})
                self.assertEqual(status, 200)
                status, out = run(slug, query="northwind")
                self.assertEqual(status, 403)
                self.assertEqual(out["error"], "skill_disabled")
                self.assertEqual(out["skill"], slug)
                srv.post("/api/skills/settings", {"slug": slug, "enabled": True})
                status, _ = run(slug, query="northwind")
                self.assertEqual(status, 200)


if __name__ == "__main__":
    unittest.main()
