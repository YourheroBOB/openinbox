"""Natural-language mail search (F11) on a local SQLite FTS5 index.

    GET  /api/search?q=&account=&category=&limit=&offset=&sort=&today=&lang=
    POST /api/search          {"q", "agent": true, ...}  same, optionally rewritten by the BYO agent
    GET  /api/search/parse?q= parse only: filters, canonical query, bilingual explanation
    GET  /api/search/status   index size and engine
    POST /api/search/reindex  rebuild the index from scratch

Queries mix free words with filters, in English or Traditional Chinese:

    samira deck last week with attachments      from:samira after:2026-09-01 has:attachment
    上週 Samira 寄來有附件的信                   未讀的電子報   9月15日之後  最近3天  -cables

The index (`search_docs` + `search_fts`) lives next to the mail cache and is
brought up to date lazily before each search; deleting a mail row drops its index
row through a trigger, so the local-cache clear removes indexed text too. CJK text
is indexed as overlapping character bigrams, so any 2+ character Chinese word
matches; a single CJK character falls back to LIKE. Without FTS5 in the local
SQLite build everything falls back to LIKE (`engine: "like"`).

Relative dates ("last week", "上週") are anchored to `today=` if given, else to the
newest cached mail in demo mode, else to the clock. Date ranges are half-open:
`after:` is inclusive, `before:` is exclusive (same as Gmail).
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import date, datetime, timedelta
from threading import Lock

import agent_bridge
import yhbmail
from features import get, post
from features import contacts as contacts_mod

CATEGORIES = [t["id"] for t in yhbmail.TAXONOMY]
CATEGORY_LABELS = {
    "needs_you": ("Needs you", "需要你"), "upcoming": ("Upcoming", "今天之後"),
    "worth_a_look": ("Worth a look", "值得看"), "fyi": ("FYI", "僅供參考"), "other": ("Cleanup", "可清掉"),
}
CATEGORY_ALIASES = {
    "needs_you": ["needs_you", "needs-you", "needsyou", "needs you", "needs me", "need you", "need me",
                  "needs my reply", "need my reply", "需要你", "需要我回覆", "需要我回", "需要我", "需要回覆",
                  "待我回覆", "待回覆", "待回", "要我回覆", "要我回"],
    "upcoming": ["upcoming", "calendar", "invites", "invite", "invitations", "invitation", "events",
                 "今天之後", "行程", "會議邀請", "邀請"],
    "worth_a_look": ["worth_a_look", "worth-a-look", "worth a look", "important", "值得看", "重要"],
    "fyi": ["fyi", "僅供參考", "供參考"],
    "other": ["other", "cleanup", "newsletters", "newsletter", "promotions", "promotion", "promos", "promo",
              "marketing", "bulk", "電子報", "廣告", "促銷", "行銷", "可清掉"],
}
ALIAS_TO_CATEGORY = {a: cat for cat, names in CATEGORY_ALIASES.items() for a in names}

# `\b` treats CJK as word characters, so "2026-09-15之後" or "last week的" would not match.
ASCII_B = r"(?:(?<![A-Za-z0-9])(?=[A-Za-z0-9])|(?<=[A-Za-z0-9])(?![A-Za-z0-9]))"


def rx(pattern: str, flags: int = re.I) -> re.Pattern:
    return re.compile(pattern.replace(r"\b", ASCII_B), flags)


CJK = "\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
CJK_RUN = re.compile(f"[{CJK}]+")
HAS_CJK = re.compile(f"[{CJK}]")
TOKEN = re.compile(r"[^\W_]+")
ATTACH_HINT = re.compile(
    r"(attached|attachment|enclosed|附件|附檔|檢附|\b[\w\-]+\.(?:pdf|docx?|xlsx?|pptx?|csv|zip|ics|png|jpe?g|key)\b)", re.I)
LIKE_FIELDS = ("e.subject", "e.snippet", "e.body_text", "e.from_addr", "e.to_addr")

_lock = Lock()
_index = {"sig": None, "engine": None, "docs": 0, "built_at": None}


def _zh(lang) -> bool:
    return str(lang or "").lower().startswith("zh")


def _int(value, default: int, lo: int = 0, hi: int = 500) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


# ───────────────────────── dates ─────────────────────────

MONTHS = {"january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3, "april": 4, "apr": 4,
          "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7, "august": 8, "aug": 8, "september": 9,
          "sept": 9, "sep": 9, "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12}
MON = "|".join(sorted(MONTHS, key=len, reverse=True))
MON_ALONE = "|".join(k for k in sorted(MONTHS, key=len, reverse=True) if k != "may")
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
WD_EN = "|".join(WEEKDAYS)
WD_ZH = "一二三四五六日天"
EN_NUMS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
           "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fourteen": 14, "thirty": 30}
NUM = r"\d{1,3}|" + "|".join(sorted(EN_NUMS, key=len, reverse=True)) + r"|[一二兩三四五六七八九十]{1,3}"
UNIT_EN = r"days?|weeks?|months?|years?"
UNIT_ZH = r"天|日|週|周|個?星期|個?禮拜|個?月|年"


def to_num(s: str) -> int:
    s = s.strip().lower()
    if s.isdigit():
        return int(s)
    if s in EN_NUMS:
        return EN_NUMS[s]
    digits = {"一": 1, "二": 2, "兩": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if "十" in s:
        tens, _, ones = s.partition("十")
        return (digits.get(tens, 1) if tens else 1) * 10 + (digits.get(ones, 0) if ones else 0)
    return digits.get(s, 1)


def _unit(u: str) -> str:
    u = u.lower()
    if u.startswith("d") or u in ("天", "日"):
        return "day"
    if u.startswith("w") or u[-1] in "週周期拜":
        return "week"
    if u.startswith("m") or u.endswith("月"):
        return "month"
    return "year"


def _month_start(y: int, m: int) -> date:
    while m < 1:
        y, m = y - 1, m + 12
    while m > 12:
        y, m = y + 1, m - 12
    return date(y, m, 1)


def _minus(anchor: date, n: int, unit: str) -> date:
    if unit == "day":
        return anchor - timedelta(days=n)
    if unit == "week":
        return anchor - timedelta(weeks=n)
    if unit == "month":
        first = _month_start(anchor.year, anchor.month - n)
        nxt = _month_start(first.year, first.month + 1)
        return first.replace(day=min(anchor.day, (nxt - timedelta(days=1)).day))
    try:
        return anchor.replace(year=anchor.year - n)
    except ValueError:
        return anchor.replace(year=anchor.year - n, day=28)


def _last_n(n: int, unit: str, anchor: date):
    return _minus(anchor, n, unit) + timedelta(days=1), anchor + timedelta(days=1)


def _week(anchor: date, back: int = 0):
    start = anchor - timedelta(days=anchor.weekday()) - timedelta(weeks=back)
    return start, start + timedelta(days=7)


def _day(d: date):
    return d, d + timedelta(days=1)


def _past(start: date, end: date, anchor: date, yearless: bool):
    """A date written without a year that lands in the future means last year's."""
    if yearless and start > anchor:
        try:
            return start.replace(year=start.year - 1), end.replace(year=end.year - 1)
        except ValueError:
            return start - timedelta(days=365), end - timedelta(days=365)
    return start, end


def _ymd(y, m, d, anchor):
    yearless = not y
    try:
        s = date(int(y) if y else anchor.year, int(m), int(d))
    except ValueError:
        return None
    return _past(s, s + timedelta(days=1), anchor, yearless)


def _ym(y, m, anchor):
    m = int(m)
    if not 1 <= m <= 12:
        return None
    s = date(int(y) if y else anchor.year, m, 1)
    return _past(s, _month_start(s.year, m + 1), anchor, not y)


def _weekday(idx: int, anchor: date, back_week: bool = False, strictly_before: bool = False):
    if back_week:
        start, _ = _week(anchor, 1)
        return _day(start + timedelta(days=idx))
    delta = (anchor.weekday() - idx) % 7
    if strictly_before and delta == 0:
        delta = 7
    return _day(anchor - timedelta(days=delta))


FIXED = {
    "today": lambda a: _day(a), "今天": lambda a: _day(a), "今日": lambda a: _day(a),
    "yesterday": lambda a: _day(a - timedelta(days=1)), "昨天": lambda a: _day(a - timedelta(days=1)),
    "昨日": lambda a: _day(a - timedelta(days=1)), "前天": lambda a: _day(a - timedelta(days=2)),
    "this week": lambda a: _week(a), "last week": lambda a: _week(a, 1), "past week": lambda a: _last_n(7, "day", a),
    "this month": lambda a: (_month_start(a.year, a.month), _month_start(a.year, a.month + 1)),
    "last month": lambda a: (_month_start(a.year, a.month - 1), _month_start(a.year, a.month)),
    "past month": lambda a: _last_n(1, "month", a),
    "this year": lambda a: (date(a.year, 1, 1), date(a.year + 1, 1, 1)),
    "last year": lambda a: (date(a.year - 1, 1, 1), date(a.year, 1, 1)),
    "recent": lambda a: _last_n(7, "day", a), "recently": lambda a: _last_n(7, "day", a),
    "lately": lambda a: _last_n(7, "day", a),
}
for _k in ("本週", "本周", "這週", "這周", "這禮拜", "這星期", "這個禮拜", "這個星期", "本星期"):
    FIXED[_k] = FIXED["this week"]
for _k in ("上週", "上周", "上禮拜", "上星期", "上個禮拜", "上個星期"):
    FIXED[_k] = FIXED["last week"]
for _k in ("本月", "這個月", "這月"):
    FIXED[_k] = FIXED["this month"]
for _k in ("上個月", "上月"):
    FIXED[_k] = FIXED["last month"]
for _k in ("最近", "近期", "近來"):
    FIXED[_k] = FIXED["recent"]
FIXED["今年"], FIXED["去年"] = FIXED["this year"], FIXED["last year"]
FIXED_EN = "|".join(sorted((k.replace(" ", r"\s+") for k in FIXED if k.isascii()), key=len, reverse=True))
FIXED_ZH = "|".join(sorted((k for k in FIXED if not k.isascii()), key=len, reverse=True))

# (pattern, handler(match, anchor) -> (start, end) | None); order matters inside the alternation.
SPAN_PARTS = [
    (rf"\b(last|this|past)\s+({WD_EN})\b",
     lambda m, a: _weekday(WEEKDAYS.index(m.group(2).lower()), a, strictly_before=m.group(1).lower() != "this")),
    (rf"(上|本|這)?(?:週|周|星期|禮拜)([{WD_ZH}])",
     lambda m, a: _weekday(min(WD_ZH.index(m.group(2)), 6), a, back_week=m.group(1) == "上")),
    (rf"\b({NUM})\s+({UNIT_EN})\s+ago\b", lambda m, a: _day(_minus(a, to_num(m.group(1)), _unit(m.group(2))))),
    (rf"(\d{{1,3}}|[一二兩三四五六七八九十]{{1,3}})\s*({UNIT_ZH})前",
     lambda m, a: _day(_minus(a, to_num(m.group(1)), _unit(m.group(2))))),
    (rf"\b(?:in\s+the\s+)?(?:last|past|previous)\s+({NUM})\s+({UNIT_EN})\b",
     lambda m, a: _last_n(to_num(m.group(1)), _unit(m.group(2)), a)),
    (rf"(?:最近|過去|近|前)\s*(\d{{1,3}}|[一二兩三四五六七八九十]{{1,3}})\s*({UNIT_ZH})(?:內|以內|之內)?",
     lambda m, a: _last_n(to_num(m.group(1)), _unit(m.group(2)), a)),
    (rf"(\d{{1,3}}|[一二兩三四五六七八九十]{{1,3}})\s*({UNIT_ZH})(?:內|以內|之內)",
     lambda m, a: _last_n(to_num(m.group(1)), _unit(m.group(2)), a)),
    (rf"\b(?:{FIXED_EN})\b", lambda m, a: FIXED[re.sub(r"\s+", " ", m.group(0).lower())](a)),
    (rf"(?:{FIXED_ZH})", lambda m, a: FIXED[m.group(0)](a)),
    (r"(?<!\d)(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?!\d)", lambda m, a: _ymd(m.group(1), m.group(2), m.group(3), a)),
    (r"(?<!\d)(\d{4})[-/](\d{1,2})(?![-/.]?\d)", lambda m, a: _ym(m.group(1), m.group(2), a)),
    (r"(?:(\d{4})\s*年\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*[日號号]?",
     lambda m, a: _ymd(m.group(1), m.group(2), m.group(3), a)),
    (r"(?:(\d{4})\s*年\s*)?(\d{1,2})\s*月(?!\s*\d)", lambda m, a: _ym(m.group(1), m.group(2), a)),
    (r"(\d{4})\s*年(?!\s*\d)", lambda m, a: (date(int(m.group(1)), 1, 1), date(int(m.group(1)) + 1, 1, 1))),
    (rf"\b({MON})\.?\s+(\d{{4}})(?!\d)", lambda m, a: _ym(m.group(2), MONTHS[m.group(1).lower()], a)),
    (rf"\b({MON})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?![\da-z])(?:,?\s+(\d{{4}})(?!\d))?",
     lambda m, a: _ymd(m.group(3), MONTHS[m.group(1).lower()], m.group(2), a)),
    (rf"(?<!\d)(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({MON})\b\.?(?:,?\s+(\d{{4}})(?!\d))?",
     lambda m, a: _ymd(m.group(3), MONTHS[m.group(2).lower()], m.group(1), a)),
    (rf"\b({MON_ALONE})\b\.?", lambda m, a: _ym(None, MONTHS[m.group(1).lower()], a)),
    (r"(?<![\d/])(\d{1,2})/(\d{1,2})(?![\d/])", lambda m, a: _ymd(None, m.group(1), m.group(2), a)),
    (rf"\b({WD_EN})\b", lambda m, a: _weekday(WEEKDAYS.index(m.group(1).lower()), a)),
]
SPAN_COMPILED = [(rx(p, re.I), fn) for p, fn in SPAN_PARTS]
SPAN = "(?:" + "|".join(f"(?:{p})" for p, _ in SPAN_PARTS) + ")"
SPAN_RX = rx(SPAN)
PLAIN_WEEKDAY = rx(rf"^(?:{WD_EN})$", re.I)

RANGE_BETWEEN = rx(rf"\bbetween\s+(?P<a>{SPAN})\s+and\s+(?P<b>{SPAN})", re.I)
RANGE_TO = rx(
    rf"(?:\bfrom\s+|從\s*|自\s*|由\s*)?(?P<a>{SPAN})\s*(?:\bto\b|\buntil\b|\btill\b|\bthrough\b|到|至|~|～|—|–)\s*(?P<b>{SPAN})",
    re.I)
AFTER_PRE = rx(rf"(?:\bsince|\bafter|\bfrom|\bnewer\s+than|從|自)\s*(?P<a>{SPAN})\s*(?:起|開始|以來|之後|以後)?", re.I)
AFTER_POST = rx(rf"(?P<a>{SPAN})\s*(?:之後|以後|以來|後|起|開始)", re.I)
BEFORE_PRE = rx(rf"(?:\bbefore|\buntil|\btill|\bprior\s+to|\bolder\s+than|早於)\s*(?P<a>{SPAN})", re.I)
BEFORE_POST = rx(rf"(?P<a>{SPAN})\s*(?:之前|以前|前)(?!\s*\d)", re.I)
BARE = rx(rf"(?:\b(?P<pre>on|in|during)\s+)?(?P<a>{SPAN})", re.I)
REL_OP = rx(r"^(\d{1,4})([dwmy])$", re.I)


def span_of(text: str, anchor: date):
    text = text.strip()
    for rx, fn in SPAN_COMPILED:
        m = rx.fullmatch(text)
        if m:
            try:
                return fn(m, anchor)
            except (ValueError, KeyError, OverflowError):
                return None
    return None


# ───────────────────────── query parser ─────────────────────────

OP_KEYS = {
    "from": "from", "寄件人": "from", "寄件者": "from", "to": "to", "cc": "to", "收件人": "to", "收件者": "to",
    "subject": "subject", "主旨": "subject", "after": "after", "since": "after", "before": "before",
    "until": "before", "on": "on", "newer_than": "newer_than", "older_than": "older_than", "has": "has",
    "is": "is", "in": "category", "label": "category", "category": "category", "cat": "category",
    "類別": "category", "分類": "category", "account": "account", "信箱": "account",
}
OP_RE = rx(
    r"(?<![^\s(（])(-?)(" + "|".join(sorted(map(re.escape, OP_KEYS), key=len, reverse=True)) + r")\s*[:：]\s*"
    r"(\"[^\"]*\"|“[^”]*”|「[^」]*」|[^\s]+)", re.I)
QUOTE_RE = rx(r"(?<![^\s(（])(-?)(?:\"([^\"]+)\"|“([^”]+)”|「([^」]+)」|『([^』]+)』)")
ATTACH_NO = rx(r"\b(?:without|no|w/o)\s+(?:any\s+)?attachments?\b|沒有附件|沒附件|無附件|不含附件|不帶附件", re.I)
ATTACH_YES = rx(
    r"\b(?:with|has|have|having|containing|incl(?:uding)?)\s+(?:an?\s+|any\s+|some\s+)?"
    r"(?:attachments?|attached\s+files?|files?)\b|\battachments?\b|\battached\b|(?:有|帶|含|附|夾帶)?(?:附件|附檔|夾檔)",
    re.I)
UNREAD_RE = rx(r"\bunread\b|\bnot\s+(?:yet\s+)?read\b|\bunopened\b|未讀|沒讀過?|還沒讀|還沒看", re.I)
READ_RE = rx(r"\balready\s+read\b|已讀|看過的", re.I)
CATEGORY_RE = rx(
    "|".join(
        (r"\b" + re.escape(a).replace(r"\ ", r"\s+") + r"\b") if a.isascii() else re.escape(a)
        for a in sorted(ALIAS_TO_CATEGORY, key=len, reverse=True)
        if a not in ("other", "bulk", "events", "calendar", "invite", "invitation", "promo")
    ), re.I)
NAME_CHARS = r"[^\s,，。;；、!?！？]"
EN_FROM = rx(
    rf"\b(?P<kw>sent\s+by|written\s+by|(?:e-?mails?|mails?|messages?|letters?)\s+from|from|by)\s+"
    rf"(?P<v>\"[^\"]+\"|{NAME_CHARS}+(?:\s+{NAME_CHARS}+){{0,2}})", re.I)
EN_TO = rx(rf"\b(?:sent\s+to|addressed\s+to|cc(?:'?d)?|to)\s+(?P<v>\"[^\"]+\"|{NAME_CHARS}+(?:\s+{NAME_CHARS}+){{0,2}})", re.I)
ZH_FROM_KEY = rx(rf"(?:寄件人|寄件者|寄信人|發件人|發信人|來自)\s*(?:是|為|[:：])?\s*(?P<v>{NAME_CHARS}+)")
ZH_FROM_VERB = rx(
    rf"(?:從|由)?\s*(?P<v>{NAME_CHARS}+?)\s*(?:寄給我的|寄給我|寄過來的|寄來的|寄來|寄的|發來的|發來|傳來的|傳來|來的信|來信)")
ZH_TO_KEY = rx(rf"(?:寄給|發給|傳給|收件人是|收件者是)\s*(?P<v>{NAME_CHARS}+)")
EMAILISH = rx(r"^[\w.+%-]*@[\w.-]+$|^[\w-]+\.(?:example|com|org|net|io|dev|tw)$", re.I)

EN_STOP = set("""
a an the and of in on at for with about regarding re show me find search get list all any my our your i we you
emails email mail mails messages message thread threads conversation conversations please related concerning
that which who what where when is are was were be been some just only can could would will look looking need
""".split())
ZH_LEAD = ["請幫我找出", "請幫我找", "請幫我", "幫我找出", "幫我找", "幫我查", "幫我", "給我看", "給我", "找出", "搜尋",
           "查詢", "顯示", "列出", "所有", "全部", "請找", "找", "有關", "關於", "跟", "的"]
ZH_TAIL = ["的信件", "的郵件", "的信", "的那封", "那封", "信件", "郵件", "相關", "有關", "的", "信", "嗎", "呢", "吧"]
ZH_ALL = set(ZH_LEAD) | set(ZH_TAIL) | {"", "有", "和", "與", "或", "我", "請"}
ZH_CUT = ["的", "寄", "發", "傳", "有", "關於", "附件", "在", "和", "跟", "或"]
OR_WORDS = {"or", "或", "或是", "或者", "|"}
PERSON_QUOTED = rx(
    r"(?P<kw>\bsent\s+by|\bfrom|\bto|\bcc|寄件人|寄件者|來自|收件人|收件者|寄給)\s*[:：]?\s*"
    r"(?:\"(?P<a>[^\"]+)\"|“(?P<b>[^”]+)”|「(?P<c>[^」]+)」)")


def _clean_value(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] + v[-1] in ('""', "“”", "「」", "『』"):
        v = v[1:-1]
    return v.strip()


def strip_zh(chunk: str) -> str:
    """Peel request words off a Chinese chunk: `幫我找合約的信` -> `合約`; never leaves a lone character."""
    chunk = chunk.strip()
    while True:
        before = chunk
        for w in ZH_LEAD:
            if chunk.startswith(w) and (len(chunk) - len(w) >= 2 or chunk[len(w):] in ZH_ALL):
                chunk = chunk[len(w):]
                break
        for w in ZH_TAIL:
            if chunk.endswith(w) and (len(chunk) - len(w) >= 2 or chunk[: -len(w)] in ZH_ALL):
                chunk = chunk[: -len(w)]
                break
        if chunk == before:
            break
    return "" if chunk in ZH_ALL else chunk


def _cut_head(chunk: str) -> tuple[str, str]:
    """`王小明的合約` -> (`王小明`, `的合約`); `samira上週` -> (`samira`, `上週`)."""
    m = re.match(rf"[A-Za-z0-9._%+@-]+(?=[{CJK}])", chunk)
    if m:
        return m.group(0), chunk[m.end():]
    best = len(chunk)
    for w in ZH_CUT:
        i = chunk.find(w, 1)
        if 0 < i < best:
            best = i
    m = SPAN_RX.search(chunk, 1)
    if m and m.start() < best:
        best = m.start()
    return chunk[:best], chunk[best:]


class Parser:
    def __init__(self, text: str, anchor: date, resolver=None):
        self.raw = text or ""
        self.s = " " + re.sub(r"\s+", " ", self.raw) + " "
        self.anchor = anchor
        self.resolver = resolver
        self._book = None
        self.p = {
            "terms": [], "exclude": [], "from": [], "exclude_from": [], "to": [], "subject": [],
            "after": None, "before": None, "has_attachment": None, "unread": None,
            "category": [], "exclude_category": [], "account": None, "contacts": {}, "notes": [],
        }

    # helpers
    def _sub(self, rx, fn) -> None:
        def rep(m):
            out = fn(m)
            return " " if out is None else out
        self.s = rx.sub(rep, self.s)

    def _range(self, start, end) -> None:
        if start and (self.p["after"] is None or start > self.p["after"]):
            self.p["after"] = start
        if end and (self.p["before"] is None or end < self.p["before"]):
            self.p["before"] = end

    def _add(self, key: str, value: str) -> None:
        value = value.strip()
        if value and value.lower() not in (v.lower() for v in self.p[key]):
            self.p[key].append(value)

    def _lookup(self, name: str, min_score: int = 50) -> list[dict]:
        if self.resolver is not None:
            return self.resolver(name)
        if self._book is None:
            self._book = contacts_mod.all_contacts()
        return contacts_mod.resolve(name, min_score, self._book)

    def _person(self, key: str, value: str) -> None:
        self._add(key, value)
        hits = self._lookup(value)
        if hits:
            self.p["contacts"][value] = [{"name": c["name"], "email": c["email"]} for c in hits[:5]]

    def _category(self, word: str, negate: bool = False) -> bool:
        cat = ALIAS_TO_CATEGORY.get(re.sub(r"\s+", " ", word.strip().lower()))
        if not cat:
            return False
        self._add("exclude_category" if negate else "category", cat)
        return True

    def _known(self, name: str) -> bool:
        return bool(EMAILISH.match(name) or self._lookup(name, 70))

    # steps
    def operators(self) -> None:
        def op(m):
            neg, key, val = m.group(1) == "-", OP_KEYS[m.group(2).lower()], _clean_value(m.group(3))
            if not val:
                return None
            rest = ""
            if key in ("from", "to") and HAS_CJK.search(val) and not m.group(3)[:1] in "\"“「":
                val, rest = _cut_head(val)
            if key == "from":
                self._person("exclude_from" if neg else "from", val)
            elif key == "to":
                self._person("to", val)
            elif key == "subject":
                self._add("subject", val)
            elif key in ("after", "before", "on"):
                span = span_of(val, self.anchor)
                if not span:
                    self.p["notes"].append(f"unparsed date: {val}")
                elif key == "after":
                    self._range(span[0], None)
                elif key == "before":
                    self._range(None, span[0])
                else:
                    self._range(*span)
            elif key in ("newer_than", "older_than"):
                rm = REL_OP.match(val)
                if not rm:
                    self.p["notes"].append(f"unparsed {key}: {val}")
                else:
                    start, _ = _last_n(int(rm.group(1)), {"d": "day", "w": "week", "m": "month", "y": "year"}[rm.group(2).lower()], self.anchor)
                    self._range(start, None) if key == "newer_than" else self._range(None, start)
            elif key == "has":
                if val.lower() in ("attachment", "attachments", "file", "files", "附件", "附檔"):
                    self.p["has_attachment"] = not neg
                else:
                    self.p["notes"].append(f"unknown has:{val}")
            elif key == "is":
                v = val.lower()
                if v in ("unread", "未讀"):
                    self.p["unread"] = not neg
                elif v in ("read", "已讀"):
                    self.p["unread"] = neg
                elif not self._category(v, neg):
                    self.p["notes"].append(f"unknown is:{val}")
            elif key == "category":
                if val.lower() not in ("inbox", "all", "收件匣", "全部") and not self._category(val, neg):
                    self.p["notes"].append(f"unknown category: {val}")
            elif key == "account":
                self.p["account"] = val
            return f" {rest} " if rest else None
        self._sub(OP_RE, op)

    def quotes(self) -> None:
        def person(m):
            name = (m.group("a") or m.group("b") or m.group("c") or "").strip()
            kw = re.sub(r"\s+", " ", m.group("kw").lower())
            self._person("to" if kw in ("to", "cc", "收件人", "收件者", "寄給") else "from", name)
            return None
        self._sub(PERSON_QUOTED, person)

        def q(m):
            text = next(g for g in m.groups()[1:] if g)
            self._add("exclude" if m.group(1) == "-" else "terms", text.strip())
            return None
        self._sub(QUOTE_RE, q)

    def dates(self) -> None:
        def both(m):
            a, b = span_of(m.group("a"), self.anchor), span_of(m.group("b"), self.anchor)
            if not a or not b:
                return m.group(0)
            self._range(min(a[0], b[0]), max(a[1], b[1]))
            return None

        def after(m):
            a = span_of(m.group("a"), self.anchor)
            if not a:
                return m.group(0)
            self._range(a[0], None)
            return None

        def before(m):
            a = span_of(m.group("a"), self.anchor)
            if not a:
                return m.group(0)
            self._range(None, a[0])
            return None

        def bare(m):
            if not m.group("pre") and PLAIN_WEEKDAY.match(m.group("a").strip()):
                return m.group(0)
            a = span_of(m.group("a"), self.anchor)
            if not a:
                return m.group(0)
            self._range(*a)
            return None

        for rx, fn in ((RANGE_BETWEEN, both), (RANGE_TO, both), (AFTER_PRE, after), (BEFORE_PRE, before),
                       (AFTER_POST, after), (BEFORE_POST, before), (BARE, bare)):
            self._sub(rx, fn)

    def flags(self) -> None:
        def att(value):
            def fn(m):
                self.p["has_attachment"] = value
                return None
            return fn
        self._sub(ATTACH_NO, att(False))
        self._sub(ATTACH_YES, att(True))

        def unread(value):
            def fn(m):
                self.p["unread"] = value
                return None
            return fn
        self._sub(UNREAD_RE, unread(True))
        self._sub(READ_RE, unread(False))
        self._sub(CATEGORY_RE, lambda m: None if self._category(m.group(0)) else m.group(0))

    def people(self) -> None:
        def zh_key(key):
            def fn(m):
                name, rest = self._pick_head(m.group("v"))
                if not name:
                    return m.group(0)
                self._person(key, name)
                return f" {rest} "
            return fn

        def zh_verb(m):
            name, rest = self._pick_tail(m.group("v"))
            if not name or name == "我":
                return m.group(0)
            self._person("from", name)
            return f" {rest} "

        self._sub(ZH_FROM_KEY, zh_key("from"))
        self._sub(ZH_FROM_VERB, zh_verb)
        self._sub(ZH_TO_KEY, lambda m: m.group(0) if m.group("v").startswith("我") else zh_key("to")(m))

        def en(key):
            def fn(m):
                raw = m.group("v")
                if raw.startswith('"'):
                    name, rest = raw.strip('"'), ""
                else:
                    tokens = raw.split()
                    n = next((k for k in (3, 2, 1) if k <= len(tokens) and self._known(" ".join(tokens[:k]))), 0)
                    strong = key == "from" and not m.group("kw").lower().startswith("by")
                    if not n:
                        if not strong or tokens[0].lower() in EN_STOP:
                            return m.group(0)
                        n = 1
                    name, rest = " ".join(tokens[:n]), " ".join(tokens[n:])
                if name.lower() in ("me", "myself", "us"):
                    return m.group(0)
                self._person(key, name)
                return f" {rest} "
            return fn

        self._sub(EN_FROM, en("from"))

        def to_fn(m):
            raw = m.group("v")
            tokens = raw.strip('"').split()
            n = next((k for k in (3, 2, 1) if k <= len(tokens) and self._known(" ".join(tokens[:k]))), 0)
            if not n:
                return m.group(0)
            self._person("to", " ".join(tokens[:n]))
            return " " + " ".join(tokens[n:]) + " "
        self._sub(EN_TO, to_fn)

    def _pick_head(self, chunk: str) -> tuple[str, str]:
        chunk = chunk.strip()
        if not HAS_CJK.search(chunk):
            return chunk, ""
        for n in range(len(chunk), 1, -1):
            if self._known(chunk[:n]):
                return chunk[:n], chunk[n:]
        head, rest = _cut_head(chunk)
        return strip_zh(head), rest

    def _pick_tail(self, chunk: str) -> tuple[str, str]:
        chunk = chunk.strip()
        if not HAS_CJK.search(chunk):
            return chunk, ""
        for n in range(len(chunk), 1, -1):
            if self._known(chunk[-n:]):
                return chunk[-n:], chunk[:-n]
        name = strip_zh(chunk)
        return name, chunk[: len(chunk) - len(name)] if name and chunk.endswith(name) else ""

    def leftovers(self) -> None:
        raw = re.split(r"[\s,，。;；、!?！？()（）]+", self.s)
        words = []
        for w in raw:
            if not w:
                continue
            if w.lower() in OR_WORDS:
                pass
            elif HAS_CJK.search(w):
                w = strip_zh(w)
                if not w or w in ZH_TAIL or w in ZH_LEAD:
                    continue
            elif w.lower() in EN_STOP and not w.startswith("-"):
                continue
            words.append(w)
        out, i = [], 0
        while i < len(words):
            w = words[i]
            if w.lower() in OR_WORDS:
                i += 1
                continue
            if w.startswith("-") and len(w) > 1:
                self._add("exclude", w[1:].strip("'\""))
                i += 1
                continue
            group = [w.strip("'\"")]
            while i + 2 < len(words) and words[i + 1].lower() in OR_WORDS:
                group.append(words[i + 2].strip("'\""))
                i += 2
            out.append(group[0] if len(group) == 1 else group)
            i += 1
        for t in out:
            if t and t not in self.p["terms"]:
                self.p["terms"].append(t)

    def run(self) -> dict:
        self.operators()
        self.quotes()
        self.dates()
        self.flags()
        self.people()
        self.leftovers()
        p = self.p
        if p["after"] and p["before"] and p["after"] >= p["before"]:
            p["notes"].append("empty date range")
        p["after"] = p["after"].isoformat() if p["after"] else None
        p["before"] = p["before"].isoformat() if p["before"] else None
        p["raw"] = self.raw
        p["anchor"] = self.anchor.isoformat()
        p["canonical"] = canonical(p)
        return p


def parse_query(text: str, anchor: date | None = None, resolver=None) -> dict:
    return Parser(text, anchor or datetime.now(yhbmail.TZ).date(), resolver).run()


def _q(v: str) -> str:
    return f'"{v}"' if re.search(r"[\s:：]", v) else v


def canonical(p: dict) -> str:
    out = [f"from:{_q(v)}" for v in p["from"]] + [f"-from:{_q(v)}" for v in p["exclude_from"]]
    out += [f"to:{_q(v)}" for v in p["to"]] + [f"subject:{_q(v)}" for v in p["subject"]]
    if p["after"]:
        out.append(f"after:{p['after']}")
    if p["before"]:
        out.append(f"before:{p['before']}")
    if p["has_attachment"] is not None:
        out.append("has:attachment" if p["has_attachment"] else "-has:attachment")
    if p["unread"] is not None:
        out.append("is:unread" if p["unread"] else "is:read")
    out += [f"category:{c}" for c in p["category"]] + [f"-category:{c}" for c in p["exclude_category"]]
    if p["account"]:
        out.append(f"account:{_q(p['account'])}")
    for t in p["terms"]:
        out.append(" OR ".join(_q(x) for x in t) if isinstance(t, list) else _q(t))
    out += [f"-{_q(t)}" for t in p["exclude"]]
    return " ".join(out)


def explain(p: dict, lang: str = "en") -> list[dict]:
    zh = _zh(lang)
    chips = []

    def add(kind, en, zh_text, value=""):
        chips.append({"kind": kind, "text": zh_text if zh else en, "value": value})

    for v in p["from"]:
        who = ", ".join(c["email"] for c in p["contacts"].get(v, [])[:2])
        add("from", f"From: {v}" + (f" ({who})" if who else ""), f"寄件人：{v}" + (f"（{who}）" if who else ""), v)
    for v in p["exclude_from"]:
        add("exclude_from", f"Not from: {v}", f"排除寄件人：{v}", v)
    for v in p["to"]:
        add("to", f"To: {v}", f"收件人：{v}", v)
    for v in p["subject"]:
        add("subject", f"Subject: {v}", f"主旨：{v}", v)
    if p["after"] or p["before"]:
        last = (date.fromisoformat(p["before"]) - timedelta(days=1)).isoformat() if p["before"] else ""
        if p["after"] and p["before"]:
            text = (f"{p['after']} → {last}",) * 2 if p["after"] != last else (f"On {last}", f"日期：{last}")
        elif p["after"]:
            text = (f"Since {p['after']}", f"{p['after']} 起")
        else:
            text = (f"Before {p['before']}", f"{p['before']} 之前")
        add("date", text[0], text[1], f"{p['after'] or ''}..{p['before'] or ''}")
    if p["has_attachment"] is not None:
        add("has_attachment", *(("Has attachment", "有附件") if p["has_attachment"] else ("No attachment", "沒有附件")))
    if p["unread"] is not None:
        add("unread", *(("Unread", "未讀") if p["unread"] else ("Read", "已讀")))
    for c in p["category"]:
        add("category", f"Category: {CATEGORY_LABELS[c][0]}", f"類別：{CATEGORY_LABELS[c][1]}", c)
    for c in p["exclude_category"]:
        add("exclude_category", f"Not in: {CATEGORY_LABELS[c][0]}", f"排除類別：{CATEGORY_LABELS[c][1]}", c)
    if p["account"]:
        add("account", f"Account: {p['account']}", f"信箱：{p['account']}", p["account"])
    for t in p["terms"]:
        if isinstance(t, list):
            add("terms", "Words: " + " or ".join(t), "關鍵字：" + " 或 ".join(t), "|".join(t))
        else:
            add("terms", f"Words: {t}", f"關鍵字：{t}", t)
    for t in p["exclude"]:
        add("exclude", f"Without: {t}", f"排除：{t}", t)
    return chips


# ───────────────────────── index ─────────────────────────

def index_text(text: str) -> str:
    def bigrams(m):
        s = m.group(0)
        return f" {s} " if len(s) == 1 else " " + " ".join(s[i:i + 2] for i in range(len(s) - 1)) + " "
    return CJK_RUN.sub(bigrams, text or "")


def fts_expr(term: str) -> str | None:
    """FTS5 MATCH expression for one user term, or None when it needs LIKE instead."""
    tokens = TOKEN.findall(index_text(term.lower()))
    if not tokens or any(len(t) == 1 and HAS_CJK.match(t) for t in tokens):
        return None
    if len(tokens) == 1 and not HAS_CJK.search(tokens[0]):
        return f'"{tokens[0]}"*'
    return '"' + " ".join(tokens) + '"'


def _fts_ok(con) -> bool:
    try:
        con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS temp._tpi_fts_probe USING fts5(x)")
        con.execute("DROP TABLE temp._tpi_fts_probe")
        return True
    except sqlite3.OperationalError:
        return False


def _ensure_schema(con) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS search_docs (
            docid INTEGER PRIMARY KEY AUTOINCREMENT,
            email_id TEXT UNIQUE NOT NULL,
            stamp TEXT,
            att INTEGER DEFAULT 0
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5(
            subject, sender, recipients, body, tokenize = 'unicode61 remove_diacritics 2'
        );
        CREATE TRIGGER IF NOT EXISTS search_emails_deleted AFTER DELETE ON emails BEGIN
            DELETE FROM search_fts WHERE rowid IN (SELECT docid FROM search_docs WHERE email_id = old.id);
            DELETE FROM search_docs WHERE email_id = old.id;
        END;
        """
    )


def _signature(con) -> tuple:
    """Changes whenever mail is added, re-synced or deleted (the delete trigger shrinks search_docs)."""
    mail = tuple(con.execute(
        "SELECT COUNT(*), MAX(synced_at), TOTAL(date_ts), "
        "TOTAL(LENGTH(subject) + LENGTH(body_text) + LENGTH(from_addr) + LENGTH(to_addr)) FROM emails").fetchone())
    return mail + (con.execute("SELECT COUNT(*) FROM search_docs").fetchone()[0],)


def ensure_index(force: bool = False) -> dict:
    with _lock:
        con = yhbmail.db()
        try:
            if _index["engine"] is None:
                _index["engine"] = "fts5" if _fts_ok(con) else "like"
            if _index["engine"] != "fts5":
                return {"engine": "like", "indexed": 0, "removed": 0}
            _ensure_schema(con)
            sig = _signature(con)
            if not force and sig == _index["sig"]:
                return {"engine": "fts5", "indexed": 0, "removed": 0}
            current = {r[0]: r[1] or "" for r in con.execute("SELECT id, synced_at FROM emails")}
            have = {r[0]: (r[1], r[2] or "") for r in con.execute("SELECT email_id, docid, stamp FROM search_docs")}
            stale = [(eid, docid) for eid, (docid, stamp) in have.items()
                     if force or eid not in current or current[eid] != stamp]
            for _, docid in stale:
                con.execute("DELETE FROM search_fts WHERE rowid=?", (docid,))
                con.execute("DELETE FROM search_docs WHERE docid=?", (docid,))
            stale_ids = {eid for eid, _ in stale}
            todo = [eid for eid in current if eid not in have or eid in stale_ids]
            for i in range(0, len(todo), 200):
                chunk = todo[i:i + 200]
                marks = ",".join("?" for _ in chunk)
                for r in con.execute(
                        f"SELECT id, subject, snippet, body_text, from_addr, to_addr, synced_at FROM emails WHERE id IN ({marks})",
                        chunk).fetchall():
                    body = r["body_text"] or ""
                    if r["snippet"] and r["snippet"] not in body:
                        body = f"{r['snippet']}\n{body}"
                    att = 1 if ATTACH_HINT.search(body) else 0
                    cur = con.execute("INSERT INTO search_docs(email_id, stamp, att) VALUES (?,?,?)",
                                      (r["id"], r["synced_at"] or "", att))
                    con.execute("INSERT INTO search_fts(rowid, subject, sender, recipients, body) VALUES (?,?,?,?,?)",
                                (cur.lastrowid, index_text(r["subject"]), index_text(r["from_addr"]),
                                 index_text(r["to_addr"]), index_text(body)))
            con.commit()
            _index["docs"] = con.execute("SELECT COUNT(*) FROM search_docs").fetchone()[0]
            _index["sig"] = sig[:-1] + (_index["docs"],)
            _index["built_at"] = yhbmail.now_iso()
            return {"engine": "fts5", "indexed": len(todo), "removed": len(stale)}
        finally:
            con.close()


def index_status() -> dict:
    ensure_index()
    con = yhbmail.db()
    emails = con.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
    docs = con.execute("SELECT COUNT(*) FROM search_docs").fetchone()[0] if _index["engine"] == "fts5" else 0
    con.close()
    return {"engine": _index["engine"], "emails": emails, "indexed": docs, "built_at": _index["built_at"],
            "fresh": _index["engine"] != "fts5" or docs == emails}


# ───────────────────────── search ─────────────────────────

def _like(v: str) -> str:
    return "%" + v.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _like_any(term: str, args: list) -> str:
    args.extend([_like(term)] * len(LIKE_FIELDS))
    return "(" + " OR ".join(f"{f} LIKE ? ESCAPE '\\'" for f in LIKE_FIELDS) + ")"


def build_sql(p: dict, account=None, category=None, use_fts: bool = True) -> tuple[str | None, list[str], list]:
    where, args = [], []
    match_parts = []
    for t in p["terms"]:
        group = t if isinstance(t, list) else [t]
        exprs = [fts_expr(x) for x in group] if use_fts else [None]
        if all(exprs):
            match_parts.append("(" + " OR ".join(exprs) + ")" if len(exprs) > 1 else exprs[0])
        else:
            where.append("(" + " OR ".join(_like_any(x, args) for x in group) + ")")
    for t in p["exclude"]:
        expr = fts_expr(t) if use_fts else None
        if expr:
            where.append("e.id NOT IN (SELECT d2.email_id FROM search_fts JOIN search_docs d2 "
                         "ON d2.docid = search_fts.rowid WHERE search_fts MATCH ?)")
            args.append(expr)
        else:
            where.append("NOT " + _like_any(t, args))
    for key, col, joiner in (("from", "e.from_addr", " OR "), ("to", "e.to_addr", " OR ")):
        if p[key]:
            where.append("(" + joiner.join(f"{col} LIKE ? ESCAPE '\\'" for _ in p[key]) + ")")
            args.extend(_like(v) for v in p[key])
    for v in p["exclude_from"]:
        where.append("e.from_addr NOT LIKE ? ESCAPE '\\'")
        args.append(_like(v))
    for v in p["subject"]:
        where.append("e.subject LIKE ? ESCAPE '\\'")
        args.append(_like(v))
    if p["after"]:
        where.append("e.date_ts >= ?")
        args.append(_ts(p["after"]))
    if p["before"]:
        where.append("e.date_ts < ?")
        args.append(_ts(p["before"]))
    if p["has_attachment"] is not None:
        hint = "COALESCE(d.att, 0) = 1" if use_fts else _attach_like(args)
        where.append(f"(e.has_attachment = 1 OR {hint})" if p["has_attachment"] else f"NOT (e.has_attachment = 1 OR {hint})")
    if p["unread"] is not None:
        where.append("e.unread = ?")
        args.append(1 if p["unread"] else 0)
    cats = list(p["category"])
    if category and category != "all":
        where.append("e.category = ?")
        args.append(category)
    if cats:
        where.append("e.category IN (" + ",".join("?" for _ in cats) + ")")
        args.extend(cats)
    if p["exclude_category"]:
        where.append("e.category NOT IN (" + ",".join("?" for _ in p["exclude_category"]) + ")")
        args.extend(p["exclude_category"])
    for acc in (p["account"], account):
        if acc:
            where.append("e.account LIKE ? ESCAPE '\\'")
            args.append(_like(acc))
    match = " AND ".join(match_parts) if match_parts else None
    return match, where, args


def _attach_like(args: list) -> str:
    words = ("attached", "attachment", "附件", ".pdf")
    args.extend(_like(w) for w in words)
    return "(" + " OR ".join("e.body_text LIKE ? ESCAPE '\\'" for _ in words) + ")"


def _ts(iso: str) -> int:
    d = date.fromisoformat(iso)
    return int(datetime(d.year, d.month, d.day, tzinfo=yhbmail.TZ).timestamp())


def _needles(p: dict) -> list[str]:
    out = []
    for t in p["terms"]:
        for x in (t if isinstance(t, list) else [t]):
            out.append(x.lower())
    return out


def highlight(row: dict, needles: list[str], width: int = 150) -> str:
    text = re.sub(r"\s+", " ", (row.get("body_text") or row.get("snippet") or "")).strip()
    low = text.lower()
    pos = min((i for i in (low.find(n) for n in needles if n) if i >= 0), default=-1)
    if pos < 0:
        return text[:width] + ("…" if len(text) > width else "")
    start = max(0, pos - width // 3)
    piece = text[start:start + width]
    return ("…" if start else "") + piece + ("…" if start + width < len(text) else "")


def run_search(p: dict, account=None, category=None, limit: int = 50, offset: int = 0, sort: str = "auto") -> dict:
    status = ensure_index()
    use_fts = status["engine"] == "fts5"
    match, where, args = build_sql(p, account, category, use_fts)
    cond = (" AND " + " AND ".join(where)) if where else ""
    if match:
        base = ("FROM search_fts JOIN search_docs d ON d.docid = search_fts.rowid "
                "JOIN emails e ON e.id = d.email_id WHERE search_fts MATCH ?" + cond)
        args = [match] + args
        rank = "bm25(search_fts, 6.0, 4.0, 1.5, 1.0)"
    else:
        join = "LEFT JOIN search_docs d ON d.email_id = e.id " if use_fts else ""
        base = f"FROM emails e {join}WHERE 1=1" + cond
        rank = "0"
    att = "COALESCE(d.att, 0)" if use_fts else "0"
    order = "e.date_ts DESC" if sort == "date" or not match else "rank, e.date_ts DESC"
    con = yhbmail.db()
    try:
        total = con.execute(f"SELECT COUNT(*) {base}", args).fetchone()[0]
        rows = [dict(r) for r in con.execute(
            f"SELECT e.*, {att} AS att_hint, {rank} AS rank {base} ORDER BY {order} LIMIT ? OFFSET ?",
            args + [limit, offset])]
    except sqlite3.OperationalError as e:
        con.close()
        return {"emails": [], "total": 0, "engine": status["engine"], "error": f"query failed: {e}"[:300]}
    con.close()
    needles = _needles(p)
    out = []
    for r in rows:
        r["labels"] = json.loads(r.pop("labels_json", None) or "[]")
        r["attachment_flagged"] = bool(r["has_attachment"])
        r["has_attachment"] = bool(r["has_attachment"] or r.pop("att_hint", 0))
        r["score"] = round(-float(r.pop("rank") or 0), 4)
        r["highlight"] = highlight(r, needles)
        out.append(r)
    return {"emails": out, "total": total, "engine": status["engine"], "sort": "date" if not match or sort == "date" else "relevance",
            "terms": needles}


# ───────────────────────── anchor + agent ─────────────────────────

def anchor_date(value=None) -> tuple[date, str]:
    for raw, source in ((value, "param"), (os.environ.get("OPENINBOX_TODAY"), "env")):
        if raw:
            try:
                return date.fromisoformat(str(raw)[:10]), source
            except ValueError:
                pass
    if (yhbmail.load_cfg().get("mode") or "demo") == "demo":
        con = yhbmail.db()
        ts = con.execute("SELECT MAX(date_ts) FROM emails").fetchone()[0]
        con.close()
        if ts:
            return datetime.fromtimestamp(ts, yhbmail.TZ).date(), "demo"
    return datetime.now(yhbmail.TZ).date(), "clock"


REWRITE_PROMPT = {
    "en": (
        "Rewrite the user's email search request as ONE line of search operators, nothing else.\n"
        "Operators: from:NAME to:NAME subject:WORD after:YYYY-MM-DD before:YYYY-MM-DD (exclusive) "
        "has:attachment is:unread is:read category:{cats} -WORD (exclude), plus plain keywords. "
        "Quote values with spaces. Today is {today}. Never invent names or dates that the request does not imply.\n"
        "Request: {q}"),
    "zh": (
        "把使用者的找信需求改寫成「一行」搜尋運算式，不要其他文字。\n"
        "可用：from:寄件人 to:收件人 subject:主旨字 after:YYYY-MM-DD before:YYYY-MM-DD（不含當天） "
        "has:attachment is:unread is:read category:{cats} -字（排除），其餘放關鍵字。"
        "含空白的值用雙引號。今天是 {today}。需求沒提到的人名、日期不可自行編造。\n"
        "需求：{q}"),
}


def clean_agent_line(text: str) -> str:
    text = re.sub(r"```[a-z]*", "", text or "").strip()
    for line in text.splitlines():
        line = line.strip().strip("`").strip()
        line = re.sub(r"^(?:query|search|搜尋|查詢)\s*[:：]\s*", "", line, flags=re.I)
        if line:
            return line[:300]
    return ""


def ask_agent(prompt: str, lang: str) -> tuple[str, str, str | None]:
    cfg = agent_bridge.load_agent_cfg()
    driver = cfg.get("driver") or "local"
    if driver == "local":
        return "", "local", None
    try:
        if driver == "openai_compatible":
            block = cfg.get("openai_compatible") or {}
            key = os.environ.get(block.get("api_key_env") or "OPENAI_API_KEY") or ""
            body = json.dumps({"model": block.get("model") or "gpt-4.1-mini", "temperature": 0,
                               "messages": [{"role": "user", "content": prompt}]}).encode()
            data = agent_bridge._post_json(
                (block.get("base_url") or "").rstrip("/") + "/chat/completions",
                {"Content-Type": "application/json", **({"Authorization": f"Bearer {key}"} if key else {})},
                body, timeout=60, allow_private=bool(block.get("allow_private")))
            text = data["choices"][0]["message"]["content"] or ""
        elif driver in ("cli", "http"):
            pack = {"ask": prompt, "lang": "zh-Hant" if _zh(lang) else "en", "mode": "search_rewrite"}
            text = agent_bridge._cli(pack, cfg) if driver == "cli" else agent_bridge._http(pack, cfg)
        else:
            return "", driver, f"unknown agent driver {driver}"
    except Exception as e:
        return "", driver, f"{type(e).__name__}: {e}"[:300]
    line = clean_agent_line(text)
    return line, driver, None if line else "agent returned an empty answer"


def agent_rewrite(q: str, lang: str, anchor: date) -> dict:
    zh = _zh(lang)
    prompt = REWRITE_PROMPT["zh" if zh else "en"].format(q=q, today=anchor.isoformat(), cats="|".join(CATEGORIES))
    line, driver, error = ask_agent(prompt, lang)
    if driver == "local":
        note = ("未接 LLM（agent.json 的 driver 為 local），改用內建規則解析。" if zh
                else "No LLM wired (agent.json driver is local); using the built-in parser.")
        return {"used": False, "driver": "local", "query": "", "error": None, "note": note}
    if error:
        note = (f"BYO agent（{driver}）改寫失敗，改用內建規則解析：{error}" if zh
                else f"BYO agent ({driver}) rewrite failed; using the built-in parser: {error}")
        return {"used": False, "driver": driver, "query": "", "error": error, "note": note}
    note = f"BYO agent（{driver}）改寫為：{line}" if zh else f"BYO agent ({driver}) rewrote it as: {line}"
    return {"used": True, "driver": driver, "query": line, "error": None, "note": note}


def search_request(q: str, lang: str, account=None, category=None, limit: int = 50, offset: int = 0,
                   sort: str = "auto", today=None, agent: bool = False) -> dict:
    q = (q or "").strip()[:500]
    anchor, source = anchor_date(today)
    rewrite = None
    parsed = parse_query(q, anchor)
    if agent and q:
        rewrite = agent_rewrite(q, lang, anchor)
        if rewrite["used"]:
            rewrite["heuristic"] = parsed["canonical"]
            parsed = parse_query(rewrite["query"], anchor)
    result = run_search(parsed, account=account, category=category, limit=limit, offset=offset, sort=sort)
    out = {"q": q, "parsed": parsed, "canonical": parsed["canonical"], "explain": explain(parsed, lang),
           "anchor": anchor.isoformat(), "anchor_source": source, "lang": "zh-Hant" if _zh(lang) else "en",
           "limit": limit, "offset": offset, **result}
    if rewrite is not None:
        out["rewrite"] = rewrite
    return out


# ───────────────────────── routes ─────────────────────────

def _lang(req) -> str:
    return "zh-Hant" if req.lang_zh() else "en"


def _params(src: dict) -> dict:
    sort = str(src.get("sort") or "auto")
    return {"account": src.get("account") or None, "category": src.get("category") or None,
            "limit": _int(src.get("limit"), 50, 1, 500), "offset": _int(src.get("offset"), 0, 0, 100000),
            "sort": sort if sort in ("auto", "date", "relevance") else "auto", "today": src.get("today")}


@get("/api/search")
def search_get(req):
    return search_request(req.query.get("q") or "", _lang(req), **_params(req.query),
                          agent=str(req.query.get("agent") or "").lower() in ("1", "true", "yes"))


@post("/api/search")
def search_post(req):
    b = req.body
    if not isinstance(b.get("q", ""), str):
        return {"error": "q must be a string"}, 400
    return search_request(b.get("q") or "", _lang(req), **_params(b), agent=bool(b.get("agent")))


@get("/api/search/parse")
def search_parse(req):
    anchor, source = anchor_date(req.query.get("today"))
    parsed = parse_query(req.query.get("q") or "", anchor)
    return {"parsed": parsed, "canonical": parsed["canonical"], "explain": explain(parsed, _lang(req)),
            "anchor": anchor.isoformat(), "anchor_source": source}


@get("/api/search/status")
def search_status(req):
    return index_status()


@post("/api/search/reindex")
def search_reindex(req):
    out = ensure_index(force=True)
    return {"ok": True, **out, **index_status()}
