"""Rule conditions, rule validation limits, MCP argument validation and the same-origin guard.

These call the pure functions directly (no HTTP, no database writes). Fictional data only.
Run: python3 -m unittest discover -s tests -p "cpb_test_*.py"
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace

import _tpi_server  # noqa: F401  (sets OPENINBOX_ROOT and sys.path before server imports)
import mcp_server as M
from features import _origin, rules

NOW = 1_700_000_000


def ctx(**kw) -> dict:
    return {"marks": {}, "now_ts": NOW, "replied": set(), **kw}


def row(**kw) -> dict:
    base = {"id": "m1", "from_addr": "Pat Lee <pat@example.com>", "to_addr": "me@example.com",
            "subject": "Invoice 42", "snippet": "snip", "body_text": "Please pay by Friday.",
            "account": "me@example.com", "category": "needs_you", "unread": 1, "labels": ["Work"],
            "date_ts": NOW - 3 * 86400}
    base.update(kw)
    return base


def hit(r: dict, field: str, op: str, value, **c) -> bool:
    return rules.test_condition(r, {"field": field, "op": op, "value": value}, ctx(**c))


class StringOps(unittest.TestCase):
    def test_contains_is_case_insensitive_and_negatable(self):
        self.assertTrue(hit(row(), "subject", "contains", "INVOICE"))
        self.assertFalse(hit(row(), "subject", "contains", "receipt"))
        self.assertTrue(hit(row(), "subject", "not_contains", "receipt"))

    def test_equals_ignores_surrounding_space_and_case(self):
        self.assertTrue(hit(row(subject="  Invoice 42 "), "subject", "equals", "invoice 42"))
        self.assertTrue(hit(row(), "subject", "not_equals", "invoice"))

    def test_starts_and_ends_with(self):
        self.assertTrue(hit(row(), "subject", "starts_with", "inv"))
        self.assertFalse(hit(row(), "subject", "starts_with", "42"))
        self.assertTrue(hit(row(subject="Invoice 42  "), "subject", "ends_with", "42"))

    def test_in_and_not_in(self):
        self.assertTrue(hit(row(), "category", "in", ["fyi", " Needs_You "]))
        self.assertFalse(hit(row(), "category", "in", ["fyi"]))
        self.assertTrue(hit(row(), "category", "not_in", ["fyi", "other"]))

    def test_regex_is_case_insensitive_search(self):
        self.assertTrue(hit(row(), "subject", "regex", r"invoice\s+\d+"))
        self.assertFalse(hit(row(), "subject", "regex", r"^\d+"))

    def test_from_matches_display_name_and_address(self):
        self.assertTrue(hit(row(), "from", "contains", "pat lee"))
        self.assertTrue(hit(row(), "from", "contains", "@example.com"))

    def test_missing_fields_behave_like_empty_text(self):
        bare = {"id": "x"}
        self.assertFalse(hit(bare, "subject", "contains", "a"))
        self.assertTrue(hit(bare, "subject", "not_contains", "a"))
        self.assertTrue(hit(bare, "subject", "equals", ""))

    def test_body_falls_back_to_snippet_and_text_joins_all(self):
        self.assertTrue(hit(row(body_text=""), "body", "contains", "snip"))
        self.assertTrue(hit(row(), "text", "contains", "pay by"))
        self.assertTrue(hit(row(), "text", "contains", "invoice 42"))


class OtherTypes(unittest.TestCase):
    def test_bool_fields_use_identity_with_the_wanted_bool(self):
        self.assertTrue(hit(row(unread=1), "unread", "is", True))
        self.assertTrue(hit(row(unread=0), "unread", "is", False))
        self.assertFalse(hit(row(unread=None), "unread", "is", True))

    def test_replied_uses_the_precomputed_set(self):
        self.assertTrue(hit(row(), "replied", "is", True, replied={"m1"}))
        self.assertTrue(hit(row(), "replied", "is", False, replied={"other"}))

    def test_age_days_boundaries(self):
        r = row(date_ts=NOW - 3 * 86400)
        self.assertTrue(hit(r, "age_days", "gte", 3))
        self.assertTrue(hit(r, "age_days", "lte", 3))
        self.assertFalse(hit(r, "age_days", "gt", 3))
        self.assertFalse(hit(r, "age_days", "lt", 3))
        self.assertTrue(hit(r, "age_days", "equals", 3))

    def test_undated_mail_has_age_zero(self):
        self.assertTrue(hit(row(date_ts=0), "age_days", "equals", 0))
        self.assertTrue(hit(row(date_ts=None), "age_days", "lt", 1))

    def test_label_combines_mail_labels_and_rule_marks(self):
        marks = {"m1": {"labels": ["Receipts"], "archived": False}}
        self.assertTrue(hit(row(), "label", "contains", "work", marks=marks))
        self.assertTrue(hit(row(), "label", "contains", "RECEIPTS", marks=marks))
        self.assertTrue(hit(row(), "label", "not_contains", "Receipts"))


class MatchLogic(unittest.TestCase):
    CONDS = [{"field": "subject", "op": "contains", "value": "invoice"},
             {"field": "unread", "op": "is", "value": False}]

    def test_all_vs_any(self):
        self.assertFalse(rules.matches(row(), {"match": "all", "conditions": self.CONDS}, ctx()))
        self.assertTrue(rules.matches(row(), {"match": "any", "conditions": self.CONDS}, ctx()))

    def test_empty_conditions_never_match(self):
        for mode in ("all", "any"):
            self.assertFalse(rules.matches(row(), {"match": mode, "conditions": []}, ctx()))


class ActionHelpers(unittest.TestCase):
    def test_action_key_is_stable_and_case_folded(self):
        self.assertEqual(rules.action_key({"type": "label", "label": "Receipts"}), "label:receipts")
        self.assertEqual(rules.action_key({"type": "task", "action": "follow_up"}), "task:follow_up")
        self.assertEqual(rules.action_key({"type": "archive"}), "archive")

    def test_fill_template(self):
        r = row(from_addr='"Pat Lee" <pat@example.com>', date_raw="2024-05-06 10:00")
        out = rules.fill_template("Hi {first_name} ({sender}), re {subject} on {date}. {tbd} {unknown}", r, "en")
        self.assertEqual(out, "Hi Pat (Pat Lee), re Invoice 42 on 2024-05-06. [TBD] {unknown}")
        self.assertIn("[待填]", rules.fill_template("{tbd}", r, "zh-Hant"))

    def test_fill_template_with_bare_address_sender(self):
        out = rules.fill_template("{sender}", row(from_addr="pat@example.com"), "en")
        self.assertEqual(out, "pat@example.com")

    def test_check_action_mark_read_on_read_mail_is_already_done(self):
        self.assertEqual(rules.check_action(row(unread=0), {"type": "mark_read"})[0], "already")
        self.assertEqual(rules.check_action(row(unread=1), {"type": "mark_read"})[0], "planned")

    def test_noreply_senders_get_no_draft(self):
        status, why = rules.check_action(row(from_addr="No-Reply <noreply@example.com>"), {"type": "draft_reply"})
        self.assertEqual(status, "skipped")
        self.assertIn("no-reply", why)

    def test_template_language_follows_the_mail(self):
        text, source, lang = rules.draft_text(row(subject="請確認", body_text="你好"),
                                              {"type": "draft_reply", "template": "EN {tbd}",
                                               "template_zh": "中文 {tbd}"})
        self.assertEqual((text, source, lang), ("中文 [待填]", "template", "zh-Hant"))
        text, _, lang = rules.draft_text(row(), {"type": "draft_reply", "template": "EN {tbd}",
                                                 "template_zh": "中文 {tbd}"})
        self.assertEqual((text, lang), ("EN [TBD]", "en"))


class Validation(unittest.TestCase):
    GOOD = {"id": "r1", "conditions": [{"field": "subject", "op": "contains", "value": "x"}],
            "actions": [{"type": "archive"}]}

    def v(self, *rule_overrides, **top):
        doc = {"rules": [dict(self.GOOD, **o) for o in rule_overrides]}
        doc.update(top)
        return rules.validate(doc)

    def test_defaults_and_list_shorthand(self):
        clean, errors = rules.validate([self.GOOD])
        self.assertEqual(errors, [])
        r = clean["rules"][0]
        self.assertEqual((r["match"], r["enabled"], r["stop"], r["name"]), ("all", True, False, "r1"))

    def test_top_level_shape_errors(self):
        for bad in (None, "x", {}, {"rules": "nope"}, 5):
            clean, errors = rules.validate(bad)
            self.assertEqual(clean["rules"], [], repr(bad))
            self.assertEqual(len(errors), 1, repr(bad))
            self.assertIsNone(errors[0]["rule"])

    def test_id_rules(self):
        for bad in ("", "UPPER", "-lead", "a b", "x" * 41):
            self.assertTrue(self.v({"id": bad})[1], repr(bad))
        self.assertEqual(self.v({"id": "x" * 40})[1], [])
        errs = self.v({"id": "dup"}, {"id": "dup"})[1]
        self.assertEqual(len(errs), 1)
        self.assertIn("duplicate", errs[0]["message"])

    def test_value_type_checks(self):
        bad_conds = [
            {"field": "unread", "op": "is", "value": "yes"},
            {"field": "age_days", "op": "gte", "value": True},
            {"field": "age_days", "op": "gte", "value": "3"},
            {"field": "subject", "op": "contains", "value": "   "},
            {"field": "subject", "op": "in", "value": []},
            {"field": "subject", "op": "in", "value": [1]},
            {"field": "subject", "op": "regex", "value": "("},
            {"field": "subject", "op": "gte", "value": 1},
            {"field": "nope", "op": "contains", "value": "x"},
            "not-an-object",
        ]
        for c in bad_conds:
            self.assertTrue(self.v({"conditions": [c]})[1], repr(c))

    def test_limits_truncate_values(self):
        clean, errors = self.v({"conditions": [{"field": "subject", "op": "contains", "value": "x" * 500},
                                               {"field": "subject", "op": "in", "value": ["a"] * 80}]})
        self.assertEqual(errors, [])
        conds = clean["rules"][0]["conditions"]
        self.assertEqual(len(conds[0]["value"]), 200)
        self.assertEqual(len(conds[1]["value"]), 50)

    def test_count_limits(self):
        many_conds = [{"field": "subject", "op": "contains", "value": "x"}] * (rules.MAX_CONDITIONS + 1)
        self.assertTrue(self.v({"conditions": many_conds})[1])
        many_actions = [{"type": "archive"}] * (rules.MAX_ACTIONS + 1)
        self.assertTrue(self.v({"actions": many_actions})[1])
        many_rules = [{"id": f"r{i}", "conditions": self.GOOD["conditions"], "actions": self.GOOD["actions"]}
                      for i in range(rules.MAX_RULES + 1)]
        clean, errors = rules.validate({"rules": many_rules})
        self.assertTrue(errors)
        self.assertEqual(len(clean["rules"]), rules.MAX_RULES)

    def test_action_checks(self):
        for a in ({"type": "delete"}, {"type": "label"}, {"type": "label", "label": "x" * 41},
                  {"type": "task", "action": "nonsense"}, {"type": "draft_reply", "template": 5}, "archive"):
            self.assertTrue(self.v({"actions": [a]})[1], repr(a))
        clean, _ = self.v({"actions": [{"type": "label", "label": "  Receipts "}]})
        self.assertEqual(clean["rules"][0]["actions"], [{"type": "label", "label": "Receipts"}])

    def test_empty_conditions_or_actions_are_errors(self):
        self.assertTrue(self.v({"conditions": []})[1])
        self.assertTrue(self.v({"actions": []})[1])

    def test_errors_are_localised(self):
        _, errors = rules.validate({"rules": [{"id": "BAD"}]}, "zh-Hant")
        self.assertTrue(all(any("\u4e00" <= ch <= "\u9fff" for ch in e["message"]) for e in errors))

    def test_enabled_false_and_stop_flags(self):
        clean, _ = self.v({"enabled": False, "stop": 1, "match": "any"})
        r = clean["rules"][0]
        self.assertEqual((r["enabled"], r["stop"], r["match"]), (False, True, "any"))


class McpArguments(unittest.TestCase):
    def test_integer_coercion_and_clamping(self):
        v = lambda x: M.validate_args("brain_board", {"hours": x})["hours"]
        self.assertEqual(v("24"), 24)
        self.assertEqual(v(" 7 "), 7)
        self.assertEqual(v(2.0), 2)
        self.assertEqual(v(0), 1)
        self.assertEqual(v(-5), 1)
        self.assertEqual(v("-5"), 1)
        self.assertEqual(v(10 ** 9), 8760)

    def test_integer_rejections(self):
        for bad in (2.5, True, "abc", None, [], "1.5"):
            with self.assertRaises(M.ToolArgError, msg=repr(bad)):
                M.validate_args("brain_board", {"hours": bad})

    def test_shape_errors(self):
        for bad in ([], "s", 3):
            with self.assertRaises(M.ToolArgError):
                M.validate_args("brain_board", bad)
        self.assertEqual(M.validate_args("brain_board", None), {})
        with self.assertRaises(M.ToolArgError):
            M.validate_args("brain_board", {"unknown": 1})

    def test_required_and_enum(self):
        with self.assertRaises(M.ToolArgError):
            M.validate_args("save_draft", {"subject": "s"})
        with self.assertRaises(M.ToolArgError):
            M.validate_args("list_inbox", {"category": "spam"})
        self.assertEqual(M.validate_args("list_inbox", {"category": "fyi", "limit": 500}),
                         {"category": "fyi", "limit": 200})

    def test_text_length_cap(self):
        self.assertEqual(len(M.validate_args("search_brain", {"q": "x" * M.MAX_TEXT})["q"]), M.MAX_TEXT)
        with self.assertRaises(M.ToolArgError):
            M.validate_args("search_brain", {"q": "x" * (M.MAX_TEXT + 1)})

    def test_bilingual_error_messages(self):
        with self.assertRaises(M.ToolArgError) as cm:
            M.validate_args("brain_board", {"hours": "x"})
        self.assertIn(" / ", str(cm.exception))


def fake_req(origin=None, site=None, port=8770):
    headers = {}
    if origin is not None:
        headers["Origin"] = origin
    if site is not None:
        headers["Sec-Fetch-Site"] = site
    handler = SimpleNamespace(headers=SimpleNamespaceDict(headers), server=SimpleNamespace(server_address=("127.0.0.1", port)))
    return SimpleNamespace(handler=handler)


class SimpleNamespaceDict(dict):
    def get(self, key, default=None):
        for k, v in self.items():
            if k.lower() == key.lower():
                return v
        return default


class OriginGuard(unittest.TestCase):
    def test_no_origin_header_is_allowed(self):
        self.assertTrue(_origin.local_origin(fake_req()))

    def test_same_origin_variants(self):
        for o in ("http://127.0.0.1:8770", "http://localhost:8770", "HTTP://LOCALHOST:8770/", " http://127.0.0.1:8770 "):
            self.assertTrue(_origin.local_origin(fake_req(origin=o)), o)

    def test_foreign_or_lookalike_origins_are_refused(self):
        for o in ("https://evil.example", "http://127.0.0.1:9999", "http://127.0.0.1.evil.example:8770",
                  "https://127.0.0.1:8770", "null", "http://localhost:8770@evil.example", ""):
            self.assertFalse(_origin.local_origin(fake_req(origin=o)), repr(o))

    def test_read_guard_refuses_cross_site_even_without_origin(self):
        self.assertFalse(_origin.local_read(fake_req(site="cross-site")))
        self.assertFalse(_origin.local_read(fake_req(site="Cross-Site", origin="http://127.0.0.1:8770")))
        self.assertTrue(_origin.local_read(fake_req(site="same-origin")))
        self.assertTrue(_origin.local_read(fake_req()))

    def test_request_without_handler_is_treated_as_local(self):
        self.assertTrue(_origin.local_origin(SimpleNamespace(handler=None)))

    def test_refuse_is_a_403_in_both_languages(self):
        for zh in (True, False):
            body, status = _origin.refuse(zh)
            self.assertEqual(status, 403)
            self.assertTrue(body["error"])


if __name__ == "__main__":
    unittest.main()
