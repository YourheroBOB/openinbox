"""Seeded, reproducible fuzz tests for openinbox parsing / validation / conversion helpers.

Scope: the parsing / validation / conversion helpers of ``server/features/agents.py`` —

* ``parse_mention``                        — @agent mention routing parser (pure)
* ``_valid_id`` / ``ID_RE``                — deliverable id validation
* ``_slug``                                — free text -> filesystem-safe slug conversion
* ``error_label``                          — exception -> safe label sanitiser
* ``_render_html`` / ``_render_md``        — card dict -> escaped HTML / Markdown conversion
* ``save_deliverable`` / ``read_deliverable`` / ``list_deliverables`` — round trip
* ``mentions_alias``                       — recipient-list alias validation (read-only check)

Standard library only. All randomness comes from ``random.Random`` seeded with fixed
constants, so any failure is reproducible from the case number in the assertion
message. No network, no real credentials, nothing outside a throwaway ``tempfile``
root is read or written: ``OPENINBOX_ROOT`` is pointed at ``tempfile.mkdtemp()``
before the server modules are imported, so deliverable files land in the temp dir.

Run standalone (a few seconds, far under the 30 s budget):

    python3 -m unittest tests.test_fmb_fuzz_agents -v

or with the whole suite:

    python3 -m unittest discover -s tests
"""
from __future__ import annotations

import html
import json
import os
import random
import re
import string
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Throwaway app root FIRST, so importing the server modules can never touch the repo.
os.environ["OPENINBOX_ROOT"] = tempfile.mkdtemp(prefix="fmb_fuzz_agents_")
_SERVER_DIR = str(ROOT / "server")
if _SERVER_DIR not in sys.path:
    sys.path.insert(0, _SERVER_DIR)

import features.agents as AG  # noqa: E402  (needs sys.path + OPENINBOX_ROOT set above)

SEED = 0x0FBF2026  # fixed master seed; each test derives its own sub-seed

# ── random input generators (all driven by explicit seeds) ──────────────────

_TEXT_PIECES = [
    "@agent", "@research", "@prep", "@meeting", "@research-company",
    "@AGENT", "@Research", "@PrEp", "@agent,", "@agent:", "@agent!", "@agent.",
    "x@agent", "@agents", "@agentic", "@ research", "@research-companyx", "@agent@example.com",
    "公司", "company", "Corp", "Inc.", "ltd", "股份", "有限",
    "會議", "meeting", "agenda", "議程", "準備", "call", "prep",
    "please", "pls", "can you", "could you", "請幫我", "幫我", "麻煩", "查一下", "幫忙", "查", "研究",
    "Samira Ortiz", "Northwind", "priya@talentloop.example", "you@example.com",
    "\n", "\r\n", " ", "  ", "\t", "：", ":", "，", ",", "。", ".", "！", "!", "；",
    "<script>alert(1)</script>", "<img src=x onerror=alert(2)>", "&amp;", "&#39;", "&quot;",
    "HTTP 404", "HTTP 500", "FAKE_VALUE_FOR_TEST", "😀", "é", "中", "日本語", "«»", "¥€$",
    "\x00", "\x1b[31m", "A" * 50, "b" * 200, "c" * 2000,
]

_ALPHABET = (
    string.ascii_letters + string.digits + " \t\n.,:;@-_<>\"'&%$#*!?/\\|()[]{}+=~`^"
    + "中文測試請幫會議公司😀éÀÿµ«»"
)

_ADDR_PIECES = [
    "agent@example.com", "AGENT@EXAMPLE.COM", "Agent <agent@example.com>",
    "agent@example.comx", "xagent@example.com", "agent+tag@example.com",
    "agent @ example.com", "a@b.example", "you@example.com",
    "Samira Ortiz <samira@northwind.example>", '"agent@example.com" <other@x.example>',
    "", "  ", ",", "agent@example.com,", ";", "Northwind 公司 <ir@northwind.example>",
]


def _rand_text(rnd: random.Random, max_len: int = 200) -> str:
    """Random text assembled from adversarial pieces and random characters."""
    out: list = []
    target = rnd.randint(0, max_len)
    while sum(len(p) for p in out) < target:
        if rnd.random() < 0.6:
            out.append(rnd.choice(_TEXT_PIECES))
        else:
            out.append("".join(rnd.choice(_ALPHABET) for _ in range(rnd.randint(1, 10))))
    return "".join(out)[:max_len]


def _rand_idish(rnd: random.Random) -> str:
    """Random string shaped like (or deliberately unlike) a deliverable id / slug input."""
    style = rnd.randint(0, 6)
    if style == 0:
        return ""
    if style == 1:
        return "".join(rnd.choice(string.ascii_lowercase + string.digits + "-")
                       for _ in range(rnd.randint(1, 90)))
    if style == 2:
        return "".join(rnd.choice(string.ascii_letters + string.digits + "-._/\\")
                       for _ in range(rnd.randint(1, 40)))
    if style == 3:
        return _rand_text(rnd, 60)
    if style == 4:
        return rnd.choice("abz09-") * rnd.randint(1, 100)
    if style == 5:
        return rnd.choice(["-", "--", "a", "ab", "abc", "abc-", "-abc", "aBc", "abc\n",
                           "a b c", "../x", "..", ".", "a.b", "a/b", "AAA", "000"])
    return "".join(rnd.choice("中文會議公司😀éÀ-_./") for _ in range(rnd.randint(1, 30)))


def _rand_card(rnd: random.Random) -> dict:
    lines = []
    for _ in range(rnd.randint(0, 12)):
        prefix = rnd.choice(["# ", "## ", "### ", "- ", "  - ", "", "", ""])
        lines.append(prefix + _rand_text(rnd, 80))
    return {
        "id": "fuzz-card",
        "title": _rand_text(rnd, 60),
        "kind": rnd.choice(AG.TASK_KINDS),
        "target": _rand_text(rnd, 40),
        "lang": rnd.choice(["zh", "en"]),
        "created": _rand_text(rnd, 20),
        "driver": rnd.choice(["local", "cli", "http", ""]),
        "fallback": rnd.random() < 0.5,
        "text": "\n".join(lines),
        "sources": [],
    }


class _TagScan(HTMLParser):
    """Collect every start/empty-element tag name and attribute name seen."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, tuple(k for k, _ in attrs)))

    def handle_startendtag(self, tag, attrs):
        self.tags.append((tag, tuple(k for k, _ in attrs)))


# ── parse_mention ───────────────────────────────────────────────────────────

class TestParseMentionFuzz(unittest.TestCase):
    """Fuzz the @agent mention parser: no crash + structural invariants."""

    def test_fuzz_shape_and_invariants(self):
        rnd = random.Random(SEED + 1)
        for i in range(2500):
            if rnd.random() < 0.4:  # structured: real mention embedded in noise
                word = rnd.choice(["@agent", "@research", "@prep", "@meeting",
                                   "@research-company", "@AGENT", "@Research",
                                   "@agent!", "@agent:", "x@agent", "@agents"])
                tail = rnd.choice(["Samira Ortiz", "Northwind 公司", "please 幫我查 Lee",
                                   "meeting prep 議程", "corp inc", ""])
                t = (_rand_text(rnd, 60) + word + rnd.choice([" ", ": ", "\n", "，", ""])
                     + tail + _rand_text(rnd, 120))
            elif rnd.random() < 0.05:  # occasionally cross the MAX_BODY boundary
                t = _rand_text(rnd, 5200)
            else:
                t = _rand_text(rnd, rnd.choice([0, 5, 40, 200, 800]))

            try:
                res = AG.parse_mention(t)
            except Exception as exc:  # noqa: BLE001 — the point is: it must not raise
                self.fail(f"case {i}: parse_mention raised {type(exc).__name__}: "
                          f"input~{t[:120]!r}")

            truncated = (t or "")[: AG.MAX_BODY]
            if not AG.MENTION_RE.search(truncated):
                self.assertIsNone(res, f"case {i}: no mention in truncated text but got {res!r}")
                continue
            self.assertIsNotNone(res, f"case {i}: mention present but parse returned None")
            self.assertIsInstance(res, dict, f"case {i}: {type(res)}")
            self.assertEqual(set(res), {"kind", "target", "word", "ask"}, f"case {i}: {set(res)}")
            self.assertIsInstance(res["target"], str)
            self.assertIsInstance(res["ask"], str)
            # kind is always one of the three task kinds
            self.assertIn(res["kind"], AG.TASK_KINDS, f"case {i}: {res['kind']}")
            # word is always a known routing word, lowercased
            self.assertIn(res["word"], AG.MENTIONS, f"case {i}: {res['word']}")
            self.assertEqual(res["word"], res["word"].lower())
            # explicit routing words map deterministically to their task kind
            mapped = AG.MENTIONS.get(res["word"])
            if mapped is not None:
                self.assertEqual(res["kind"], mapped, f"case {i}: {res}")
            # bounds and cleanliness of extracted fields
            self.assertLessEqual(len(res["target"]), 120, f"case {i}: target too long")
            self.assertLessEqual(len(res["ask"]), 1000, f"case {i}: ask too long")
            # strip happens before the [:120] slice, so a sliced target may keep a
            # trailing space; only assert full cleanliness on unsliced targets.
            if len(res["target"]) < 120:
                self.assertEqual(res["target"], res["target"].strip(), f"case {i}: {res['target']!r}")
            # pure function: deterministic for the same input
            if i % 10 == 0:
                self.assertEqual(AG.parse_mention(t), res, f"case {i}: not deterministic")

    def test_edge_inputs(self):
        for t in (None, "", "   ", "\n", "\x00"):
            self.assertIsNone(AG.parse_mention(t))
        # MENTION_RE's lookbehind (?<![\w.]) rejects a mention glued to a word char
        # ("x@agent"), so pad with a space to isolate the MAX_BODY window behaviour.
        far = "x" * 4000 + " @agent someone"   # mention outside the window
        self.assertIsNone(AG.parse_mention(far))
        near = "x" * 3000 + " @agent someone"   # mention inside the window
        self.assertIsNotNone(AG.parse_mention(near))


# ── deliverable id validation ───────────────────────────────────────────────

class TestDeliverableIdFuzz(unittest.TestCase):
    """Fuzz the id validator: consistency with ID_RE and path-safety of accepted ids."""

    def test_fuzz_valid_id(self):
        rnd = random.Random(SEED + 2)
        for i in range(4000):
            s = _rand_idish(rnd)
            self.assertIs(AG._valid_id(s), bool(AG.ID_RE.match(s)),
                          f"case {i}: _valid_id disagrees with ID_RE on {s!r}")
            if AG._valid_id(s):
                # anything accepted must be safe to bolt into a filename
                self.assertNotIn("/", s, f"case {i}: {s!r}")
                self.assertNotIn("\\", s, f"case {i}: {s!r}")
                self.assertNotIn("..", s, f"case {i}: {s!r}")
                self.assertTrue(s and s[0].isalnum() and s[0].islower() or s[0].isdigit(),
                                f"case {i}: {s!r}")
                # ID_RE uses re.match + '$', which tolerates one trailing newline;
                # skip the strict length check for that single known nuance.
                if "\n" not in s:
                    self.assertTrue(3 <= len(s) <= 81, f"case {i}: len {len(s)} {s!r}")

    def test_rejects_traversal(self):
        for bad in ("../../x", "..", ".", "a/../b", "/etc/passwd", "a\\b", "", "-abc",
                    "ABC", "a b", "ab", "a.b"):
            self.assertFalse(AG._valid_id(bad), bad)


# ── slug conversion ─────────────────────────────────────────────────────────

class TestSlugFuzz(unittest.TestCase):
    """Fuzz the slug converter: any input becomes a short, safe, non-empty slug."""

    def test_fuzz_slug(self):
        rnd = random.Random(SEED + 3)
        for i in range(3000):
            s = _rand_idish(rnd)
            out = AG._slug(s)
            self.assertTrue(out, f"case {i}: empty slug for {s!r}")
            self.assertLessEqual(len(out), 40, f"case {i}: {out!r}")
            self.assertRegex(out, r"^[a-z0-9-]*$", f"case {i}: {out!r}")
            self.assertEqual(out, out.strip("-"), f"case {i}: untrimmed dashes {out!r}")
            if i % 7 == 0:
                self.assertEqual(AG._slug(s), out, f"case {i}: not deterministic")

    def test_slug_fallbacks(self):
        self.assertEqual(AG._slug(""), "card")
        self.assertEqual(AG._slug(None), "card")
        self.assertEqual(AG._slug("!!!"), "card")
        self.assertEqual(AG._slug("  Samira Ortiz  "), "samira-ortiz")


# ── error label sanitiser ───────────────────────────────────────────────────

class TestErrorLabelFuzz(unittest.TestCase):
    """Fuzz the exception sanitiser: the message body must never leak into the label."""

    class _Coded(Exception):
        def __init__(self, msg, code):
            super().__init__(msg)
            self.code = code

    def test_fuzz_no_message_leak(self):
        rnd = random.Random(SEED + 4)
        types = [ValueError, RuntimeError, KeyError, OSError, ArithmeticError, TypeError]
        for i in range(2000):
            msg = (_rand_text(rnd, 200) + f" LEAKMARK{i}QZ " + _rand_text(rnd, 60))
            exc = rnd.choice(types)(msg)
            label = AG.error_label(exc)
            # a unique sentinel embedded in the message must never survive
            self.assertNotIn("LEAKMARK", label, f"case {i}: label leaked message content")
            # shape: exception class name, optionally plus ": HTTP <digits>"
            self.assertRegex(label, r"^[A-Za-z_][A-Za-z0-9_]*(?:: HTTP \d+)?$", f"case {i}: {label!r}")
            if i % 9 == 0:
                self.assertEqual(AG.error_label(exc), label, f"case {i}: not deterministic")

    def test_fuzz_code_attribute(self):
        rnd = random.Random(SEED + 5)
        for i in range(500):
            code = rnd.choice([rnd.randint(100, 599), 0, 999, 42])
            exc = self._Coded("LEAKMARK2 " + _rand_text(rnd, 80), code)
            label = AG.error_label(exc)
            self.assertEqual(label, f"_Coded: HTTP {code}", f"case {i}")
            self.assertNotIn("LEAKMARK2", label, f"case {i}: leaked")
        # a non-int code attribute falls back to the message-scan path
        self.assertEqual(AG.error_label(self._Coded("boom HTTP 404 gone", "404")),
                         "_Coded: HTTP 404")
        self.assertEqual(AG.error_label(self._Coded("quiet failure", None)), "_Coded")


# ── HTML / Markdown card rendering ──────────────────────────────────────────

class TestRenderFuzz(unittest.TestCase):
    """Fuzz the card renderers: only whitelisted tags/attrs, everything escaped."""

    ALLOWED_TAGS = {"html", "head", "meta", "style", "title", "body", "div",
                    "h1", "h2", "h3", "li", "p"}
    ALLOWED_ATTRS = {"html": {"lang"}, "meta": {"charset"}, "div": {"class"}}

    def test_fuzz_render_html(self):
        rnd = random.Random(SEED + 6)
        for i in range(1200):
            card = _rand_card(rnd)
            try:
                out = AG._render_html(card)
            except Exception as exc:  # noqa: BLE001
                self.fail(f"case {i}: _render_html raised {type(exc).__name__}")
            self.assertTrue(out.startswith("<!doctype html><html lang="), f"case {i}")
            self.assertTrue(out.endswith("</body></html>\n"), f"case {i}")
            # cheap structural safety net
            self.assertNotIn("<script", out.lower(), f"case {i}: script tag leaked")
            self.assertNotIn("javascript:", out.lower(), f"case {i}: js url leaked")
            # every tag and attribute must come from the fixed whitelist
            scan = _TagScan()
            scan.feed(out)
            scan.close()
            for tag, attrkeys in scan.tags:
                self.assertIn(tag, self.ALLOWED_TAGS, f"case {i}: unexpected tag <{tag}>")
                self.assertLessEqual(set(attrkeys), self.ALLOWED_ATTRS.get(tag, set()),
                                     f"case {i}: unexpected attrs on <{tag}>: {attrkeys}")
            # the title is html-escaped into the document
            self.assertIn(html.escape(card["title"]), out, f"case {i}: title missing/escaped wrong")
            # every non-empty text line appears in escaped form (prefix rules mirrored)
            for ln in card["text"].splitlines():
                s = ln.rstrip()
                if not s:
                    continue
                if s.startswith("### "):
                    frag = s[4:]
                elif s.startswith("## "):
                    frag = s[3:]
                elif s.startswith("# "):
                    frag = s[2:]
                elif s.lstrip().startswith("- "):
                    frag = s.lstrip()[2:]
                else:
                    frag = s
                self.assertIn(html.escape(frag), out, f"case {i}: line not escaped verbatim")

    def test_fuzz_render_md(self):
        rnd = random.Random(SEED + 16)
        for i in range(600):
            card = _rand_card(rnd)
            out = AG._render_md(card)
            self.assertTrue(out.startswith("# " + card["title"]), f"case {i}: bad md header")
            self.assertIn(card["text"].rstrip(), out, f"case {i}: md lost the body text")
            self.assertTrue(out.endswith("\n"), f"case {i}: md not newline-terminated")


# ── mentions_alias (routing validation, read-only) ─────────────────────────

class TestMentionsAliasFuzz(unittest.TestCase):
    """Fuzz the alias routing check: never crashes, bool result, conservative bound."""

    def test_fuzz_crashfree_and_conservative(self):
        rnd = random.Random(SEED + 7)
        for i in range(800):
            if rnd.random() < 0.5:
                s = rnd.choice([", ", "; ", " "]).join(
                    rnd.choice(_ADDR_PIECES) for _ in range(rnd.randint(0, 4)))
            else:
                s = _rand_text(rnd, 120)
            try:
                res = AG.mentions_alias(s)
            except Exception as exc:  # noqa: BLE001
                self.fail(f"case {i}: mentions_alias raised {type(exc).__name__} on {s[:80]!r}")
            self.assertIsInstance(res, bool, f"case {i}: {type(res)}")
            # conservative invariant: with no "@" there is no addr-spec that could
            # equal the alias (weaker than a substring check on purpose — parse_addr
            # may normalise spacing/quotes, so a literal-substring requirement would
            # over-specify compose.py's parser)
            if "@" not in (s or ""):
                self.assertFalse(res, f"case {i}: matched with no address at all: {s[:80]!r}")
            if i % 11 == 0:
                self.assertEqual(AG.mentions_alias(s), res, f"case {i}: not deterministic")

    def test_edge_inputs(self):
        for s in (None, "", "   ", ",", "no at sign here"):
            self.assertIsInstance(AG.mentions_alias(s), bool)


# ── deliverable round trip (temp root only) ─────────────────────────────────

class TestDeliverableRoundtripFuzz(unittest.TestCase):
    """Fuzz save/read/list with adversarial targets: ids stay valid, data round-trips."""

    BAD_TARGETS = ["../../etc/passwd", "a/b/c", "<b>x</b>", "..\\..\\x",
                   "公司 😀 " + "z" * 130, "", "\n\t", "CONVERT_ME"]

    def test_fuzz_roundtrip(self):
        rnd = random.Random(SEED + 8)
        seen = set()
        for i in range(60):
            kind = rnd.choice(AG.TASK_KINDS)
            target = rnd.choice(self.BAD_TARGETS) if rnd.random() < 0.5 else _rand_text(rnd, 60)
            text = "\n".join(_rand_text(rnd, 60) for _ in range(rnd.randint(0, 6)))
            result = {"kind": kind, "target": target, "text": text,
                      "driver": rnd.choice(["local", "cli", "http", ""]),
                      "fallback": rnd.random() < 0.5, "sources": [], "error": None}
            lang = rnd.choice(["zh", "en", "zh-Hant", "EN", ""])
            title = _rand_text(rnd, 40) if rnd.random() < 0.5 else ""
            try:
                card = AG.save_deliverable(result, lang=lang, title=title)
            except Exception as exc:  # noqa: BLE001
                self.fail(f"case {i}: save_deliverable raised {type(exc).__name__}")
            # the id is always validator-clean, even for traversal-flavored targets
            self.assertTrue(AG._valid_id(card["id"]), f"case {i}: bad id {card['id']!r}")
            self.assertEqual(card["kind"], kind)
            self.assertEqual(card["lang"], "zh" if str(lang or "").lower().startswith("zh") else "en")
            seen.add(card["id"])
            # files only ever land inside the temp deliverables dir
            for suffix in ("md", "html", "json"):
                self.assertTrue((AG.DELIV_DIR / f"{card['id']}.{suffix}").is_file(),
                                f"case {i}: {suffix} file missing")
            # all three formats read back with the right content type prefix
            got_md = AG.read_deliverable(card["id"], "md")
            got_html = AG.read_deliverable(card["id"], "html")
            got_json = AG.read_deliverable(card["id"], "json")
            for got, prefix in ((got_md, b"# "), (got_html, b"<!doctype html>"), (got_json, b"{")):
                self.assertIsNotNone(got, f"case {i}: read_deliverable returned None")
                body, ctype = got
                self.assertTrue(body, f"case {i}: empty body")
                self.assertTrue(body.startswith(prefix), f"case {i}: wrong {ctype[:20]} prefix")
                self.assertIn("charset=utf-8", ctype)
            # the JSON card is a faithful round trip of what was saved
            j = json.loads(AG.read_deliverable(card["id"], "json")[0].decode("utf-8"))
            self.assertEqual(j["id"], card["id"])
            self.assertEqual(j["kind"], kind)
            self.assertEqual(j["text"], text)
            self.assertEqual(j["target"], target)
            # and it is listed
            ids = [c.get("id") for c in AG.list_deliverables(200)]
            self.assertIn(card["id"], ids, f"case {i}: not listed")
            # invalid formats / ids never resolve to a path
            self.assertIsNone(AG.read_deliverable("../" + card["id"], "md"))
            self.assertIsNone(AG.read_deliverable(card["id"], "exe"))
            self.assertIsNone(AG.read_deliverable("", "md"))
        self.assertTrue(seen, "no deliverables were created")

    def test_invalid_reads(self):
        for did, fmt in (("../../x", "md"), ("..", "json"), ("a b", "html"),
                         ("ok-ish-id", "exe"), ("ok-ish-id", ""), ("ok-ish-id", "MD")):
            self.assertIsNone(AG.read_deliverable(did, fmt), (did, fmt))


if __name__ == "__main__":
    unittest.main()
