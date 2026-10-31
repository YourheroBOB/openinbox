"""Edge and regression tests for card rendering and error labels in `server/features/agents.py`.

Covers what the endpoint tests do not: HTML escaping of hostile card text, heading/list
rendering, empty bodies, the metadata header, the fallback marker, and `error_label`, which
must never echo the original exception message (it can carry an upstream body or a CLI echo
of the prompt). Pure functions only: no disk, no mail, no network.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = str(ROOT / "server")
if SERVER not in sys.path:
    sys.path.insert(0, SERVER)

from features import agents  # noqa: E402  (needs the path setup above)


def card(**over):
    """A complete fictional card record, as stored in `<id>.json`."""
    data = {
        "id": "research-person-example-20260101-000000-000000",
        "title": "Person research: Example Person",
        "kind": "research_person",
        "target": "Example Person",
        "lang": "en",
        "created": "2026-01-01 09:00",
        "driver": "local",
        "fallback": False,
        "text": "",
        "sources": [],
    }
    data.update(over)
    return data


class RenderHtmlEdgeTest(unittest.TestCase):
    def test_escapes_markup_from_card_text(self):
        out = agents._render_html(card(text='# T\n\n"><script>alert(1)</script>\n- <img src=x onerror=1>\n'))
        lowered = out.lower()
        self.assertNotIn("<script", lowered)
        self.assertNotIn("<img", lowered)
        self.assertNotIn("<iframe", lowered)
        self.assertIn("&lt;script&gt;", out)
        self.assertIn('charset="utf-8"', out)

    def test_headings_lists_and_plain_lines(self):
        out = agents._render_html(card(text="# One\n## Two\n### Three\n- item\n   - nested\n\n\nplain\n"))
        self.assertIn("<h1>One</h1>", out)
        self.assertIn("<h2>Two</h2>", out)
        self.assertIn("<h3>Three</h3>", out)
        self.assertIn("<li>item</li>", out)
        self.assertIn("<li>nested</li>", out)
        self.assertIn("<p>plain</p>", out)

    def test_blank_lines_are_dropped(self):
        out = agents._render_html(card(text="\n\n\n"))
        self.assertNotIn("<p>", out)

    def test_empty_text_still_produces_a_closed_document(self):
        out = agents._render_html(card(text=""))
        self.assertTrue(out.startswith("<!doctype html>"))
        self.assertTrue(out.rstrip().endswith("</html>"))

    def test_language_attribute_and_kind_label(self):
        zh = agents._render_html(card(lang="zh"))
        self.assertIn('lang="zh-Hant"', zh)
        self.assertIn(agents.LABELS["zh"]["research_person"], zh)
        en = agents._render_html(card(lang="en"))
        self.assertIn('lang="en"', en)
        self.assertIn(agents.LABELS["en"]["research_person"], en)

    def test_title_is_escaped_in_head(self):
        out = agents._render_html(card(title="<b>A & B</b>"))
        self.assertIn("<title>&lt;b&gt;A &amp; B&lt;/b&gt;</title>", out)
        self.assertNotIn("<b>", out)

    def test_no_links_or_remote_resources_are_emitted(self):
        out = agents._render_html(card(text="see https://example.com/a and <a href=x>\n"))
        lowered = out.lower()
        self.assertNotIn("<a ", lowered)
        self.assertNotIn('href="', lowered)
        self.assertNotIn('src="http', lowered)


class RenderMarkdownEdgeTest(unittest.TestCase):
    def test_header_lines_carry_metadata(self):
        md = agents._render_md(card(lang="zh", created="2026-01-02 03:04", driver="cli", text="# 內容\n"))
        self.assertTrue(md.startswith("# Person research: Example Person\n"))
        self.assertIn(f"- {agents.LABELS['zh']['kind']}: {agents.LABELS['zh']['research_person']}", md)
        self.assertIn(f"- {agents.LABELS['zh']['created']}: 2026-01-02 03:04", md)
        self.assertIn(f"- {agents.LABELS['zh']['driver']}: cli", md)
        self.assertIn("# 內容", md)

    def test_fallback_marker_only_when_fallback(self):
        self.assertIn(agents.LABELS["en"]["fallback"], agents._render_md(card(lang="en", fallback=True)))
        self.assertNotIn(agents.LABELS["en"]["fallback"], agents._render_md(card(lang="en", fallback=False)))

    def test_text_is_not_followed_by_extra_blank_lines(self):
        md = agents._render_md(card(text="body\n\n\n"))
        self.assertTrue(md.endswith("body\n"))
        self.assertNotIn("\n\n\n", md)

    def test_empty_text_still_has_a_header_block(self):
        md = agents._render_md(card(text=""))
        self.assertTrue(md.endswith("\n"))
        self.assertNotIn("\n\n\n", md)


class _Coded(Exception):
    """Fake bridge error carrying an HTTP-style status the way agent_bridge may attach it."""

    def __init__(self, message: str = "", code=None):
        super().__init__(message)
        if code is not None:
            self.code = code


class ErrorLabelEdgeTest(unittest.TestCase):
    def test_integer_code_attribute_wins(self):
        self.assertEqual(agents.error_label(_Coded("boom", code=503)), "_Coded: HTTP 503")

    def test_status_found_in_the_message(self):
        self.assertEqual(
            agents.error_label(RuntimeError("upstream said HTTP 429 slow down")),
            "RuntimeError: HTTP 429",
        )

    def test_non_integer_code_falls_back_to_the_message(self):
        exc = _Coded("gateway HTTP 502", code="500")
        self.assertEqual(agents.error_label(exc), "_Coded: HTTP 502")

    def test_no_status_leaves_the_class_name_only(self):
        self.assertEqual(agents.error_label(RuntimeError("connection reset")), "RuntimeError")
        self.assertEqual(agents.error_label(ValueError()), "ValueError")

    def test_malformed_statuses_are_not_guessed(self):
        for message in ("HTTP 99", "HTTP 1000", "HTTPS 500", "http 500", "HTTP500"):
            with self.subTest(message=message):
                self.assertEqual(agents.error_label(RuntimeError(message)), "RuntimeError")

    def test_message_body_is_never_echoed(self):
        exc = RuntimeError("SENTINEL_MESSAGE_TEXT with HTTP 500 and more detail")
        label = agents.error_label(exc)
        self.assertEqual(label, "RuntimeError: HTTP 500")
        self.assertNotIn("SENTINEL_MESSAGE_TEXT", label)
        self.assertNotIn("more detail", label)


class ConfigurationRegressionTest(unittest.TestCase):
    def test_every_task_kind_has_a_label_in_both_languages(self):
        for lang in ("zh", "en"):
            for kind in agents.TASK_KINDS:
                with self.subTest(lang=lang, kind=kind):
                    self.assertTrue(agents.LABELS[lang].get(kind))

    def test_every_named_mention_maps_to_a_known_task_kind(self):
        for word, kind in agents.MENTIONS.items():
            with self.subTest(word=word):
                self.assertTrue(kind is None or kind in agents.TASK_KINDS)

    def test_required_header_labels_exist_in_both_languages(self):
        for lang in ("zh", "en"):
            for key in ("title", "kind", "created", "driver", "fallback", "no_source"):
                with self.subTest(lang=lang, key=key):
                    self.assertTrue(agents.LABELS[lang].get(key))


if __name__ == "__main__":
    unittest.main()
