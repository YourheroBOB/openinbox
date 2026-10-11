"""Composer + AI Write: new mail, reply and forward as local drafts. Nothing is ever sent.

- Drafts live in the core `drafts` table (this module adds columns), so the core
  Drafts view keeps listing them and the local-cache clear keeps them.
- AI Write drafts from the thread, the persona, the learned voice and the draft
  style (Professional / Balanced / Casual). With a BYO agent (agent.json driver
  openai_compatible / cli / http) the agent writes; otherwise a rule-based writer
  fills a template, labelled as heuristic, and writes [TBD] / [待填] wherever a
  fact would have to be invented.
- Rewrite: more formal / shorter / friendlier, or a free-form instruction.
- Voice learning: saving a draft that was edited from AI text keeps the pair as a
  voice sample (compose_voice_samples) and folds a profile into persona.json under
  `voice` (plus learned lines in `how_you_write`). Samples are the user's own
  record: they survive a cache clear, and persona.rebuild re-attaches them.
- CJK font choice for the composer or the whole app: local font stacks only.
"""
from __future__ import annotations

import difflib
import json
import os
import re
import statistics
from collections import Counter
from urllib.parse import unquote

import agent_bridge
import persona
import yhbmail
from features import get, post

KINDS = ("new", "reply", "forward")
TONES = ("formal", "shorter", "friendlier")

STYLES = {
    "professional": {
        "en": "Professional", "zh": "專業",
        "desc_en": "Formal greeting and sign-off, complete sentences, no slang.",
        "desc_zh": "正式稱謂與結語，完整句子，不用口語。",
        "greet_en": "Dear {name},", "greet_en_anon": "Hello,",
        "greet_zh": "{name} 您好：", "greet_zh_anon": "您好：",
        "close_en": "Best regards,", "close_zh": "敬祝 順心",
        "thanks_en": "Thank you for your email regarding “{subject}”.",
        "thanks_zh": "感謝您來信說明「{subject}」。",
    },
    "balanced": {
        "en": "Balanced", "zh": "平衡",
        "desc_en": "Friendly but to the point. The default.",
        "desc_zh": "友善但直接，預設值。",
        "greet_en": "Hi {name},", "greet_en_anon": "Hi there,",
        "greet_zh": "{name} 你好：", "greet_zh_anon": "你好：",
        "close_en": "Best,", "close_zh": "謝謝！",
        "thanks_en": "Thanks for your note about “{subject}”.",
        "thanks_zh": "謝謝你的來信（「{subject}」）。",
    },
    "casual": {
        "en": "Casual", "zh": "輕鬆",
        "desc_en": "Short and relaxed, like a message to a teammate.",
        "desc_zh": "簡短輕鬆，像傳訊息給同事。",
        "greet_en": "Hey {name},", "greet_en_anon": "Hey,",
        "greet_zh": "嗨 {name}，", "greet_zh_anon": "嗨，",
        "close_en": "Cheers,", "close_zh": "先這樣，再聊！",
        "thanks_en": "Thanks for the note!",
        "thanks_zh": "收到，謝啦！",
    },
}
STYLE_IDS = list(STYLES)

FONTS = [
    {"id": "system", "en": "System default", "zh": "系統預設", "lang": "", "stack": ""},
    {"id": "sans_tc", "en": "Sans · Traditional Chinese (Noto Sans TC)", "zh": "黑體 · 繁中（思源黑體 TC）",
     "lang": "zh-Hant",
     "stack": '"Noto Sans TC", "Source Han Sans TC", "PingFang TC", "Microsoft JhengHei", "Heiti TC", sans-serif'},
    {"id": "serif_tc", "en": "Serif · Traditional Chinese (Noto Serif TC)", "zh": "明體 · 繁中（思源宋體 TC）",
     "lang": "zh-Hant",
     "stack": '"Noto Serif TC", "Source Han Serif TC", "Songti TC", "PMingLiU", "MingLiU", serif'},
    {"id": "kai_tc", "en": "Kai · Traditional Chinese (LXGW WenKai TC)", "zh": "楷體 · 繁中（霞鶩文楷 TC）",
     "lang": "zh-Hant",
     "stack": '"LXGW WenKai TC", "Kaiti TC", "BiauKai", "DFKai-SB", "STKaiti", serif'},
    {"id": "sans_sc", "en": "Sans · Simplified Chinese (Noto Sans SC)", "zh": "黑體 · 簡中（思源黑體 SC）",
     "lang": "zh-Hans",
     "stack": '"Noto Sans SC", "Source Han Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif'},
    {"id": "sans_jp", "en": "Gothic · Japanese (Noto Sans JP)", "zh": "黑體 · 日文（Noto Sans JP）",
     "lang": "ja",
     "stack": '"Noto Sans JP", "Source Han Sans JP", "Hiragino Sans", "Hiragino Kaku Gothic ProN", '
              '"Yu Gothic", "Meiryo", sans-serif'},
    {"id": "serif_jp", "en": "Mincho · Japanese (Noto Serif JP)", "zh": "明朝 · 日文（Noto Serif JP）",
     "lang": "ja",
     "stack": '"Noto Serif JP", "Source Han Serif JP", "Hiragino Mincho ProN", "Yu Mincho", "MS Mincho", serif'},
    {"id": "sans_kr", "en": "Gothic · Korean (Noto Sans KR)", "zh": "黑體 · 韓文（Noto Sans KR）",
     "lang": "ko",
     "stack": '"Noto Sans KR", "Source Han Sans K", "Apple SD Gothic Neo", "Malgun Gothic", sans-serif'},
    {"id": "serif_kr", "en": "Myeongjo · Korean (Noto Serif KR)", "zh": "明朝 · 韓文（Noto Serif KR）",
     "lang": "ko",
     "stack": '"Noto Serif KR", "Source Han Serif K", "AppleMyungjo", "Batang", serif'},
    {"id": "mono_cjk", "en": "Monospace · CJK (Sarasa Mono)", "zh": "等寬 · 中日韓（更紗黑體 Mono）",
     "lang": "",
     "stack": '"Sarasa Mono TC", "Noto Sans Mono CJK TC", "Menlo", "Consolas", monospace'},
]
FONT_IDS = [f["id"] for f in FONTS]
FONT_SCOPES = ("compose", "app")
DEFAULT_SETTINGS = {"style": "balanced", "font": "system", "font_scope": "compose", "font_size": 15}

GREETING_EN = re.compile(r"^(dear|hi|hello|hey|good (?:morning|afternoon|evening)|greetings)\b", re.I)
GREETING_ZH = re.compile(r"(您好|你好|嗨|哈囉)")
CLOSING_RE = re.compile(
    r"^(best( regards| wishes)?|kind regards|warm regards|regards|cheers|thanks( so much| again)?|thank you|"
    r"many thanks|sincerely|talk soon|all the best|敬祝\s*\S{0,4}|祝\S{0,4}|謝謝(你|您)?(，祝順心)?|感謝(你|您)?|"
    r"先這樣(，再聊)?|再聊|敬上|順心)[,，!！.。～]?$", re.I)
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|(?<=[。！？])\s*|\n+")
QUESTION_RE = re.compile(r"(\?|？|can you|could you|would you|will you|let me know|please|reply with|"
                         r"need (a|your)|yes/no|請|麻煩|是否|需要)", re.I)
DEADLINE_RE = re.compile(
    r"\b(?:by|before|due|until|no later than)\s+[^.,;!?\n]{2,40}|"
    r"\d{1,2}月\d{1,2}日(?:前|之前)?|\d{4}-\d{2}-\d{2}", re.I)
CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]")
EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]")
ADDR_RE = re.compile(r"^[^@\s<>,;]+@[^@\s<>,;]+\.[^@\s<>,;]+$")

CONTRACTIONS = [
    (r"\bcan't\b", "cannot"), (r"\bwon't\b", "will not"), (r"\bshan't\b", "shall not"),
    (r"\bI'm\b", "I am"), (r"\bI've\b", "I have"), (r"\bI'll\b", "I will"), (r"\bI'd\b", "I would"),
    (r"\bwe're\b", "we are"), (r"\bwe've\b", "we have"), (r"\bwe'll\b", "we will"),
    (r"\byou're\b", "you are"), (r"\byou've\b", "you have"), (r"\byou'll\b", "you will"),
    (r"\bthey're\b", "they are"), (r"\bit's\b", "it is"), (r"\bthat's\b", "that is"),
    (r"\bthere's\b", "there is"), (r"\blet's\b", "let us"), (r"\bisn't\b", "is not"),
    (r"\baren't\b", "are not"), (r"\bwasn't\b", "was not"), (r"\bdon't\b", "do not"),
    (r"\bdoesn't\b", "does not"), (r"\bdidn't\b", "did not"), (r"\bhaven't\b", "have not"),
    (r"\bcouldn't\b", "could not"), (r"\bwouldn't\b", "would not"), (r"\bshouldn't\b", "should not"),
]
CASUAL_EN = [
    (r"\bgonna\b", "going to"), (r"\bwanna\b", "want to"), (r"\byeah\b", "yes"), (r"\byep\b", "yes"),
    (r"\bASAP\b", "as soon as possible"), (r"\bthx\b", "thank you"), (r"\bthanks a lot\b", "thank you very much"),
    (r"\bthanks\b", "thank you"), (r"\bFYI\b", "for your information"), (r"\bkinda\b", "somewhat"),
]
CASUAL_ZH = [
    ("謝謝啦", "謝謝"), ("謝啦", "謝謝"), ("沒問題", "沒有問題"), ("OK", "可以"), ("ok", "可以"),
    ("啦", ""), ("喔", ""), ("哦", ""), ("～", "。"), ("~", "。"),
]
FILLER_SENTENCES = re.compile(
    r"^(i hope (this|the) (e-?mail|message|note) finds you well|hope (you are|you're|all is) (doing )?well|"
    r"i hope you('re| are) (doing )?well|i just wanted to (reach out|follow up|check in)|i wanted to reach out|"
    r"please (do not|don't) hesitate to (contact|reach out)|please let me know if you have any questions|"
    r"feel free to (reach out|contact me|let me know)|thank you for your (time|attention)|"
    r"希望你一切都好|希望您一切都好|希望你一切順利|不好意思打擾了?|如有任何問題.{0,12}|有任何問題.{0,12}|"
    r"thanks in advance)",
    re.I)
FILLER_WORDS_EN = re.compile(r"\b(just|really|actually|basically|very|quite|simply|definitely)\s+", re.I)
FILLER_WORDS_ZH = re.compile(r"(其實|基本上|真的|非常地?|就是說)")

INSTRUCTION_KEYS = [
    ("formal", re.compile(r"(formal|polite|professional|正式|禮貌|客氣|專業)", re.I)),
    ("shorter", re.compile(r"(short|brief|concise|trim|簡短|精簡|短一點|縮短|簡潔)", re.I)),
    ("friendlier", re.compile(r"(friendl|warm|kind|casual|親切|友善|溫和|輕鬆|熱情)", re.I)),
    ("bullets", re.compile(r"(bullet|list|條列|列點|分點)", re.I)),
    ("thanks", re.compile(r"(thank|gratitude|感謝|謝謝|致謝)", re.I)),
    ("apology", re.compile(r"(apolog|sorry|道歉|抱歉|致歉)", re.I)),
]

LEARNED_PREFIX = "Learned from your edits: "


def _zh(lang) -> bool:
    return str(lang or "").lower().startswith("zh")


def _lang(req) -> str:
    return "zh-Hant" if req.lang_zh() else "en"


def _text_lang(text: str) -> str:
    text = text or ""
    letters = sum(1 for c in text if c.isalpha())
    return "zh" if letters and len(CJK_RE.findall(text)) / letters > 0.2 else "en"


def _clip(value, n: int) -> str:
    return str(value or "")[:n]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def _tbd(lang) -> str:
    return "[待填]" if _zh(lang) else "[TBD]"


# ───────────────────────── storage ─────────────────────────

DRAFT_COLUMNS = {"kind": "TEXT", "cc": "TEXT", "bcc": "TEXT", "quote": "TEXT", "ai_body": "TEXT",
                 "style": "TEXT", "font": "TEXT", "source_id": "TEXT", "lang": "TEXT", "updated_at": "TEXT"}


_ensured: set = set()


def ensure_tables() -> None:
    if str(yhbmail.DB) in _ensured and yhbmail.DB.exists():
        return
    yhbmail.init_db()
    con = yhbmail.db()
    have = {r[1] for r in con.execute("PRAGMA table_info(drafts)")}
    for col, typ in DRAFT_COLUMNS.items():
        if col not in have:
            con.execute(f"ALTER TABLE drafts ADD COLUMN {col} {typ}")
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS compose_settings (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS compose_voice_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            draft_id INTEGER,
            lang TEXT,
            ai_text TEXT,
            final_text TEXT,
            ratio REAL,
            created_at TEXT,
            updated_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_compose_voice_draft ON compose_voice_samples(draft_id);
        """
    )
    con.commit()
    con.close()
    _ensured.add(str(yhbmail.DB))


# ───────────────────────── settings ─────────────────────────

def font_by_id(font_id: str) -> dict:
    return next((f for f in FONTS if f["id"] == font_id), FONTS[0])


def load_settings() -> dict:
    ensure_tables()
    con = yhbmail.db()
    raw = {r["key"]: r["value"] for r in con.execute("SELECT key, value FROM compose_settings")}
    con.close()
    out = dict(DEFAULT_SETTINGS)
    for key in out:
        if key in raw:
            try:
                out[key] = json.loads(raw[key])
            except json.JSONDecodeError:
                pass
    if out["style"] not in STYLES:
        out["style"] = DEFAULT_SETTINGS["style"]
    if out["font"] not in FONT_IDS:
        out["font"] = DEFAULT_SETTINGS["font"]
    if out["font_scope"] not in FONT_SCOPES:
        out["font_scope"] = DEFAULT_SETTINGS["font_scope"]
    return out


def save_settings(changes: dict) -> tuple[dict, int]:
    clean = {}
    if "style" in changes:
        if changes["style"] not in STYLES:
            return {"error": f"style must be one of {', '.join(STYLE_IDS)}"}, 400
        clean["style"] = changes["style"]
    if "font" in changes:
        if changes["font"] not in FONT_IDS:
            return {"error": "unknown font", "fonts": FONT_IDS}, 400
        clean["font"] = changes["font"]
    if "font_scope" in changes:
        if changes["font_scope"] not in FONT_SCOPES:
            return {"error": f"font_scope must be one of {', '.join(FONT_SCOPES)}"}, 400
        clean["font_scope"] = changes["font_scope"]
    if "font_size" in changes:
        try:
            size = int(changes["font_size"])
        except (TypeError, ValueError):
            return {"error": "font_size must be a number"}, 400
        clean["font_size"] = max(12, min(24, size))
    ensure_tables()
    con = yhbmail.db()
    for key, value in clean.items():
        con.execute("INSERT INTO compose_settings(key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, json.dumps(value)))
    con.commit()
    con.close()
    return load_settings(), 200


def settings_view(lang: str) -> dict:
    zh = _zh(lang)
    s = load_settings()
    font = font_by_id(s["font"])
    return {
        **s,
        "font_stack": font["stack"], "font_lang": font["lang"],
        "styles": [{"id": k, "name": v["zh" if zh else "en"], "description": v["desc_zh" if zh else "desc_en"],
                    "sample": sample_opening(k, lang)} for k, v in STYLES.items()],
        "fonts": [{"id": f["id"], "name": f["zh" if zh else "en"], "lang": f["lang"], "stack": f["stack"]}
                  for f in FONTS],
        "font_scopes": list(FONT_SCOPES),
        "tones": list(TONES),
    }


def sample_opening(style: str, lang: str) -> str:
    st = STYLES[style]
    if _zh(lang):
        return f"{st['greet_zh'].format(name='Maya')}\n{st['thanks_zh'].format(subject='設計審查')}\n{st['close_zh']}"
    return f"{st['greet_en'].format(name='Maya')}\n{st['thanks_en'].format(subject='Design review')}\n{st['close_en']}"


# ───────────────────────── addresses + prefill ─────────────────────────

def parse_addr(raw: str) -> tuple[str, str]:
    raw = (raw or "").strip()
    m = re.match(r'^"?([^"<]*?)"?\s*<([^>]+)>', raw)
    if m:
        name, addr = m.group(1).strip(), m.group(2).strip()
        return name or addr, addr
    return raw, raw


def first_name(raw: str) -> str:
    """Greeting name from an address; empty for bulk senders or when nothing usable."""
    name, addr = parse_addr(raw.split(",")[0] if raw else "")
    low = addr.lower()
    if not addr or any(x in low for x in yhbmail.NOISE_FROM):
        return ""
    if name and name != addr and "@" not in name:
        return name.split()[0] if not CJK_RE.search(name) else name
    local = addr.split("@")[0]
    return local.capitalize() if local.isalpha() else ""


def split_addrs(value: str) -> list[str]:
    return [a.strip() for a in re.split(r"[,;，；]", value or "") if a.strip()]


def address_warnings(fields: dict, lang: str) -> list[str]:
    zh = _zh(lang)
    out = []
    for key in ("to", "cc", "bcc"):
        for a in split_addrs(fields.get(key) or ""):
            if not ADDR_RE.match(parse_addr(a)[1]):
                out.append(f"{key}：「{a}」不像信箱位址" if zh else f"{key}: '{a}' does not look like an address")
    return out


def _prefix(subject: str, tag: str) -> str:
    subject = (subject or "").strip()
    if re.match(rf"^{tag}\s*[:：]", subject, re.I):
        return subject
    return f"{tag}: {subject}".strip()


def reply_quote(item: dict, lang: str) -> str:
    body = (item.get("body_text") or item.get("snippet") or "").strip()
    quoted = "\n".join("> " + ln if ln.strip() else ">" for ln in body.splitlines()) or ">"
    who = item.get("from_addr") or ""
    when = item.get("date_raw") or ""
    head = f"{when}，{who} 寫道：" if _zh(lang) else f"On {when}, {who} wrote:"
    return f"{head}\n{quoted}"


def forward_quote(item: dict, lang: str) -> str:
    body = (item.get("body_text") or item.get("snippet") or "").strip()
    if _zh(lang):
        head = ["---------- 轉寄的郵件 ----------", f"寄件者：{item.get('from_addr') or ''}",
                f"日期：{item.get('date_raw') or ''}", f"主旨：{item.get('subject') or ''}",
                f"收件者：{item.get('to_addr') or ''}"]
    else:
        head = ["---------- Forwarded message ----------", f"From: {item.get('from_addr') or ''}",
                f"Date: {item.get('date_raw') or ''}", f"Subject: {item.get('subject') or ''}",
                f"To: {item.get('to_addr') or ''}"]
    return "\n".join(head) + "\n\n" + body


def start(kind: str, item_id: str = "", lang: str = "en", account: str = "") -> tuple[dict, int]:
    if kind not in KINDS:
        return {"error": f"kind must be one of {', '.join(KINDS)}"}, 400
    zh = _zh(lang)
    settings = load_settings()
    out = {"kind": kind, "account": account or "", "to": "", "cc": "", "bcc": "", "subject": "", "body": "",
           "quote": "", "source_id": "", "in_reply_to": "", "style": settings["style"], "font": settings["font"],
           "warnings": []}
    if kind == "new":
        return out, 200
    if not item_id:
        return {"error": "item_id is required for reply and forward"}, 400
    item = yhbmail.get_email(item_id)
    if not item:
        return {"error": "email not found"}, 404
    out["account"] = account or item.get("account") or ""
    out["source_id"] = item_id
    if kind == "reply":
        out["to"] = parse_addr(item.get("from_addr") or "")[1]
        out["subject"] = _prefix(item.get("subject"), "Re")
        out["quote"] = reply_quote(item, lang)
        out["in_reply_to"] = item_id
        if any(x in out["to"].lower() for x in yhbmail.NOISE_FROM):
            out["warnings"].append("寄件者看起來是不收信的系統地址。" if zh
                                   else "The sender looks like a no-reply address.")
    else:
        out["subject"] = _prefix(item.get("subject"), "Fwd")
        out["quote"] = forward_quote(item, lang)
        if item.get("has_attachment"):
            out["warnings"].append("原信附件不會帶進本機草稿。" if zh
                                   else "Original attachments are not carried into the local draft.")
    return out, 200


# ───────────────────────── drafts ─────────────────────────

def compose_body(text: str, quote: str) -> str:
    text = (text or "").rstrip()
    quote = (quote or "").strip()
    if not quote:
        return text
    return f"{text}\n\n{quote}" if text else quote


def draft_view(row: dict) -> dict:
    row = dict(row)
    body, quote = row.get("body") or "", row.get("quote") or ""
    text = body
    if quote and body.endswith(quote):
        text = body[: len(body) - len(quote)].rstrip()
    return {
        "id": row["id"], "kind": row.get("kind") or ("reply" if row.get("in_reply_to") else "new"),
        "account": row.get("account") or "", "to": row.get("to_addr") or "", "cc": row.get("cc") or "",
        "bcc": row.get("bcc") or "", "subject": row.get("subject") or "", "body": body, "text": text,
        "quote": quote, "ai_body": row.get("ai_body") or "", "style": row.get("style") or "",
        "font": row.get("font") or "", "source_id": row.get("source_id") or row.get("in_reply_to") or "",
        "in_reply_to": row.get("in_reply_to") or "", "lang": row.get("lang") or "",
        "created_at": row.get("created_at") or "", "updated_at": row.get("updated_at") or row.get("created_at") or "",
    }


def get_draft(draft_id: int) -> dict | None:
    ensure_tables()
    con = yhbmail.db()
    row = con.execute("SELECT * FROM drafts WHERE id=?", (draft_id,)).fetchone()
    con.close()
    return draft_view(row) if row else None


def list_drafts(limit: int = 100) -> list[dict]:
    ensure_tables()
    con = yhbmail.db()
    rows = [draft_view(r) for r in con.execute("SELECT * FROM drafts ORDER BY id DESC LIMIT ?", (limit,))]
    con.close()
    return rows


def save_draft(data: dict, lang: str = "en") -> tuple[dict, int]:
    zh = _zh(lang)
    kind = data.get("kind") or "new"
    if kind not in KINDS:
        return {"error": f"kind must be one of {', '.join(KINDS)}"}, 400
    style = data.get("style") or ""
    if style and style not in STYLES:
        return {"error": f"style must be one of {', '.join(STYLE_IDS)}"}, 400
    font = data.get("font") or ""
    if font and font not in FONT_IDS:
        return {"error": "unknown font"}, 400
    source_id = _clip(data.get("source_id") or data.get("in_reply_to"), 300)
    if kind in ("reply", "forward") and source_id and not yhbmail.get_email(source_id):
        return {"error": "source email not found"}, 404
    text = _clip(data.get("text") if data.get("text") is not None else data.get("body"), 100_000)
    quote = _clip(data.get("quote"), 100_000)
    ai_body = _clip(data.get("ai_body"), 100_000)
    if not (text.strip() or (data.get("subject") or "").strip() or (data.get("to") or "").strip()):
        return {"error": "empty draft"}, 400
    fields = {
        "account": _clip(data.get("account") or "you@example.com", 300),
        "to_addr": _clip(data.get("to"), 2000), "cc": _clip(data.get("cc"), 2000), "bcc": _clip(data.get("bcc"), 2000),
        "subject": _clip(data.get("subject"), 500), "body": compose_body(text, quote), "quote": quote,
        "ai_body": ai_body, "style": style, "font": font, "kind": kind, "source_id": source_id,
        "in_reply_to": source_id if kind == "reply" else "", "lang": "zh-Hant" if zh else "en",
        "updated_at": yhbmail.now_iso(),
    }
    ensure_tables()
    con = yhbmail.db()
    draft_id = data.get("id")
    status = 200
    if draft_id:
        try:
            draft_id = int(draft_id)
        except (TypeError, ValueError):
            con.close()
            return {"error": "bad id"}, 400
        if not con.execute("SELECT 1 FROM drafts WHERE id=?", (draft_id,)).fetchone():
            con.close()
            return {"error": "draft not found"}, 404
        sets = ", ".join(f"{k}=?" for k in fields)
        con.execute(f"UPDATE drafts SET {sets} WHERE id=?", (*fields.values(), draft_id))
    else:
        fields["created_at"] = fields["updated_at"]
        cols = ", ".join(fields)
        marks = ", ".join("?" for _ in fields)
        draft_id = con.execute(f"INSERT INTO drafts({cols}) VALUES ({marks})", tuple(fields.values())).lastrowid
        status = 201
    con.commit()
    con.close()
    learned = learn(ai_body, text, draft_id) if ai_body.strip() and text.strip() else {"learned": False}
    note = "草稿只存在本機，不會寄出。" if zh else "Saved as a local draft only. Nothing is sent."
    return {"ok": True, "draft": get_draft(draft_id), "learned": learned,
            "warnings": address_warnings(data, lang), "note": note}, status


# ───────────────────────── agent ─────────────────────────

WRITE_SYSTEM = {
    "zh": ("你是 TooPowerInbox 的寫信助理，在使用者自己的電腦上運作（BYO agent）。"
           "只輸出信件內文，不要主旨、不要 Markdown、不要 emoji。人名、金額、日期只能照抄提供的內容；"
           "缺的事實寫「[待填]」，不要編造。這是本機草稿，永遠不會寄出，也不要宣稱已寄出。"),
    "en": ("You are the TooPowerInbox writing assistant, running on the user's own machine (BYO agent). "
           "Output the email body only: no subject line, no markdown, no emoji. Copy names, amounts and dates "
           "only from the provided content; write [TBD] for any missing fact instead of inventing it. "
           "This is a local draft that is never sent; never claim it was sent."),
}


def agent_driver() -> str:
    return agent_bridge.load_agent_cfg().get("driver") or "local"


def ask_agent(prompt: str, lang: str) -> tuple[str, str, str | None]:
    """One prompt through the configured BYO agent. Returns (text, driver, error)."""
    cfg = agent_bridge.load_agent_cfg()
    driver = cfg.get("driver") or "local"
    if driver == "local":
        return "", "local", None
    system = WRITE_SYSTEM["zh" if _zh(lang) else "en"]
    try:
        if driver == "openai_compatible":
            block = cfg.get("openai_compatible") or {}
            base = (block.get("base_url") or "").rstrip("/")
            key = os.environ.get(block.get("api_key_env") or "OPENAI_API_KEY") or ""
            body = json.dumps({
                "model": block.get("model") or "gpt-4.1-mini",
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                "temperature": 0.4,
            }).encode()
            data = agent_bridge._post_json(
                f"{base}/chat/completions",
                {"Content-Type": "application/json", **({"Authorization": f"Bearer {key}"} if key else {})},
                body, timeout=110, allow_private=bool(block.get("allow_private")))
            text = data["choices"][0]["message"]["content"] or ""
        elif driver in ("cli", "http"):
            pack = {"ask": system + "\n\n" + prompt, "lang": "zh-Hant" if _zh(lang) else "en", "mode": "compose"}
            text = agent_bridge._cli(pack, cfg) if driver == "cli" else agent_bridge._http(pack, cfg)
        else:
            return "", driver, f"unknown agent driver {driver}"
    except Exception as e:
        return "", driver, f"{type(e).__name__}: {e}"[:300]
    text = clean_agent_text(text)
    return text, driver, None if text else "agent returned an empty answer"


def clean_agent_text(text: str) -> str:
    text = (text or "").strip()
    fence = re.match(r"^```[\w-]*\n(.*?)\n```$", text, re.S)
    if fence:
        text = fence.group(1).strip()
    return re.sub(r"^(subject|主旨)\s*[:：][^\n]*\n+", "", text, flags=re.I).strip()


def record_turn(skill: str, ask: str, answer: str, driver: str) -> None:
    con = yhbmail.db()
    con.execute("INSERT INTO agent_turns(skill, ask, answer, driver, created_at) VALUES (?,?,?,?,?)",
                (skill, ask[:2000], answer[:4000], driver, yhbmail.now_iso()))
    con.commit()
    con.close()


def source_label(source: str, driver: str, lang: str) -> str:
    if source == "agent":
        return f"AI 草稿 · {driver}" if _zh(lang) else f"AI draft · {driver}"
    return "規則草稿（未接 LLM）" if _zh(lang) else "Heuristic draft (no LLM)"


# ───────────────────────── voice learning ─────────────────────────

def _sentences(text: str) -> list[str]:
    return [s.strip() for s in SENT_SPLIT.split(text or "") if s and s.strip()]


def _lines(text: str) -> list[str]:
    return [ln.strip() for ln in (text or "").splitlines() if ln.strip()]


def greeting_word(text: str) -> str:
    lines = _lines(text)
    if not lines or len(lines[0]) > 60:
        return ""
    first = lines[0]
    m = GREETING_EN.match(first)
    if m:
        word = m.group(1)
        return word[0].upper() + word[1:].lower()
    m = GREETING_ZH.search(first)
    return m.group(1) if m else ""


def signoff_line(text: str) -> str:
    lines = _lines(text)
    tail = lines[-3:] if len(lines) > 3 else lines[1:]
    for ln in tail:
        if len(ln) <= 30 and CLOSING_RE.match(ln):
            return ln
    return ""


def learn(ai_text: str, final_text: str, draft_id=None) -> dict:
    ai_text, final_text = (ai_text or "").strip(), (final_text or "").strip()
    if not ai_text or not final_text:
        return {"learned": False, "reason": "empty"}
    ratio = difflib.SequenceMatcher(None, ai_text, final_text).ratio()
    if ratio >= 0.98:
        return {"learned": False, "reason": "unchanged", "ratio": round(ratio, 3)}
    ensure_tables()
    now = yhbmail.now_iso()
    lang = _text_lang(final_text)
    con = yhbmail.db()
    row = con.execute("SELECT id FROM compose_voice_samples WHERE draft_id=?", (draft_id,)).fetchone() \
        if draft_id else None
    if row:
        con.execute("UPDATE compose_voice_samples SET lang=?, ai_text=?, final_text=?, ratio=?, updated_at=? WHERE id=?",
                    (lang, ai_text, final_text, ratio, now, row["id"]))
        sample_id, updated = row["id"], True
    else:
        sample_id = con.execute(
            "INSERT INTO compose_voice_samples(draft_id, lang, ai_text, final_text, ratio, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?)", (draft_id, lang, ai_text, final_text, ratio, now, now)).lastrowid
        updated = False
    con.commit()
    con.close()
    profile = sync_persona()
    return {"learned": True, "sample_id": sample_id, "updated": updated, "ratio": round(ratio, 3),
            "samples": profile["samples"]}


def voice_samples(limit: int = 50) -> list[dict]:
    ensure_tables()
    con = yhbmail.db()
    rows = [dict(r) for r in con.execute(
        "SELECT * FROM compose_voice_samples ORDER BY id DESC LIMIT ?", (limit,))]
    con.close()
    return rows


QUOTED_RE = re.compile(r"“[^”]*”|「[^」]*」|\"[^\"]*\"")
PLACEHOLDER_RE = re.compile(r"\[(TBD|待填)\]")


def shape(sentence: str) -> str:
    """Comparable form of a sentence: thread-specific quoted text is masked."""
    return _norm(QUOTED_RE.sub("“…”", sentence or ""))


def _phrase_counts(samples: list[dict]) -> tuple[Counter, Counter, dict]:
    removed, added, original = Counter(), Counter(), {}
    for s in samples:
        for sent in _sentences(s["ai_text"]) + _sentences(s["final_text"]):
            original.setdefault(shape(sent), sent.strip())
        ai, final = _sentences(s["ai_text"]), _sentences(s["final_text"])
        final_n, ai_n = [shape(x) for x in final], [shape(x) for x in ai]
        for sent in dict.fromkeys(ai):
            n = shape(sent)
            if PLACEHOLDER_RE.search(sent) or not 8 <= len(n) <= 160:
                continue
            if not any(difflib.SequenceMatcher(None, n, f).ratio() > 0.8 for f in final_n):
                removed[n] += 1
        for sent in dict.fromkeys(final):
            n = shape(sent)
            if 8 <= len(n) <= 160 and not GREETING_EN.match(n) and not CLOSING_RE.match(sent.strip()) \
                    and not any(difflib.SequenceMatcher(None, n, a).ratio() > 0.8 for a in ai_n):
                added[n] += 1
    return removed, added, original


def lang_profile(samples: list[dict]) -> dict:
    if not samples:
        return {}
    ratios = [len(s["final_text"]) / max(1, len(s["ai_text"])) for s in samples]
    length_ratio = round(statistics.median(ratios), 2)
    # Only an opening / sign-off the user actually changed is a habit; a kept one just mirrors the style.
    greetings = Counter(g for g, a in ((greeting_word(s["final_text"]), greeting_word(s["ai_text"])) for s in samples)
                        if g and g != a)
    signoffs = Counter(x for x, a in ((signoff_line(s["final_text"]), signoff_line(s["ai_text"])) for s in samples)
                       if x and x != a)
    ex_ai = sum(len(re.findall(r"[!！]", s["ai_text"])) for s in samples)
    ex_final = sum(len(re.findall(r"[!！]", s["final_text"])) for s in samples)
    removed, added, original = _phrase_counts(samples)
    avoid = [p for p, n in removed.most_common(10) if n >= 2 or FILLER_SENTENCES.match(p)][:5]
    adds = [p for p, n in added.most_common(5) if n >= 2]
    return {
        "samples": len(samples),
        "length_ratio": length_ratio,
        "length_bias": "shorter" if length_ratio < 0.85 else "longer" if length_ratio > 1.15 else "same",
        "greeting": greetings.most_common(1)[0][0] if greetings else "",
        "signoff": signoffs.most_common(1)[0][0] if signoffs else "",
        "exclaim": "avoid" if ex_ai and ex_final < ex_ai / 2 else "likes" if ex_final > ex_ai else "neutral",
        "avoid_phrases": avoid,
        "added_phrases": adds,
        "avoid_examples": [original.get(p, p) for p in avoid],
        "added_examples": [original.get(p, p) for p in adds],
    }


def traits(by_lang: dict) -> tuple[list[str], list[str]]:
    en, zh = [], []
    for code, p in by_lang.items():
        if not p:
            continue
        pct = int(round(p["length_ratio"] * 100))
        tag_en = " (Chinese mail)" if code == "zh" else ""
        tag_zh = "（中文信）" if code == "zh" else "（英文信）"
        if p["length_bias"] == "shorter":
            en.append(f"Trims AI drafts to about {pct}% of their length{tag_en}.")
            zh.append(f"常把 AI 草稿刪到約 {pct}% 長度，偏好精簡{tag_zh}。")
        elif p["length_bias"] == "longer":
            en.append(f"Expands AI drafts to about {pct}% with more detail{tag_en}.")
            zh.append(f"常把 AI 草稿補長到約 {pct}%，偏好交代細節{tag_zh}。")
        if p["greeting"]:
            en.append(f"Opens with “{p['greeting']}”{tag_en}.")
            zh.append(f"開頭習慣用「{p['greeting']}」{tag_zh}。")
        if p["signoff"]:
            en.append(f"Signs off with “{p['signoff']}”{tag_en}.")
            zh.append(f"結尾習慣用「{p['signoff']}」{tag_zh}。")
        if p["exclaim"] == "avoid":
            en.append(f"Avoids exclamation marks{tag_en}.")
            zh.append(f"不太用驚嘆號{tag_zh}。")
        for phrase in p["avoid_examples"][:2]:
            en.append(f"Cuts phrases like “{phrase[:60]}”.")
            zh.append(f"會刪掉「{phrase[:60]}」這類句子。")
        for phrase in p["added_examples"][:2]:
            en.append(f"Often adds “{phrase[:60]}”.")
            zh.append(f"常補上「{phrase[:60]}」。")
    return en, zh


def voice_count() -> int:
    ensure_tables()
    con = yhbmail.db()
    n = con.execute("SELECT COUNT(*) FROM compose_voice_samples").fetchone()[0]
    con.close()
    return n


def voice_profile() -> dict:
    samples = voice_samples(30)
    by_lang = {code: lang_profile([s for s in samples if s["lang"] == code]) for code in ("en", "zh")}
    by_lang = {k: v for k, v in by_lang.items() if v}
    t_en, t_zh = traits(by_lang)
    return {
        "samples": voice_count(),
        "by_lang": by_lang,
        "traits_en": t_en,
        "traits_zh": t_zh,
        "recent": [{"id": s["id"], "lang": s["lang"], "ai": s["ai_text"][:600], "final": s["final_text"][:600],
                    "ratio": round(s["ratio"] or 0, 3), "at": s["updated_at"]} for s in samples[:5]],
        "updated_at": samples[0]["updated_at"] if samples else "",
    }


def attach_voice(p: dict, profile: dict | None = None) -> dict:
    """Fold the learned voice into a persona dict and rewrite vault/persona.{json,md}."""
    profile = profile or voice_profile()
    p = dict(p)
    p["voice"] = profile
    write = [x for x in (p.get("how_you_write") or []) if not str(x).startswith(LEARNED_PREFIX)]
    p["how_you_write"] = write + [LEARNED_PREFIX + t for t in profile["traits_en"][:4]]
    persona.PERSONA_PATH.parent.mkdir(parents=True, exist_ok=True)
    persona.PERSONA_PATH.write_text(json.dumps(p, ensure_ascii=False, indent=2))
    md_path = persona.PERSONA_PATH.with_suffix(".md")
    md = md_path.read_text() if md_path.exists() else "# 更了解你 / Know you better\n"
    md = md.split("\n## 學到的語氣 / Learned voice", 1)[0].rstrip() + "\n"
    md += "\n## 學到的語氣 / Learned voice\n"
    md += f"- samples: {profile['samples']}\n"
    md += "".join(f"- {a} / {b}\n" for a, b in zip(profile["traits_en"], profile["traits_zh"]))
    md_path.write_text(md)
    return p


def sync_persona() -> dict:
    profile = voice_profile()
    attach_voice(persona.load(), profile)
    return profile


def forget(sample_id=None) -> int:
    ensure_tables()
    con = yhbmail.db()
    if sample_id is None:
        n = con.execute("DELETE FROM compose_voice_samples").rowcount
    else:
        n = con.execute("DELETE FROM compose_voice_samples WHERE id=?", (int(sample_id),)).rowcount
    con.commit()
    con.close()
    sync_persona()
    return n


def _install_persona_hook() -> None:
    core = persona.rebuild
    if getattr(core, "_tpi_compose", False):
        return

    def rebuild_with_voice():
        return attach_voice(core())

    rebuild_with_voice._tpi_compose = True
    persona.rebuild = rebuild_with_voice


_install_persona_hook()


# ───────────────────────── AI Write ─────────────────────────

def _sentence_case(text: str, lang: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return ""
    if not _zh(lang) and text[0].islower():
        text = text[0].upper() + text[1:]
    if text[-1] not in ".!?。！？…":
        text += "。" if CJK_RE.search(text[-1]) else "."
    return text


def _signer(style: str) -> str:
    ident = (persona.load().get("identity") or {})
    name = (ident.get("name") or "").strip()
    if not name or name.lower() == "you":
        return ""
    return name if style == "professional" or CJK_RE.search(name) else name.split()[0]


def greet_line(style: str, lang: str, name: str, voice: dict) -> str:
    st = STYLES[style]
    zh = _zh(lang)
    word = voice.get("greeting") or ""
    if word:
        if zh:
            if word in ("您好", "你好"):
                return f"{name} {word}：" if name else f"{word}："
            return f"{word} {name}，" if name else f"{word}，"
        return f"{word} {name}," if name else f"{word},"
    if zh:
        return st["greet_zh"].format(name=name) if name else st["greet_zh_anon"]
    return st["greet_en"].format(name=name) if name else st["greet_en_anon"]


def heuristic_write(kind: str, item: dict | None, instruction: str, style: str, lang: str,
                    to: str = "", subject: str = "") -> str:
    zh = _zh(lang)
    st = STYLES[style]
    voice = (voice_profile()["by_lang"].get("zh" if zh else "en")) or {}
    avoid = set(voice.get("avoid_phrases") or [])
    short = voice.get("length_bias") == "shorter"
    tbd = _tbd(lang)
    name = first_name(item.get("from_addr") or "") if (kind == "reply" and item) else first_name(to)
    lines: list[str] = []
    instr = _sentence_case(instruction, lang)

    if kind == "reply" and item:
        subj = (item.get("subject") or "").strip()
        if not short:
            lines.append(st["thanks_zh" if zh else "thanks_en"].format(subject=subj[:80]))
        body = item.get("body_text") or item.get("snippet") or ""
        dl = DEADLINE_RE.search(body)
        if instr:
            lines.append(instr)
        else:
            asks = [s for s in _sentences(body) if QUESTION_RE.search(s)][:2]
            for ask in asks:
                ask = ask.strip()
                lines.append(f"關於「{ask[:120]}」：{tbd}" if zh else f"On “{ask[:120]}”: {tbd}")
            if not asks:
                lines.append(f"細節我會在 {tbd} 前回覆。" if zh else f"I'll follow up with the details by {tbd}.")
        if dl:
            lines.append(f"已注意到期限：{dl.group(0).strip()}。" if zh else f"Noted the deadline: {dl.group(0).strip()}.")
    elif kind == "forward" and item:
        sender = parse_addr(item.get("from_addr") or "")[0]
        subj = (item.get("subject") or "").strip()
        lines.append(f"轉寄 {sender} 的「{subj[:80]}」給你參考。" if zh
                     else f"Forwarding “{subj[:80]}” from {sender} for your reference.")
        lines.append(instr or (f"麻煩看一下，{tbd}" if zh else f"Could you take a look? {tbd}"))
    else:
        if instr:
            lines.append(instr)
        else:
            lines.append(f"{tbd}（在上方「告訴 AI 要寫什麼」輸入重點）" if zh
                         else f"{tbd} (type what this mail is about in the AI box above)")
    lines = [ln for ln in lines if shape(ln) not in avoid]
    if voice.get("exclaim") == "avoid":
        lines = [ln.replace("！", "。").replace("!", ".") for ln in lines]

    out = [greet_line(style, lang, name, voice), ""]
    sep = "" if zh else " "
    if kind == "reply" and len(lines) > 1 and not short:
        out.append(lines[0])
        out.append("")
        out.append("\n".join(lines[1:]))
    elif kind == "reply":
        out.append("\n".join(lines))
    else:
        out.append(sep.join(lines) if zh else " ".join(lines))
    out += ["", voice.get("signoff") or st["close_zh" if zh else "close_en"]]
    signer = _signer(style)
    if signer:
        out.append(signer)
    return "\n".join(out).strip()


def write_prompt(kind: str, item_id: str, instruction: str, style: str, lang: str, to: str, subject: str,
                 current: str) -> str:
    zh = _zh(lang)
    st = STYLES[style]
    profile = voice_profile()
    voice_lang = profile["by_lang"].get("zh" if zh else "en") or {}
    p = persona.load()
    write_rules = [x for x in p.get("how_you_write") or [] if not str(x).startswith(LEARNED_PREFIX)]
    examples = [s for s in profile["recent"] if s["lang"] == ("zh" if zh else "en")][:3]
    kind_text = {
        "new": ("一封新信", "a new email"), "reply": ("回覆下面這封信", "a reply to the email below"),
        "forward": ("轉寄下面這封信時附上的說明", "the note on top of forwarding the email below"),
    }[kind][0 if zh else 1]
    parts = []
    if zh:
        parts.append(f"請用繁體中文寫{kind_text}。")
        parts.append(f"草稿風格：{st['zh']}——{st['desc_zh']} 稱謂參考「{st['greet_zh']}」，結語參考「{st['close_zh']}」。")
    else:
        parts.append(f"Write {kind_text} in English.")
        parts.append(f"Draft style: {st['en']} — {st['desc_en']} Greeting like “{st['greet_en']}”, "
                     f"sign-off like “{st['close_en']}”.")
    if write_rules:
        parts.append(("使用者的文風：" if zh else "How the user writes: ") + " / ".join(write_rules[:5]))
    traits_list = profile["traits_zh" if zh else "traits_en"]
    if traits_list:
        parts.append(("從使用者修改草稿學到的語氣：" if zh else "Voice learned from the user's edits: ")
                     + " ".join(traits_list[:6]))
    if voice_lang.get("greeting") or voice_lang.get("signoff"):
        parts.append((f"優先使用開頭「{voice_lang.get('greeting')}」、結尾「{voice_lang.get('signoff')}」。" if zh else
                      f"Prefer the opening “{voice_lang.get('greeting')}” and sign-off “{voice_lang.get('signoff')}”."))
    for ex in examples:
        parts.append(("範例——AI 原稿：\n" if zh else "Example — AI draft:\n") + ex["ai"][:400]
                     + ("\n使用者改成：\n" if zh else "\nThe user changed it to:\n") + ex["final"][:400])
    signer = _signer(style)
    if signer:
        parts.append(f"署名：{signer}" if zh else f"Sign as: {signer}")
    parts.append(("使用者指示：" if zh else "User instruction: ")
                 + (instruction or ("（無，寫一封合理的回覆）" if zh else "(none: write a sensible email)")))
    if to:
        parts.append(("收件者：" if zh else "To: ") + to)
    if subject:
        parts.append(("主旨：" if zh else "Subject: ") + subject)
    if current.strip():
        parts.append(("目前草稿（可參考或改寫）：\n" if zh else "Current draft (reuse or improve):\n") + current[:4000])
    ctx = agent_bridge.copilot_thread_context(item_id) if item_id else ""
    if ctx:
        parts.append("─ Thread ─\n" + ctx)
    parts.append("只回信件內文。" if zh else "Reply with the email body only.")
    return "\n\n".join(parts)


def ai_write(data: dict, lang: str) -> tuple[dict, int]:
    kind = data.get("kind") or "new"
    if kind not in KINDS:
        return {"error": f"kind must be one of {', '.join(KINDS)}"}, 400
    style = data.get("style") or load_settings()["style"]
    if style not in STYLES:
        return {"error": f"style must be one of {', '.join(STYLE_IDS)}"}, 400
    item_id = str(data.get("item_id") or data.get("source_id") or "")
    item = yhbmail.get_email(item_id) if item_id else None
    if item_id and not item:
        return {"error": "email not found"}, 404
    if kind in ("reply", "forward") and not item:
        return {"error": "item_id is required for reply and forward"}, 400
    instruction = _clip(data.get("instruction"), 2000).strip()
    to, subject, current = _clip(data.get("to"), 2000), _clip(data.get("subject"), 500), _clip(data.get("body"), 8000)
    text, driver, error = ask_agent(write_prompt(kind, item_id, instruction, style, lang, to, subject, current), lang)
    source = "agent" if text else "heuristic"
    if not text:
        text = heuristic_write(kind, item, instruction, style, lang, to, subject)
        driver = driver if error else "local"
    else:
        record_turn("compose:write", instruction or item_id or kind, text, driver)
    out = {"text": text, "kind": kind, "style": style, "source": source, "driver": driver,
           "label": source_label(source, driver, lang), "error": error}
    if not subject.strip() and kind == "new" and instruction:
        out["subject_suggestion"] = _sentence_case(instruction, lang).rstrip(".。")[:80]
    return out, 200


# ───────────────────────── rewrite ─────────────────────────

def _split_frame(text: str) -> tuple[str, list[str], str]:
    """(greeting line, body lines, closing block) — greeting/closing only when they look like one."""
    lines = (text or "").strip("\n").splitlines()
    greet = ""
    if lines and len(lines[0].strip()) <= 60 and (GREETING_EN.match(lines[0].strip()) or GREETING_ZH.search(lines[0])
                                                 or re.search(r"[,，:：]$", lines[0].strip())):
        greet = lines.pop(0)
    closing: list[str] = []
    non_empty = [i for i, ln in enumerate(lines) if ln.strip()]
    for i in reversed(non_empty[-3:]):
        if len(lines[i].strip()) <= 30 and CLOSING_RE.match(lines[i].strip()):
            closing = lines[i:]
            lines = lines[:i]
            break
    return greet, lines, "\n".join(closing)


def _join_frame(greet: str, body: list[str], closing: str) -> str:
    body_text = "\n".join(body).strip("\n")
    body_text = re.sub(r"\n{3,}", "\n\n", body_text)
    parts = [p for p in (greet.strip(), body_text, closing.strip()) if p]
    return "\n\n".join(parts)


def _swap_greeting(greet: str, style: str, lang: str) -> str:
    if not greet:
        return greet
    zh = _zh(lang) or bool(CJK_RE.search(greet))
    if zh:
        m = re.match(r"^(?:嗨|哈囉|Hi|Hey)?\s*(.*?)\s*(?:您好|你好)?\s*[,，:：!！]?$", greet.strip())
        name = (m.group(1) if m else "").strip()
        st = STYLES[style]
        return st["greet_zh"].format(name=name) if name else st["greet_zh_anon"]
    m = re.match(r"^(?:dear|hi|hello|hey|good (?:morning|afternoon|evening)|greetings)?\s*(.*?)[,!:]?$",
                 greet.strip(), re.I)
    name = (m.group(1) if m else "").strip()
    st = STYLES[style]
    return st["greet_en"].format(name=name) if name else st["greet_en_anon"]


def _swap_closing(closing: str, style: str, lang: str) -> str:
    st = STYLES[style]
    zh = _zh(lang) or bool(CJK_RE.search(closing))
    new = st["close_zh" if zh else "close_en"]
    if not closing:
        return closing
    lines = closing.splitlines()
    lines[0] = new
    return "\n".join(lines)


def to_formal(text: str, lang: str) -> str:
    greet, body, closing = _split_frame(text)
    out = []
    for ln in body:
        ln = ln.replace("’", "'")
        for pat, rep in CONTRACTIONS + CASUAL_EN:
            ln = re.sub(pat, lambda m, r=rep: r[0].upper() + r[1:] if m.group(0)[0].isupper() else r, ln, flags=re.I)
        if CJK_RE.search(ln):
            for a, b in CASUAL_ZH:
                ln = ln.replace(a, b)
            ln = ln.replace("你們", "貴方").replace("你", "您")
        ln = re.sub(r"[!！]+", lambda m: "。" if "！" in m.group(0) else ".", ln)
        ln = EMOJI_RE.sub("", ln)
        ln = re.sub(r"。{2,}", "。", ln)
        out.append(ln.rstrip())
    return _join_frame(_swap_greeting(greet, "professional", lang), out, _swap_closing(closing, "professional", lang))


def to_friendlier(text: str, lang: str) -> str:
    greet, body, closing = _split_frame(text)
    zh = _zh(lang) or bool(CJK_RE.search(text))
    body = [ln.replace("貴方", "你們").replace("您", "你") for ln in body] if zh else \
        [re.sub(r"\bThank you\b", "Thanks so much", ln) for ln in body]
    opener = "希望你這週一切順利！" if zh else "Hope your week is going well!"
    joined = _norm("\n".join(body))
    if _norm(opener) not in joined and not re.search(r"hope (your|you|this|all)|希望你|希望您", joined, re.I):
        body = [opener, ""] + body
    new_greet = _swap_greeting(greet, "balanced", lang)
    new_close = closing
    if closing:
        lines = closing.splitlines()
        lines[0] = "謝謝你，祝順心！" if zh else "Thanks so much,"
        new_close = "\n".join(lines)
    else:
        new_close = "謝謝你！" if zh else "Thanks so much!"
    return _join_frame(new_greet, body, new_close)


def to_shorter(text: str, lang: str) -> str:
    greet, body, closing = _split_frame(text)
    paras, cur = [], []
    for ln in body + [""]:
        if ln.strip():
            cur.append(ln.strip())
        elif cur:
            paras.append(" ".join(cur))
            cur = []
    keep_re = re.compile(r"(\?|？|\[TBD\]|\[待填\]|\d|let me know|please|請|麻煩|today|tomorrow|tonight|"
                         r"\b(?:mon|tues|wednes|thurs|fri|satur|sun)day\b|\bby\b|\bbefore\b|\buntil\b|"
                         r"週[一二三四五六日]|星期|禮拜|今天|明天|前)", re.I)
    new_paras = []
    for para in paras:
        sents = [s for s in _sentences(para) if not FILLER_SENTENCES.match(s.strip())]
        sents = [FILLER_WORDS_ZH.sub("", FILLER_WORDS_EN.sub("", s)) for s in sents]
        if len(sents) > 2:
            sents = sents[:2] + [s for s in sents[2:] if keep_re.search(s)]
        if sents:
            new_paras.append(("" if CJK_RE.search(para) else " ").join(sents))
    if len(new_paras) > 3:
        new_paras = new_paras[:2] + [p for p in new_paras[2:] if keep_re.search(p)][:1]
    out = _join_frame(greet, [p + "\n" for p in new_paras], closing)
    if len(out) >= len(text.strip()) and new_paras:
        first = _sentences(new_paras[0])[:1]
        out = _join_frame(greet, first + [p for p in new_paras[1:] if keep_re.search(p)][:1], closing)
    return out


def to_bullets(text: str, lang: str) -> str:
    greet, body, closing = _split_frame(text)
    sents = [s for ln in body if ln.strip() for s in _sentences(ln.lstrip("-*• "))]
    return _join_frame(greet, ["- " + s for s in sents], closing)


def add_line(text: str, line: str, top: bool) -> str:
    greet, body, closing = _split_frame(text)
    if _norm(line) in _norm("\n".join(body)):
        return text
    body = [line, ""] + body if top else body + ["", line]
    return _join_frame(greet, body, closing)


def instruction_ops(instruction: str) -> list[str]:
    return [op for op, rx in INSTRUCTION_KEYS if rx.search(instruction or "")]


def heuristic_rewrite(text: str, ops: list[str], lang: str) -> str:
    zh = _zh(lang) or _text_lang(text) == "zh"
    for op in ops:
        if op == "formal":
            text = to_formal(text, lang)
        elif op == "shorter":
            text = to_shorter(text, lang)
        elif op == "friendlier":
            text = to_friendlier(text, lang)
        elif op == "bullets":
            text = to_bullets(text, lang)
        elif op == "thanks":
            text = add_line(text, "謝謝你的協助。" if zh else "Thank you for your help.", top=False)
        elif op == "apology":
            text = add_line(text, "造成不便，敬請見諒。" if zh else "Apologies for any inconvenience.", top=True)
    return text


TONE_TEXT = {
    "formal": ("改得更正式、更有禮貌", "more formal and polite"),
    "shorter": ("改得更短、更精簡，只留重點", "shorter and more concise, keep only what matters"),
    "friendlier": ("改得更友善、更溫和", "friendlier and warmer"),
}


def rewrite(data: dict, lang: str) -> tuple[dict, int]:
    text = _clip(data.get("body") or data.get("text"), 20_000)
    if not text.strip():
        return {"error": "body is empty"}, 400
    tone = data.get("tone") or ""
    if tone and tone not in TONES:
        return {"error": f"tone must be one of {', '.join(TONES)}"}, 400
    instruction = _clip(data.get("instruction"), 2000).strip()
    if not tone and not instruction:
        return {"error": "give a tone or an instruction"}, 400
    style = data.get("style") or load_settings()["style"]
    if style not in STYLES:
        return {"error": f"style must be one of {', '.join(STYLE_IDS)}"}, 400
    zh = _zh(lang)
    goal = []
    if tone:
        goal.append(TONE_TEXT[tone][0 if zh else 1])
    if instruction:
        goal.append(instruction)
    st = STYLES[style]
    if zh:
        prompt = (f"請改寫下面這封信的草稿：{'；'.join(goal)}。保持原本的語言、事實、人名、日期、金額不變，"
                  f"不要新增事實。草稿風格設定：{st['zh']}（{st['desc_zh']}）。只回改寫後的信件內文。\n\n─ 草稿 ─\n{text}")
    else:
        prompt = (f"Rewrite the email draft below: {'; '.join(goal)}. Keep its language, facts, names, dates and "
                  f"amounts unchanged and add no new facts. Draft style setting: {st['en']} ({st['desc_en']}). "
                  f"Reply with the rewritten email body only.\n\n─ Draft ─\n{text}")
    out_text, driver, error = ask_agent(prompt, lang)
    if out_text:
        record_turn("compose:rewrite", "; ".join(goal), out_text, driver)
        return {"text": out_text, "source": "agent", "driver": driver, "applied": [tone] if tone else [],
                "label": source_label("agent", driver, lang), "error": None, "note": ""}, 200
    ops = ([tone] if tone else []) + [op for op in instruction_ops(instruction) if op != tone]
    new_text = heuristic_rewrite(text, ops, lang)
    note = ""
    if instruction and not instruction_ops(instruction):
        note = ("這個指示需要接 LLM 才能照做（agent.json 設定 driver）；目前規則只認得：正式、簡短、友善、條列、感謝、道歉。"
                if zh else "This instruction needs an LLM (set a driver in agent.json); the local rules only know: "
                           "formal, shorter, friendlier, bullets, thanks, apology.")
    return {"text": new_text, "source": "heuristic", "driver": driver if error else "local", "applied": ops,
            "label": source_label("heuristic", "local", lang), "error": error, "note": note,
            "changed": new_text.strip() != text.strip()}, 200


# ───────────────────────── routes ─────────────────────────

@get("/api/compose/settings")
def compose_settings(req):
    return settings_view(_lang(req))


@post("/api/compose/settings")
def compose_settings_save(req):
    out, status = save_settings(req.body)
    if status != 200:
        return out, status
    return settings_view(_lang(req))


@post("/api/compose/start")
def compose_start(req):
    b = req.body
    return start(str(b.get("kind") or "new"), str(b.get("item_id") or ""), _lang(req), str(b.get("account") or ""))


@get("/api/compose/drafts")
def compose_drafts(req):
    try:
        limit = max(1, min(500, int(req.query.get("limit") or 100)))
    except ValueError:
        limit = 100
    return {"drafts": list_drafts(limit)}


@get("/api/compose/draft/*")
def compose_draft_get(req):
    try:
        draft = get_draft(int(unquote(req.params)))
    except ValueError:
        return {"error": "bad id"}, 400
    return draft if draft else ({"error": "draft not found"}, 404)


@post("/api/compose/draft")
def compose_draft_save(req):
    return save_draft(req.body, _lang(req))


@post("/api/compose/write")
def compose_write(req):
    return ai_write(req.body, _lang(req))


@post("/api/compose/rewrite")
def compose_rewrite(req):
    return rewrite(req.body, _lang(req))


@post("/api/compose/learn")
def compose_learn(req):
    b = req.body
    if not str(b.get("ai_body") or "").strip() or not str(b.get("body") or "").strip():
        return {"error": "ai_body and body are required"}, 400
    return learn(str(b["ai_body"]), str(b["body"]), b.get("draft_id"))


@get("/api/compose/voice")
def compose_voice(req):
    return voice_profile()


@post("/api/compose/voice/forget")
def compose_voice_forget(req):
    b = req.body
    if b.get("all"):
        return {"ok": True, "deleted": forget(None), "voice": voice_profile()}
    try:
        sample_id = int(b.get("id"))
    except (TypeError, ValueError):
        return {"error": "give an id or all: true"}, 400
    return {"ok": True, "deleted": forget(sample_id), "voice": voice_profile()}
