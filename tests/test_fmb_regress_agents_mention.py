"""Regression tests for @agent mention parsing and alias routing (server/features/agents.py).

These pin the defensive branches that the module grew after earlier breakage
(see the module docstring and state/tpi-agents.md), so a future "cleanup" cannot
silently reopen them:

1. `@research-company` resolves as the company word; it must not be stopped early and
   read as `@research`.
2. The mention regex carries a word boundary plus a negative lookbehind, so a mail
   address like `ops@agent.example`, a word like `@agentbot`, or `@researcher` never
   fires a task.
3. Polite request words around the target are stripped, so `@agent 請幫我查 X` targets X
   and `@research X 請幫我查` also targets X.
4. A pasted thread longer than MAX_BODY is cut first, so a mention past the cut is
   ignored instead of firing on a half-pasted body.
5. A bare `@agent` yields an empty target; the HTTP layer (not the parser) fills it in.
6. The agent alias is matched on the whole addr-spec only: a longer local part or an
   extra label after the domain is not the alias.

Everything below is pure: no network, no files, no real addresses (all samples use the
reserved example.com domain and made-up names).
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _path in (ROOT / "server", ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from features import agents  # noqa: E402

try:  # mentions_alias() delegates address parsing to the compose helpers.
    from features.compose import parse_addr, split_addrs  # noqa: E402,F401
    _HAVE_COMPOSE = True
except Exception:  # pragma: no cover - keeps this file runnable on its own
    _HAVE_COMPOSE = False


class TestMentionParsing(unittest.TestCase):
    """parse_mention() must be a pure, bounded, predictable router."""

    def test_plain_text_has_no_mention(self):
        for text in ("", None, "just saying hello", "mail me at ops@agent.example"):
            self.assertIsNone(agents.parse_mention(text), text)

    def test_word_boundary_blocks_longer_words(self):
        for text in ("@agentbot please look", "@researcher Samira", "@preparation notes"):
            self.assertIsNone(agents.parse_mention(text), text)

    def test_bare_agent_leaves_target_empty(self):
        parsed = agents.parse_mention("@agent")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["word"], "agent")
        self.assertEqual(parsed["kind"], "research_person")
        self.assertEqual(parsed["target"], "")
        self.assertEqual(parsed["ask"], "")

    def test_research_word_targets_person(self):
        parsed = agents.parse_mention("@research Samira Ortiz")
        self.assertEqual(parsed["word"], "research")
        self.assertEqual(parsed["kind"], "research_person")
        self.assertEqual(parsed["target"], "Samira Ortiz")
        self.assertEqual(parsed["ask"], "Samira Ortiz")

    def test_research_company_is_not_shortened_to_research(self):
        parsed = agents.parse_mention("@research-company Northwind Ltd")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["word"], "research-company")
        self.assertEqual(parsed["kind"], "research_company")
        self.assertEqual(parsed["target"], "Northwind Ltd")

    def test_prep_and_meeting_words_map_to_meeting_prep(self):
        for text in ("@prep Q3 budget review", "@meeting Q3 budget review"):
            parsed = agents.parse_mention(text)
            self.assertIsNotNone(parsed, text)
            self.assertEqual(parsed["kind"], "meeting_prep", text)
            self.assertEqual(parsed["target"], "Q3 budget review", text)

    def test_generic_agent_infers_kind(self):
        self.assertEqual(agents.parse_mention("@agent 明天的會議 agenda")["kind"], "meeting_prep")
        self.assertEqual(agents.parse_mention("@agent Northwind Ltd")["kind"], "research_company")
        self.assertEqual(agents.parse_mention("@agent Samira Ortiz")["kind"], "research_person")

    def test_polite_words_are_stripped_from_the_target(self):
        self.assertEqual(agents.parse_mention("@agent 請幫我查 Samira Ortiz")["target"], "Samira Ortiz")
        self.assertEqual(agents.parse_mention("@research Samira Ortiz 請幫我查")["target"], "Samira Ortiz")

    def test_target_stays_on_the_first_line(self):
        parsed = agents.parse_mention("@research Samira Ortiz\nNorthwind")
        self.assertEqual(parsed["target"], "Samira Ortiz")
        self.assertIn("Northwind", parsed["ask"])

    def test_mention_is_case_insensitive(self):
        parsed = agents.parse_mention("@AGENT Samira Ortiz")
        self.assertEqual(parsed["word"], "agent")
        self.assertEqual(parsed["kind"], "research_person")
        self.assertEqual(parsed["target"], "Samira Ortiz")

    def test_target_and_ask_are_bounded(self):
        parsed = agents.parse_mention("@agent " + "a" * 300)
        self.assertEqual(len(parsed["target"]), 120)
        parsed = agents.parse_mention("@agent Samira\n" + "b" * 3000)
        self.assertLessEqual(len(parsed["ask"]), 1000)

    def test_oversized_thread_cuts_before_the_mention(self):
        text = "filler " * 800 + "@agent Samira"
        self.assertGreater(len(text), agents.MAX_BODY)
        self.assertIsNone(agents.parse_mention(text))


@unittest.skipUnless(_HAVE_COMPOSE, "features.compose address helpers unavailable")
class TestAliasRouting(unittest.TestCase):
    """The alias is a routing word only; matching it must stay strict."""

    def test_exact_alias_addresses_match(self):
        for addr in (
            "agent@example.com",
            "Agent <agent@example.com>",
            "Agent <Agent@Example.COM>",
        ):
            self.assertTrue(agents.mentions_alias(addr), addr)

    def test_longer_or_extended_addresses_do_not_match(self):
        for addr in (
            "",
            "agents@example.com",
            "agent@example.com.evil.example",
            "someone@example.com",
            "no-reply@agent.example.com",
        ):
            self.assertFalse(agents.mentions_alias(addr), addr)

    def test_one_alias_among_a_list_matches(self):
        self.assertTrue(agents.mentions_alias("Dana Lee <dana@example.com>, agent@example.com"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
