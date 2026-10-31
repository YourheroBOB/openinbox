"""Edge and regression tests for the agent deliverable store (`server/features/agents.py`).

Scope: id validation, path containment, corrupt or partial card files, listing limits, and
read/format dispatch. The task and mention endpoints have their own tests; this file never
calls them, never reads mail and never touches the network. Every file is written under a
throwaway directory and the module's DELIV_DIR is patched, so the checkout's data/ is never
written to.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SERVER = str(ROOT / "server")
if SERVER not in sys.path:
    sys.path.insert(0, SERVER)

from features import agents  # noqa: E402  (needs the path setup above)

CARD_KEYS = {"id", "title", "kind", "target", "lang", "created", "driver", "fallback"}


def card(**over):
    """A complete fictional card dict, as `save_deliverable` would receive it."""
    data = {
        "kind": "research_person",
        "target": "Example Person",
        "title": "Person research: Example Person",
        "driver": "local",
        "fallback": True,
        "text": "# Person research: Example Person\n\n- Role: [missing]\n",
        "sources": [],
    }
    data.update(over)
    return data


def stored(**over):
    """A complete card record, as written to `<id>.json` on disk."""
    data = {
        "id": "research-person-example-20260101-000000-000000",
        "title": "Person research: Example Person",
        "kind": "research_person",
        "target": "Example Person",
        "lang": "en",
        "created": "2026-01-01 09:00",
        "driver": "local",
        "fallback": False,
        "text": "# hidden body\n",
        "sources": [],
    }
    data.update(over)
    return data


class ValidIdEdgeTest(unittest.TestCase):
    """`_valid_id` is the only gate before a path is built, so its edges matter."""

    def test_rejects_unsafe_or_malformed_ids(self):
        for bad in (
            "", None, "..", "../etc/passwd", "a/../b", "abc.md", "ABC", "-lead",
            "ab", "a" * 82, "abc def", "abc:", "abc\tdef", "abc\\def", "ａｂｃ",
        ):
            with self.subTest(bad=bad):
                self.assertFalse(agents._valid_id(bad))

    def test_accepts_lowercase_ids_within_the_length_limit(self):
        for good in ("abc", "000", "a1-2", "research-person-x-20260101-000000-000000", "a" * 81):
            with self.subTest(good=good):
                self.assertTrue(agents._valid_id(good))

    def test_length_boundary_is_81_characters(self):
        self.assertTrue(agents._valid_id("a" * 81))
        self.assertFalse(agents._valid_id("a" * 82))


class DeliverableStoreEdgeTest(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.dir = self.root / "deliverables"
        patcher = mock.patch.object(agents, "DELIV_DIR", self.dir)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _write(self, name: str, body: str) -> Path:
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self.dir / name
        path.write_text(body, encoding="utf-8")
        return path

    # ── read ────────────────────────────────────────────────────────────

    def test_read_before_anything_is_saved(self):
        self.assertFalse(self.dir.exists())
        self.assertIsNone(agents.read_deliverable("abc", "md"))

    def test_read_rejects_bad_ids(self):
        self._write("abc.md", "hello")
        for bad in ("../abc", "abc/..", "abc.md", "ABC", "ab", "", None):
            with self.subTest(bad=bad):
                self.assertIsNone(agents.read_deliverable(bad, "md"))

    def test_read_rejects_unknown_formats(self):
        self._write("abc.md", "hello")
        for fmt in ("txt", "MD", "HTML", "json ", "", None):
            with self.subTest(fmt=fmt):
                self.assertIsNone(agents.read_deliverable("abc", fmt))

    def test_read_returns_bytes_and_matching_content_type(self):
        self._write("abc.md", "line\n")
        self._write("abc.html", "<p>x</p>\n")
        self._write("abc.json", "{}\n")

        body, ctype = agents.read_deliverable("abc", "md")
        self.assertEqual(body, b"line\n")
        self.assertTrue(ctype.startswith("text/markdown"))

        body, ctype = agents.read_deliverable("abc", "html")
        self.assertEqual(body, b"<p>x</p>\n")
        self.assertTrue(ctype.startswith("text/html"))

        body, ctype = agents.read_deliverable("abc", "json")
        self.assertEqual(body, b"{}\n")
        self.assertTrue(ctype.startswith("application/json"))

    def test_missing_file_for_a_valid_id_is_none(self):
        self._write("abc.md", "hello")
        self.assertIsNone(agents.read_deliverable("abcd", "md"))

    def test_trailing_newline_in_id_never_leaves_the_folder(self):
        # `$` in ID_RE tolerates a trailing newline; the read must still stay inside DELIV_DIR.
        self._write("abc.md", "hello")
        self.assertIsNone(agents.read_deliverable("abc\n", "md"))

    # ── save ────────────────────────────────────────────────────────────

    def test_save_keeps_every_file_inside_the_deliverable_folder(self):
        saved = agents.save_deliverable(
            {"kind": "research_person", "target": "../../escape", "text": "x"}, lang="en")
        self.assertTrue(agents._valid_id(saved["id"]))
        self.assertNotIn("/", saved["id"])
        self.assertNotIn("..", saved["id"])
        written = {p.relative_to(self.root) for p in self.root.rglob("*") if p.is_file()}
        expected = {Path("deliverables") / f"{saved['id']}.{ext}" for ext in ("md", "html", "json")}
        self.assertEqual(written, expected)

    def test_save_with_cjk_only_target_still_makes_a_valid_id(self):
        saved = agents.save_deliverable(
            {"kind": "meeting_prep", "target": "範例對象的會議", "text": "- 目的：[待填]"}, lang="zh-Hant")
        self.assertTrue(agents._valid_id(saved["id"]))
        self.assertIn("card", saved["id"])
        self.assertEqual(saved["lang"], "zh")

    def test_default_title_is_trimmed_when_target_is_empty(self):
        zh = agents.save_deliverable({"kind": "research_person", "target": "", "text": "x"}, lang="zh-Hant")
        self.assertEqual(zh["title"], agents.LABELS["zh"]["research_person"])
        en = agents.save_deliverable({"kind": "research_person", "target": "", "text": "x"}, lang="en")
        self.assertEqual(en["title"], agents.LABELS["en"]["research_person"])

    def test_save_returns_only_public_metadata(self):
        saved = agents.save_deliverable(card(), lang="en")
        self.assertEqual(set(saved), CARD_KEYS)
        self.assertIs(saved["fallback"], True)

    def test_missing_text_is_stored_as_empty(self):
        saved = agents.save_deliverable({"kind": "research_person", "target": "Example Person"}, lang="en")
        raw = json.loads((self.dir / f"{saved['id']}.json").read_text(encoding="utf-8"))
        self.assertEqual(raw["text"], "")
        self.assertEqual(raw["sources"], [])

    def test_saved_text_round_trips_through_json(self):
        text = "# 標題\n\n- <script>alert(1)</script>\n"
        saved = agents.save_deliverable(
            {"kind": "research_company", "target": "Example Co", "text": text}, lang="en")
        raw = json.loads((self.dir / f"{saved['id']}.json").read_text(encoding="utf-8"))
        self.assertEqual(raw["text"], text)
        self.assertEqual(raw["id"], saved["id"])
        self.assertEqual(raw["kind"], "research_company")

    def test_two_saves_of_the_same_target_get_distinct_ids(self):
        first = agents.save_deliverable(card(), lang="en")
        second = agents.save_deliverable(card(), lang="en")
        self.assertNotEqual(first["id"], second["id"])
        self.assertTrue(agents._valid_id(second["id"]))
        self.assertEqual(len(agents.list_deliverables()), 2)

    # ── list ────────────────────────────────────────────────────────────

    def test_list_on_missing_folder_is_empty(self):
        self.assertEqual(agents.list_deliverables(), [])

    def test_list_skips_corrupt_and_misnamed_files(self):
        self._write("abc.json", "{not json")
        self._write("abc-empty.json", "")
        self._write("x.json", json.dumps(stored(id="x")))
        self._write("UpperCase.json", json.dumps(stored()))
        self._write("abc-notes.txt", "ignored")
        self.assertEqual(agents.list_deliverables(), [])

    def test_list_tolerates_partial_cards_and_hides_body_text(self):
        self._write("abc.json", json.dumps({"id": "abc", "text": "hidden body"}))
        out = agents.list_deliverables()
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["id"], "abc")
        self.assertIsNone(out[0]["title"])
        self.assertEqual(set(out[0]), CARD_KEYS)
        self.assertNotIn("hidden body", json.dumps(out))

    def test_list_is_newest_first_and_honours_the_limit(self):
        for cid, created in (
            ("aaa", "2026-01-01 09:00"),
            ("bbb", "2026-01-03 09:00"),
            ("ccc", "2026-01-02 09:00"),
        ):
            self._write(f"{cid}.json", json.dumps(stored(id=cid, created=created)))
        self.assertEqual([c["id"] for c in agents.list_deliverables()], ["bbb", "ccc", "aaa"])
        self.assertEqual([c["id"] for c in agents.list_deliverables(2)], ["bbb", "ccc"])
        self.assertEqual(agents.list_deliverables(0), [])

    def test_saved_card_is_listed_and_readable(self):
        saved = agents.save_deliverable(
            {"kind": "meeting_prep", "target": "Example Co", "text": "## Agenda\n- decide\n"}, lang="en")
        listed = agents.list_deliverables()
        self.assertEqual([c["id"] for c in listed], [saved["id"]])
        self.assertEqual(listed[0]["kind"], "meeting_prep")

        body, _ = agents.read_deliverable(saved["id"], "md")
        self.assertIn(b"## Agenda", body)
        html_body, _ = agents.read_deliverable(saved["id"], "html")
        self.assertIn(b"<h2>Agenda</h2>", html_body)


if __name__ == "__main__":
    unittest.main()
