"""以固定亂數種子的模糊／不變量測試：openinbox 的解析、驗證、轉換輔助函式。

對象是 ``server/features/agents.py`` 裡把不可信文字變成路由決策與檔案的純函式：
``parse_mention``、``mentions_alias``、``_valid_id``、``_slug``、``_render_md``、
``_render_html``、``error_label``。

每個語料都來自 ``random.Random(<固定種子>)``，所以失敗可以原樣重現。斷言只寫不變量
（不是黃金輸出）：不崩潰、形狀有界，且輸入文字不能逃逸成路徑、標籤或錯誤字串。

不連網、不寫檔、不碰真信箱；字串全部是合成資料。單檔可跑：
``python3 tests/test_fmb_fuzz_agents.py``。
"""

from __future__ import annotations

import pathlib
import random
import re
import sys
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
_SERVER_DIR = str(REPO_ROOT / "server")
if _SERVER_DIR not in sys.path:
    sys.path.insert(0, _SERVER_DIR)

# 固定種子：下面每個語料都可重現。想換一份語料就在本機改這個數字。
SEED = 20251012

_AGENTS = None
_AGENTS_ERROR = None
try:  # 與其他 features 測試相同的匯入方式；sys.path 已在上面補好
    import features.agents as _AGENTS
except Exception as _exc:  # pragma: no cover - 只有 checkout 不完整時才會走到
    _AGENTS_ERROR = _exc

agents = _AGENTS


def setUpModule():
    if agents is None:  # pragma: no cover
        raise unittest.SkipTest("features.agents unavailable: %r" % (_AGENTS_ERROR,))


# 刻意混入 @ 以外的標點、換行、控制字元、全形／中日韓字元與雙向控制字元。
ALPHABET = (
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    " @._-+:;'\"()[]{}<>,/\\|!?~`^*=&%$#"
    "\n\r\t"
    "你好世界請幫我查研究會議公司行號"
    "\x00\x01\x07\x1f\u00a0\u200b\u200e\u202e\ufeff"
)
NO_AT_ALPHABET = ALPHABET.replace("@", "")

ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{2,80}$")
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
LABEL_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:: HTTP [0-9]{3})?$")
TAG_PATTERN = re.compile(r"</?([A-Za-z][A-Za-z0-9]*)")
ALLOWED_TAGS = frozenset(
    {"html", "head", "meta", "title", "style", "body", "div", "h1", "h2", "h3", "li", "p"}
)

DANGEROUS_LINES = (
    "<script>alert(1)</script>",
    "</style><img src=x onerror=alert(1)>",
    "<iframe src=\"about:blank\"></iframe>",
    "<!-- comment -->",
    "<h1>not a heading</h1>",
    "&amp; &lt; &",
    "<svg/onload=alert(1)>",
)

# 固定的一批惡意／病態字串：每個輔助函式都要能吞下去。
NASTY_STRINGS = (
    "",
    " ",
    "\n",
    "\r\n",
    "\t",
    "\x00",
    "\x00\x01\x02\x1f",
    "@",
    "@@",
    "@agent",
    "@agent ",
    "@agent\n",
    "@agent\r\nsecond line",
    "@agent " + "長" * 3000,
    "a" * 10000,
    "\u202e@agent reversed",
    "\ufeff@research x",
    "@prep \u3000 meeting",
    "@research-company",
    "@RESEARCH-COMPANY",
    "@agent\t查一下",
    "x@agent",
    "@agent@example.com",
    "user@example.com @agent check this",
    "<script>@agent alert(1)</script>",
    "@agent " + "🎯" * 500,
    "../../etc/passwd",
    "a/b/c",
    "..%2f..%2f",
)


def rand_text(rng, max_len=120):
    """由固定種子產生長度 0..max_len-1 的隨機字串。"""
    n = rng.randrange(0, max(1, max_len))
    return "".join(rng.choice(ALPHABET) for _ in range(n))


def rand_line(rng):
    if rng.random() < 0.35:
        return rng.choice(DANGEROUS_LINES)
    return rand_text(rng, 60).replace("\n", " ").replace("\r", " ")


def rand_card(rng):
    """一張刻意含惡意字元的成果卡片，符合 _render_md／_render_html 需要的欄位。"""
    lines = [rand_line(rng) for _ in range(rng.randrange(0, 10))]
    if rng.random() < 0.5:
        lines.append(rng.choice(["# Heading", "## Section", "### Sub", "- bullet", "  - nested"]))
    return {
        "id": "fuzz-card-%d" % rng.randrange(10 ** 6),
        "title": rand_line(rng),
        "kind": rng.choice(list(agents.TASK_KINDS)),
        "target": "target",
        "lang": rng.choice(["zh", "en"]),
        "created": "2026-10-12 10:00",
        "driver": rng.choice(["local", "openai_compatible", "cli", "http"]),
        "fallback": rng.random() < 0.5,
        "text": "\n".join(lines),
        "sources": [],
    }


class FuzzParseMention(unittest.TestCase):
    """parse_mention()：一則 thread 訊息 -> {"kind","target","word","ask"} 或 None。"""

    def _check(self, text, got):
        if got is None:
            return
        self.assertIsInstance(got, dict)
        self.assertEqual(set(got), {"kind", "target", "word", "ask"})
        self.assertIn(got["kind"], agents.TASK_KINDS)
        self.assertIsInstance(got["word"], str)
        self.assertEqual(got["word"], got["word"].lower())
        self.assertIn(got["word"], agents.MENTIONS)
        self.assertIsInstance(got["target"], str)
        self.assertIsInstance(got["ask"], str)
        self.assertLessEqual(len(got["target"]), 120)
        self.assertLessEqual(len(got["ask"]), 1000)
        self.assertNotIn("\n", got["target"])
        self.assertNotIn("\n", got["ask"])
        self.assertNotIn("\r", got["ask"])
        fixed = agents.MENTIONS[got["word"]]
        if fixed is not None:
            self.assertEqual(got["kind"], fixed)

    def test_random_text_keeps_shape(self):
        rng = random.Random(SEED + 1)
        for _ in range(1200):
            text = rand_text(rng)
            self._check(text, agents.parse_mention(text))

    def test_text_without_at_never_triggers(self):
        rng = random.Random(SEED + 2)
        for _ in range(400):
            n = rng.randrange(0, 120)
            text = "".join(rng.choice(NO_AT_ALPHABET) for _ in range(n))
            self.assertIsNone(agents.parse_mention(text), text[:60])

    def test_generated_mentions_always_parse(self):
        rng = random.Random(SEED + 3)
        words = list(agents.MENTIONS)
        heads = " ,;:()[]\n"  # 不可用 '.'：lookbehind 會擋掉緊接在 @ 前的句點
        for _ in range(500):
            word = rng.choice(words)
            if rng.random() < 0.3:
                word = word.upper() if rng.random() < 0.5 else word.title()
            head = "".join(rng.choice(heads) for _ in range(rng.randrange(0, 4)))
            text = "%s@%s %s" % (head, word, rand_text(rng, 40))
            got = agents.parse_mention(text)
            self.assertIsNotNone(got, text[:80])
            self._check(text, got)
            expected = agents.MENTIONS[word.lower()]
            if expected is not None:
                self.assertEqual(got["kind"], expected, text[:80])

    def test_body_limit_truncates_input(self):
        limit = agents.MAX_BODY
        self.assertIsNone(agents.parse_mention("a" * limit + " @agent someone"))
        inside = "a" * (limit - 20) + " @agent someone"
        self.assertIsNotNone(agents.parse_mention(inside))

    def test_long_input_is_bounded(self):
        rng = random.Random(SEED + 4)
        for _ in range(20):
            n = rng.randrange(0, 4000)
            text = "前言 " * (n // 3) + "@agent " + "y" * n
            self._check(text, agents.parse_mention(text))

    def test_parse_is_deterministic(self):
        rng = random.Random(SEED + 5)
        for _ in range(300):
            text = rand_text(rng)
            self.assertEqual(agents.parse_mention(text), agents.parse_mention(text))

    def test_empty_inputs_give_none(self):
        self.assertIsNone(agents.parse_mention(""))
        self.assertIsNone(agents.parse_mention(None))


class FuzzMentionsAlias(unittest.TestCase):
    """mentions_alias()：收件者標頭是否正好指向 agent 別名（只用於路由）。"""

    def _alias(self, text):
        try:
            return agents.mentions_alias(text)
        except ImportError as exc:  # pragma: no cover - compose 輔助函式缺席時
            self.skipTest("features.compose helpers unavailable: %r" % (exc,))

    def test_exact_alias_matches(self):
        self.assertIs(self._alias("agent@example.com"), True)
        self.assertIs(self._alias("AGENT@Example.COM"), True)

    def test_random_recipients_never_crash(self):
        rng = random.Random(SEED + 11)
        for _ in range(500):
            text = rand_text(rng, 160)
            got = self._alias(text)
            self.assertIsInstance(got, bool)
            if got:
                # 只可能在字串（忽略空白後）真的含有別名時為真
                self.assertIn("agent@example.com", re.sub(r"\s+", "", text).lower())

    def test_lookalikes_are_not_the_alias(self):
        for text in (
            "",
            "@",
            "@example.com",
            "agent@",
            "agent@example.org",
            "notagent@example.com",
            "agent-bot@example.com",
            "agent@sub.example.com",
            "agent@example.com.evil.example",
            "user@example.com",
        ):
            self.assertIs(self._alias(text), False, text)


class FuzzSlugAndIds(unittest.TestCase):
    """_slug() 與 _valid_id() 是唯一會變成檔名的字串來源。"""

    def test_slug_is_always_a_safe_single_segment(self):
        rng = random.Random(SEED + 21)
        samples = [rand_text(rng, 120) for _ in range(1200)]
        samples += [
            "",
            " ",
            "....",
            "-",
            "--",
            "/",
            "\\",
            "../../etc/passwd",
            "a" * 500,
            "Ａ" * 40,
            "已" * 40,
            "\x00\x01",
            "UPPER lower 123",
        ]
        for text in samples:
            slug = agents._slug(text)
            self.assertIsInstance(slug, str)
            self.assertGreaterEqual(len(slug), 1, text[:40])
            self.assertLessEqual(len(slug), 40, text[:40])
            self.assertRegex(slug, SLUG_PATTERN)
            self.assertEqual(slug, slug.lower())
            self.assertNotIn("/", slug)
            self.assertNotIn("\\", slug)
            self.assertNotIn("..", slug)
            self.assertEqual(pathlib.PurePosixPath(slug).name, slug)

    def test_valid_id_is_strict_and_path_safe(self):
        rng = random.Random(SEED + 22)
        samples = [rand_text(rng, 100) for _ in range(1200)]
        samples += [
            "",
            "ab",
            "abc",
            "a" * 82,
            "a" * 83,
            "../abc",
            "a/b",
            "ABC",
            "-abc",
            "a b",
            "日本語",
            "demo-card-2026",
        ]
        for text in samples:
            ok = agents._valid_id(text)
            self.assertIsInstance(ok, bool)
            if ok:
                self.assertRegex(text, ID_PATTERN)
                self.assertNotIn("/", text)
                self.assertNotIn("\\", text)
                self.assertNotIn("..", text)
                self.assertEqual(pathlib.PurePosixPath(text).name, text)
        self.assertFalse(agents._valid_id(None))

    def test_id_length_boundaries(self):
        # ID_RE = ^[a-z0-9][a-z0-9-]{2,80}$：1 個開頭字元 + 最多 80 個尾隨字元 = 長度上限 81。
        self.assertTrue(agents._valid_id("a" * 81))
        self.assertFalse(agents._valid_id("a" * 82))
        self.assertFalse(agents._valid_id("a" * 83))
        self.assertFalse(agents._valid_id("ab"))
        self.assertTrue(agents._valid_id("abc"))
        self.assertFalse(agents._valid_id(""))
        self.assertFalse(agents._valid_id("../abc"))
        self.assertFalse(agents._valid_id("ABC"))


class FuzzRenderCard(unittest.TestCase):
    """成果卡片渲染：輸入文字永遠不得變成標記或主動內容。"""

    def test_html_card_has_no_active_content(self):
        rng = random.Random(SEED + 31)
        for _ in range(300):
            card = rand_card(rng)
            out = agents._render_html(card)
            low = out.lower()
            self.assertTrue(out.startswith("<!doctype html>"), out[:40])
            self.assertNotIn("<script", low)
            self.assertNotIn("<iframe", low)
            self.assertNotIn("<object", low)
            self.assertNotIn("<embed", low)
            self.assertEqual(low.count("<style>"), 1)
            self.assertEqual(low.count("</style>"), 1)
            self.assertEqual(low.count("<body>"), 1)
            for tag in TAG_PATTERN.findall(out):
                self.assertIn(tag.lower(), ALLOWED_TAGS, out[:160])

    def test_html_card_escapes_title_and_body(self):
        card = {
            "id": "demo-card",
            "title": "<i>t</i>",
            "kind": "research_person",
            "target": "x",
            "lang": "en",
            "created": "2026-10-12 10:00",
            "driver": "local",
            "fallback": False,
            "text": "<b>hi</b> & <script>alert(1)</script>",
            "sources": [],
        }
        out = agents._render_html(card)
        self.assertIn("&lt;i&gt;t&lt;/i&gt;", out)
        self.assertIn(
            "&lt;b&gt;hi&lt;/b&gt; &amp; &lt;script&gt;alert(1)&lt;/script&gt;", out
        )
        self.assertNotIn("<script", out.lower())
        self.assertNotIn("<i>", out)
        self.assertNotIn("<b>", out)

    def test_markdown_card_keeps_text_and_labels(self):
        rng = random.Random(SEED + 33)
        for _ in range(200):
            card = rand_card(rng)
            md = agents._render_md(card)
            self.assertIsInstance(md, str)
            self.assertTrue(md.startswith("# "), md[:60])
            self.assertIn(card["title"], md)
            self.assertIn(card["text"].rstrip(), md)
            self.assertIn(agents.LABELS[card["lang"]][card["kind"]], md)
            self.assertTrue(md.endswith("\n"))


class FuzzErrorLabel(unittest.TestCase):
    """error_label()：只留例外類別與 HTTP 狀態碼，絕不外洩原始訊息。"""

    def test_random_messages_do_not_leak(self):
        rng = random.Random(SEED + 41)
        classes = (ValueError, TypeError, KeyError, RuntimeError, OSError, TimeoutError, LookupError)
        for i in range(400):
            marker = "MARKER-%04d" % i
            exc = rng.choice(classes)("%s %s" % (marker, rand_text(rng, 80)))
            label = agents.error_label(exc)
            self.assertNotIn(marker, label)
            self.assertNotIn("\n", label)
            self.assertNotIn("\r", label)
            self.assertRegex(label, LABEL_PATTERN)
            self.assertLessEqual(len(label), 40)

    def test_status_codes_come_from_code_or_http_token(self):
        class Boom(Exception):
            pass

        exc = Boom("upstream said HTTP 404: not found")
        exc.code = 503
        self.assertEqual(agents.error_label(exc), "Boom: HTTP 503")
        self.assertEqual(agents.error_label(Boom("HTTP 500 boom")), "Boom: HTTP 500")
        self.assertEqual(agents.error_label(Boom("HTTP 99999 too long")), "Boom")
        self.assertEqual(agents.error_label(Boom("HTTP 40")), "Boom")
        self.assertEqual(agents.error_label(Boom("no status here")), "Boom")
        soft = Boom("x")
        soft.code = "503"
        self.assertEqual(agents.error_label(soft), "Boom")


class FuzzPathologicalInputs(unittest.TestCase):
    """固定的一批病態字串，逐一丟進每個輔助函式：結果只能是不變量成立，不能是例外。"""

    def test_helpers_survive_pathological_strings(self):
        rng = random.Random(SEED + 51)
        for text in NASTY_STRINGS:
            with self.subTest(sample=text[:32]):
                self._one(text, rng)

    def _one(self, text, rng):
        got = agents.parse_mention(text)
        if got is not None:
            self.assertIn(got["kind"], agents.TASK_KINDS)
            self.assertLessEqual(len(got["target"]), 120)
            self.assertLessEqual(len(got["ask"]), 1000)
            self.assertNotIn("\n", got["target"])

        slug = agents._slug(text)
        self.assertRegex(slug, SLUG_PATTERN)
        self.assertLessEqual(len(slug), 40)
        self.assertIsInstance(agents._valid_id(slug), bool)
        self.assertIsInstance(agents._valid_id(text), bool)

        label = agents.error_label(ValueError(text))
        self.assertRegex(label, LABEL_PATTERN)

        card = {
            "id": slug,
            "title": text[:80],
            "kind": rng.choice(list(agents.TASK_KINDS)),
            "target": text[:40],
            "lang": rng.choice(["zh", "en"]),
            "created": "2026-10-12 10:00",
            "driver": "local",
            "fallback": True,
            "text": text[:400],
            "sources": [],
        }
        out = agents._render_html(card)
        self.assertNotIn("<script", out.lower())
        for tag in TAG_PATTERN.findall(out):
            self.assertIn(tag.lower(), ALLOWED_TAGS)
        self.assertIsInstance(agents._render_md(card), str)


if __name__ == "__main__":  # 單檔執行：python3 tests/test_fmb_fuzz_agents.py
    unittest.main(verbosity=2)
