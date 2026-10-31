"""Regression tests for deliverable cards in ``server/features/agents.py`` (F33).

Defensive branches pinned here, each of which is the residue of a past defect:

* ``ID_RE`` + ``_valid_id``: ids are validated before any path is built, so a crafted id
  such as ``../../etc/passwd`` cannot reach outside ``data/deliverables/``.
* ``read_deliverable`` whitelists the format, so ``.txt`` / ``MD`` / ``json.md`` are
  refused instead of being turned into an arbitrary file read.
* ``save_deliverable`` slugifies the target, so a hostile subject still produces a valid
  id and writes only the three card files inside the deliverables folder.
* ``_render_html`` escapes every line and the title, and emits no script, so an email that
  contains ``<script>`` or an ``onerror=`` attribute cannot become active content.
* ``_render_md`` marks the fallback, so a local-heuristic card is never presented as an
  agent answer.
* ``list_deliverables`` skips broken JSON and misnamed files: one bad card used to break
  the whole listing.

Everything is written under a temp directory; the real ``data/`` tree is never touched.
"""
from __future__ import annotations

import atexit
import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
_SERVER = ROOT / "server"
if str(_SERVER) not in sys.path:
    sys.path.insert(0, str(_SERVER))

_TMP_ROOT = tempfile.mkdtemp(prefix="fmb-regress-agents-deliv-")
atexit.register(shutil.rmtree, _TMP_ROOT, True)
os.environ.setdefault("OPENINBOX_ROOT", _TMP_ROOT)

try:  # pragma: no cover - import guard only
    from features import agents
except Exception as exc:  # pragma: no cover
    agents = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


def setUpModule():
    if agents is None:
        raise unittest.SkipTest(f"features.agents unavailable: {_IMPORT_ERROR!r}")


class _TmpDelivMixin:
    """Point ``agents.DELIV_DIR`` at a throwaway folder for each test."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="fmb-deliv-cards-")
        self._orig_dir = agents.DELIV_DIR
        agents.DELIV_DIR = pathlib.Path(self._tmp)

    def tearDown(self):
        agents.DELIV_DIR = self._orig_dir
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _write_card(self, did="research-person-samira-20260101-000000-000000"):
        d = pathlib.Path(self._tmp)
        (d / f"{did}.md").write_text("# hi\n", encoding="utf-8")
        (d / f"{did}.html").write_text("<p>hi</p>", encoding="utf-8")
        (d / f"{did}.json").write_text(json.dumps({"id": did}), encoding="utf-8")
        return did


class IdValidationTests(unittest.TestCase):
    def test_boundary_lengths_are_enforced(self):
        self.assertTrue(agents._valid_id("x" * 81))
        self.assertFalse(agents._valid_id("x" * 82))
        self.assertFalse(agents._valid_id(""))
        self.assertFalse(agents._valid_id(None))

    def test_hostile_ids_are_rejected(self):
        for did in (
            "../../etc/passwd",
            "..",
            ".",
            "a/../../b",
            "sub/dir",
            "Upper-Case-1",
            "-lead",
            "with space",
            "ok\u0000id",
        ):
            self.assertFalse(agents._valid_id(did), did)


class ReadDeliverableTests(_TmpDelivMixin, unittest.TestCase):
    def test_traversal_ids_are_refused(self):
        for did in (
            "../../etc/passwd",
            "..",
            ".",
            "a/../../b",
            "sub/dir",
            "Upper-Case-1",
            "-lead",
            "x" * 82,
            "with space",
        ):
            self.assertIsNone(agents.read_deliverable(did, "md"), did)

    def test_only_md_html_json_formats(self):
        did = self._write_card()
        for fmt in ("txt", "MD", "json.md", "", "../x"):
            self.assertIsNone(agents.read_deliverable(did, fmt), fmt)
        for fmt, ctype in (
            ("md", "text/markdown"),
            ("html", "text/html"),
            ("json", "application/json"),
        ):
            got = agents.read_deliverable(did, fmt)
            self.assertIsNotNone(got, fmt)
            body, got_ctype = got
            self.assertIsInstance(body, bytes)
            self.assertTrue(got_ctype.startswith(ctype), got_ctype)

    def test_missing_file_returns_none_instead_of_raising(self):
        self.assertIsNone(agents.read_deliverable("research-person-nobody-20260101-000000-000000", "md"))


class SaveDeliverableTests(_TmpDelivMixin, unittest.TestCase):
    def test_hostile_target_never_escapes_the_deliverables_dir(self):
        result = {
            "kind": "research_person",
            "target": "../../../etc/passwd",
            "text": "# x\n",
            "driver": "local",
            "fallback": True,
            "sources": [],
        }
        card = agents.save_deliverable(result, lang="en")
        self.assertTrue(agents._valid_id(card["id"]))
        self.assertNotIn("/", card["id"])
        self.assertNotIn("..", card["id"])
        tmp = pathlib.Path(self._tmp)
        files = list(tmp.iterdir())
        self.assertEqual(len(files), 3)
        for p in files:
            self.assertEqual(p.parent, tmp)
            self.assertTrue(p.name.startswith(card["id"]), p.name)

    def test_card_is_written_as_md_html_and_json(self):
        result = {
            "kind": "meeting_prep",
            "target": "Weekly planning",
            "text": "## Agenda\n- one\n",
            "driver": "openai_compatible",
            "fallback": False,
            "sources": [],
        }
        card = agents.save_deliverable(result, lang="zh")
        self.assertEqual(card["kind"], "meeting_prep")
        self.assertEqual(card["lang"], "zh")
        self.assertIn("Weekly planning", card["title"])

        got = agents.read_deliverable(card["id"], "json")
        self.assertIsNotNone(got)
        data = json.loads(got[0].decode("utf-8"))
        self.assertEqual(data["id"], card["id"])
        self.assertEqual(data["lang"], "zh")

        md = agents.read_deliverable(card["id"], "md")
        self.assertIsNotNone(md)
        self.assertIn("會議準備", md[0].decode("utf-8"))


class RenderHtmlTests(unittest.TestCase):
    def _card(self, text, title="<b>x</b>"):
        return {
            "id": "research-person-x-20260101-000000-000000",
            "title": title,
            "kind": "research_person",
            "target": "x",
            "lang": "en",
            "created": "2026-01-01 00:00",
            "driver": "local",
            "fallback": False,
            "text": text,
        }

    def test_script_in_the_body_is_escaped(self):
        out = agents._render_html(self._card("<script>alert(1)</script>"))
        self.assertNotIn("<script", out.lower())
        self.assertIn("&lt;script&gt;", out)

    def test_event_handler_in_the_title_is_escaped(self):
        out = agents._render_html(self._card("ok", title='<img src=x onerror="alert(1)">'))
        self.assertNotIn("<img", out.lower())
        self.assertNotIn('onerror="alert', out)

    def test_headings_and_bullets_are_rendered(self):
        out = agents._render_html(self._card("# Title\n## Section\n- one\n- two\nplain"))
        self.assertIn("<h1>Title</h1>", out)
        self.assertIn("<h2>Section</h2>", out)
        self.assertIn("<li>one</li>", out)
        self.assertIn("<li>two</li>", out)
        self.assertIn("<p>plain</p>", out)

    def test_html_card_has_no_active_content(self):
        out = agents._render_html(self._card("see javascript:alert(1)"))
        self.assertNotIn("<script", out.lower())
        self.assertNotIn("<iframe", out.lower())
        self.assertNotIn("srcdoc", out.lower())


class RenderMarkdownTests(unittest.TestCase):
    def _card(self, lang="en", fallback=True, driver="local"):
        return {
            "id": "meeting-prep-weekly-20260101-000000-000000",
            "title": "Meeting prep: Weekly planning",
            "kind": "meeting_prep",
            "target": "Weekly planning",
            "lang": lang,
            "created": "2026-01-01 00:00",
            "driver": driver,
            "fallback": fallback,
            "text": "## Agenda\n- one\n",
        }

    def test_fallback_is_marked_in_english(self):
        self.assertIn("Fell back to local", agents._render_md(self._card()))

    def test_fallback_is_marked_in_chinese(self):
        self.assertIn("退回本機", agents._render_md(self._card(lang="zh")))

    def test_no_fallback_marker_when_the_agent_answered(self):
        md = agents._render_md(self._card(fallback=False, driver="openai_compatible"))
        self.assertNotIn("Fell back to local", md)
        self.assertIn("openai_compatible", md)


class ListDeliverablesTests(_TmpDelivMixin, unittest.TestCase):
    def test_broken_and_misnamed_cards_are_skipped(self):
        d = pathlib.Path(self._tmp)
        a = "research-person-a-20260101-000000-000000"
        b = "research-person-b-20260202-000000-000000"
        (d / f"{a}.json").write_text(
            json.dumps({"id": a, "title": "A", "kind": "research_person", "created": "2026-01-01 09:00"}),
            encoding="utf-8",
        )
        (d / f"{b}.json").write_text(
            json.dumps({"id": b, "title": "B", "kind": "research_person", "created": "2026-02-02 09:00"}),
            encoding="utf-8",
        )
        (d / "broken-card-20260101-000000-000000.json").write_text("{not json", encoding="utf-8")
        (d / "Bad_Name-000.json").write_text(json.dumps({"id": "Bad_Name-000"}), encoding="utf-8")
        (d / "notes.txt").write_text("nope", encoding="utf-8")

        ids = [c["id"] for c in agents.list_deliverables(50)]
        self.assertEqual(ids, [b, a])

    def test_cards_missing_metadata_do_not_raise(self):
        d = pathlib.Path(self._tmp)
        c = "research-person-c-20260303-000000-000000"
        (d / f"{c}.json").write_text(json.dumps({"id": c}), encoding="utf-8")
        cards = agents.list_deliverables(50)
        self.assertEqual([card["id"] for card in cards], [c])
        self.assertIsNone(cards[0]["created"])

    def test_limit_is_applied(self):
        d = pathlib.Path(self._tmp)
        for i in range(3):
            did = f"research-person-n{i}-2026010{i + 1}-000000-000000"
            (d / f"{did}.json").write_text(
                json.dumps({"id": did, "created": f"2026-01-0{i + 1} 09:00"}), encoding="utf-8"
            )
        self.assertEqual(len(agents.list_deliverables(2)), 2)

    def test_missing_dir_lists_nothing(self):
        agents.DELIV_DIR = pathlib.Path(self._tmp) / "not-created"
        self.assertEqual(agents.list_deliverables(10), [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
