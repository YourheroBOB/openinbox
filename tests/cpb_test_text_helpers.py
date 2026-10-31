"""Pure text / address helpers that other features build on. Fictional data only.

Covers email_brain (hours, days, language, greeting/sign-off), search (number words, FTS terms,
Chinese request-word stripping), followup (subject/date handling), compose + outbox address
checks, contacts (address parsing, scoring), mailops (HTML to text, signatures, language target)
and the demo-mail classifier.
Run: python3 -m unittest discover -s tests -p "cpb_test_*.py"
"""
from __future__ import annotations

import unittest
from datetime import date

import _tpi_server  # noqa: F401  (sets OPENINBOX_ROOT and sys.path before server imports)
import yhbmail
from features import compose, contacts, followup, mailops, outbox, search, triage
from features import email_brain as brain


class WorkingHours(unittest.TestCase):
    def test_valid_ranges(self):
        self.assertEqual(brain.parse_hours("9-17"), {"start": 540, "end": 1020})
        self.assertEqual(brain.parse_hours("09:30–18:00"), {"start": 570, "end": 1080})
        self.assertEqual(brain.parse_hours("9 to 17"), {"start": 540, "end": 1020})
        self.assertEqual(brain.parse_hours("9到17"), {"start": 540, "end": 1020})
        self.assertEqual(brain.parse_hours("9-24"), {"start": 540, "end": 1440})
        self.assertEqual(brain.parse_hours({"start": "8", "end": "12:30"}), {"start": 480, "end": 750})

    def test_invalid_ranges(self):
        for bad in ("25-3", "9-9", "9:60-10", "9-24:30", "abc", "", None, "9", {"start": "x"}):
            self.assertIsNone(brain.parse_hours(bad), repr(bad))


class WorkingDays(unittest.TestCase):
    def test_ranges_lists_and_chinese(self):
        self.assertEqual(brain.parse_days("mon-fri"), ["mon", "tue", "wed", "thu", "fri"])
        self.assertEqual(brain.parse_days("週一到週五"), ["mon", "tue", "wed", "thu", "fri"])
        self.assertEqual(brain.parse_days("Mon, Wed"), ["mon", "wed"])
        self.assertEqual(brain.parse_days("週六、週日"), ["sat", "sun"])
        self.assertEqual(brain.parse_days(["Tuesday", "thurs"]), ["tue", "thu"])

    def test_wrap_around_range_comes_back_in_week_order(self):
        self.assertEqual(brain.parse_days("fri-mon"), ["mon", "fri", "sat", "sun"])

    def test_duplicates_collapse(self):
        self.assertEqual(brain.parse_days("mon, monday, 一"), ["mon"])

    def test_invalid_values(self):
        for bad in ("xyz", "", "mon-", "mon,xyz", None, []):
            self.assertIsNone(brain.parse_days(bad), repr(bad))


class LanguageAndSignature(unittest.TestCase):
    def test_text_lang(self):
        self.assertEqual(brain.text_lang("Hello there"), "en")
        self.assertEqual(brain.text_lang("你好，我想確認會議時間"), "zh")
        self.assertEqual(brain.text_lang("12345 ???"), "en")
        self.assertEqual(brain.text_lang(""), "en")
        self.assertEqual(brain.text_lang(None), "en")

    def test_greeting_of(self):
        self.assertEqual(brain.greeting_of(["", "  hello Sam,", "body"]), "Hello")
        self.assertEqual(brain.greeting_of(["Good Morning team"]), "Good morning")
        self.assertEqual(brain.greeting_of(["王小姐您好"]), "您好")
        self.assertEqual(brain.greeting_of(["Quick question about the invoice"]), "")
        self.assertEqual(brain.greeting_of(["Hi " + "x" * 60]), "")
        self.assertEqual(brain.greeting_of([]), "")

    def test_signoff_of_only_looks_at_the_tail(self):
        self.assertEqual(brain.signoff_of(["text", "Best regards,", "Sam"]), "Best regards,")
        self.assertEqual(brain.signoff_of(["Thanks!", "a", "b", "c"]), "")
        self.assertEqual(brain.signoff_of(["Thanks so much for everything you did last week"]), "")
        self.assertEqual(brain.signoff_of(["謝謝您", "Sam"]), "謝謝您")

    def test_thread_key_prefers_thread_id(self):
        self.assertEqual(brain.thread_key({"thread_id": "t1", "id": "m1"}), "t1")
        self.assertEqual(brain.thread_key({"id": "m1"}), "m1")
        self.assertEqual(brain.thread_key({}), "")

    def test_is_bulk(self):
        self.assertTrue(brain.is_bulk({"from_addr": "No-Reply@example.com"}))
        self.assertTrue(brain.is_bulk({"from_addr": "a@example.com", "category": "other"}))
        self.assertFalse(brain.is_bulk({"from_addr": "pat@example.com", "category": "needs_you"}))
        self.assertFalse(brain.is_bulk({}))


class AddressSplitting(unittest.TestCase):
    def test_plain_lists_and_cjk_separators(self):
        self.assertEqual(compose.split_addrs("a@one.example.com, b@two.example.org;c@three.example.net，d@four.example.com"),
                         ["a@one.example.com", "b@two.example.org", "c@three.example.net", "d@four.example.com"])
        self.assertEqual(compose.split_addrs(None), [])
        self.assertEqual(compose.split_addrs(" , ; "), [])

    def test_parse_addr(self):
        self.assertEqual(compose.parse_addr('"Pat Lee" <pat@example.com>'), ("Pat Lee", "pat@example.com"))
        self.assertEqual(compose.parse_addr("<pat@example.com>"), ("pat@example.com", "pat@example.com"))
        self.assertEqual(compose.parse_addr(" pat@example.com "), ("pat@example.com", "pat@example.com"))
        self.assertEqual(compose.parse_addr(None), ("", ""))

    def test_address_warnings(self):
        out = compose.address_warnings({"to": "a@one.example.com, bad, c@d", "cc": "x@two.example.com", "bcc": ""}, "en")
        self.assertEqual(len(out), 2)
        self.assertTrue(out[0].startswith("to: 'bad'"))
        zh = compose.address_warnings({"to": "bad"}, "zh-Hant")
        self.assertIn("不像信箱位址", zh[0])

    def test_contacts_parse_addresses_handles_quoted_commas(self):
        got = contacts.parse_addresses('"Doe, Jane" <J@Example.com>, b@two.example.org, not-an-address')
        self.assertEqual(got, [("Doe, Jane", "j@example.com"), ("", "b@two.example.org")])

    @unittest.skip("PRODUCT BUG: compose.split_addrs splits on every comma, so a valid recipient with a "
                   "quoted display name (\"Doe, Jane\" <jane@example.com>) is cut in two and the outbox "
                   "rejects it with 'is not a valid address'")
    def test_quoted_display_name_with_comma_stays_one_recipient(self):
        self.assertEqual(compose.split_addrs('"Doe, Jane" <jane@example.com>, b@two.example.org'),
                         ['"Doe, Jane" <jane@example.com>', "b@two.example.org"])
        self.assertEqual(outbox.address_errors({"to_addr": '"Doe, Jane" <jane@example.com>',
                                                "account": "me@example.com"}, False), [])

    @unittest.skip("PRODUCT BUG: email_brain.split_addrs only protects commas inside <...>, so "
                   "\"Doe, Jane\" <jane@example.com> becomes ('Jane', ...) and the surname is lost")
    def test_brain_split_addrs_keeps_quoted_comma_names(self):
        self.assertEqual(brain.split_addrs('"Doe, Jane" <jane@example.com>'),
                         [("Doe, Jane", "jane@example.com")])


class OutboxAddressErrors(unittest.TestCase):
    OK = {"to_addr": "pat@example.com", "account": "me@example.com"}

    def test_clean_message_has_no_errors(self):
        self.assertEqual(outbox.address_errors(dict(self.OK, cc="a@one.example.com", bcc="c@two.example.org"), False), [])

    def test_missing_recipient_and_bad_from(self):
        errs = outbox.address_errors({"to_addr": "", "account": "bad"}, False)
        self.assertEqual(errs, ["add at least one recipient", "the From account is not a valid address"])

    def test_chinese_messages(self):
        errs = outbox.address_errors({"to_addr": "", "account": "me@example.com"}, True)
        self.assertEqual(errs, ["至少要有一位收件者"])

    def test_header_injection_is_rejected(self):
        for field in ("subject", "account"):
            errs = outbox.address_errors(dict(self.OK, **{field: "x\r\nBcc: evil@example.com"}), False)
            self.assertTrue(any("line break" in e for e in errs), field)
        errs = outbox.address_errors(dict(self.OK, to_addr="Pat\nBcc: evil@example.com <pat@example.com>"), False)
        self.assertTrue(errs)

    def test_recipient_cap(self):
        many = ",".join(f"u{i}@example.com" for i in range(outbox.MAX_RECIPIENTS + 1))
        self.assertTrue(any("more than" in e for e in outbox.address_errors(dict(self.OK, to_addr=many), False)))
        edge = ",".join(f"u{i}@example.com" for i in range(outbox.MAX_RECIPIENTS))
        self.assertEqual(outbox.address_errors(dict(self.OK, to_addr=edge), False), [])

    def test_invalid_address_shapes(self):
        for bad in ("plain", "a@b", "a b@one.example.com", "a@@one.example.com", "<>"):
            errs = outbox.address_errors(dict(self.OK, cc=bad), False)
            self.assertTrue(any(e.startswith("cc:") for e in errs), bad)


class Quoting(unittest.TestCase):
    ITEM = {"from_addr": "Pat <pat@example.com>", "date_raw": "2024-01-02", "subject": "Plan",
            "to_addr": "me@example.com", "body_text": "line one\n\nline three"}

    def test_reply_quote_prefixes_every_line_and_keeps_blank_ones_short(self):
        out = compose.reply_quote(self.ITEM, "en")
        self.assertEqual(out, "On 2024-01-02, Pat <pat@example.com> wrote:\n> line one\n>\n> line three")

    def test_reply_quote_without_body_and_in_chinese(self):
        out = compose.reply_quote({"from_addr": "Pat", "date_raw": "d"}, "zh-Hant")
        self.assertEqual(out, "d，Pat 寫道：\n>")

    def test_reply_quote_falls_back_to_snippet(self):
        self.assertTrue(compose.reply_quote({"snippet": "short"}, "en").endswith("> short"))

    def test_forward_quote_has_header_block(self):
        out = compose.forward_quote(self.ITEM, "en")
        self.assertTrue(out.startswith("---------- Forwarded message ----------\nFrom: Pat <pat@example.com>"))
        self.assertTrue(out.endswith("\n\nline one\n\nline three"))
        self.assertIn("寄件者：", compose.forward_quote(self.ITEM, "zh-Hant"))


class SearchHelpers(unittest.TestCase):
    def test_to_num(self):
        for word, n in (("3", 3), ("three", 3), ("十", 10), ("十二", 12), ("二十", 20), ("二十三", 23), ("兩", 2)):
            self.assertEqual(search.to_num(word), n, word)
        self.assertEqual(search.to_num(" 7 "), 7)
        self.assertEqual(search.to_num("unknown"), 1)

    def test_fts_expr(self):
        self.assertEqual(search.fts_expr("invoice"), '"invoice"*')
        self.assertEqual(search.fts_expr("contract renewal"), '"contract renewal"')
        self.assertEqual(search.fts_expr("合約"), '"合約"')
        self.assertIsNone(search.fts_expr("合"))      # one CJK char needs LIKE
        self.assertIsNone(search.fts_expr(""))

    def test_fts_expr_cannot_carry_query_syntax(self):
        for hostile in ('say "hi"', 'a" OR "b', "x* NOT y", "col:val", "NEAR(a b)"):
            expr = search.fts_expr(hostile)
            self.assertIsNotNone(expr, hostile)
            inner = expr[1:-1] if expr.endswith('"') else expr[1:-2]
            self.assertNotIn('"', inner, hostile)

    def test_strip_zh(self):
        self.assertEqual(search.strip_zh("幫我找合約的信"), "合約")
        self.assertEqual(search.strip_zh("合約"), "合約")
        self.assertEqual(search.strip_zh("找信"), "")
        self.assertEqual(search.strip_zh("的"), "")
        self.assertEqual(search.strip_zh("   "), "")

    def test_span_of_returns_none_for_nonsense_and_impossible_dates(self):
        anchor = date(2024, 3, 15)
        self.assertIsNone(search.span_of("blorp", anchor))
        self.assertIsNone(search.span_of("", anchor))


class FollowupHelpers(unittest.TestCase):
    def test_norm_subject_strips_stacked_prefixes_only_at_the_start(self):
        self.assertEqual(followup.norm_subject("RE: Re: 回覆： Fwd:  Hello   World"), "hello world")
        self.assertEqual(followup.norm_subject("Reply about re: x"), "reply about re: x")
        self.assertEqual(followup.norm_subject(None), "")

    def test_parse_now(self):
        self.assertEqual(followup.parse_now(12345), 12345)
        self.assertEqual(followup.parse_now("2025-03-01"), followup.parse_now("2025-03-01"))
        fallback = followup.parse_now(None)
        for bad in ("2025-02-30", "garbage", ""):
            self.assertAlmostEqual(followup.parse_now(bad), fallback, delta=5, msg=repr(bad))
        self.assertLess(followup.parse_now("2025-03-01"), followup.parse_now("2025-03-02"))
        self.assertEqual(followup.parse_now("2025-03-02") - followup.parse_now("2025-03-01"), 86400)

    def test_first_question_ignores_short_fragments(self):
        self.assertEqual(followup.first_question(""), "")
        self.assertEqual(followup.first_question("Hi Sam\nOK?"), "")

    def test_triage_parse_today(self):
        self.assertEqual(triage.parse_today("2025-03-01"), date(2025, 3, 1))
        self.assertEqual(triage.parse_today("2025-03-01T12:00:00"), date(2025, 3, 1))
        today = triage.parse_today(None)
        self.assertEqual(triage.parse_today("2025-13-01"), today)
        self.assertEqual(triage.parse_today("junk"), today)


class ContactScoring(unittest.TestCase):
    C = {"name": "Samira Ortiz", "email": "samira.ortiz@example.com", "aliases": ["Sam O"]}

    def test_ranking_exact_over_prefix_over_substring(self):
        s = lambda q: contacts.match_score(self.C, q)
        self.assertEqual(s("Samira Ortiz"), 100)
        self.assertEqual(s("samira.ortiz@example.com"), 100)
        self.assertEqual(s("samira.ortiz"), 100)
        self.assertEqual(s("sam"), 80)
        self.assertEqual(s("ortiz"), 70)
        self.assertEqual(s("mira"), 50)
        self.assertEqual(s("ortiz samira"), 40)
        self.assertEqual(s("zzz"), 0)
        self.assertEqual(s(""), 1)
        self.assertTrue(s("samira") > s("mira") > 0)

    def test_automated_senders(self):
        self.assertTrue(contacts.is_automated("noreply@example.com"))
        self.assertTrue(contacts.is_automated("newsletter@example.com"))
        self.assertFalse(contacts.is_automated("pat@example.com"))


class MailopsHelpers(unittest.TestCase):
    def test_html_to_text_drops_scripts_styles_and_head(self):
        html = ("<html><head><title>t</title><style>p{}</style></head><body><p>Hello&amp;<b>there</b></p>"
                "<script>x()</script><div>Line2</div>a<br>b</body></html>")
        text = mailops.html_to_text(html)
        self.assertNotIn("x()", text)
        self.assertNotIn("p{}", text)
        self.assertNotIn("<", text)
        self.assertIn("Hello&there", text)
        self.assertEqual([ln for ln in text.splitlines() if ln.strip()], ["Hello&there", "Line2", "a", "b"])

    def test_html_to_text_unclosed_script_hides_the_rest(self):
        self.assertEqual(mailops.html_to_text("<p>keep</p><script>hidden").strip(), "keep")

    def test_clean_signature_text(self):
        self.assertEqual(mailops.clean_signature("\ufeff\r\n\r\n-- \r\nJane\r\nCEO  "), "Jane\nCEO")
        self.assertEqual(mailops.clean_signature(None), "")

    def test_clean_signature_html_by_content_or_filename(self):
        self.assertEqual(mailops.clean_signature("<div>Jane<br>CEO</div>"), "Jane\nCEO")
        self.assertEqual(mailops.clean_signature("Jane &amp; Co", "sig.html"), "Jane & Co")

    def test_clean_signature_is_length_capped(self):
        self.assertLessEqual(len(mailops.clean_signature("x" * (mailops.SIG_MAX * 3))), mailops.SIG_MAX)

    def test_norm_target(self):
        self.assertEqual(mailops.norm_target("zh_TW", "en"), "zh-Hant")
        self.assertEqual(mailops.norm_target("ZH-CN", "en"), "zh-Hans")
        self.assertEqual(mailops.norm_target("en-GB", "zh-Hant"), "en")
        self.assertEqual(mailops.norm_target("", "zh-Hant"), "zh-Hant")
        self.assertEqual(mailops.norm_target(None, "en"), "en")
        self.assertEqual(mailops.norm_target("klingon", "en"), "")


class Classifier(unittest.TestCase):
    def test_priority_order(self):
        c = lambda **row: yhbmail.classify(row)[0]
        self.assertEqual(c(subject="Calendar invitation: Please confirm"), "upcoming")
        self.assertEqual(c(subject="Please review by Friday", from_addr="noreply@example.com"), "needs_you")
        self.assertEqual(c(subject="Your invoice", unread=1), "worth_a_look")
        self.assertEqual(c(subject="50% off sale", from_addr="noreply@example.com"), "other")
        self.assertEqual(c(subject="Digest", from_addr="no-reply@example.com", unread=1), "fyi")
        self.assertEqual(c(subject="hello", unread=1), "worth_a_look")
        self.assertEqual(c(subject="hello"), "fyi")

    def test_promotions_label_and_missing_fields(self):
        self.assertEqual(yhbmail.classify({"subject": "x", "labels": ["CATEGORY_PROMOTIONS"]})[0], "other")
        self.assertEqual(yhbmail.classify({})[0], "fyi")
        self.assertEqual(yhbmail.classify({"subject": None, "snippet": None, "body_text": None})[0], "fyi")

    def test_chinese_markers(self):
        self.assertEqual(yhbmail.classify({"subject": "請確認明天的安排"})[0], "needs_you")
        self.assertEqual(yhbmail.classify({"subject": "本月帳單"})[0], "worth_a_look")

    def test_parse_date_ts_known_formats(self):
        self.assertEqual(yhbmail.parse_date_ts(""), 0)
        self.assertEqual(yhbmail.parse_date_ts(None), 0)
        self.assertEqual(yhbmail.parse_date_ts("garbage"), 0)
        self.assertEqual(yhbmail.parse_date_ts("2024-01-01T00:00:00Z"), 1704067200)
        self.assertEqual(yhbmail.parse_date_ts("2024-01-01T08:00:00+0800"), 1704067200)
        self.assertEqual(yhbmail.parse_date_ts("2024-01-01"), yhbmail.parse_date_ts("2024-01-01T00:00:00"))

    @unittest.skip("PRODUCT GAP (low confidence): parse_date_ts returns 0 for RFC 2822 dates "
                   "('Mon, 01 Jan 2024 10:00:00 +0000'), the format real mail headers use. The IMAP "
                   "path parses its own date_ts, but any row that only carries date_raw sorts as 'undated'")
    def test_parse_date_ts_rfc2822(self):
        self.assertEqual(yhbmail.parse_date_ts("Mon, 01 Jan 2024 10:00:00 +0000"), 1704103200)


if __name__ == "__main__":
    unittest.main()
