"""F30 automation rules: JSON conditions, dry run first, local-only idempotent actions."""
from __future__ import annotations

import json
import unittest

import _tpi_followup_util as fu
import _tpi_server as srv
import yhbmail

DRAFT_RULE = {
    "id": "scope-ack", "name": "Ack the scope question", "match": "all",
    "conditions": [{"field": "from", "op": "contains", "value": "northwind"},
                   {"field": "subject", "op": "contains", "value": "friday scope"}],
    "actions": [{"type": "draft_reply", "template": "Hi {first_name},\n\nGot it, re “{subject}”. Back to you by {tbd}.\n\nBest,"}],
}


def run(body: dict) -> dict:
    status, out = srv.post("/api/rules/run", {"now": fu.NOW, **body})
    assert status == 200, out
    return out


def marks(*ids) -> dict:
    return srv.post("/api/rules/marks", {"ids": [fu.demo_id(i) for i in ids]})[1]["marks"]


def draft_count() -> int:
    return len(srv.get("/api/drafts")[1]["drafts"])


class RulesTest(unittest.TestCase):
    def setUp(self):
        self.base = fu.Baseline()

    def tearDown(self):
        self.base.restore()

    def test_demo_rules_and_schema(self):
        status, d = srv.get("/api/rules?lang=zh-Hant")
        self.assertEqual(status, 200)
        self.assertEqual((d["source"], d["errors"]), ("demo", []))
        self.assertEqual([r["id"] for r in d["rules"]],
                         ["receipts", "changelogs", "promotions", "system-asks", "holding-reply"])
        fields = {f["id"] for f in d["schema"]["fields"]}
        self.assertTrue({"from", "subject", "label", "unread", "replied", "age_days", "lane"} <= fields)
        self.assertEqual({a["id"] for a in d["schema"]["actions"]},
                         {"label", "archive", "mark_read", "draft_reply", "task"})
        self.assertIn("加標籤", [a["label"] for a in d["schema"]["actions"]])

    def test_validation_errors(self):
        bad = {"rules": [
            {"id": "Bad Id", "conditions": [{"field": "from", "op": "contains", "value": "x"}], "actions": [{"type": "archive"}]},
            {"id": "a", "conditions": [{"field": "nope", "op": "contains", "value": "x"}], "actions": [{"type": "archive"}]},
            {"id": "a", "conditions": [{"field": "unread", "op": "contains", "value": "x"}], "actions": [{"type": "archive"}]},
            {"id": "b", "conditions": [{"field": "subject", "op": "regex", "value": "("}], "actions": [{"type": "explode"}]},
            {"id": "c", "conditions": [], "actions": []},
            {"id": "d", "conditions": [{"field": "age_days", "op": "gte", "value": "3"}],
             "actions": [{"type": "label", "label": ""}]},
        ]}
        status, out = srv.post("/api/rules/validate", {"doc": bad})
        self.assertEqual(status, 200)
        self.assertFalse(out["ok"])
        text = " ".join(e["message"] for e in out["errors"])
        for needle in ("id:", "unknown field", "op must be", "bad regex", "unknown action", "duplicate id",
                       "non-empty list", "must be a number", "label: 1 to 40"):
            self.assertIn(needle, text)
        status, out = srv.post("/api/rules", {"doc": bad})
        self.assertEqual(status, 400)
        self.assertFalse((srv.ROOT / "rules.json").exists())
        zh = srv.post("/api/rules/validate", {"doc": {"rules": "x"}, "lang": "zh-Hant"})[1]
        self.assertIn("最外層", zh["errors"][0]["message"])

    def test_dry_run_changes_nothing(self):
        drafts = draft_count()
        before = {e["id"]: e["unread"] for e in srv.get("/api/inbox?limit=200")[1]["emails"]}
        out = run({})
        self.assertTrue(out["dry_run"])
        self.assertIsNone(out["run_id"])
        self.assertGreater(out["counts"]["planned"], 0)
        self.assertEqual(out["counts"]["applied"], 0)
        self.assertIn("nothing was changed", out["note"])
        self.assertEqual(out["per_rule"]["promotions"], 1)
        self.assertEqual(out["per_rule"]["changelogs"], 1)
        self.assertEqual(marks("m5", "m6"), {fu.demo_id("m5"): {"labels": [], "archived": False},
                                             fu.demo_id("m6"): {"labels": [], "archived": False}})
        after = {e["id"]: e["unread"] for e in srv.get("/api/inbox?limit=200")[1]["emails"]}
        self.assertEqual(before, after)
        self.assertEqual(draft_count(), drafts)
        self.assertEqual(srv.get("/api/rules/runs")[1]["runs"], [])
        self.assertEqual(srv.get("/api/triage/tasks")[1]["tasks"], [])

    def test_apply_is_local_and_idempotent(self):
        out = run({"dry_run": False})
        self.assertFalse(out["dry_run"])
        self.assertTrue(out["ok"], out)
        self.assertGreater(out["counts"]["applied"], 0)
        m = marks("m5", "m6", "m3")
        self.assertEqual(m[fu.demo_id("m6")], {"labels": ["Promotions"], "archived": True})
        self.assertEqual(m[fu.demo_id("m5")], {"labels": ["Changelog"], "archived": True})
        self.assertEqual(m[fu.demo_id("m3")]["labels"], ["Receipts"])
        tasks = srv.get("/api/triage/tasks")[1]["tasks"]
        self.assertEqual([(t["email_id"], t["action"]) for t in tasks], [(fu.demo_id("m2"), "review")])
        self.assertEqual(yhbmail.counts()["emails"], srv.N_EMAILS, "archive never deletes mail")
        again = run({"dry_run": False})
        self.assertEqual(again["counts"]["applied"], 0)
        self.assertGreater(again["counts"]["already"], 0)
        self.assertEqual(len(srv.get("/api/triage/tasks")[1]["tasks"]), 1)
        runs = srv.get("/api/rules/runs")[1]["runs"]
        self.assertEqual(len(runs), 2)
        self.assertEqual(runs[1]["applied"], out["counts"]["applied"])
        status, _ = srv.post("/api/rules/marks/remove", {"email_id": fu.demo_id("m6"), "kind": "archived"})
        self.assertEqual(status, 200)
        self.assertFalse(marks("m6")[fu.demo_id("m6")]["archived"])
        run({"dry_run": False})
        self.assertFalse(marks("m6")[fu.demo_id("m6")]["archived"], "an undone action is not re-applied")

    def test_draft_reply_preview_then_local_draft(self):
        preview = run({"doc": {"rules": [DRAFT_RULE]}})
        hit = preview["matched"]
        self.assertEqual([m["email_id"] for m in hit], [fu.demo_id("m1")])
        action = hit[0]["actions"][0]
        self.assertEqual(action["status"], "planned")
        self.assertIn("Hi Samira,", action["detail"]["preview"])
        self.assertIn("[TBD]", action["detail"]["preview"])
        self.assertEqual(srv.post("/api/rules/run", {"doc": {"rules": [DRAFT_RULE]}, "dry_run": False})[0], 400)
        status, saved = srv.post("/api/rules", {"doc": {"rules": [DRAFT_RULE]}})
        self.assertEqual((status, saved["source"]), (200, "file"))
        on_disk = json.loads((srv.ROOT / "rules.json").read_text())
        self.assertEqual(on_disk["rules"][0]["id"], "scope-ack")
        out = run({"dry_run": False})
        action = out["matched"][0]["actions"][0]
        self.assertEqual(action["status"], "applied", action)
        draft = srv.get(f"/api/compose/draft/{action['detail']['draft_id']}")[1]
        self.assertEqual(draft["source_id"], fu.demo_id("m1"))
        self.assertTrue(draft["subject"].startswith("Re: "))
        self.assertIn("Hi Samira,", draft["body"])
        self.assertIn("wrote:", draft["body"], "the original is quoted")
        n = draft_count()
        self.assertEqual(run({"dry_run": False})["counts"]["applied"], 0)
        self.assertEqual(draft_count(), n)

    def test_reply_draft_not_made_for_noreply_or_existing_draft(self):
        rule = {"id": "all-needs", "conditions": [{"field": "lane", "op": "equals", "value": "needs_you"}],
                "actions": [{"type": "draft_reply", "template": "Hi {first_name}"}]}
        out = run({"doc": {"rules": [rule]}})
        status = {m["email_id"]: m["actions"][0]["status"] for m in out["matched"]}
        self.assertEqual(status[fu.demo_id("m2")], "skipped")
        self.assertEqual(status[fu.demo_id("m1")], "planned")
        srv.post("/api/compose/draft", {"kind": "reply", "source_id": fu.demo_id("m1"), "text": "mine"})
        out = run({"doc": {"rules": [rule]}})
        self.assertEqual({m["email_id"]: m["actions"][0]["status"] for m in out["matched"]}[fu.demo_id("m1")], "already")

    def test_fields_and_ops(self):
        def ids(conds, match="all"):
            rule = {"id": "t", "match": match, "conditions": conds, "actions": [{"type": "archive"}]}
            return sorted(m["email_id"][-2:] for m in run({"doc": {"rules": [rule]}})["matched"])
        self.assertEqual(ids([{"field": "replied", "op": "is", "value": True}]), ["m1", "m4", "m7"])
        self.assertEqual(ids([{"field": "unread", "op": "is", "value": False}]), ["m3", "m5", "m7"])
        self.assertEqual(ids([{"field": "label", "op": "contains", "value": "category_promotions"}]), ["m6"])
        self.assertEqual(ids([{"field": "age_days", "op": "gte", "value": 4.5}]), ["m7", "m8"])
        self.assertEqual(ids([{"field": "from", "op": "regex", "value": r"@(cloud|bytecloud)\.example"}]), ["m2", "m8"])
        self.assertEqual(ids([{"field": "subject", "op": "starts_with", "value": "invitation"},
                              {"field": "subject", "op": "contains", "value": "receipt"}], "any"), ["m3", "m4"])
        self.assertEqual(ids([{"field": "category", "op": "in", "value": ["other"]}]), ["m5", "m6"])
        self.assertEqual(len(ids([{"field": "text", "op": "not_contains", "value": "zzzz"}])), srv.N_EMAILS)

    def test_mark_read_and_stop(self):
        rule = {"id": "read-promos", "conditions": [{"field": "label", "op": "contains", "value": "CATEGORY_PROMOTIONS"}],
                "actions": [{"type": "mark_read"}], "stop": True}
        later = {"id": "later", "conditions": [{"field": "from", "op": "contains", "value": "promo"}],
                 "actions": [{"type": "label", "label": "Never"}]}
        srv.post("/api/rules", {"doc": {"rules": [rule, later]}})
        out = run({"dry_run": False})
        self.assertEqual([m["rule_id"] for m in out["matched"]], ["read-promos"])
        self.assertFalse(srv.get(f"/api/thread/{fu.demo_id('m6')}")[1]["unread"])

    def test_cross_origin_cannot_change_anything(self):
        evil = "https://evil.example.com"
        self.assertEqual(fu.post_from("/api/rules/run", {"dry_run": False}, evil)[0], 403)
        self.assertEqual(fu.post_from("/api/rules", {"doc": {"rules": [DRAFT_RULE]}}, evil)[0], 403)
        self.assertEqual(fu.post_from("/api/rules/marks/remove", {"email_id": "x", "kind": "archived"}, evil)[0], 403)
        self.assertFalse((srv.ROOT / "rules.json").exists())
        status, out = fu.post_from("/api/rules/run", {"dry_run": True}, evil)
        self.assertEqual((status, out["dry_run"]), (200, True))
        status, out = fu.post_from("/api/rules/run", {"dry_run": False, "now": fu.NOW}, fu.local_origin())
        self.assertEqual((status, out["dry_run"]), (200, False))

    def test_bad_rules_file_is_reported(self):
        (srv.ROOT / "rules.json").write_text("{not json")
        d = srv.get("/api/rules")[1]
        self.assertEqual((d["source"], d["rules"]), ("file", []))
        self.assertIn("rules.json", d["errors"][0]["message"])
        self.assertEqual(run({})["counts"]["planned"], 0)


if __name__ == "__main__":
    unittest.main()
