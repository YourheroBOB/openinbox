"""Regression tests for @mention routing in ``server/features/agents.py`` (F32/F33).

Every assertion below pins a branch that only exists because of a past defect:

* ``MENTION_RE`` lists ``research-company`` before ``research``. With the shorter word
  first, ``@research-company Acme`` used to route to *person* research and the target
  became ``"-company Acme"``.
* the ``(?<![\\w.])`` lookbehind keeps an ``@`` that belongs to an address
  (``bob@agent.example.com``) from being read as an agent mention.
* the trailing ``\\b`` stops ``@researching`` / ``@meetings`` / ``@preparation`` from
  triggering a task.
* ``REQUEST_VERBS`` strips a polite request prefix so ``@agent 請幫我查 X`` targets ``X``
  instead of the whole sentence.
* ``MAX_BODY`` truncation keeps a huge message from scanning an unbounded string.
* ``mentions_alias`` compares the whole addr-spec, so a longer local-part or one extra
  domain label is not mistaken for the agent alias.

Fictional addresses only (``*.example``); nothing here reads a real mailbox.
"""
from __future__ import annotations

import atexit
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

_TMP_ROOT = tempfile.mkdtemp(prefix="fmb-regress-agents-mention-")
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


class ParseMentionTests(unittest.TestCase):
    def test_research_company_wins_over_research(self):
        got = agents.parse_mention("@research-company Northwind Traders")
        self.assertIsNotNone(got)
        self.assertEqual(got["kind"], "research_company")
        self.assertEqual(got["target"], "Northwind Traders")
        self.assertEqual(got["word"], "research-company")

    def test_at_sign_inside_an_address_is_not_a_mention(self):
        self.assertIsNone(agents.parse_mention("please write to bob@agent.example.com about it"))

    def test_at_sign_after_a_dot_is_not_a_mention(self):
        self.assertIsNone(agents.parse_mention("see foo.@agent later"))

    def test_word_boundary_stops_prefix_matches(self):
        for text in (
            "@researching the market",
            "@meetings next week",
            "@preparation notes",
            "@agency work",
            "price @ 5 dollars",
        ):
            self.assertIsNone(agents.parse_mention(text), text)

    def test_bare_mention_has_no_target(self):
        got = agents.parse_mention("@agent")
        self.assertIsNotNone(got)
        self.assertEqual(got["kind"], "research_person")
        self.assertEqual(got["target"], "")
        self.assertEqual(got["word"], "agent")

    def test_polite_request_words_are_stripped_from_the_target(self):
        got = agents.parse_mention("@agent 請幫我查 Samira Ortiz 最近往來")
        self.assertIsNotNone(got)
        self.assertEqual(got["target"], "Samira Ortiz 最近往來")

    def test_mention_word_sets_the_kind(self):
        got = agents.parse_mention("@prep Weekly planning")
        self.assertIsNotNone(got)
        self.assertEqual(got["kind"], "meeting_prep")
        self.assertEqual(got["target"], "Weekly planning")

    def test_company_word_in_the_target_infers_company_research(self):
        got = agents.parse_mention("@agent Northwind 股份有限公司")
        self.assertIsNotNone(got)
        self.assertEqual(got["kind"], "research_company")

    def test_meeting_word_in_the_ask_infers_meeting_prep(self):
        got = agents.parse_mention("@agent tomorrow's meeting agenda please")
        self.assertIsNotNone(got)
        self.assertEqual(got["kind"], "meeting_prep")

    def test_matching_is_case_insensitive(self):
        got = agents.parse_mention("@AGENT Samira")
        self.assertIsNotNone(got)
        self.assertEqual(got["word"], "agent")
        self.assertEqual(got["target"], "Samira")

    def test_ask_drops_the_mention_word(self):
        got = agents.parse_mention("hi @agent please check\nthe thread")
        self.assertIsNotNone(got)
        self.assertEqual(got["ask"], "hi please check the thread")

    def test_target_length_is_capped(self):
        got = agents.parse_mention("@agent " + "x" * 200)
        self.assertIsNotNone(got)
        self.assertEqual(len(got["target"]), 120)

    def test_body_is_truncated_before_scanning(self):
        text = "y" * agents.MAX_BODY + "\n@agent Samira"
        self.assertIsNone(agents.parse_mention(text))

    def test_empty_or_none_input_is_not_a_mention(self):
        self.assertIsNone(agents.parse_mention(""))
        self.assertIsNone(agents.parse_mention(None))

    def test_every_mention_word_maps_to_a_known_kind(self):
        for word, kind in agents.MENTIONS.items():
            if kind is not None:
                self.assertIn(kind, agents.TASK_KINDS, word)


class MentionsAliasTests(unittest.TestCase):
    def test_exact_alias_matches(self):
        self.assertTrue(agents.mentions_alias("agent@example.com"))
        self.assertTrue(agents.mentions_alias("Agent Team <AGENT@example.com>"))
        self.assertTrue(agents.mentions_alias("someone@example.com, agent@example.com"))

    def test_lookalikes_do_not_match(self):
        for addr in (
            "notagent@example.com",
            "agent2@example.com",
            "xagent@example.com",
            "agent@example.com.evil.example",
            "agent@sub.example.com",
        ):
            self.assertFalse(agents.mentions_alias(addr), addr)

    def test_empty_alias_is_false(self):
        self.assertFalse(agents.mentions_alias(""))
        self.assertFalse(agents.mentions_alias(None))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
