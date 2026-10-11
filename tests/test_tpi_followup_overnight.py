"""F31 overnight run: triage + rules (dry run) + follow-ups + local drafts + a morning brief."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import _tpi_followup_util as fu
import _tpi_server as srv
from features import overnight

SCRIPT = srv.REPO / "scripts" / "overnight.py"


def night(**body) -> dict:
    status, out = srv.post("/api/overnight/run", {"now": fu.NOW, **body})
    assert status == 200, out
    return out


class OvernightTest(unittest.TestCase):
    def setUp(self):
        self.base = fu.Baseline()

    def tearDown(self):
        self.base.restore()

    def test_english_brief(self):
        out = night(lang="en")
        self.assertTrue(out["ok"], out)
        md = out["markdown"]
        for heading in ("# Morning handoff · 2026-09-19", "## At a glance", "## Needs you",
                        "## Waiting on others (overdue)", "## Rules (dry run)", "## Today"):
            self.assertIn(heading, md)
        self.assertIn("nothing was sent", md)
        self.assertIn("Byte Cloud renewal on the 20th", md)
        self.assertIn("✓ answered", md)
        self.assertIn("Northwind investor call", md)
        s = out["summary"]
        self.assertEqual((s["sent"], s["rules_dry_run"], s["overdue"], s["needs_you"]), (0, True, 2, 2))
        path = srv.ROOT / out["brief_path"]
        self.assertTrue(path.is_file())
        self.assertEqual(path.read_text(), md)
        self.assertEqual((srv.ROOT / "data" / "briefs" / "latest.md").read_text(), md)
        data = json.loads(path.with_suffix(".json").read_text())
        self.assertEqual(data["summary"], s)
        latest = srv.get("/api/overnight/latest")[1]["run"]
        self.assertEqual((latest["id"], latest["markdown"]), (out["id"], md))
        self.assertEqual(srv.get(f"/api/overnight/run/{out['id']}")[1]["summary"], s)
        self.assertEqual(srv.get("/api/overnight/run/99999")[0], 404)

    def test_chinese_brief(self):
        md = night(lang="zh-Hant")["markdown"]
        for needle in ("# 早晨交接 · 2026-09-19", "## 一眼看完", "## 需要你", "## 等對方回覆（逾期）",
                       "## 自動化規則（dry-run）", "## 今天行程", "沒有寄出任何信", "✓ 已回覆"):
            self.assertIn(needle, md)

    def test_drafts_prepared_once(self):
        first = night(lang="en")
        made = first["summary"]["drafts_new"]
        self.assertEqual(made, 1, first["markdown"])
        self.assertIn("✎ nudge draft #", first["markdown"])
        drafts = srv.get("/api/drafts")[1]["drafts"]
        nudge = drafts[0]
        self.assertIn("Hi Jordan,", nudge["body"])
        second = night(lang="en")
        self.assertEqual(second["summary"]["drafts_new"], 0)
        self.assertEqual(second["summary"]["drafts_existing"], 1)
        self.assertEqual(len(srv.get("/api/drafts")[1]["drafts"]), len(drafts))
        off = night(lang="en", drafts=False)
        self.assertEqual(off["summary"]["drafts_new"] + off["summary"]["drafts_existing"], 0)

    def test_reply_draft_for_an_unanswered_ask(self):
        fu.add_email("test:night:ask", "Can you confirm the venue by Friday?", "Robin Park <robin@example.com>",
                     "2026-09-18 18:00", "Hi Alex,\n\nCan you confirm the venue by Friday? Please reply yes/no.\n\nRobin",
                     unread=True)
        out = night(lang="en")
        self.assertNotIn("data", out, "the API response stays small")
        self.assertEqual(out["summary"]["drafts_new"], 2, out["markdown"])
        self.assertRegex(out["markdown"], r"Can you confirm the venue by Friday\?\*\* — .*\(✎ draft #\d+\)")
        draft = next(d for d in srv.get("/api/compose/drafts")[1]["drafts"] if d["source_id"] == "test:night:ask")
        self.assertEqual(draft["kind"], "reply")
        self.assertEqual(draft["to"], "robin@example.com")
        self.assertEqual(night(lang="en")["summary"]["drafts_new"], 0)

    def test_rules_dry_run_unless_asked(self):
        night(lang="en")
        mark = srv.post("/api/rules/marks", {"ids": [fu.demo_id("m6")]})[1]["marks"][fu.demo_id("m6")]
        self.assertFalse(mark["archived"])
        out = night(lang="en", apply_rules=True)
        self.assertFalse(out["summary"]["rules_dry_run"])
        self.assertGreater(out["summary"]["rules_applied"], 0)
        self.assertIn("## Rules\n", out["markdown"])
        mark = srv.post("/api/rules/marks", {"ids": [fu.demo_id("m6")]})[1]["marks"][fu.demo_id("m6")]
        self.assertTrue(mark["archived"])

    def test_one_run_at_a_time_and_same_origin(self):
        self.assertTrue(overnight._lock.acquire(blocking=False))
        try:
            status, out = srv.post("/api/overnight/run", {"now": fu.NOW})
            self.assertEqual(status, 409, out)
        finally:
            overnight._lock.release()
        self.assertEqual(fu.post_from("/api/overnight/run", {}, "https://evil.example.com")[0], 403)
        self.assertEqual(srv.get("/api/overnight/runs")[1]["runs"], [])

    def test_script_on_a_fresh_root(self):
        root = Path(tempfile.mkdtemp(prefix="tpi-night-"))
        self.addCleanup(shutil.rmtree, root, True)
        for name in ("fixtures", "skills"):
            shutil.copytree(srv.REPO / name, root / name)
        for name in ("accounts.example.json", "agent.example.json"):
            shutil.copy(srv.REPO / name, root / name)
        env = {k: v for k, v in os.environ.items() if k != "OPENINBOX_ROOT"}
        cmd = [sys.executable, str(SCRIPT), "--root", str(root), "--no-sync", "--lang", "en", "--now", fu.NOW, "--json"]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertTrue(out["ok"])
        self.assertEqual((out["summary"]["sent"], out["summary"]["needs_you"], out["summary"]["drafts_new"]), (0, 2, 1))
        self.assertTrue((root / out["brief_path"]).is_file())
        self.assertTrue((root / "data" / "openinbox.db").is_file())
        r = subprocess.run([sys.executable, str(SCRIPT), "--root", str(root), "--lang", "zh-Hant", "--now", fu.NOW,
                            "--print"], capture_output=True, text=True, timeout=120, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("# 早晨交接", r.stdout)
        self.assertIn("已同步", r.stdout)
        self.assertIn("先前已有 1 份", r.stdout)
        self.assertFalse((srv.REPO / "data" / "briefs" / Path(out["brief_path"]).name).exists())

    def test_script_on_an_empty_root_uses_repo_fixtures(self):
        root = Path(tempfile.mkdtemp(prefix="tpi-night-empty-"))
        self.addCleanup(shutil.rmtree, root, True)
        env = {k: v for k, v in os.environ.items() if k != "OPENINBOX_ROOT"}
        cmd = [sys.executable, str(SCRIPT), "--root", str(root), "--no-sync", "--lang", "en", "--now", fu.NOW, "--json"]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertTrue(out["ok"])
        self.assertEqual((out["summary"]["sent"], out["summary"]["needs_you"]), (0, 2))
        self.assertGreater(out["summary"]["overdue"], 0)
        self.assertGreater(out["summary"]["rules_matched"], 0)
        self.assertFalse((root / "fixtures").exists())

    def test_script_help(self):
        r = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0)
        for flag in ("--no-sync", "--apply-rules", "--no-drafts", "--lang", "--now"):
            self.assertIn(flag, r.stdout)
        self.assertTrue(os.access(SCRIPT, os.X_OK))


if __name__ == "__main__":
    unittest.main()
