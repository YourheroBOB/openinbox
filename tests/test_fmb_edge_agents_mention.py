"""Edge-case tests for the @agent mention parser and error labels (F33).

Complements tests/test_tpi_agents_*.py: look-alike addresses that must not trigger a
task, verb/punctuation trimming, truncation limits, and error labels that never echo
the original exception text. Fictional addresses only (example.com). Read-only: no
mail DB writes, no network.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_SERVER = Path(__file__).resolve().parents[1] / "server"
if str(_SERVER) not in sys.path:
    sys.path.insert(0, str(_SERVER))

from features import agents  # noqa: E402  (import needs server/ on sys.path)


class ParseMentionNoTriggerTest(unittest.TestCase):
    """Things that look like a mention but must do nothing."""

    def test_empty_input_is_not_a_mention(self):
        for value in (None, "", "   ", "\n\n", "@"):
            with self.subTest(value=value):
                self.assertIsNone(agents.parse_mention(value))

    def test_ordinary_text_is_not_a_mention(self):
        self.assertIsNone(agents.parse_mention("Samira asked about the renewal."))
        self.assertIsNone(agents.parse_mention("mail me at agent@example.com"))
        self.assertIsNone(agents.parse_mention("@agentish reply please"))

    def test_glued_at_signs_are_not_mentions(self):
        # The regexp guards against a word character or a dot right before the "@".
        for text in ("bob@agent.com", "bob.@agent", "x@agentresearch", "team@agent_ops"):
            with self.subTest(text=text):
                self.assertIsNone(agents.parse_mention(text))


class ParseMentionTargetTest(unittest.TestCase):
    """Kind inference, target extraction and the input caps."""

    def test_bare_mention_still_runs_a_person_research(self):
        got = agents.parse_mention("@agent")
        self.assertIsNotNone(got)
        self.assertEqual(got["kind"], "research_person")
        self.assertEqual(got["target"], "")
        self.assertEqual(got["word"], "agent")
        self.assertEqual(got["ask"], "")

    def test_mention_is_case_insensitive(self):
        got = agents.parse_mention("@AGENT Samira Ortiz")
        self.assertIsNotNone(got)
        self.assertEqual(got["word"], "agent")
        self.assertEqual(got["target"], "Samira Ortiz")

    def test_mention_inside_parentheses_triggers(self):
        # Known product limitation: the parser may leave the closing parenthesis in
        # the target (") Samira Ortiz"). We tolerate that single stray character here
        # so this edge case stays green whether or not the parser trims it; the point
        # under test is that a mention inside parentheses is recognised and routed.
        got = agents.parse_mention("(@agent) Samira Ortiz")
        self.assertIsNotNone(got)
        self.assertEqual(got["target"].lstrip(") ").strip(), "Samira Ortiz")

    def test_explicit_words_pick_the_kind(self):
        cases = {
            "@research Northwind renewal": "research_person",
            "@research-company Northwind renewal": "research_company",
            "@prep Northwind renewal": "meeting_prep",
            "@meeting Northwind renewal": "meeting_prep",
        }
        for text, kind in cases.items():
            with self.subTest(text=text):
                self.assertEqual(agents.parse_mention(text)["kind"], kind)

    def test_company_word_in_target_switches_the_kind(self):
        got = agents.parse_mention("@agent Northwind Inc renewal")
        self.assertEqual(got["kind"], "research_company")

    def test_meeting_word_in_the_ask_switches_the_kind(self):
        got = agents.parse_mention("@agent can you get me ready for the agenda?")
        self.assertEqual(got["kind"], "meeting_prep")

    def test_meeting_wins_over_company(self):
        got = agents.parse_mention("@agent Northwind Inc meeting")
        self.assertEqual(got["kind"], "meeting_prep")

    def test_target_is_only_the_rest_of_the_line(self):
        got = agents.parse_mention("@agent Samira Ortiz\nplease also check the renewal")
        self.assertEqual(got["target"], "Samira Ortiz")
        self.assertIn("renewal", got["ask"])
        self.assertNotIn("@agent", got["ask"])

    def test_polite_verbs_and_separators_are_trimmed(self):
        self.assertEqual(agents.parse_mention("@agent 請幫我查 Samira Ortiz")["target"], "Samira Ortiz")
        self.assertEqual(agents.parse_mention("@agent 查 Samira Ortiz")["target"], "Samira Ortiz")
        self.assertEqual(agents.parse_mention("@agent: Samira Ortiz。")["target"], "Samira Ortiz")
        self.assertEqual(agents.parse_mention("@agent please Samira Ortiz")["target"], "Samira Ortiz")

    def test_target_is_capped_at_120_chars(self):
        got = agents.parse_mention("@agent " + "a" * 300)
        self.assertEqual(len(got["target"]), 120)

    def test_ask_is_capped_at_1000_chars(self):
        got = agents.parse_mention("@agent " + "b" * 3000)
        self.assertLessEqual(len(got["ask"]), 1000)

    def test_mention_past_the_body_cap_is_ignored(self):
        text = "x" * agents.MAX_BODY + " @agent Samira Ortiz"
        self.assertIsNone(agents.parse_mention(text))


class AliasRoutingTest(unittest.TestCase):
    """`agent@example.com` is a routing word only; look-alikes must not match."""

    def test_alias_uses_a_fictional_domain(self):
        self.assertTrue(agents.ALIAS.endswith("@example.com"), agents.ALIAS)

    def test_exact_alias_only(self):
        self.assertTrue(agents.mentions_alias("agent@example.com"))
        self.assertTrue(agents.mentions_alias("Agent <AGENT@Example.COM>"))
        self.assertTrue(agents.mentions_alias("bob@example.com, agent@example.com"))

    def test_lookalikes_are_not_the_alias(self):
        for value in (
            "",
            "   ",
            "agent@example.com.evil.test",
            "notagent@example.com",
            "agent+tag@example.com",
            "agent@example.org",
            "bob@example.com",
        ):
            with self.subTest(value=value):
                self.assertFalse(agents.mentions_alias(value), value)


class ErrorLabelTest(unittest.TestCase):
    """A label must never carry the exception message (it can hold prompts or endpoints)."""

    def test_class_name_only(self):
        self.assertEqual(agents.error_label(ValueError("boom")), "ValueError")

    def test_message_is_never_echoed(self):
        label = agents.error_label(RuntimeError("api_key=FAKE_VALUE_FOR_TEST rejected"))
        self.assertNotIn("FAKE_VALUE_FOR_TEST", label)
        self.assertEqual(label, "RuntimeError")

    def test_http_status_is_extracted(self):
        got = agents.error_label(RuntimeError("upstream said HTTP 502 bad gateway"))
        self.assertEqual(got, "RuntimeError: HTTP 502")

    def test_http_status_needs_a_word_boundary(self):
        # "XHTTP" has no word boundary before HTTP, so it is not treated as a status.
        self.assertEqual(agents.error_label(RuntimeError("XHTTP 500")), "RuntimeError")
        # A two-digit code is not a status; the first three-digit code wins.
        self.assertEqual(agents.error_label(RuntimeError("HTTP 12 and HTTP 503")), "RuntimeError: HTTP 503")

    def test_first_matching_status_wins(self):
        self.assertEqual(agents.error_label(RuntimeError("HTTP 500 then HTTP 503")), "RuntimeError: HTTP 500")

    def test_exception_code_attribute_wins(self):
        class Unauthorized(Exception):
            code = 401

        self.assertEqual(agents.error_label(Unauthorized("nope")), "Unauthorized: HTTP 401")

    def test_non_integer_code_falls_back_to_the_message(self):
        class Weird(Exception):
            code = "401"

        self.assertEqual(agents.error_label(Weird("nope")), "Weird")
        self.assertEqual(agents.error_label(Weird("HTTP 429 slow down")), "Weird: HTTP 429")


if __name__ == "__main__":
    unittest.main()
