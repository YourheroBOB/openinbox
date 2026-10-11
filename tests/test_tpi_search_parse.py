"""Query parser: English / Traditional Chinese natural language and search operators."""
from __future__ import annotations

import random
import unittest
from datetime import date

import _tpi_server as srv  # noqa: F401  (sets the throwaway root before server imports)
import features.search as search

ANCHOR = date(2026, 9, 16)  # a Wednesday
PEOPLE = {
    "samira": ("Samira Ortiz", "samira@northwind.example"),
    "samira ortiz": ("Samira Ortiz", "samira@northwind.example"),
    "maya": ("Maya Singh", "maya@studio.example"),
    "王小明": ("王小明", "xiaoming@example.com"),
}


def resolver(name):
    hit = PEOPLE.get(name.strip().lower())
    return [{"name": hit[0], "email": hit[1]}] if hit else []


def parse(q, anchor=ANCHOR):
    return search.parse_query(q, anchor, resolver)


class DateTest(unittest.TestCase):
    def span(self, q):
        p = parse(q)
        return p["after"], p["before"]

    def test_english_relative(self):
        cases = {
            "last week": ("2026-09-07", "2026-09-14"),
            "this week": ("2026-09-14", "2026-09-21"),
            "today": ("2026-09-16", "2026-09-17"),
            "yesterday": ("2026-09-15", "2026-09-16"),
            "last 3 days": ("2026-09-14", "2026-09-17"),
            "in the past two weeks": ("2026-09-03", "2026-09-17"),
            "this month": ("2026-09-01", "2026-10-01"),
            "last month": ("2026-08-01", "2026-09-01"),
            "2 days ago": ("2026-09-14", "2026-09-15"),
            "on friday": ("2026-09-11", "2026-09-12"),
            "last friday": ("2026-09-11", "2026-09-12"),
            "recently": ("2026-09-10", "2026-09-17"),
        }
        for q, want in cases.items():
            self.assertEqual(self.span(q), want, q)

    def test_english_absolute(self):
        cases = {
            "in September": ("2026-09-01", "2026-10-01"),
            "Sep 15": ("2026-09-15", "2026-09-16"),
            "15 Sep 2026": ("2026-09-15", "2026-09-16"),
            "September 2025": ("2025-09-01", "2025-10-01"),
            "2026-09-15": ("2026-09-15", "2026-09-16"),
            "since Sep 15": ("2026-09-15", None),
            "after 2026-09-14": ("2026-09-14", None),
            "before 2026-09-15": (None, "2026-09-15"),
            "between Sep 14 and Sep 15": ("2026-09-14", "2026-09-16"),
            "from 2026-09-01 to 2026-09-10": ("2026-09-01", "2026-09-11"),
            "December": ("2025-12-01", "2026-01-01"),
        }
        for q, want in cases.items():
            self.assertEqual(self.span(q), want, q)

    def test_chinese(self):
        cases = {
            "上週": ("2026-09-07", "2026-09-14"),
            "本週": ("2026-09-14", "2026-09-21"),
            "今天": ("2026-09-16", "2026-09-17"),
            "昨天": ("2026-09-15", "2026-09-16"),
            "前天": ("2026-09-14", "2026-09-15"),
            "最近3天": ("2026-09-14", "2026-09-17"),
            "過去兩週": ("2026-09-03", "2026-09-17"),
            "上個月": ("2026-08-01", "2026-09-01"),
            "9月15日": ("2026-09-15", "2026-09-16"),
            "9月15日之後": ("2026-09-15", None),
            "2026-09-15之前": (None, "2026-09-15"),
            "9/14到9/15": ("2026-09-14", "2026-09-16"),
            "3天前": ("2026-09-13", "2026-09-14"),
            "上週一": ("2026-09-07", "2026-09-08"),
            "2026年8月": ("2026-08-01", "2026-09-01"),
        }
        for q, want in cases.items():
            self.assertEqual(self.span(q), want, q)

    def test_ranges_intersect(self):
        self.assertEqual(self.span("this month last week"), ("2026-09-07", "2026-09-14"))

    def test_plain_weekday_word_stays_a_keyword(self):
        p = parse("design review thursday")
        self.assertIsNone(p["after"])
        self.assertIn("thursday", p["terms"])


class OperatorTest(unittest.TestCase):
    def test_gmail_style_operators(self):
        p = parse('from:samira to:maya subject:"term sheet" after:2026-09-01 before:2026-09-15 '
                  'has:attachment is:unread category:newsletter -from:noreply account:you@example.com')
        self.assertEqual(p["from"], ["samira"])
        self.assertEqual(p["to"], ["maya"])
        self.assertEqual(p["subject"], ["term sheet"])
        self.assertEqual((p["after"], p["before"]), ("2026-09-01", "2026-09-15"))
        self.assertIs(p["has_attachment"], True)
        self.assertIs(p["unread"], True)
        self.assertEqual(p["category"], ["other"])
        self.assertEqual(p["exclude_from"], ["noreply"])
        self.assertEqual(p["account"], "you@example.com")
        self.assertEqual(p["terms"], [])

    def test_negations_and_relative_operators(self):
        p = parse("-has:attachment is:read newer_than:7d")
        self.assertIs(p["has_attachment"], False)
        self.assertIs(p["unread"], False)
        self.assertEqual(p["after"], "2026-09-10")
        self.assertEqual(parse("older_than:2d")["before"], "2026-09-15")

    def test_chinese_operator_keys(self):
        p = parse("寄件人：王小明上週的合約")
        self.assertEqual(p["from"], ["王小明"])
        self.assertEqual((p["after"], p["before"]), ("2026-09-07", "2026-09-14"))
        self.assertEqual(p["terms"], ["合約"])

    def test_unknown_operator_values_are_noted_not_fatal(self):
        p = parse("has:stars category:nope after:someday")
        self.assertEqual(len(p["notes"]), 3)


class NaturalLanguageTest(unittest.TestCase):
    def test_english_sentence(self):
        p = parse("unread emails from samira with attachments about the deck")
        self.assertEqual(p["from"], ["samira"])
        self.assertIs(p["unread"], True)
        self.assertIs(p["has_attachment"], True)
        self.assertEqual(p["terms"], ["deck"])
        self.assertEqual(p["contacts"]["samira"][0]["email"], "samira@northwind.example")

    def test_multiword_contact_and_quotes(self):
        p = parse("from Samira Ortiz term sheet")
        self.assertEqual(p["from"], ["Samira Ortiz"])
        self.assertEqual(p["terms"], ["term", "sheet"])
        p = parse('from "Samira Ortiz" "term sheet"')
        self.assertEqual(p["from"], ["Samira Ortiz"])
        self.assertEqual(p["terms"], ["term sheet"])

    def test_by_and_to_need_a_known_person(self):
        p = parse("sorted by date")
        self.assertEqual(p["from"], [])
        self.assertEqual(parse("invoices sent to maya")["to"], ["maya"])
        self.assertEqual(parse("reply to vendor")["to"], [])

    def test_chinese_sentences(self):
        p = parse("上週 Samira 寄來有附件的信")
        self.assertEqual(p["from"], ["Samira"])
        self.assertEqual((p["after"], p["before"]), ("2026-09-07", "2026-09-14"))
        self.assertIs(p["has_attachment"], True)
        self.assertEqual(p["terms"], [])

        p = parse("幫我找王小明寄來的合約")
        self.assertEqual(p["from"], ["王小明"])
        self.assertEqual(p["terms"], ["合約"])

        p = parse("寄給 Samira 的信")
        self.assertEqual(p["to"], ["Samira"])

        p = parse("未讀的電子報")
        self.assertIs(p["unread"], True)
        self.assertEqual(p["category"], ["other"])
        self.assertEqual(p["terms"], [])

        self.assertEqual(parse("需要我回的信")["category"], ["needs_you"])
        self.assertIs(parse("沒有附件的信")["has_attachment"], False)

    def test_unknown_chinese_name_without_contacts(self):
        p = search.parse_query("幫我找林大同寄來的報價單", ANCHOR, lambda name: [])
        self.assertEqual(p["from"], ["林大同"])
        self.assertEqual(p["terms"], ["報價單"])

    def test_or_groups_and_exclusions(self):
        self.assertEqual(parse("invoice or receipt")["terms"], [["invoice", "receipt"]])
        self.assertEqual(parse("receipt 或 renewal")["terms"], [["receipt", "renewal"]])
        p = parse("unsubscribe -cables")
        self.assertEqual(p["terms"], ["unsubscribe"])
        self.assertEqual(p["exclude"], ["cables"])
        self.assertEqual(parse("「合約草稿」")["terms"], ["合約草稿"])

    def test_categories(self):
        self.assertEqual(parse("important unread")["category"], ["worth_a_look"])
        self.assertEqual(parse("needs you")["category"], ["needs_you"])
        self.assertEqual(parse("行程")["category"], ["upcoming"])


class CanonicalTest(unittest.TestCase):
    KEYS = ("terms", "exclude", "from", "exclude_from", "to", "subject", "after", "before",
            "has_attachment", "unread", "category", "exclude_category", "account")

    def test_round_trip(self):
        for q in ("unread emails from samira with attachments about the deck", "上週 Samira 寄來有附件的信",
                  'from "Samira Ortiz" "term sheet" -cables', "invoice or receipt since Sep 1",
                  "寄件人：王小明上週的合約", "-has:attachment is:read -category:other account:you@example.com",
                  "需要我回的信 9/14到9/15"):
            p = parse(q)
            again = parse(p["canonical"])
            for k in self.KEYS:
                self.assertEqual(again[k], p[k], f"{q!r} -> {p['canonical']!r}: {k}")

    def test_empty(self):
        p = parse("   ")
        self.assertEqual(p["canonical"], "")
        self.assertEqual(search.explain(p), [])

    def test_explain_both_languages(self):
        p = parse("上週 Samira 寄來有附件的未讀信 -cables")
        zh = " ".join(c["text"] for c in search.explain(p, "zh-Hant"))
        en = " ".join(c["text"] for c in search.explain(p, "en"))
        for word in ("寄件人：Samira", "2026-09-07 → 2026-09-13", "有附件", "未讀", "排除：cables"):
            self.assertIn(word, zh)
        for word in ("From: Samira", "2026-09-07 → 2026-09-13", "Has attachment", "Unread", "Without: cables"):
            self.assertIn(word, en)
        self.assertIn("samira@northwind.example", zh)

    def test_never_crashes(self):
        rnd = random.Random(7)
        alphabet = list("abc xyz:\"'-()0123456789/年月日週上本前後之寄來的附件未讀或OR「」*%_\\")
        for _ in range(300):
            q = "".join(rnd.choice(alphabet) for _ in range(rnd.randint(0, 40)))
            p = parse(q)
            self.assertIsInstance(p["canonical"], str)


if __name__ == "__main__":
    unittest.main()
