"""Regression tests for deliverable cards (server/features/agents.py).

The module documents three fixes that are easy to undo by accident, so each one gets a
test that fails loudly if the guard disappears:

1. A deliverable id is checked against a strict pattern *before* any path is built, so a
   crafted id (`../escape`, `cards/../../escape`) cannot reach outside data/deliverables/.
   The id also has to survive a hostile target string.
2. The HTML card escapes every line of mail text and loads no external resource, because
   the UI previews it in a sandboxed iframe.
3. `error_label()` reports only the exception class (plus an HTTP status when one is named)
   and never the message, because agent_bridge errors can echo an endpoint body or CLI
   stderr of the prompt.

All file I/O happens in a throwaway tempfile directory; nothing here touches the repo's
real data/deliverables/ folder. Fake credentials use the obvious FAKE_VALUE_FOR_TEST.
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
for _path in (ROOT / "server", ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from features import agents  # noqa: E402


class TestDeliverableIdGuard(unittest.TestCase):
    """_valid_id() is the only thing standing between an id and a file path."""

    def test_accepts_the_generated_shape(self):
        self.assertTrue(agents._valid_id("research-person-samira-ortiz-20260101-120000-000001"))

    def test_rejects_traversal_and_odd_shapes(self):
        for bad in (
            "",
            ".",
            "..",
            "../escape",
            "..%2fescape",
            "cards/../../escape",
            "-leading-dash",
            "UPPER-case",
            "with space",
            "with.dot",
            "a",
            "ab",
            "x" * 90,
        ):
            self.assertFalse(agents._valid_id(bad), bad)


class TestDeliverableStore(unittest.TestCase):
    """save / read / list round trips against an isolated directory."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="fmb-regress-deliv-"))
        self.addCleanup(shutil.rmtree, self.dir, True)
        patcher = mock.patch.object(agents, "DELIV_DIR", self.dir)
        patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def _result(**over):
        base = {
            "kind": "research_person",
            "target": "Samira Ortiz",
            "text": "# Person brief\n- Role: [missing]",
            "driver": "local",
            "fallback": True,
            "sources": [],
        }
        base.update(over)
        return base

    def test_read_refuses_traversal_and_unknown_formats(self):
        self.assertIsNone(agents.read_deliverable("../escape", "md"))
        self.assertIsNone(agents.read_deliverable("cards/../../escape", "html"))
        self.assertIsNone(agents.read_deliverable("valid-card-id", "txt"))
        self.assertIsNone(agents.read_deliverable("", "md"))

    def test_missing_card_is_a_plain_none(self):
        self.assertIsNone(agents.read_deliverable("no-such-card-in-this-test", "md"))

    def test_save_writes_md_html_and_json(self):
        card = agents.save_deliverable(self._result(), lang="en")
        self.assertRegex(card["id"], agents.ID_RE)
        for fmt in ("md", "html", "json"):
            got = agents.read_deliverable(card["id"], fmt)
            self.assertIsNotNone(got, fmt)
            body, ctype = got
            self.assertTrue(body, fmt)
            self.assertIn("charset=utf-8", ctype)
        self.assertEqual(
            sorted(p.name for p in self.dir.iterdir()),
            sorted(f"{card['id']}.{fmt}" for fmt in ("md", "html", "json")),
        )

    def test_saved_card_round_trips_its_metadata(self):
        card = agents.save_deliverable(self._result(), lang="en")
        listed = agents.list_deliverables(limit=10)
        self.assertEqual([c["id"] for c in listed], [card["id"]])
        self.assertEqual(listed[0]["kind"], "research_person")
        self.assertTrue(listed[0]["fallback"])
        meta = json.loads((self.dir / f"{card['id']}.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["target"], "Samira Ortiz")
        self.assertEqual(meta["lang"], "en")

    def test_html_card_allows_no_script_or_external_resource(self):
        text = "# Report\n<script>alert(1)</script>\n- <img src=x onerror=alert(1)>"
        card = agents.save_deliverable(self._result(text=text), lang="en")
        out = (self.dir / f"{card['id']}.html").read_text(encoding="utf-8")
        self.assertNotIn("<script", out)
        self.assertNotIn("<img", out)
        self.assertIn("&lt;script&gt;", out)
        self.assertIn("&lt;img", out)
        self.assertNotIn("http://", out)
        self.assertNotIn("https://", out)

    def test_markdown_card_carries_labels_and_fallback_note(self):
        card = agents.save_deliverable(self._result(), lang="zh-Hant")
        self.assertEqual(card["lang"], "zh")
        md = (self.dir / f"{card['id']}.md").read_text(encoding="utf-8")
        self.assertIn("人物研究", md)
        self.assertIn("退回本機", md)
        self.assertIn("Role: [missing]", md)

    def test_title_is_generated_per_language(self):
        en = agents.save_deliverable(self._result(target="Samira Ortiz"), lang="en")
        self.assertEqual(en["title"], "Person research: Samira Ortiz")
        zh = agents.save_deliverable(self._result(target="Samira Ortiz"), lang="zh-Hant")
        self.assertEqual(zh["title"], "人物研究：Samira Ortiz")

    def test_hostile_target_cannot_shape_the_id(self):
        card = agents.save_deliverable(self._result(target="../../etc/passwd"), lang="en")
        did = card["id"]
        self.assertRegex(did, agents.ID_RE)
        self.assertNotIn("/", did)
        self.assertNotIn(".", did)
        self.assertNotIn("..", did)
        self.assertTrue((self.dir / f"{did}.md").is_file())

    def test_list_skips_corrupt_and_foreign_files(self):
        card = agents.save_deliverable(self._result(), lang="en")
        (self.dir / "broken-card.json").write_text("{not json", encoding="utf-8")
        (self.dir / "NOT-A-VALID-ID.json").write_text("{}", encoding="utf-8")
        (self.dir / "notes.txt").write_text("ignored", encoding="utf-8")
        listed = agents.list_deliverables(limit=10)
        self.assertEqual([c["id"] for c in listed], [card["id"]])


class TestSlug(unittest.TestCase):
    """The slug feeds the id, so non-ASCII and junk input must degrade safely."""

    def test_ascii_text_becomes_a_dash_slug(self):
        self.assertEqual(agents._slug("Samira Ortiz"), "samira-ortiz")

    def test_non_ascii_and_empty_fall_back_to_card(self):
        for text in ("", None, "李小明", "!!!"):
            self.assertEqual(agents._slug(text), "card", text)

    def test_slug_is_length_bounded(self):
        self.assertLessEqual(len(agents._slug("a" * 200)), 40)


class TestErrorLabel(unittest.TestCase):
    """Agent failures may echo endpoint bodies or CLI stderr; only the class may leak."""

    def test_class_and_http_status_only(self):
        class FakeAuthError(Exception):
            code = 401

        self.assertEqual(
            agents.error_label(FakeAuthError("FAKE_VALUE_FOR_TEST")),
            "FakeAuthError: HTTP 401",
        )

    def test_http_status_is_read_from_the_message(self):
        label = agents.error_label(RuntimeError("worker said HTTP 503 while streaming"))
        self.assertEqual(label, "RuntimeError: HTTP 503")
        self.assertNotIn("worker", label)

    def test_message_text_never_leaks(self):
        for exc in (
            ValueError("FAKE_VALUE_FOR_TEST"),
            RuntimeError("Authorization: FAKE_VALUE_FOR_TEST"),
        ):
            label = agents.error_label(exc)
            self.assertNotIn("FAKE_VALUE_FOR_TEST", label)
            self.assertEqual(label, type(exc).__name__)

    def test_non_integer_code_attribute_is_ignored(self):
        exc = RuntimeError("no status here")
        exc.code = "500"
        self.assertEqual(agents.error_label(exc), "RuntimeError")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
