"""核心函式的性質式與表格驅動不變量測試。

只使用 Python 標準庫；不連線、不接觸正式服務。檔案系統測試一律在暫存資料夾中執行。
"""
from __future__ import annotations

import json
import random
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_ROOT = REPO_ROOT / "server"
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from features import agents  # noqa: E402
import second_brain  # noqa: E402


class AgentMentionPropertyTests(unittest.TestCase):
    """parse_mention 與路由 helper 的純函式及邊界不變量。"""

    MENTION_CASES = (
        ("agent", "Sample Person", "research_person"),
        ("research", "Sample Person", "research_person"),
        ("research-company", "Example Company", "research_company"),
        ("prep", "Weekly planning", "meeting_prep"),
        ("meeting", "Weekly planning", "meeting_prep"),
    )

    def test_parse_mention_is_deterministic_bounded_and_preserves_target(self):
        prefixes = ("", "Context before\n", "Please handle this\n")
        suffixes = ("", "\nTrailing context", " -- end")

        for word, target, expected_kind in self.MENTION_CASES:
            for prefix in prefixes:
                for suffix in suffixes:
                    text = f"{prefix}@{word} {target}{suffix}"
                    with self.subTest(word=word, prefix=prefix, suffix=suffix):
                        parsed = agents.parse_mention(text)

                        self.assertIsNotNone(parsed)
                        self.assertEqual(parsed["kind"], expected_kind)
                        self.assertEqual(parsed["word"], word)
                        self.assertIn(target, parsed["target"])
                        self.assertIn(target, parsed["ask"])
                        self.assertNotIn(f"@{word}", parsed["ask"])
                        self.assertLessEqual(len(parsed["target"]), 120)
                        self.assertLessEqual(len(parsed["ask"]), 1000)
                        self.assertEqual(parsed, agents.parse_mention(text))

    def test_generic_agent_kind_is_driven_by_markers_in_the_request(self):
        cases = (
            ("Sample Person", "research_person"),
            ("Example Company", "research_company"),
            ("Weekly meeting agenda", "meeting_prep"),
        )

        for target, expected_kind in cases:
            with self.subTest(target=target):
                parsed = agents.parse_mention(f"@agent {target}")
                self.assertIsNotNone(parsed)
                self.assertEqual(parsed["kind"], expected_kind)

    def test_mention_recognition_respects_token_and_length_boundaries(self):
        for text in (
            "",
            "plain request",
            "someone@example.com",
            "@unknown Sample Person",
            "@researcher Sample Person",
            "x@agent Sample Person",
            "mail.@agent Sample Person",
        ):
            with self.subTest(text=text):
                self.assertIsNone(agents.parse_mention(text))

        first_wins = agents.parse_mention(
            "@research Sample Person\n@prep Weekly planning"
        )
        self.assertIsNotNone(first_wins)
        self.assertEqual(first_wins["word"], "research")
        self.assertEqual(first_wins["kind"], "research_person")

        marker = "@agent Sample Person"
        at_limit = " " * (agents.MAX_BODY - len(marker)) + marker
        after_limit = " " * agents.MAX_BODY + marker

        parsed_at_limit = agents.parse_mention(at_limit)
        self.assertIsNotNone(parsed_at_limit)
        self.assertEqual(parsed_at_limit["word"], "agent")
        self.assertIsNone(agents.parse_mention(after_limit))

    def test_agent_alias_matching_is_exact(self):
        cases = (
            ("agent@example.com", True),
            ("  AGENT@EXAMPLE.COM  ", True),
            ("Routing Alias <agent@example.com>", True),
            ("one@example.com, agent@example.com", True),
            ("agent@example.com, other@example.com", True),
            ("notagent@example.com", False),
            ("agent@example.com.evil", False),
            ("agent@sub.example.com", False),
            ("xagent@example.com", False),
        )

        for address, expected in cases:
            with self.subTest(address=address):
                self.assertEqual(agents.mentions_alias(address), expected)

    def test_agent_slug_is_canonical_idempotent_and_bounded(self):
        fixed = (
            "",
            " ",
            "Sample Person",
            "UPPER CASE",
            "a" * 39,
            "a" * 41,
            "a" * 47 + "-tail",
            "中文",
            "a--b",
            "--a--",
            "symbols / \\ @ _",
        )
        rng = random.Random(20260101)
        alphabet = "abcXYZ09 -_/\\@\u4e00"
        generated = [
            "".join(rng.choice(alphabet) for _ in range(rng.randrange(0, 80)))
            for _ in range(256)
        ]

        for raw in fixed + tuple(generated):
            with self.subTest(raw=raw):
                slug = agents._slug(raw)
                self.assertTrue(slug)
                self.assertLessEqual(len(slug), 40)
                self.assertRegex(slug, r"^[a-z0-9][a-z0-9-]*$")
                self.assertFalse(slug.endswith("-"))
                self.assertEqual(slug, slug.lower())
                self.assertEqual(agents._slug(slug), slug)
                self.assertEqual(agents._slug(raw.lower()), slug)

    def test_deliverable_id_boundaries_are_table_driven(self):
        valid = (
            "abc",
            # 既有 ID_RE 允許尾端連字號；它仍是單一且安全的路徑片段。
            "abc-",
            "a12",
            "a-b-c",
            "a" * 81,
        )
        invalid = (
            "",
            "a",
            "ab",
            "-abc",
            "ABC",
            "a_b",
            "a/b",
            "../safe",
            "a..b",
            "a b",
            "a" * 82,
        )

        for did in valid:
            with self.subTest(did=did):
                self.assertTrue(agents._valid_id(did))
        for did in invalid:
            with self.subTest(did=did):
                self.assertFalse(agents._valid_id(did))


@contextmanager
def isolated_second_brain(root: Path):
    """將 Second Brain 的所有寫入導向暫存根目錄。"""
    vault = root / "vault"
    cards = vault / "cards"
    index = vault / "index.json"
    vault.mkdir(parents=True, exist_ok=True)
    index.write_text(
        json.dumps({"updated_at": "2026-01-01T00:00:00+00:00", "count": 0, "cards": []}),
        encoding="utf-8",
    )

    with mock.patch.object(second_brain, "ROOT", root), \
            mock.patch.object(second_brain, "CARDS", cards), \
            mock.patch.object(second_brain, "INDEX", index):
        yield cards, index


class SecondBrainPropertyTests(unittest.TestCase):
    """Second Brain 卡片儲存與搜尋的往返、冪等及單調不變量。"""

    def test_add_card_round_trip_is_idempotent_and_updates_in_place(self):
        with tempfile.TemporaryDirectory(prefix="openinbox-fmb-prop-") as tmp:
            root = Path(tmp)
            with isolated_second_brain(root) as (cards, index):
                first = second_brain.add_card(
                    "Repeatable Card", "stable body"
                )
                second = second_brain.add_card(
                    "Repeatable Card", "stable body"
                )

                self.assertEqual(first["id"], second["id"])
                self.assertEqual(first["body"], second["body"])

                loaded = second_brain.load()
                self.assertEqual(loaded["count"], 1)
                self.assertEqual(len(loaded["cards"]), 1)
                self.assertEqual(loaded["cards"][0]["id"], first["id"])
                self.assertEqual(loaded["cards"][0]["body"], "stable body")

                on_disk = json.loads(index.read_text(encoding="utf-8"))
                self.assertEqual(on_disk["count"], 1)
                self.assertEqual(len(on_disk["cards"]), 1)
                self.assertEqual(on_disk["cards"][0]["id"], first["id"])
                self.assertEqual(on_disk["cards"][0]["body"], "stable body")
                self.assertEqual(len(list(cards.glob("*.md"))), 1)

                updated = second_brain.add_card(
                    "Repeatable Card", "updated body"
                )
                loaded = second_brain.load()
                self.assertEqual(updated["id"], first["id"])
                self.assertEqual(loaded["count"], 1)
                self.assertEqual(len(loaded["cards"]), 1)
                self.assertEqual(loaded["cards"][0]["body"], "updated body")
                self.assertEqual(len(list(cards.glob("*.md"))), 1)

    def test_search_is_case_insensitive_complete_and_prefix_monotone(self):
        corpus = [
            {
                "id": "alpha-card",
                "title": "Alpha Needle",
                "body": "Bravo details",
                "category": "projects",
            },
            {
                "id": "bravo-card",
                "title": "Charlie",
                "body": "Delta summary",
                "category": "notes",
            },
            {
                "id": "charlie-card",
                "title": "Echo",
                "body": "Foxtrot",
                "category": "projects",
            },
        ]

        with tempfile.TemporaryDirectory(prefix="openinbox-fmb-prop-") as tmp:
            root = Path(tmp)
            with isolated_second_brain(root) as (_cards, index):
                index.write_text(
                    json.dumps(
                        {
                            "updated_at": "2026-01-01T00:00:00+00:00",
                            "count": len(corpus),
                            "cards": corpus,
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )

                cases = (
                    ("alpha", {"alpha-card"}),
                    ("BRAVO", {"alpha-card"}),
                    ("projects", {"alpha-card", "charlie-card"}),
                    ("needle", {"alpha-card"}),
                    ("missing", set()),
                    ("", {"alpha-card", "bravo-card", "charlie-card"}),
                )

                for query, expected in cases:
                    with self.subTest(query=query):
                        results = second_brain.search(query)
                        self.assertEqual(
                            {card["id"] for card in results}, expected
                        )
                        for card in results:
                            blob = (
                                f"{card.get('title') or ''} "
                                f"{card.get('body') or ''} "
                                f"{card.get('category') or ''}"
                            ).lower()
                            self.assertIn(query.lower(), blob)

                def result_ids(query: str) -> set[str]:
                    return {card["id"] for card in second_brain.search(query)}

                for prefix in ("a", "alpha", "bravo", "project", "e"):
                    with self.subTest(prefix=prefix):
                        self.assertTrue(
                            result_ids(prefix + "x").issubset(result_ids(prefix))
                        )


if __name__ == "__main__":
    unittest.main()
