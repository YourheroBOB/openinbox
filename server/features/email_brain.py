"""Email Brain: what your mail says about you, with a Fix for every inference.

Five sections are inferred from local mail only: the cached inbox plus your own
sent mail (demo mode: fixtures/demo_sent.json; live: cached mail sent from one
of the configured accounts).

    identity       name, role, organization, timezone, signature
    tone           formality, length, greeting, sign-off, languages, exclamation marks, rules
    contacts       frequent correspondents and how you relate to each
    projects       topics that keep coming back across threads, with people and calendar events
    work_patterns  active hours, work days, peak hours, reply speed, notes

A Fix is the user's own record (table brain_fixes, kept on a local-cache clear).
It overrides the inference and takes effect at once: persona.json / persona.md
get the corrected identity and an `email_brain` block, the AI Write prompt gets
an "about the user" block (compose.write_prompt), and a fixed greeting /
sign-off is used by the rule-based drafts too.
"""
from __future__ import annotations

import json
import math
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime

import persona
import yhbmail
from features import get, post

try:
    from features import compose
except Exception:  # compose is optional; the brain still works without it
    compose = None

SENT_FIXTURE = yhbmail.ROOT / "fixtures" / "demo_sent.json"
SECTIONS = ("identity", "tone", "contacts", "projects", "work_patterns")
SECTION_TEXT = {
    "identity": ("Identity & workplace", "身分與職場",
                 "Who you are at work, read from your signature and sent mail.",
                 "從簽名檔與寄件備份推得你的身分與工作單位。"),
    "tone": ("Writing tone", "寫作語氣",
             "How your own mail reads: formality, length, openings and sign-offs.",
             "你自己寫的信：正式程度、長短、開頭與結尾。"),
    "contacts": ("Contacts & relationships", "常聯絡人與關係",
                 "People you write with most, and what they are to you.",
                 "最常往來的人，以及他們和你的關係。"),
    "projects": ("Active projects", "進行中專案",
                 "Topics that keep coming back across threads.",
                 "在多個信件串反覆出現的主題。"),
    "work_patterns": ("Work patterns", "工作模式",
                      "When you are active in your mail and how fast you reply.",
                      "你什麼時段在處理信件、多快回信。"),
}
KEYS = {
    "identity": ("name", "role", "organization", "timezone", "signature"),
    "tone": ("formality", "length", "greeting", "signoff", "languages", "exclamations", "rules"),
    "work_patterns": ("active_hours", "work_days", "peak_hours", "reply_speed", "notes"),
}
KEY_TEXT = {
    "name": ("Name", "姓名"), "role": ("Role", "職稱"), "organization": ("Organization", "工作單位"),
    "timezone": ("Timezone", "時區"), "signature": ("Signature", "簽名檔"),
    "formality": ("Formality", "正式程度"), "length": ("Length", "篇幅"), "greeting": ("Opening", "開頭"),
    "signoff": ("Sign-off", "結尾"), "languages": ("Languages", "使用語言"),
    "exclamations": ("Exclamation marks", "驚嘆號"), "rules": ("Your rules", "你的規則"),
    "active_hours": ("Active hours", "活躍時段"), "work_days": ("Work days", "工作日"),
    "peak_hours": ("Peak hours", "高峰時段"), "reply_speed": ("Reply speed", "回信速度"),
    "notes": ("Notes", "備註"),
}
ENUMS = {
    ("tone", "formality"): {"formal": ("Formal", "正式"), "balanced": ("Balanced", "平衡"),
                            "casual": ("Casual", "輕鬆")},
    ("tone", "length"): {"short": ("Short", "簡短"), "medium": ("Medium", "中等"), "long": ("Long", "詳細")},
    ("tone", "exclamations"): {"avoid": ("Avoids them", "幾乎不用"), "sometimes": ("Sometimes", "偶爾"),
                               "often": ("Often", "常用")},
    ("work_patterns", "reply_speed"): {
        "within_hour": ("Within an hour", "一小時內"), "within_hours": ("Within a few hours", "幾小時內"),
        "same_day": ("Same day", "當天"), "next_day": ("Next day", "隔天"), "slower": ("Slower", "較慢")},
}
RELATIONSHIPS = {
    "investor": ("Investor", "投資人"), "client": ("Client", "客戶"), "vendor": ("Vendor / billing", "廠商／帳務"),
    "collaborator": ("Collaborator", "合作夥伴"), "teammate": ("Teammate", "同事"),
    "recruiter": ("Recruiting", "招募"), "personal": ("Personal", "私人"), "other": ("Other", "其他"),
}
PROJECT_STATUS = {"active": ("Active", "進行中"), "paused": ("Quiet", "暫停"), "done": ("Done", "已完成")}
SOURCE_TEXT = {"fix": ("Fixed by you", "你已修正"), "mail": ("From your mail", "從信件推得"),
               "seed": ("From your profile seed", "來自個人設定"), "config": ("From settings", "來自設定"),
               "default": ("Not enough mail yet", "信件不足，尚未推得"), "voice": ("From your draft edits", "從你改草稿學到")}
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DAY_TEXT = {"mon": ("Mon", "週一"), "tue": ("Tue", "週二"), "wed": ("Wed", "週三"), "thu": ("Thu", "週四"),
            "fri": ("Fri", "週五"), "sat": ("Sat", "週六"), "sun": ("Sun", "週日")}
DAY_ALIASES = {**{d: d for d in DAYS},
               **{"monday": "mon", "tuesday": "tue", "wednesday": "wed", "thursday": "thu", "friday": "fri",
                  "saturday": "sat", "sunday": "sun", "tues": "tue", "thur": "thu", "thurs": "thu"},
               **{"一": "mon", "二": "tue", "三": "wed", "四": "thu", "五": "fri", "六": "sat", "日": "sun", "天": "sun"}}

LIMITS = {"text": 200, "rules": 600, "note": 300, "name": 80}
ADDR_RE = re.compile(r"[^@\s<>,;\"']+@[^@\s<>,;\"']+\.[^@\s<>,;\"']+")
NAME_ADDR_RE = re.compile(r'^\s*"?([^"<]*?)"?\s*<([^>]+)>\s*$')
CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*[A-Za-z]|[A-Za-z]")
SUBJECT_PREFIX_RE = re.compile(r"^\s*((re|fwd?|aw|sv|回覆|轉寄)\s*[:：]\s*)+", re.I)
GREETING_RE = re.compile(r"^(dear|hi|hello|hey|good (?:morning|afternoon|evening)|greetings)\b", re.I)
GREETING_ZH_RE = re.compile(r"(您好|你好|嗨|哈囉)")
CLOSING_RE = re.compile(
    r"^(best( regards| wishes)?|kind regards|warm regards|regards|cheers|thanks( so much| again)?|thank you|"
    r"many thanks|sincerely|talk soon|all the best|敬祝\s*\S{0,4}|祝\S{0,4}|謝謝(你|您)?|感謝(你|您)?|"
    r"先這樣(，再聊)?|再聊|敬上|順心)[,，!！.。～]?$", re.I)
SIG_ROLE_RE = re.compile(r"\s*(?:,|·|\||—|–|\s-\s|\s+at\s+|\s+@\s+)\s*", re.I)
HHMM_RE = re.compile(r"^\s*(\d{1,2})(?::(\d{2}))?\s*(?:-|–|—|~|～|to|到|至)\s*(\d{1,2})(?::(\d{2}))?\s*$", re.I)

FORMAL_MARKERS = re.compile(r"(^dear\b|best regards|kind regards|sincerely|respectfully|敬上|敬祝|您好|貴公司|敬請)", re.I | re.M)
CASUAL_MARKERS = re.compile(r"(^hey\b|cheers|\b(?:I'll|I'm|can't|won't|don't|it's|we're|that's|gonna|wanna)\b|"
                            r"謝啦|啦|喔|～|[\U0001F300-\U0001FAFF])", re.I | re.M)

RELATION_RULES = [
    ("investor", re.compile(r"(investor|term sheet|seed round|series [a-c]\b|pro-rata|valuation|cap table|"
                            r"fundrais|投資|募資)", re.I)),
    ("recruiter", re.compile(r"(hiring|recruit|portfolio|candidate|shortlist|talent|interview|招募|履歷|面試)", re.I)),
    ("collaborator", re.compile(r"(\bdesign\b|design review|mockup|prototype|figma|wireframe|設計|合作)", re.I)),
    ("client", re.compile(r"(client|customer|proposal|statement of work|quote|客戶|報價|委託)", re.I)),
    ("vendor", re.compile(r"(invoice|receipt|billing|renewal|subscription|帳單|續約|發票|收據)", re.I)),
]

STOPWORDS = set("""
a about above after again against all also am an and any are aren as at be because been before being below
between both but by can cannot could did do does doing don done down during each few for from further had has
have having he her here hers him his how i if in into is it its itself just let me more most my no nor not now
of off on once only or other our ours out over own same she should so some such than that the their them then
there these they this those through to too under until up very was we were what when where which while who whom
why will with would you your yours yes okay ok via per still again ever every much many lot lots
re fwd fw hi hello hey dear thanks thank best regards cheers please kind sincerely confirm confirmed reply replies
send sent sending email emails mail note notes question questions update updated today tomorrow tonight yesterday
week weeks next last month months year years day days time times morning afternoon evening monday tuesday
wednesday thursday friday saturday sunday mon tue tues wed thu thur thurs fri sat sun january february march
april may june july august september october november december jan feb mar apr jun jul aug sep sept oct nov dec
minute minutes hour hours works work working start starting started share shared need needs needed make sure keep
cut fine short version strong great good fit book booked also able like want know think look looking see seen
attached attachment attachments invitation invite invited line lines two three four five six seven eight nine ten
first second third one half new old sure back soon later earlier quick quickly let's i'll we'll can't won't don't
it's that's we're you're about around above draft drafts thing things way stays stay check checked checking
""".split())


def _zh(lang) -> bool:
    return str(lang or "").lower().startswith("zh")


def _lang(req) -> str:
    return "zh-Hant" if req.lang_zh() else "en"


def _tx(pair, lang) -> str:
    return pair[1] if _zh(lang) else pair[0]


def _clip(value, n: int) -> str:
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(value if value is not None else ""))[:n].strip()


# ───────────────────────── storage ─────────────────────────

_ensured: set = set()


def ensure_tables() -> None:
    if str(yhbmail.DB) in _ensured and yhbmail.DB.exists():
        return
    yhbmail.init_db()
    con = yhbmail.db()
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS brain_fixes (
            section TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            created_at TEXT,
            updated_at TEXT,
            PRIMARY KEY (section, key)
        );
        """
    )
    con.commit()
    con.close()
    _ensured.add(str(yhbmail.DB))


def load_fixes() -> dict:
    ensure_tables()
    con = yhbmail.db()
    out: dict = {s: {} for s in SECTIONS}
    for r in con.execute("SELECT section, key, value, created_at, updated_at FROM brain_fixes ORDER BY rowid"):
        try:
            value = json.loads(r["value"])
        except json.JSONDecodeError:
            continue
        if r["section"] in out and isinstance(value, dict):
            out[r["section"]][r["key"]] = {**value, "_at": r["updated_at"] or r["created_at"] or ""}
    con.close()
    return out


def list_fixes() -> list[dict]:
    rows = []
    for section, items in load_fixes().items():
        for key, value in items.items():
            rows.append({"section": section, "key": key, "updated_at": value.get("_at", ""),
                         "value": {k: v for k, v in value.items() if not k.startswith("_")}})
    return rows


def _store_fix(section: str, key: str, value: dict) -> None:
    ensure_tables()
    now = yhbmail.now_iso()
    con = yhbmail.db()
    con.execute(
        "INSERT INTO brain_fixes(section, key, value, created_at, updated_at) VALUES (?,?,?,?,?) "
        "ON CONFLICT(section, key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (section, key, json.dumps(value, ensure_ascii=False), now, now))
    con.commit()
    con.close()


def delete_fixes(section: str | None = None, key: str | None = None) -> int:
    ensure_tables()
    con = yhbmail.db()
    if section is None:
        n = con.execute("DELETE FROM brain_fixes").rowcount
    elif key is None:
        n = con.execute("DELETE FROM brain_fixes WHERE section=?", (section,)).rowcount
    else:
        n = con.execute("DELETE FROM brain_fixes WHERE section=? AND key=?", (section, key)).rowcount
    con.commit()
    con.close()
    return n


# ───────────────────────── mail sources ─────────────────────────

def split_addrs(raw: str) -> list[tuple[str, str]]:
    """[(display name, lowercase address)] for every address in a header value."""
    out = []
    for part in re.split(r"[,;，；](?![^<]*>)", raw or ""):
        part = part.strip()
        if not part:
            continue
        m = NAME_ADDR_RE.match(part)
        if m:
            name, addr = m.group(1).strip(), m.group(2).strip()
        else:
            hit = ADDR_RE.search(part)
            if not hit:
                continue
            addr, name = hit.group(0), ""
        out.append((name if name and "@" not in name else "", addr.lower()))
    return out


def own_addresses() -> set:
    cfg = yhbmail.load_cfg()
    return {str(a.get("email") or "").lower() for a in (cfg.get("accounts") or []) if a.get("email")}


def is_demo() -> bool:
    cfg = yhbmail.load_cfg()
    accounts = cfg.get("accounts") or []
    return (cfg.get("mode") or "demo") == "demo" or not accounts or all(a.get("driver") == "demo" for a in accounts)


def _with_ts(row: dict) -> dict:
    row = dict(row)
    row["date_ts"] = row.get("date_ts") or yhbmail.parse_date_ts(row.get("date_raw") or "")
    return row


def load_mail() -> tuple[list[dict], list[dict]]:
    """(received, sent). Sent = demo fixture in demo mode + cached mail from one of your own accounts."""
    own = own_addresses()
    received, sent = [], []
    for e in yhbmail.list_emails(limit=2000):
        frm = split_addrs(e.get("from_addr") or "")
        if frm and frm[0][1] in own:
            sent.append(_with_ts(e))
        else:
            received.append(_with_ts(e))
    if is_demo() and SENT_FIXTURE.exists():
        try:
            data = json.loads(SENT_FIXTURE.read_text())
        except (OSError, json.JSONDecodeError):
            data = {}
        seen = {s["id"] for s in sent}
        sent += [_with_ts(s) for s in data.get("sent") or [] if isinstance(s, dict) and s.get("id") not in seen]
    sent.sort(key=lambda r: r.get("date_ts") or 0)
    received.sort(key=lambda r: r.get("date_ts") or 0)
    return received, sent


def persona_seed() -> dict:
    if yhbmail.FIXTURE.exists() and is_demo():
        try:
            return json.loads(yhbmail.FIXTURE.read_text()).get("persona_seed") or {}
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def is_bulk(row: dict) -> bool:
    frm = (row.get("from_addr") or "").lower()
    return any(x in frm for x in yhbmail.NOISE_FROM) or row.get("category") == "other"


def thread_key(row: dict) -> str:
    return str(row.get("thread_id") or row.get("id") or "")


def body_lines(body: str) -> list[str]:
    """Your own words: quoted text, forwarded blocks and the signature are dropped."""
    out = []
    for ln in (body or "").splitlines():
        s = ln.strip()
        if s in ("--", "-- ", "—") or re.match(r"^-{2,}\s*(forwarded|original|轉寄)", s, re.I):
            break
        if re.match(r"^on .{4,80} wrote:$", s, re.I) or re.search(r"寫道[:：]$", s):
            break
        if s.startswith(">"):
            continue
        out.append(ln.rstrip())
    while out and not out[-1].strip():
        out.pop()
    return out


def signature_block(body: str) -> list[str]:
    lines = [ln.strip() for ln in (body or "").splitlines()]
    for i, ln in enumerate(lines):
        if ln in ("--", "-- ", "—"):
            return [x for x in lines[i + 1:i + 6] if x]
    return []


def greeting_of(lines: list[str]) -> str:
    first = next((ln.strip() for ln in lines if ln.strip()), "")
    if not first or len(first) > 60:
        return ""
    m = GREETING_RE.match(first)
    if m:
        w = m.group(1)
        return w[0].upper() + w[1:].lower()
    m = GREETING_ZH_RE.search(first)
    return m.group(1) if m else ""


def signoff_of(lines: list[str]) -> str:
    tail = [ln.strip() for ln in lines if ln.strip()][-3:]
    for ln in tail:
        if len(ln) <= 30 and CLOSING_RE.match(ln):
            return ln
    return ""


def text_lang(text: str) -> str:
    letters = sum(1 for c in text or "" if c.isalpha())
    return "zh" if letters and len(CJK_RE.findall(text)) / letters > 0.2 else "en"


def local_dt(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, yhbmail.TZ)


def _subjects(rows: list[dict], n: int = 3) -> list[str]:
    seen, out = set(), []
    for r in sorted(rows, key=lambda x: -(x.get("date_ts") or 0)):
        s = SUBJECT_PREFIX_RE.sub("", r.get("subject") or "").strip()
        if s and s.lower() not in seen:
            seen.add(s.lower())
            out.append(s[:90])
        if len(out) >= n:
            break
    return out


# ───────────────────────── inference ─────────────────────────

def item(section: str, key: str, value, lang: str, source: str, evidence: list[str] | None = None,
         basis: str = "", confidence: float = 0.0, kind: str = "text", display: str | None = None) -> dict:
    out = {"section": section, "key": key, "label": _tx(KEY_TEXT.get(key, (key, key)), lang),
           "value": value, "display": display if display is not None else ("" if value is None else str(value)),
           "source": source, "source_label": _tx(SOURCE_TEXT[source], lang), "evidence": evidence or [],
           "basis": basis, "confidence": round(confidence, 2), "kind": kind, "fixed": False, "inferred": value,
           "inferred_display": None, "note": ""}
    enum = ENUMS.get((section, key))
    if enum:
        out["kind"] = "enum"
        out["options"] = [{"id": k, "label": _tx(v, lang)} for k, v in enum.items()]
        if value in enum:
            out["display"] = _tx(enum[value], lang)
    return out


def apply_scalar_fix(it: dict, fix: dict | None, lang: str) -> dict:
    if not fix:
        return it
    it = dict(it)
    it["inferred_display"] = it["display"]
    it["value"] = fix.get("value")
    enum = ENUMS.get((it["section"], it["key"]))
    if enum and it["value"] in enum:
        it["display"] = _tx(enum[it["value"]], lang)
    elif it["key"] == "active_hours" and isinstance(it["value"], dict):
        it["display"] = hours_text(it["value"]["start"], it["value"]["end"])
    elif it["key"] == "work_days" and isinstance(it["value"], list):
        it["display"] = days_text(it["value"], lang)
    else:
        it["display"] = str(it["value"] or "")
    it["source"], it["source_label"] = "fix", _tx(SOURCE_TEXT["fix"], lang)
    it["fixed"], it["note"], it["fixed_at"] = True, fix.get("note") or "", fix.get("_at", "")
    return it


def infer_identity(received: list[dict], sent: list[dict], lang: str) -> list[dict]:
    zh = _zh(lang)
    seed = persona_seed()
    names, sig_names, roles, orgs, sigs = Counter(), Counter(), Counter(), Counter(), Counter()
    name_rows, sig_rows = defaultdict(list), defaultdict(list)
    for s in sent:
        frm = split_addrs(s.get("from_addr") or "")
        if frm and frm[0][0]:
            names[frm[0][0]] += 1
            name_rows[frm[0][0]].append(s)
        block = signature_block(s.get("body_text") or "")
        if block:
            sig = "\n".join(block[:4])
            sigs[sig] += 1
            sig_rows[sig].append(s)
            if len(block) >= 2 and "@" not in block[1] and len(block[1]) <= 80:
                parts = [p for p in SIG_ROLE_RE.split(block[1], maxsplit=1) if p and p.strip()]
                if len(parts) == 2:
                    roles[parts[0].strip()] += 1
                    orgs[parts[1].strip()] += 1
                elif parts:
                    roles[parts[0].strip()] += 1
            if "@" not in block[0] and len(block[0]) <= 40:
                sig_names[block[0]] += 1
                name_rows[block[0]].append(s)
    if not names:
        names = sig_names
    n_sent = len(sent)
    out = []

    def pick(counter: Counter, key: str, seed_value: str, rows_by: dict | None, basis_en: str, basis_zh: str):
        if counter and counter.most_common(1)[0][1] > 0:
            value, n = counter.most_common(1)[0]
            rows = (rows_by or {}).get(value) or sig_rows_all
            return item("identity", key, value, lang, "mail", _subjects(rows),
                        basis_zh.format(n=n, total=n_sent) if zh else basis_en.format(n=n, total=n_sent),
                        min(1.0, n / max(1, n_sent) + 0.3))
        if seed_value:
            return item("identity", key, seed_value, lang, "seed", [], "", 0.5)
        return item("identity", key, "", lang, "default", [], "", 0.0)

    sig_rows_all = [r for rows in sig_rows.values() for r in rows]
    out.append(pick(names, "name", seed.get("name") or "", name_rows,
                    "Display name on {n} of {total} sent emails.", "{total} 封寄件中有 {n} 封用這個寄件人名稱。"))
    out.append(pick(roles, "role", seed.get("role") or "", None,
                    "Title line in {n} signatures.", "{n} 個簽名檔的職稱行。"))
    out.append(pick(orgs, "organization", seed.get("organization") or "", None,
                    "Company in {n} signatures.", "{n} 個簽名檔寫的公司。"))
    tz = seed.get("timezone") or ""
    if tz:
        out.append(item("identity", "timezone", tz, lang, "seed", [], "", 0.6))
    else:
        off = yhbmail.TZ.utcoffset(None)
        hours = int(off.total_seconds() // 3600) if off is not None else 0
        out.append(item("identity", "timezone", f"UTC{hours:+03d}:00", lang, "config", [],
                        "OPENINBOX_TZ_OFFSET" if not zh else "依 OPENINBOX_TZ_OFFSET 設定", 0.4))
    if sigs:
        sig, n = sigs.most_common(1)[0]
        out.append(item("identity", "signature", sig, lang, "mail", _subjects(sig_rows[sig]),
                        f"{n} 封寄件用這個簽名檔。" if zh else f"Used on {n} sent emails.", min(1.0, n / max(1, n_sent) + 0.3),
                        kind="multiline"))
    else:
        out.append(item("identity", "signature", "", lang, "default", [], "", 0.0, kind="multiline"))
    return out


def infer_tone(sent: list[dict], lang: str) -> list[dict]:
    zh = _zh(lang)
    seed = persona_seed()
    greetings, signoffs, langs = Counter(), Counter(), Counter()
    sizes, scores, exclaim = [], [], 0
    for s in sent:
        lines = body_lines(s.get("body_text") or "")
        text = "\n".join(lines)
        if not text.strip():
            continue
        g, so = greeting_of(lines), signoff_of(lines)
        if g:
            greetings[g] += 1
        if so:
            signoffs[so] += 1
        langs[text_lang(text)] += 1
        words = len(WORD_RE.findall(text)) + len(CJK_RE.findall(text)) / 1.6
        sizes.append(words)
        scores.append(len(FORMAL_MARKERS.findall(text)) - len(CASUAL_MARKERS.findall(text)))
        if re.search(r"[!！]", text):
            exclaim += 1
    n = len(sizes)
    subjects = _subjects(sent)
    out = []
    if n:
        mean = sum(scores) / n
        formality = "formal" if mean >= 0.5 else "casual" if mean <= -0.5 else "balanced"
        out.append(item("tone", "formality", formality, lang, "mail", subjects,
                        (f"{n} 封寄件的正式／口語用詞平均分數 {mean:+.1f}。" if zh
                         else f"Formal vs casual markers average {mean:+.1f} over {n} sent emails."), 0.6))
        median = statistics.median(sizes)
        length = "short" if median < 60 else "medium" if median < 150 else "long"
        out.append(item("tone", "length", length, lang, "mail", subjects,
                        f"中位數約 {int(median)} 字。" if zh else f"Median about {int(median)} words.", 0.7))
    else:
        out.append(item("tone", "formality", "balanced", lang, "default"))
        out.append(item("tone", "length", "medium", lang, "default"))
    for key, counter in (("greeting", greetings), ("signoff", signoffs)):
        if counter:
            v, k = counter.most_common(1)[0]
            out.append(item("tone", key, v, lang, "mail", [f"{w} ×{c}" for w, c in counter.most_common(3)],
                            f"{n} 封裡有 {k} 封。" if zh else f"{k} of {n} sent emails.", k / max(1, n)))
        else:
            out.append(item("tone", key, "", lang, "default"))
    if langs:
        names = {"en": ("English", "英文"), "zh": ("Chinese", "中文")}
        total = sum(langs.values())
        disp = " · ".join(f"{_tx(names[k], lang)} {round(100 * c / total)}%" for k, c in langs.most_common())
        out.append(item("tone", "languages", ", ".join(k for k, _ in langs.most_common()), lang, "mail", [],
                        f"依 {total} 封寄件的文字判斷。" if zh else f"Detected on {total} sent emails.", 0.8,
                        display=disp))
    else:
        out.append(item("tone", "languages", "", lang, "default"))
    if n:
        ratio = exclaim / n
        ex = "avoid" if ratio == 0 else "sometimes" if ratio < 0.35 else "often"
        out.append(item("tone", "exclamations", ex, lang, "mail", [],
                        f"{n} 封裡有 {exclaim} 封用了驚嘆號。" if zh else f"{exclaim} of {n} sent emails use one.", 0.6))
    else:
        out.append(item("tone", "exclamations", "sometimes", lang, "default"))
    rules = [str(x) for x in seed.get("how_you_write") or []]
    out.append(item("tone", "rules", "\n".join(rules), lang, "seed" if rules else "default", [], "",
                    0.5 if rules else 0.0, kind="multiline"))
    return out


def voice_traits(lang: str) -> list[str]:
    if compose is None:
        return []
    try:
        v = compose.voice_profile()
    except Exception:
        return []
    return list(v.get("traits_zh" if _zh(lang) else "traits_en") or [])[:6]


def org_slug(identity: list[dict]) -> str:
    org = next((i["value"] for i in identity if i["key"] == "organization"), "") or ""
    words = [w.lower() for w in WORD_RE.findall(org) if len(w) >= 4 and w.lower() not in ("labs", "studio", "group")]
    return words[0] if words else ""


def relationship_for(addr: str, blob: str, own_domains: set, slug: str) -> tuple[str, int]:
    domain = addr.split("@")[-1]
    if domain in own_domains or (slug and slug in domain):
        return "teammate", 9
    hits = Counter()
    for rel, rx in RELATION_RULES:
        hits[rel] = len(rx.findall(blob))
    rel, n = hits.most_common(1)[0]
    return (rel, n) if n else ("other", 0)


def infer_contacts(received: list[dict], sent: list[dict], identity: list[dict], lang: str) -> list[dict]:
    zh = _zh(lang)
    own = own_addresses()
    generic = {"example.com", "gmail.com", "outlook.com", "hotmail.com", "yahoo.com", "icloud.com"}
    own_domains = {a.split("@")[-1] for a in own} - generic
    slug = org_slug(identity)
    stats: dict = defaultdict(lambda: {"names": Counter(), "received": 0, "sent": 0, "last": 0, "rows": [],
                                       "threads": set()})
    for r in received:
        if is_bulk(r):
            continue
        for name, addr in split_addrs(r.get("from_addr") or "")[:1]:
            if addr in own:
                continue
            st = stats[addr]
            st["received"] += 1
            if name:
                st["names"][name] += 1
            st["last"] = max(st["last"], r.get("date_ts") or 0)
            st["rows"].append(r)
            st["threads"].add(thread_key(r))
    for s in sent:
        seen = set()
        for field in ("to_addr", "cc_addr", "cc"):
            for name, addr in split_addrs(s.get(field) or ""):
                if addr in own or addr in seen or any(x in addr for x in yhbmail.NOISE_FROM):
                    continue
                seen.add(addr)
                st = stats[addr]
                st["sent"] += 1
                if name:
                    st["names"][name] += 1
                st["last"] = max(st["last"], s.get("date_ts") or 0)
                st["rows"].append(s)
                st["threads"].add(thread_key(s))
    out = []
    for addr, st in stats.items():
        if not (st["sent"] >= 1 or st["received"] >= 2):
            continue
        blob = " ".join(f"{r.get('subject') or ''} {r.get('body_text') or r.get('snippet') or ''}" for r in st["rows"])
        rel, strength = relationship_for(addr, blob, own_domains, slug)
        name = st["names"].most_common(1)[0][0] if st["names"] else addr.split("@")[0].capitalize()
        direction = "two_way" if st["sent"] and st["received"] else "outbound" if st["sent"] else "inbound"
        dir_text = {"two_way": ("Two-way", "雙向往來"), "outbound": ("Mostly you write", "多半是你寫給對方"),
                    "inbound": ("Mostly they write", "多半是對方寫來")}[direction]
        if rel == "teammate":
            basis = "與你同一個網域／公司。" if zh else "Same domain / company as you."
        elif strength:
            basis = (f"信件內容有 {strength} 處和「{_tx(RELATIONSHIPS[rel], 'zh')}」相關的字詞。" if zh
                     else f"{strength} mentions in your threads point to {RELATIONSHIPS[rel][0].lower()}.")
        else:
            basis = "信件內容看不出明確關係。" if zh else "Nothing in the threads says what they are to you."
        out.append({
            "section": "contacts", "key": addr, "email": addr, "name": name, "relationship": rel,
            "relationship_label": _tx(RELATIONSHIPS[rel], lang), "inferred_relationship": rel,
            "received": st["received"], "sent": st["sent"], "threads": len(st["threads"]),
            "score": st["sent"] * 2 + st["received"], "direction": direction, "direction_label": _tx(dir_text, lang),
            "last": local_dt(st["last"]).isoformat(timespec="minutes") if st["last"] else "",
            "evidence": _subjects(st["rows"]), "basis": basis, "source": "mail",
            "source_label": _tx(SOURCE_TEXT["mail"], lang), "fixed": False, "note": "", "hidden": False,
            "manual": False,
        })
    out.sort(key=lambda c: (-c["score"], -c["threads"], c["email"]))
    return out[:12]


def apply_contact_fixes(contacts: list[dict], fixes: dict, lang: str) -> list[dict]:
    by_key = {c["key"]: dict(c) for c in contacts}
    order = [c["key"] for c in contacts]
    for key, fix in fixes.items():
        c = by_key.get(key)
        if c is None:
            c = {"section": "contacts", "key": key, "email": key, "name": key.split("@")[0].capitalize(),
                 "relationship": "other", "inferred_relationship": None, "received": 0, "sent": 0, "threads": 0,
                 "score": 0, "direction": "", "direction_label": "", "last": "", "evidence": [], "basis": "",
                 "manual": True, "hidden": False, "note": ""}
            by_key[key] = c
            order.append(key)
        c["inferred_name"] = c.get("name")
        if fix.get("name"):
            c["name"] = fix["name"]
        if fix.get("relationship"):
            c["relationship"] = fix["relationship"]
        c["note"] = fix.get("note") or ""
        c["hidden"] = bool(fix.get("hidden"))
        c["fixed"], c["fixed_at"] = True, fix.get("_at", "")
        c["source"], c["source_label"] = "fix", _tx(SOURCE_TEXT["fix"], lang)
    for c in by_key.values():
        rel = c["relationship"]
        c["relationship_label"] = _tx(RELATIONSHIPS[rel], lang) if rel in RELATIONSHIPS else rel
    return [by_key[k] for k in order]


def _tokens(text: str) -> list[tuple[str, str, int, int, bool]]:
    """(lower, original, start, end, at_sentence_start) for each word."""
    out = []
    for m in WORD_RE.finditer(text):
        orig = m.group(0)
        low = re.sub(r"'s$", "", orig.lower()).strip("'-")
        before = text[:m.start()].rstrip()
        at_start = not before or before[-1] in ".!?:：\n。！？"
        out.append((low, orig, m.start(), m.end(), at_start))
    return out


def infer_projects(received: list[dict], sent: list[dict], contacts: list[dict], identity: list[dict],
                   lang: str) -> list[dict]:
    zh = _zh(lang)
    own = own_addresses()
    pool = [r for r in received if not is_bulk(r)] + sent
    exclude = set(STOPWORDS)
    for c in contacts:
        exclude |= {w.lower() for w in WORD_RE.findall(c.get("name") or "")}
        exclude |= {w.lower() for w in WORD_RE.findall(c["email"].split("@")[0])}
    for r in pool:
        for field in ("from_addr", "to_addr", "cc_addr"):
            for name, addr in split_addrs(r.get(field) or ""):
                exclude |= {w.lower() for w in WORD_RE.findall(name)}
                exclude |= {w.lower() for w in WORD_RE.findall(addr.split("@")[0])}
    for i in identity:
        if i["key"] in ("name", "organization", "role"):
            exclude |= {w.lower() for w in WORD_RE.findall(str(i["value"] or ""))}
    exclude |= {a.split("@")[0] for a in own}

    threads: dict = defaultdict(set)
    messages: Counter = Counter()
    in_subject: Counter = Counter()
    forms: dict = defaultdict(Counter)
    proper: Counter = Counter()
    rows_by_thread: dict = defaultdict(list)
    for r in pool:
        tkey = thread_key(r)
        rows_by_thread[tkey].append(r)
        subject = SUBJECT_PREFIX_RE.sub("", r.get("subject") or "")
        lines = body_lines(r.get("body_text") or r.get("snippet") or "")
        if lines and (GREETING_RE.match(lines[0].strip()) or GREETING_ZH_RE.search(lines[0])):
            lines = lines[1:]
        lines = [ln for ln in lines if not CLOSING_RE.match(ln.strip()) and len(ln.strip()) > 0]
        if lines and len(lines[-1].strip()) <= 20 and len(WORD_RE.findall(lines[-1])) <= 2:
            lines = lines[:-1]
        seen_here: set = set()
        for part, is_subject in ((subject, True), ("\n".join(lines), False)):
            toks = _tokens(part)
            terms = []
            for i, (low, orig, start, end, at_start) in enumerate(toks):
                if len(low) >= 4 and low not in exclude:
                    terms.append((low, orig, orig[:1].isupper() and not at_start))
                if i + 1 < len(toks):
                    nlow, norig, nstart, _, _ = toks[i + 1]
                    if (low not in exclude and nlow not in exclude and len(low) >= 3 and len(nlow) >= 3
                            and not part[end:nstart].strip()):
                        both_caps = orig[:1].isupper() and norig[:1].isupper()
                        terms.append((f"{low} {nlow}", f"{orig} {norig}", both_caps))
            for low, orig, is_proper in terms:
                forms[low][orig] += 1
                if is_proper:
                    proper[low] += 1
                threads[low].add(tkey)
                if is_subject:
                    in_subject[low] += 1
                if low not in seen_here:
                    messages[low] += 1
                    seen_here.add(low)
    qualifying = {t for t, ths in threads.items() if len(ths) >= 2 and in_subject[t]}
    bigram_words = {w for t in qualifying if " " in t for w in t.split()}
    cands = [t for t in qualifying if " " in t or t not in bigram_words]

    def jaccard(a: set, b: set) -> float:
        return len(a & b) / max(1, len(a | b))

    clusters: list[dict] = []
    for t in sorted(cands, key=lambda x: (-len(threads[x]), -messages[x], x)):
        home = next((c for c in clusters if jaccard(c["threads"], threads[t]) >= 0.5), None)
        if home:
            home["terms"].append(t)
            home["threads"] |= threads[t]
        else:
            clusters.append({"terms": [t], "threads": set(threads[t])})

    def name_score(t: str):
        return (proper[t] > 0, len(threads[t]), " " in t, messages[t])

    events = yhbmail.list_events()
    sent_ids = {s.get("id") for s in sent}
    ref = max([r.get("date_ts") or 0 for r in pool] or [0])
    out = []
    for c in clusters[:8]:
        main = max(c["terms"], key=name_score)
        caps = [f for f in forms[main] if f[:1].isupper()]
        display = max(caps or forms[main], key=lambda f: (forms[main][f], f))
        display = display[:1].upper() + display[1:]
        rows = [r for tk in c["threads"] for r in rows_by_thread[tk]]
        rows.sort(key=lambda r: r.get("date_ts") or 0)
        people = Counter()
        for r in rows:
            for field in ("from_addr", "to_addr", "cc_addr"):
                for name, addr in split_addrs(r.get(field) or ""):
                    if addr not in own and not any(x in addr for x in yhbmail.NOISE_FROM):
                        people[name or addr] += 1
        evs = [e for e in events if any(t in (e.get("title") or "").lower() for t in c["terms"])]
        last = rows[-1].get("date_ts") or 0 if rows else 0
        upcoming = [e for e in evs if yhbmail.parse_date_ts(e.get("start_local") or "") >= ref]
        status = "active" if (ref - last) <= 21 * 86400 or upcoming else "paused"
        thread_list = []
        for tk in sorted(c["threads"], key=lambda k: -max(r.get("date_ts") or 0 for r in rows_by_thread[k])):
            latest = max(rows_by_thread[tk], key=lambda r: r.get("date_ts") or 0)
            inbox = [r for r in rows_by_thread[tk] if r.get("id") not in sent_ids]
            link = max(inbox, key=lambda r: r.get("date_ts") or 0) if inbox else latest
            thread_list.append({"thread": tk, "id": link.get("id"),
                                "subject": SUBJECT_PREFIX_RE.sub("", link.get("subject") or "").strip(),
                                "date": local_dt(latest["date_ts"]).isoformat(timespec="minutes")
                                if latest.get("date_ts") else "",
                                "in_inbox": bool(inbox), "messages": len(rows_by_thread[tk])})
        pid = re.sub(r"[^a-z0-9]+", "-", main.lower()).strip("-")[:40] or "project"
        out.append({
            "section": "projects", "key": pid, "id": pid, "name": display, "inferred_name": display,
            "terms": c["terms"], "keywords": [t for t in c["terms"] if t != main][:4],
            "status": status, "inferred_status": status, "status_label": _tx(PROJECT_STATUS[status], lang),
            "messages": len(rows), "thread_count": len(c["threads"]), "threads": thread_list[:6],
            "people": [p for p, _ in people.most_common(4)],
            "events": [{"title": e.get("title"), "start": e.get("start_local")} for e in evs][:3],
            "first": local_dt(rows[0]["date_ts"]).isoformat(timespec="minutes") if rows and rows[0].get("date_ts") else "",
            "last": local_dt(last).isoformat(timespec="minutes") if last else "",
            "basis": (f"「{display}」出現在 {len(c['threads'])} 個信件串、{len(rows)} 封信。" if zh
                      else f"“{display}” comes up in {len(c['threads'])} threads, {len(rows)} emails."),
            "source": "mail", "source_label": _tx(SOURCE_TEXT["mail"], lang), "fixed": False, "note": "",
            "hidden": False, "manual": False,
        })
    return out


def apply_project_fixes(projects: list[dict], fixes: dict, lang: str) -> list[dict]:
    by_key = {p["key"]: dict(p) for p in projects}
    order = [p["key"] for p in projects]
    for key, fix in fixes.items():
        p = by_key.get(key)
        if p is None:
            p = {"section": "projects", "key": key, "id": key, "name": fix.get("name") or key, "inferred_name": None,
                 "terms": [], "keywords": [], "status": "active", "inferred_status": None, "messages": 0,
                 "thread_count": 0, "threads": [], "people": [], "events": [], "first": "", "last": "", "basis": "",
                 "manual": True, "hidden": False, "note": ""}
            by_key[key] = p
            order.append(key)
        if fix.get("name"):
            p["name"] = fix["name"]
        if fix.get("status"):
            p["status"] = fix["status"]
        p["note"] = fix.get("note") or ""
        p["hidden"] = bool(fix.get("hidden"))
        p["fixed"], p["fixed_at"] = True, fix.get("_at", "")
        p["source"], p["source_label"] = "fix", _tx(SOURCE_TEXT["fix"], lang)
    for p in by_key.values():
        p["status_label"] = _tx(PROJECT_STATUS.get(p["status"], (p["status"], p["status"])), lang)
    return [by_key[k] for k in order]


def hours_text(start: int, end: int) -> str:
    return f"{start // 60:02d}:{start % 60:02d}–{end // 60:02d}:{end % 60:02d}"


def days_text(days: list[str], lang: str) -> str:
    idx = sorted(DAYS.index(d) for d in days if d in DAYS)
    if not idx:
        return ""
    if idx == list(range(idx[0], idx[-1] + 1)) and len(idx) >= 3:
        return f"{_tx(DAY_TEXT[DAYS[idx[0]]], lang)}–{_tx(DAY_TEXT[DAYS[idx[-1]]], lang)}"
    return ("、" if _zh(lang) else ", ").join(_tx(DAY_TEXT[DAYS[i]], lang) for i in idx)


def reply_minutes(received: list[dict], sent: list[dict]) -> list[float]:
    by_id = {r.get("id"): r for r in received}
    by_thread = defaultdict(list)
    for r in received:
        by_thread[thread_key(r)].append(r)
    out = []
    for s in sent:
        ts = s.get("date_ts") or 0
        if not ts:
            continue
        src = by_id.get(s.get("in_reply_to"))
        if not src:
            earlier = [r for r in by_thread.get(thread_key(s), []) if 0 < (r.get("date_ts") or 0) < ts]
            src = max(earlier, key=lambda r: r["date_ts"]) if earlier else None
        if src and 0 < (src.get("date_ts") or 0) < ts:
            out.append((ts - src["date_ts"]) / 60)
    return out


def infer_work(received: list[dict], sent: list[dict], lang: str) -> list[dict]:
    zh = _zh(lang)
    stamps = [s["date_ts"] for s in sent if s.get("date_ts")]
    out = []
    n = len(stamps)
    if n:
        hours = Counter(local_dt(ts).hour for ts in stamps)
        need = math.ceil(0.8 * n)
        best = (24, 0)
        for length in range(1, 25):
            for start in range(24):
                if sum(hours[(start + k) % 24] for k in range(length)) >= need:
                    best = (length, start)
                    break
            if best[0] == length:
                break
        length, start = best
        s_min, e_min = start * 60, ((start + length) % 24) * 60 or 24 * 60
        late = sum(c for h, c in hours.items() if h >= 22 or h < 6)
        basis = (f"{n} 封寄件有 {need} 封落在這個時段" + (f"；{late} 封在 22:00 之後。" if late else "。")) if zh else \
            (f"{need} of {n} sent emails fall in this window" + (f"; {late} after 22:00." if late else "."))
        out.append(item("work_patterns", "active_hours", {"start": s_min, "end": e_min}, lang, "mail",
                        [], basis, 0.7, kind="hours", display=hours_text(s_min, e_min)))
        days = Counter(DAYS[local_dt(ts).weekday()] for ts in stamps)
        active_days = [d for d in DAYS if days[d]]
        dbasis = " · ".join(f"{_tx(DAY_TEXT[d], lang)} {days[d]}" for d in DAYS if days[d])
        out.append(item("work_patterns", "work_days", active_days, lang, "mail", [], dbasis, 0.6, kind="days",
                        display=days_text(active_days, lang)))
        top = [h for h, c in hours.most_common() if c == hours.most_common(1)[0][1]][:3]
        peak = ", ".join(f"{h:02d}:00" for h in sorted(top))
        out.append(item("work_patterns", "peak_hours", peak, lang, "mail", [],
                        f"寄件最多的整點（{hours.most_common(1)[0][1]} 封）。" if zh
                        else f"Hours with the most sent mail ({hours.most_common(1)[0][1]} each).", 0.5))
    else:
        out.append(item("work_patterns", "active_hours", None, lang, "default", kind="hours", display=""))
        out.append(item("work_patterns", "work_days", [], lang, "default", kind="days", display=""))
        out.append(item("work_patterns", "peak_hours", "", lang, "default"))
    mins = reply_minutes(received, sent)
    if mins:
        med = statistics.median(mins)
        speed = ("within_hour" if med <= 60 else "within_hours" if med <= 240 else "same_day" if med <= 1440
                 else "next_day" if med <= 2880 else "slower")
        h, m = int(med // 60), int(med % 60)
        span = (f"{h} 小時 {m} 分" if h else f"{m} 分") if zh else (f"{h} h {m} min" if h else f"{m} min")
        out.append(item("work_patterns", "reply_speed", speed, lang, "mail", [],
                        f"{len(mins)} 次回覆的中位數：{span}。" if zh else f"Median of {len(mins)} replies: {span}.", 0.6))
    else:
        out.append(item("work_patterns", "reply_speed", "same_day", lang, "default"))
    inbox_hours = Counter(local_dt(r["date_ts"]).hour for r in received if r.get("date_ts") and not is_bulk(r))
    note = ""
    busy = [h for h, c in inbox_hours.most_common(3) if c >= 2]
    if busy:
        top = ", ".join(f"{h:02d}:00" for h in sorted(busy))
        note = f"來信最多的時段：{top}" if zh else f"Mail from people arrives most at {top}"
    out.append(item("work_patterns", "notes", "", lang, "default", [], note, 0.0, kind="multiline"))
    return out


def build_profile(lang: str = "en") -> dict:
    zh = _zh(lang)
    received, sent = load_mail()
    fixes = load_fixes()
    identity = [apply_scalar_fix(i, fixes["identity"].get(i["key"]), lang) for i in infer_identity(received, sent, lang)]
    tone = [apply_scalar_fix(i, fixes["tone"].get(i["key"]), lang) for i in infer_tone(sent, lang)]
    work = [apply_scalar_fix(i, fixes["work_patterns"].get(i["key"]), lang) for i in infer_work(received, sent, lang)]
    contacts = apply_contact_fixes(infer_contacts(received, sent, identity, lang), fixes["contacts"], lang)
    projects = apply_project_fixes(infer_projects(received, sent, contacts, identity, lang), fixes["projects"], lang)
    sections = []
    for sid, items in (("identity", identity), ("tone", tone), ("contacts", contacts), ("projects", projects),
                       ("work_patterns", work)):
        en, zh_name, d_en, d_zh = SECTION_TEXT[sid]
        sections.append({"id": sid, "name": zh_name if zh else en, "description": d_zh if zh else d_en,
                         "items": items, "fixed": sum(1 for i in items if i.get("fixed")),
                         "count": sum(1 for i in items if not i.get("hidden"))})
    n_fixes = sum(len(v) for v in fixes.values())
    return {
        "lang": "zh-Hant" if zh else "en",
        "sections": sections,
        "learned_voice": voice_traits(lang),
        "sources": {"received": len(received), "sent": len(sent), "demo_sent": is_demo() and SENT_FIXTURE.exists()},
        "fixes": n_fixes,
        "relationships": [{"id": k, "label": _tx(v, lang)} for k, v in RELATIONSHIPS.items()],
        "project_statuses": [{"id": k, "label": _tx(v, lang)} for k, v in PROJECT_STATUS.items()],
        "days": [{"id": d, "label": _tx(DAY_TEXT[d], lang)} for d in DAYS],
        "note": ("只讀本機快取的信件與寄件備份；修正存在本機，會立即套用到 persona 與 AI 草稿。" if zh else
                 "Reads only locally cached mail and your sent mail; fixes stay on this machine and apply to the "
                 "persona and AI drafts right away."),
        "updated_at": yhbmail.now_iso(),
    }


def section_items(profile: dict, sid: str) -> list[dict]:
    return next((s["items"] for s in profile["sections"] if s["id"] == sid), [])


def values(profile: dict, sid: str) -> dict:
    return {i["key"]: i for i in section_items(profile, sid)}


# ───────────────────────── fixes ─────────────────────────

def parse_hours(value) -> dict | None:
    if isinstance(value, dict):
        try:
            raw = f"{value.get('start')}-{value.get('end')}"
        except Exception:
            return None
    else:
        raw = str(value or "")
    m = HHMM_RE.match(raw)
    if not m:
        return None
    sh, sm, eh, em = int(m.group(1)), int(m.group(2) or 0), int(m.group(3)), int(m.group(4) or 0)
    if not (0 <= sh <= 23 and 0 <= eh <= 24 and sm < 60 and em < 60) or (eh == 24 and em):
        return None
    start, end = sh * 60 + sm, eh * 60 + em
    if start == end:
        return None
    return {"start": start, "end": end}


def parse_days(value) -> list[str] | None:
    if isinstance(value, list):
        parts = [str(x) for x in value]
    else:
        raw = str(value or "").strip().lower()
        raw = re.sub(r"(週|星期|禮拜)", "", raw)
        parts = [p for p in re.split(r"[,，、\s]+", raw) if p]
    out: list[str] = []
    for p in parts:
        p = p.strip().lower()
        rng = re.split(r"\s*(?:-|–|~|～|到|至)\s*", p)
        if len(rng) == 2 and all(x in DAY_ALIASES for x in rng):
            a, b = DAYS.index(DAY_ALIASES[rng[0]]), DAYS.index(DAY_ALIASES[rng[1]])
            span = range(a, b + 1) if a <= b else list(range(a, 7)) + list(range(0, b + 1))
            out += [DAYS[i] for i in span]
        elif p in DAY_ALIASES:
            out.append(DAY_ALIASES[p])
        else:
            return None
    return [d for d in DAYS if d in out] or None


def _err(msg_en: str, msg_zh: str, lang: str) -> tuple[dict, int]:
    return {"error": msg_zh if _zh(lang) else msg_en}, 400


def save_fix(body: dict, lang: str) -> tuple[dict, int]:
    section = str(body.get("section") or "")
    if section not in SECTIONS:
        return _err(f"section must be one of {', '.join(SECTIONS)}", f"section 必須是 {'、'.join(SECTIONS)} 之一", lang)
    key = _clip(body.get("key"), 120)
    note = _clip(body.get("note"), LIMITS["note"])
    if section in KEYS:
        if key not in KEYS[section]:
            return _err(f"key must be one of {', '.join(KEYS[section])}", f"key 必須是 {'、'.join(KEYS[section])} 之一", lang)
        if "value" not in body:
            return _err("value is required", "缺少 value", lang)
        raw = body.get("value")
        enum = ENUMS.get((section, key))
        if enum:
            value = str(raw or "")
            if value not in enum:
                return _err(f"value must be one of {', '.join(enum)}", f"value 必須是 {'、'.join(enum)} 之一", lang)
        elif key == "active_hours":
            value = parse_hours(raw)
            if not value:
                return _err("active_hours must look like 09:00-18:00", "活躍時段格式要像 09:00-18:00", lang)
        elif key == "work_days":
            value = parse_days(raw)
            if not value:
                return _err("work_days must list days, e.g. mon-fri", "工作日要列出星期，例如 mon-fri 或 週一到週五", lang)
        else:
            limit = LIMITS["rules"] if key in ("rules", "signature", "notes") else LIMITS["text"]
            value = _clip(raw, limit)
            if not value and key not in ("rules", "notes", "signature"):
                return _err("value is empty (use reset to go back to the inference)",
                            "value 是空的（要回到推論值請用「還原」）", lang)
        fix = {"value": value, "note": note}
    elif section == "contacts":
        key = key.lower()
        if not ADDR_RE.fullmatch(key):
            return _err("key must be the contact's email address", "key 必須是聯絡人的信箱位址", lang)
        old = load_fixes()["contacts"].get(key) or {}
        fix = {k: v for k, v in old.items() if not k.startswith("_")}
        if "relationship" in body:
            rel = _clip(body.get("relationship"), 40)
            if not rel:
                return _err("relationship is empty", "關係不能是空的", lang)
            fix["relationship"] = rel.lower() if rel.lower() in RELATIONSHIPS else rel
        if "name" in body:
            fix["name"] = _clip(body.get("name"), LIMITS["name"])
        if "note" in body:
            fix["note"] = note
        if "hidden" in body:
            fix["hidden"] = bool(body.get("hidden"))
        if not any(fix.get(k) for k in ("relationship", "name", "note", "hidden")):
            if old and "hidden" in body:
                delete_fixes(section, key)
                return applied(section, key, lang), 200
            return _err("give a relationship, name, note or hidden", "請給 relationship、name、note 或 hidden", lang)
    else:
        name = _clip(body.get("name"), LIMITS["name"])
        if not key:
            if not name:
                return _err("a new project needs a name", "新專案需要名稱", lang)
            key = "manual-" + (re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:32] or
                               str(abs(hash(name)) % 100000))
        if not re.fullmatch(r"[a-z0-9][a-z0-9\-]{0,63}", key):
            return _err("bad project key", "專案 key 格式不對", lang)
        old = load_fixes()["projects"].get(key) or {}
        fix = {k: v for k, v in old.items() if not k.startswith("_")}
        if "name" in body:
            fix["name"] = name
        if "status" in body:
            status = str(body.get("status") or "")
            if status not in PROJECT_STATUS:
                return _err(f"status must be one of {', '.join(PROJECT_STATUS)}",
                            f"status 必須是 {'、'.join(PROJECT_STATUS)} 之一", lang)
            fix["status"] = status
        if "note" in body:
            fix["note"] = note
        if "hidden" in body:
            fix["hidden"] = bool(body.get("hidden"))
        if not any(fix.get(k) for k in ("name", "status", "note", "hidden")):
            if old and "hidden" in body:
                delete_fixes(section, key)
                return applied(section, key, lang), 200
            return _err("give a name, status, note or hidden", "請給 name、status、note 或 hidden", lang)
        inferred = {p["key"] for p in section_items(build_profile(lang), "projects") if not p.get("manual")}
        if key not in inferred and not fix.get("name"):
            return _err("a new project needs a name", "新專案需要名稱", lang)
    _store_fix(section, key, fix)
    return applied(section, key, lang), 200


def applied(section: str, key: str, lang: str) -> dict:
    p = refresh_persona()
    profile = build_profile(lang)
    it = next((i for i in section_items(profile, section) if i["key"] == key), None)
    zh = _zh(lang)
    return {"ok": True, "section": section, "key": key, "item": it, "profile": profile,
            "persona": {"identity": p.get("identity"), "email_brain": p.get("email_brain")},
            "prompt": prompt_block(lang),
            "note": "已修正並存在本機；persona 與 AI 草稿 prompt 已更新。" if zh
            else "Fixed and saved locally; the persona and the AI draft prompt are updated."}


def reset_fix(body: dict, lang: str) -> tuple[dict, int]:
    if body.get("all"):
        n = delete_fixes()
    else:
        section = str(body.get("section") or "")
        if section not in SECTIONS:
            return _err(f"section must be one of {', '.join(SECTIONS)}", f"section 必須是 {'、'.join(SECTIONS)} 之一", lang)
        key = _clip(body.get("key"), 120)
        if not key:
            return _err("give a key or all: true", "請給 key 或 all: true", lang)
        n = delete_fixes(section, key.lower() if section == "contacts" else key)
    out = applied(str(body.get("section") or ""), _clip(body.get("key"), 120), lang)
    out["deleted"] = n
    out["note"] = "已還原成從信件推得的結果。" if _zh(lang) else "Back to what your mail says."
    return out, 200


# ───────────────────────── persona + draft prompt ─────────────────────────

def compact(profile: dict) -> dict:
    ident = values(profile, "identity")
    tone = values(profile, "tone")
    work = values(profile, "work_patterns")
    return {
        "updated_at": profile["updated_at"],
        "fixes": profile["fixes"],
        "fixed": sorted(f"{i['section']}.{i['key']}" for s in profile["sections"] for i in s["items"] if i.get("fixed")),
        "identity": {k: ident[k]["value"] for k in ("name", "role", "organization", "timezone", "signature") if k in ident},
        "tone": {k: v["value"] for k, v in tone.items()},
        "contacts": [{"name": c["name"], "email": c["email"], "relationship": c["relationship"], "note": c.get("note") or ""}
                     for c in section_items(profile, "contacts") if not c.get("hidden")][:10],
        "projects": [{"name": p["name"], "status": p["status"], "note": p.get("note") or "", "last": p.get("last") or ""}
                     for p in section_items(profile, "projects") if not p.get("hidden")][:8],
        "work_patterns": {k: v["display"] if k in ("active_hours", "work_days") else v["value"] for k, v in work.items()},
    }


MD_HEADING = "## Email Brain / 信件大腦"
VOICE_HEADING = "\n## 學到的語氣 / Learned voice"


def persona_md(brain: dict) -> str:
    ident = brain["identity"]
    tone = brain["tone"]
    work = brain["work_patterns"]
    who = " · ".join(str(ident.get(k)) for k in ("name", "role", "organization", "timezone") if ident.get(k))
    lines = [MD_HEADING, f"- Identity / 身分: {who}",
             f"- Tone / 語氣: {tone.get('formality')} · {tone.get('length')}"
             + (f" · “{tone.get('greeting')}” … “{tone.get('signoff')}”" if tone.get("greeting") or tone.get("signoff") else "")]
    if tone.get("rules"):
        lines.append("- Rules / 規則: " + " / ".join(x.strip() for x in str(tone["rules"]).splitlines() if x.strip()))
    if brain["contacts"]:
        lines.append("- Contacts / 常聯絡人: " + ", ".join(f"{c['name']} ({c['relationship']})" for c in brain["contacts"][:6]))
    if brain["projects"]:
        lines.append("- Projects / 進行中專案: " + ", ".join(f"{p['name']} ({p['status']})" for p in brain["projects"]))
    lines.append(f"- Work pattern / 工作模式: {work.get('active_hours') or '—'} · {work.get('work_days') or '—'}")
    lines.append(f"- Fixes / 修正: {brain['fixes']}")
    return "\n".join(lines) + "\n"


def attach_brain(p: dict, profile: dict | None = None) -> dict:
    """Fold the (fixed) Email Brain into a persona dict and rewrite vault/persona.{json,md}."""
    profile = profile or build_profile("en")
    brain = compact(profile)
    p = dict(p)
    identity = dict(p.get("identity") or {})
    for k in ("name", "role", "organization", "timezone"):
        if brain["identity"].get(k):
            identity[k] = brain["identity"][k]
    identity["fixed"] = sorted(k.split(".", 1)[1] for k in brain["fixed"] if k.startswith("identity."))
    p["identity"] = identity
    p["email_brain"] = brain
    persona.PERSONA_PATH.parent.mkdir(parents=True, exist_ok=True)
    persona.PERSONA_PATH.write_text(json.dumps(p, ensure_ascii=False, indent=2))
    md_path = persona.PERSONA_PATH.with_suffix(".md")
    md = md_path.read_text() if md_path.exists() else "# 更了解你 / Know you better\n"
    head, sep, voice = md.partition(VOICE_HEADING)
    head = re.sub(r"\n?" + re.escape(MD_HEADING) + r"\n.*?(?=\n## |\Z)", "", head, flags=re.S).rstrip()
    who = " · ".join(str(identity[k]) for k in ("name", "role", "organization") if identity.get(k))
    head = re.sub(r"(## 身分 / Identity\n)- [^\n]*", lambda m: m.group(1) + "- " + who, head, count=1)
    md = head + "\n\n" + persona_md(brain) + (sep + voice if sep else "")
    md_path.write_text(md)
    return p


def refresh_persona() -> dict:
    return attach_brain(persona.load())


def _install_persona_hook() -> None:
    core = persona.rebuild
    if getattr(core, "_tpi_brain", False):
        return

    def rebuild_with_brain():
        return attach_brain(core())

    rebuild_with_brain._tpi_brain = True
    persona.rebuild = rebuild_with_brain


def _recipients(item_id: str, to: str) -> list[str]:
    out = [a for _, a in split_addrs(to or "")]
    if item_id:
        row = yhbmail.get_email(item_id)
        if row:
            out += [a for _, a in split_addrs(row.get("from_addr") or "")]
    return list(dict.fromkeys(out))


def prompt_block(lang: str = "en", item_id: str = "", to: str = "", subject: str = "") -> str:
    """The 'about the user' block added to every AI Write prompt. Fixed items are marked as such."""
    zh = _zh(lang)
    profile = build_profile(lang)
    mark = "（使用者已修正）" if zh else " (corrected by the user)"
    ident, tone, work = values(profile, "identity"), values(profile, "tone"), values(profile, "work_patterns")

    def v(d, k):
        it = d.get(k) or {}
        return (it.get("display") or "", mark if it.get("fixed") else "")

    lines = ["關於使用者（Email Brain；使用者的修正優先於推論）：" if zh
             else "About the user (Email Brain; the user's corrections override inferences):"]
    who = []
    for k in ("name", "role", "organization", "timezone"):
        val, m = v(ident, k)
        if val:
            who.append(f"{_tx(KEY_TEXT[k], lang)}：{val}{m}" if zh else f"{KEY_TEXT[k][0].lower()}: {val}{m}")
    if who:
        lines.append(("- 身分：" if zh else "- Identity: ") + ("；" if zh else "; ").join(who))
    sig, m = v(ident, "signature")
    if sig and ident["signature"].get("fixed"):
        lines.append(("- 簽名檔" + m + "：" if zh else "- Signature" + m + ": ") + sig.replace("\n", " / "))
    t = []
    for k in ("formality", "length", "greeting", "signoff", "exclamations"):
        val, m = v(tone, k)
        if not val:
            continue
        if k in ("greeting", "signoff"):
            if text_lang(val) != ("zh" if zh else "en"):
                continue
            val = f"「{val}」" if zh else f"“{val}”"
        t.append(f"{_tx(KEY_TEXT[k], lang)}：{val}{m}" if zh else f"{KEY_TEXT[k][0].lower()}: {val}{m}")
    if t:
        lines.append(("- 語氣：" if zh else "- Tone: ") + ("；" if zh else "; ").join(t))
    rules, m = v(tone, "rules")
    if rules:
        lines.append(("- 寫信規則" + m + "：" if zh else "- Writing rules" + m + ": ")
                     + " / ".join(x.strip() for x in rules.splitlines() if x.strip()))
    contacts = [c for c in section_items(profile, "contacts") if not c.get("hidden")]
    for addr in _recipients(item_id, to):
        c = next((x for x in section_items(profile, "contacts") if x["email"] == addr), None)
        if not c or c.get("hidden"):
            continue
        m = mark if c.get("fixed") else ""
        line = (f"- 收件者：{c['name']} <{c['email']}>，關係：{c['relationship_label']}{m}" if zh
                else f"- Recipient: {c['name']} <{c['email']}>, relationship: {c['relationship_label']}{m}")
        if c.get("note"):
            line += (f"。備註：{c['note']}" if zh else f". Note: {c['note']}")
        lines.append(line)
    if contacts:
        lines.append(("- 常聯絡人：" if zh else "- Frequent contacts: ") + ("、" if zh else ", ").join(
            (f"{c['name']}（{c['relationship_label']}）" if zh else f"{c['name']} ({c['relationship_label']})")
            for c in contacts[:6]))
    projects = [p for p in section_items(profile, "projects") if not p.get("hidden")]
    row = yhbmail.get_email(item_id) if item_id else None
    blob = " ".join([subject or "", (row or {}).get("subject") or "", (row or {}).get("body_text") or ""]).lower()
    thread = thread_key(row) if row else ""
    for p in projects:
        hit = (thread and any(t["thread"] == thread for t in p["threads"])) or \
              (blob and any(term in blob for term in p["terms"] + [p["name"].lower()]))
        if hit:
            m = mark if p.get("fixed") else ""
            line = (f"- 相關專案：{p['name']}（{p['status_label']}）{m}" if zh
                    else f"- Related project: {p['name']} ({p['status_label']}){m}")
            if p.get("note"):
                line += (f"。備註：{p['note']}" if zh else f". Note: {p['note']}")
            lines.append(line)
    live = [p for p in projects if p["status"] == "active"]
    if live:
        lines.append(("- 進行中專案：" if zh else "- Active projects: ") + ("、" if zh else ", ").join(p["name"] for p in live))
    hours, m1 = v(work, "active_hours")
    days, m2 = v(work, "work_days")
    if hours or days:
        lines.append((f"- 工作時段：{hours}{m1} {days}{m2}；提議時間請落在這個範圍內。" if zh
                      else f"- Working hours: {hours}{m1} {days}{m2}; keep proposed times inside them.").replace("  ", " "))
    notes, m = v(work, "notes")
    if notes:
        lines.append(("- 工作備註" + m + "：" if zh else "- Work notes" + m + ": ") + notes.replace("\n", " / "))
    return "\n".join(lines)


def _install_compose_hooks() -> None:
    if compose is None:
        return
    core_prompt = compose.write_prompt
    if not getattr(core_prompt, "_tpi_brain", False):
        def write_prompt_with_brain(kind, item_id, instruction, style, lang, to, subject, current):
            base = core_prompt(kind, item_id, instruction, style, lang, to, subject, current)
            try:
                block = prompt_block(lang, item_id=item_id, to=to, subject=subject)
            except Exception:
                return base
            head, sep, tail = base.rpartition("\n\n")
            return f"{head}\n\n{block}\n\n{tail}" if sep else f"{block}\n\n{base}"

        write_prompt_with_brain._tpi_brain = True
        compose.write_prompt = write_prompt_with_brain

    core_heur = compose.heuristic_write
    if not getattr(core_heur, "_tpi_brain", False):
        def heuristic_write_with_brain(kind, item, instruction, style, lang, to="", subject=""):
            text = core_heur(kind, item, instruction, style, lang, to, subject)
            try:
                return apply_tone_fixes(text, kind, item, style, lang, to)
            except Exception:
                return text

        heuristic_write_with_brain._tpi_brain = True
        compose.heuristic_write = heuristic_write_with_brain


def apply_tone_fixes(text: str, kind: str, item: dict | None, style: str, lang: str, to: str) -> str:
    """A fixed opening / sign-off replaces the rule-based one, for drafts in the fix's own language."""
    fixes = load_fixes()["tone"]
    want = "zh" if _zh(lang) else "en"
    greet_fix = (fixes.get("greeting") or {}).get("value") or ""
    sign_fix = (fixes.get("signoff") or {}).get("value") or ""
    greet_fix = greet_fix if greet_fix and text_lang(greet_fix) == want else ""
    sign_fix = sign_fix if sign_fix and text_lang(sign_fix) == want else ""
    if not greet_fix and not sign_fix:
        return text
    greet, body, closing = compose._split_frame(text)
    if greet_fix and greet:
        name = compose.first_name(item.get("from_addr") or "") if (kind == "reply" and item) else compose.first_name(to)
        greet = compose.greet_line(style, lang, name, {"greeting": greet_fix})
    if sign_fix and closing:
        lines = closing.splitlines()
        lines[0] = sign_fix
        closing = "\n".join(lines)
    return compose._join_frame(greet, body, closing)


_install_persona_hook()
_install_compose_hooks()


# ───────────────────────── routes ─────────────────────────

@get("/api/brain/profile")
def brain_profile(req):
    profile = build_profile(_lang(req))
    sid = req.query.get("section") or ""
    if sid:
        if sid not in SECTIONS:
            return {"error": f"section must be one of {', '.join(SECTIONS)}"}, 400
        profile["sections"] = [s for s in profile["sections"] if s["id"] == sid]
    return profile


@get("/api/brain/fixes")
def brain_fixes(req):
    return {"fixes": list_fixes()}


@post("/api/brain/fix")
def brain_fix(req):
    return save_fix(req.body, _lang(req))


@post("/api/brain/fix/reset")
def brain_fix_reset(req):
    return reset_fix(req.body, _lang(req))


@get("/api/brain/prompt")
def brain_prompt(req):
    q = req.query
    item_id = q.get("item_id") or ""
    if item_id and not yhbmail.get_email(item_id):
        return {"error": "email not found"}, 404
    return {"lang": _lang(req), "text": prompt_block(_lang(req), item_id=item_id, to=q.get("to") or "",
                                                     subject=q.get("subject") or "")}
