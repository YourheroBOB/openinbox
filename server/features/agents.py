"""Agent collaboration (F32 F33): research a person or company, prepare for a meeting, and
mention an agent inside a thread. Work goes through the BYO agent bridge (`agent_bridge`),
and every result is saved as a deliverable card in Markdown and HTML.

Rules this module keeps:
- Read only. A task reads local data (persona, the local mail cache, the second brain) and
  returns text. Nothing leaves the machine except what the operator's own agent.json driver
  does with the context pack; the local driver never leaves the machine at all.
- Deliverables live in `data/deliverables/` (gitignored). Ids are checked against a strict
  pattern before any path is built, so a crafted id cannot reach outside that folder.
- The HTML card escapes everything and carries no script. The UI previews it in a sandboxed
  iframe.
- The agent alias (`agent@example.com`) is only a routing word that a thread message may
  name. This module never reads or delivers mail to it.
"""
from __future__ import annotations

import html
import json
import re
from datetime import datetime

import yhbmail
from features import Raw, get, post
from features._origin import local_origin, refuse

DELIV_DIR = yhbmail.DATA / "deliverables"
ALIAS = "agent@example.com"
MAX_BODY = 4000
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,80}$")
TASK_KINDS = ("research_person", "research_company", "meeting_prep")

# @-words a thread message can start with, mapped to a task kind.
MENTIONS = {
    "agent": None,  # generic: infer from the words after it
    "research": "research_person",
    "research-company": "research_company",
    "prep": "meeting_prep",
    "meeting": "meeting_prep",
}
MENTION_RE = re.compile(r"(?<![\w.])@(agent|research-company|research|prep|meeting)\b", re.I)
COMPANY_WORDS = re.compile(r"(公司|company|corp|inc|ltd|co\.|股份|有限)", re.I)
# Polite request words stripped from the start/end of a mention target, so "@agent 請幫我查 X" targets X.
REQUEST_VERBS = re.compile(
    r"^((please|pls|can you|could you|請幫我|幫我|麻煩|查一下|幫忙)\s*|(查|研究)\s+)+|\s*(please|pls|請幫我查|請查|幫我查|查一下)$", re.I)
MEETING_WORDS = re.compile(r"(會議|meeting|agenda|議程|prep|準備|call)", re.I)

LABELS = {
    "zh": {
        "research_person": "人物研究", "research_company": "公司研究", "meeting_prep": "會議準備",
        "title": "成果卡片", "kind": "類型", "created": "產出時間",
        "driver": "驅動", "fallback": "退回本機",
        "no_source": "（本機沒有相關資料，以下只根據你的請求）",
    },
    "en": {
        "research_person": "Person research", "research_company": "Company research", "meeting_prep": "Meeting prep",
        "title": "Deliverable", "kind": "Kind", "created": "Created",
        "driver": "Driver", "fallback": "Fell back to local",
        "no_source": "(No matching local data; this is based only on your request.)",
    },
}


def _zh(lang) -> bool:
    return str(lang or "").lower().startswith("zh")


def _lang(req) -> str:
    return "zh" if req.lang_zh() else "en"


def _now() -> str:
    return datetime.now(yhbmail.TZ).strftime("%Y-%m-%d %H:%M")


def _stamp() -> str:
    return datetime.now(yhbmail.TZ).strftime("%Y%m%d-%H%M%S-%f")


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return (s[:40] or "card").strip("-") or "card"


# ───────────────────────── parsing ─────────────────────────

def parse_mention(text: str) -> dict | None:
    """Find the first @agent mention in a thread message and the task it asks for.

    Returns {"kind", "target", "word", "ask"} or None. `target` is the text after the
    mention on the same line (the person or company to research); `ask` is the whole
    message with the mention removed. Pure function; reads nothing.
    """
    text = (text or "")[:MAX_BODY]
    m = MENTION_RE.search(text)
    if not m:
        return None
    word = m.group(1).lower()
    rest_line = text[m.end():].split("\n", 1)[0].strip()
    rest_line = REQUEST_VERBS.sub("", rest_line).strip(" :：,，。.")
    ask = re.sub(r"\s+", " ", (text[:m.start()] + " " + text[m.end():])).strip()
    kind = MENTIONS.get(word)
    if kind is None:
        if MEETING_WORDS.search(ask):
            kind = "meeting_prep"
        elif COMPANY_WORDS.search(rest_line):
            kind = "research_company"
        else:
            kind = "research_person"
    return {"kind": kind, "target": rest_line[:120], "word": word, "ask": ask[:1000]}


def mentions_alias(to_addr: str) -> bool:
    """True when a recipient line names the agent alias. Routing check only, never delivery."""
    return ALIAS in (to_addr or "").lower()


# ───────────────────────── context ─────────────────────────

def _local_sources(target: str, limit: int = 8) -> list[dict]:
    """Local mail whose subject, sender, or body mentions the target. Cache only, never remote."""
    if not target:
        return []
    out = []
    for e in yhbmail.list_emails(q=target, limit=limit):
        out.append({
            "id": e.get("id"), "subject": e.get("subject") or "",
            "from": e.get("from_addr") or "", "date": e.get("date_raw") or "",
            "snippet": (e.get("snippet") or "")[:300],
        })
    return out


def build_pack(kind: str, target: str, ask: str = "", lang: str = "en") -> dict:
    from agent_bridge import context_pack
    from persona import load as load_persona
    if kind not in TASK_KINDS:
        raise ValueError(f"unknown task kind: {kind}")
    base = context_pack(ask=ask, skill="", lang="zh-Hant" if _zh(lang) else "en")
    sources = _local_sources(target)
    rules = list(base.get("rules") or []) + [
        "Read only. Use only the local sources provided. Do not invent names, companies, amounts or dates.",
        "Write a draft brief. Mark any missing fact as [待填] or [missing].",
    ]
    return {
        "task": kind,
        "target": target,
        "ask": ask,
        "lang": base.get("lang"),
        "persona": load_persona(),
        "sources": sources,
        "brain": base.get("brain"),
        "rules": rules,
    }


def _local_brief(pack: dict) -> str:
    zh = pack.get("lang") == "zh-Hant"
    lab = LABELS["zh" if zh else "en"]
    kind = pack["task"]
    target = pack.get("target") or ("（未指定對象）" if zh else "(no target given)")
    lines = [f"# {lab[kind]}：{target}" if zh else f"# {lab[kind]}: {target}", ""]
    if pack.get("sources"):
        lines.append("## 本機資料" if zh else "## Local sources")
        for s in pack["sources"]:
            lines.append(f"- {s['subject']} · {s['from']} · {s['date']}")
            if s.get("snippet"):
                lines.append(f"  {s['snippet']}")
    else:
        lines.append(lab["no_source"])
    lines.append("")
    if kind == "meeting_prep":
        lines += (["## 會議準備", "- 目的：[待填]", "- 與會者：[待填]", "- 需要決定的事：[待填]", "- 行動項目：[待填]"]
                  if zh else
                  ["## Meeting prep", "- Goal: [missing]", "- Attendees: [missing]", "- Decisions needed: [missing]", "- Action items: [missing]"])
    elif kind == "research_company":
        lines += (["## 公司概況", "- 業務：[待填]", "- 近期動態：[待填]", "- 與我方的關係：[待填]"]
                  if zh else
                  ["## Company brief", "- Business: [missing]", "- Recent news: [missing]", "- Relationship to us: [missing]"])
    else:
        lines += (["## 人物概況", "- 職務：[待填]", "- 與我方往來：[待填]", "- 近期溝通重點：[待填]"]
                  if zh else
                  ["## Person brief", "- Role: [missing]", "- Relationship to us: [missing]", "- Recent topics: [missing]"])
    lines.append("")
    lines.append("（本機啟發式，未接 agent。在 agent.json 接上 BYO agent 可得到完整內容。）" if zh
                 else "(Local heuristic, no agent wired. Connect a BYO agent in agent.json for a full brief.)")
    return "\n".join(lines)


def run_task(kind: str, target: str, ask: str = "", lang: str = "en") -> dict:
    """Run one agent task through the bridge. Falls back to the local heuristic on any failure."""
    import agent_bridge
    if kind not in TASK_KINDS:
        raise ValueError(f"unknown task kind: {kind}")
    pack = build_pack(kind, target, ask, lang)
    cfg = agent_bridge.load_agent_cfg()
    driver = cfg.get("driver") or "local"
    text, used, error, fallback = "", driver, None, False
    try:
        if driver == "openai_compatible":
            text = agent_bridge._openai(pack, cfg).strip()
        elif driver == "cli":
            text = agent_bridge._cli(pack, cfg).strip()
        elif driver == "http":
            text = agent_bridge._http(pack, cfg).strip()
        else:
            used, fallback = "local", True
    except Exception as e:
        error, used, fallback = str(e)[:300], "local", True
    if not text:
        used, fallback = "local", True
        text = _local_brief(pack)
    return {"kind": kind, "target": target, "text": text, "driver": used,
            "fallback": fallback, "error": error, "sources": pack["sources"]}


# ───────────────────────── deliverables ─────────────────────────

def _valid_id(did: str) -> bool:
    return bool(did) and bool(ID_RE.match(did))


def _render_md(card: dict) -> str:
    zh = card["lang"] == "zh"
    lab = LABELS["zh" if zh else "en"]
    head = [
        f"# {card['title']}",
        "",
        f"- {lab['kind']}: {lab[card['kind']]}",
        f"- {lab['created']}: {card['created']}",
        f"- {lab['driver']}: {card['driver']}" + (f"（{lab['fallback']}）" if card.get("fallback") else ""),
        "",
    ]
    return "\n".join(head) + card["text"].rstrip() + "\n"


def _render_html(card: dict) -> str:
    """Escaped HTML card. No script, no external resources, no inline event handlers."""
    zh = card["lang"] == "zh"
    lab = LABELS["zh" if zh else "en"]
    esc = html.escape
    paras = []
    for ln in card["text"].splitlines():
        s = ln.rstrip()
        if not s:
            continue
        if s.startswith("### "):
            paras.append(f"<h3>{esc(s[4:])}</h3>")
        elif s.startswith("## "):
            paras.append(f"<h2>{esc(s[3:])}</h2>")
        elif s.startswith("# "):
            paras.append(f"<h1>{esc(s[2:])}</h1>")
        elif s.lstrip().startswith("- "):
            paras.append(f"<li>{esc(s.lstrip()[2:])}</li>")
        else:
            paras.append(f"<p>{esc(s)}</p>")
    body = "\n".join(paras)
    return (
        '<!doctype html><html lang="' + ("zh-Hant" if zh else "en") + '"><head><meta charset="utf-8">'
        f"<title>{esc(card['title'])}</title>"
        "<style>body{font-family:system-ui,sans-serif;max-width:720px;margin:24px auto;padding:0 16px;"
        "color:#17130c;line-height:1.6}h1{font-size:1.4em}h2{font-size:1.15em;margin-top:1.2em}"
        "li{margin-left:1.2em}.meta{color:#6b5d48;font-size:.9em}</style></head><body>"
        f"<div class=\"meta\">{esc(lab['kind'])}: {esc(lab[card['kind']])} · {esc(lab['created'])}: {esc(card['created'])} · "
        f"{esc(lab['driver'])}: {esc(card['driver'])}</div>\n{body}\n</body></html>\n"
    )


def save_deliverable(result: dict, lang: str = "en", title: str = "") -> dict:
    """Write one card as MD + HTML under data/deliverables/. Returns the card metadata."""
    zh = _zh(lang)
    kind = result["kind"]
    did = f"{kind.replace('_', '-')}-{_slug(result.get('target') or '')}-{_stamp().lower()}"
    did = re.sub(r"[^a-z0-9-]", "-", did)[:80].strip("-")
    if not _valid_id(did):
        raise ValueError("bad deliverable id")
    card = {
        "id": did,
        "title": title or (f"{LABELS['zh' if zh else 'en'][kind]}：{result.get('target') or ''}" if zh
                           else f"{LABELS['en'][kind]}: {result.get('target') or ''}").strip(": ："),
        "kind": kind,
        "target": result.get("target") or "",
        "lang": "zh" if zh else "en",
        "created": _now(),
        "driver": result.get("driver") or "local",
        "fallback": bool(result.get("fallback")),
        "text": result.get("text") or "",
        "sources": result.get("sources") or [],
    }
    DELIV_DIR.mkdir(parents=True, exist_ok=True)
    (DELIV_DIR / f"{did}.md").write_text(_render_md(card), encoding="utf-8")
    (DELIV_DIR / f"{did}.html").write_text(_render_html(card), encoding="utf-8")
    (DELIV_DIR / f"{did}.json").write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")
    return {k: card[k] for k in ("id", "title", "kind", "target", "lang", "created", "driver", "fallback")}


def list_deliverables(limit: int = 50) -> list[dict]:
    if not DELIV_DIR.is_dir():
        return []
    cards = []
    for p in DELIV_DIR.glob("*.json"):
        if not _valid_id(p.stem):
            continue
        try:
            c = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        cards.append({k: c.get(k) for k in ("id", "title", "kind", "target", "lang", "created", "driver", "fallback")})
    cards.sort(key=lambda c: c.get("created") or "", reverse=True)
    return cards[:limit]


def read_deliverable(did: str, fmt: str = "md") -> tuple[bytes, str] | None:
    if not _valid_id(did) or fmt not in ("md", "html", "json"):
        return None
    p = DELIV_DIR / f"{did}.{fmt}"
    if not p.is_file():
        return None
    ctype = {"md": "text/markdown; charset=utf-8", "html": "text/html; charset=utf-8",
             "json": "application/json; charset=utf-8"}[fmt]
    return p.read_bytes(), ctype


# ───────────────────────── HTTP ─────────────────────────

@post("/api/agents/task")
def task(req):
    if not local_origin(req):
        return refuse(req.lang_zh())
    kind = str(req.body.get("kind") or "")
    target = str(req.body.get("target") or "").strip()[:120]
    ask = str(req.body.get("ask") or "")[:1000]
    if kind not in TASK_KINDS:
        return {"error": "unknown kind", "kinds": list(TASK_KINDS)}, 400
    if not target and not ask:
        return {"error": "target or ask required"}, 400
    lang = _lang(req)
    result = run_task(kind, target or ask[:120], ask, lang)
    card = save_deliverable(result, lang=lang)
    return {"deliverable": card, "text": result["text"], "driver": result["driver"],
            "fallback": result["fallback"], "error": result["error"], "sources": result["sources"]}


@post("/api/agents/mention")
def mention(req):
    """Route one thread message. A message with @agent / @research / @prep runs the task; anything
    else returns `triggered: false` and does nothing.

    Pass `email_id` instead of `text` to route a message already in the local cache: it triggers
    when its recipients name the agent alias, or when its body carries an @agent mention. The
    cache is read only; nothing is delivered to the alias."""
    if not local_origin(req):
        return refuse(req.lang_zh())
    text = str(req.body.get("text") or "")
    via, item = "text", None
    if not text and req.body.get("email_id"):
        via = "email"
        item = yhbmail.get_email(str(req.body.get("email_id")))
        if not item:
            return {"error": "not found"}, 404
        text = (item.get("body_text") or item.get("snippet") or "")
        if item.get("subject"):
            text = f"{item['subject']}\n{text}"
        if not (mentions_alias(item.get("to_addr") or "") or MENTION_RE.search(text)):
            return {"triggered": False, "via": via, "hint": "not addressed to the agent"}
    parsed = parse_mention(text)
    if not parsed and item and mentions_alias(item.get("to_addr") or ""):
        # Addressed to the alias with no @-word: a generic request on the subject line.
        parsed = {"kind": "research_person", "target": (item.get("subject") or "")[:120],
                  "word": "alias", "ask": text[:1000]}
        if MEETING_WORDS.search(text):
            parsed["kind"] = "meeting_prep"
        elif COMPANY_WORDS.search(text):
            parsed["kind"] = "research_company"
    if not parsed:
        return {"triggered": False, "via": via, "hint": "no @agent mention"}
    lang = _lang(req)
    result = run_task(parsed["kind"], parsed["target"] or parsed["ask"][:120], parsed["ask"], lang)
    card = save_deliverable(result, lang=lang)
    return {"triggered": True, "via": via, "mention": parsed, "deliverable": card, "text": result["text"],
            "driver": result["driver"], "fallback": result["fallback"], "error": result["error"]}


@get("/api/agents/deliverables")
def deliverables(req):
    return {"deliverables": list_deliverables(int(req.query.get("limit") or 50)), "alias": ALIAS}


@get("/api/agents/deliverables/*")
def deliverable(req):
    raw = req.params.lstrip("/")
    did, _, fmt = raw.partition(".")
    got = read_deliverable(did, fmt or "md")
    if not got:
        return {"error": "not found"}, 404
    body, ctype = got
    return Raw(body, ctype)
