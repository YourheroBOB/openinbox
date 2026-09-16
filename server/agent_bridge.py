"""Bring-your-own-agent bridge.

Drivers in agent.json:
  local              built-in heuristic (always on)
  openai_compatible  any /v1/chat/completions endpoint
  cli                argv, prompt on stdin
  http               POST {ask, context, tools} to your worker
"""
from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from yhbmail import ROOT, brain_board, list_emails, now_iso

AGENT_PATH = ROOT / "agent.json"
SKILLS_DIR = ROOT / "skills"

TOOLS = [
    {"name": "list_inbox", "description": "List recent mail. Args: q, category, limit"},
    {"name": "brain_board", "description": "Five-bucket triage board. Args: hours"},
    {"name": "search_brain", "description": "Search Second Brain cards. Args: q"},
    {"name": "persona", "description": "Read the know-you-better profile. Args: none"},
    {"name": "save_draft", "description": "Store a local draft. Never sends. Args: to, subject, body"},
]


def load_agent_cfg() -> dict:
    if AGENT_PATH.exists():
        return json.loads(AGENT_PATH.read_text())
    example = ROOT / "agent.example.json"
    return json.loads(example.read_text()) if example.exists() else {"driver": "local"}


def list_skills() -> list[dict]:
    items = []
    if SKILLS_DIR.exists():
        for p in sorted(SKILLS_DIR.glob("*.md")):
            text = p.read_text()
            title = next((ln[2:].strip() for ln in text.splitlines() if ln.startswith("# ")), p.stem)
            items.append({"slug": p.stem, "name": title, "path": str(p.relative_to(ROOT))})
    return items


def skill_body(slug: str) -> str:
    p = SKILLS_DIR / f"{slug}.md"
    return p.read_text() if p.exists() else ""


def _zh(lang: str) -> bool:
    return str(lang or "").lower().startswith("zh")


def context_pack(ask: str = "", skill: str = "", lang: str = "en") -> dict:
    from persona import load as load_persona
    from second_brain import load as load_brain
    if _zh(lang):
        rules = [
            "不要寄信。草稿只留本機。",
            "不要捏造姓名、金額或日期。",
            "先處理「需要你」，再看金流，其餘最後。",
        ]
    else:
        rules = [
            "Do not send email. Drafts stay local.",
            "Do not invent names, amounts, or dates.",
            "Prefer Needs you, then money, then the rest.",
        ]
    return {
        "ask": ask,
        "skill": skill,
        "lang": "zh-Hant" if _zh(lang) else "en",
        "skill_body": skill_body(skill) if skill else "",
        "persona": load_persona(),
        "brain": load_brain(),
        "board": brain_board(168),
        "recent_mail": [
            {k: e.get(k) for k in ("id", "subject", "from_addr", "category", "snippet", "unread")}
            for e in list_emails(limit=20)
        ],
        "tools": TOOLS,
        "rules": rules,
    }


def _local_answer(pack: dict) -> str:
    board = pack["board"]
    skill = pack.get("skill") or "freeform"
    ask = pack.get("ask") or ""
    zh = _zh(pack.get("lang") or "")
    lines = [f"TooPowerInbox local agent · {now_iso()}", ""]
    if skill == "morning-brief" or "morning" in ask.lower() or "晨" in ask:
        need = board["todos"].get("needs_you") or []
        look = board["todos"].get("worth_a_look") or []
        if zh:
            lines.append("晨間簡報")
            lines.append(f"需要你：{len(need)}")
        else:
            lines.append("Morning brief")
            lines.append(f"Needs you: {len(need)}")
        for t in need[:8]:
            lines.append(f"- {t['text']}")
            lines.append(f"  {t.get('from_addr')} · {t.get('flag_reason')}")
        if zh:
            lines.append(f"值得一看：{len(look)}（列 5 則）")
        else:
            lines.append(f"Worth a look: {len(look)} (showing 5)")
        for t in look[:5]:
            lines.append(f"- {t['text']}")
    elif skill == "know-you-better" or "了解" in ask:
        p = pack.get("persona") or {}
        ident = p.get("identity") or {}
        lines.append(f"{ident.get('name')} · {ident.get('role')}")
        for x in p.get("how_you_write") or []:
            lines.append(f"- {'文風' if zh else 'write'}: {x}")
        for x in p.get("attention_now") or []:
            lines.append(f"- {'此刻' if zh else 'now'}: {x}")
    elif skill == "catch-me-up":
        from collections import Counter
        c = Counter()
        for t in (board["todos"].get("needs_you") or []) + (board["todos"].get("worth_a_look") or []):
            c[(t.get("from_addr") or "?").split("<")[-1].strip("> ")] += 1
        lines.append("誰最近最吵" if zh else "Who has been loud")
        for sender, n in c.most_common(8):
            lines.append(f"- {sender}: {n}")
    else:
        need = board["todos"].get("needs_you") or []
        look_n = len(board["todos"].get("worth_a_look") or [])
        lines.append(ask or ("收件匣快照" if zh else "Inbox snapshot"))
        if zh:
            lines.append(f"需要你 {len(need)} ／ 值得一看 {look_n}")
        else:
            lines.append(f"Needs you {len(need)} / worth a look {look_n}")
        for t in need[:6]:
            lines.append(f"- {t['text']}")
        if ask:
            hits = [e for e in pack.get("recent_mail") or [] if ask.lower() in json.dumps(e, ensure_ascii=False).lower()]
            if hits:
                lines.append("對得上的信件：" if zh else "Matches:")
                for h in hits[:5]:
                    lines.append(f"- {h.get('subject')}")
    lines.append("")
    if zh:
        lines.append("預設不寄信。若要回信先留在本機，用 save_draft。")
    else:
        lines.append("Send is disabled. Use save_draft if you want a reply sitting locally.")
    return "\n".join(lines)


def _openai(pack: dict, cfg: dict) -> str:
    block = cfg.get("openai_compatible") or {}
    base = (block.get("base_url") or "").rstrip("/")
    model = block.get("model") or "gpt-4.1-mini"
    key = os.environ.get(block.get("api_key_env") or "OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""
    prompt = json.dumps(pack, ensure_ascii=False)[:24000]
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": "You are the user's local inbox agent. Follow pack.rules. Reply in Traditional Chinese if pack.lang is zh-Hant, otherwise English."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }).encode()
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {key}"} if key else {})},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        data = json.loads(resp.read().decode())
    return data["choices"][0]["message"]["content"]


def _cli(pack: dict, cfg: dict) -> str:
    block = cfg.get("cli") or {}
    cmd = block.get("command") or ["claude", "-p"]
    timeout = int(block.get("timeout_sec") or 120)
    prompt = json.dumps(pack, ensure_ascii=False)[:24000]
    p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or f"cli exit {p.returncode}")
    return p.stdout.strip()


def _http(pack: dict, cfg: dict) -> str:
    block = cfg.get("http") or {}
    url = block.get("url")
    if not url:
        raise RuntimeError("agent.json http.url is empty")
    req = urllib.request.Request(
        url,
        data=json.dumps(pack, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=int(block.get("timeout_sec") or 60)) as resp:
        raw = resp.read().decode()
    try:
        data = json.loads(raw)
        return data.get("answer") or data.get("text") or raw
    except json.JSONDecodeError:
        return raw


def run_agent(ask: str = "", skill: str = "", driver: str | None = None, lang: str = "en") -> dict:
    cfg = load_agent_cfg()
    driver = driver or cfg.get("driver") or "local"
    pack = context_pack(ask=ask, skill=skill, lang=lang)
    error = None
    answer = ""
    used = driver
    try:
        if driver == "openai_compatible":
            answer = _openai(pack, cfg)
        elif driver == "cli":
            answer = _cli(pack, cfg)
        elif driver == "http":
            answer = _http(pack, cfg)
        else:
            used = "local"
            answer = _local_answer(pack)
    except Exception as e:
        error = str(e)[:400]
        used = "local"
        answer = _local_answer(pack)
        prefix = f"（{driver} 失敗，改走本機：{error}）\n\n" if _zh(lang) else f"(fallback to local after {driver} failed: {error})\n\n"
        answer = prefix + answer
    from yhbmail import db
    con = db()
    con.execute(
        "INSERT INTO agent_turns(skill, ask, answer, driver, created_at) VALUES (?,?,?,?,?)",
        (skill or "freeform", ask, answer, used, now_iso()),
    )
    con.commit()
    con.close()
    return {"driver": used, "skill": skill or "freeform", "ask": ask, "answer": answer, "error": error}


def invoke_tool(name: str, args: dict | None = None) -> dict:
    args = args or {}
    if name == "list_inbox":
        from yhbmail import list_emails
        return {"emails": list_emails(q=args.get("q"), category=args.get("category"), limit=int(args.get("limit") or 20))}
    if name == "brain_board":
        return brain_board(int(args.get("hours") or 168))
    if name == "search_brain":
        from second_brain import search
        return {"cards": search(args.get("q") or "")}
    if name == "persona":
        from persona import load
        return load()
    if name == "save_draft":
        from yhbmail import save_draft
        return save_draft(args.get("account") or "you@example.com", args.get("to") or "",
                          args.get("subject") or "", args.get("body") or "",
                          lang=args.get("lang") or "en")
    return {"error": f"unknown tool {name}", "tools": TOOLS}
