"""Automation rules: JSON conditions -> local label / archive / mark read / reply draft / task.

Rules live in `rules.json` at the app root (kept out of git); until you save one,
the fictional `fixtures/rules_demo.json` is shown. Shape:

    {"version": 1, "rules": [{
        "id": "receipts", "name": "Label receipts", "enabled": true,
        "match": "all",                      # all | any
        "conditions": [{"field": "subject", "op": "contains", "value": "receipt"}],
        "actions": [{"type": "label", "label": "Receipts"}, {"type": "mark_read"}],
        "stop": false}]}

Every run is a dry run unless the caller passes dry_run=false: the plan lists
what each rule would do and nothing changes. Applying is idempotent (ledger
table rule_applied) and local only: labels and "archived" are marks in this
app's database (rule_marks), "mark read" changes the local cache, reply drafts
go to the local drafts table. Nothing touches the remote mailbox and nothing is sent.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime

import yhbmail
from features import get, post
from features._origin import local_origin, refuse

try:
    from features import compose
except Exception:  # optional: drafts fall back to the core drafts table
    compose = None
try:
    from features import triage
except Exception:  # optional: lane field and task action need it
    triage = None
try:
    from features import followup
except Exception:  # optional: the replied field needs it
    followup = None

RULES_PATH = yhbmail.ROOT / "rules.json"
DEMO_RULES = yhbmail.ROOT / "fixtures" / "rules_demo.json"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
MAX_RULES, MAX_CONDITIONS, MAX_ACTIONS = 50, 20, 10
CJK_RE = re.compile(r"[\u3400-\u9fff]")

FIELDS = {
    "from": ("string", "From", "寄件者"), "to": ("string", "To", "收件者"),
    "subject": ("string", "Subject", "主旨"), "body": ("string", "Body", "內文"),
    "text": ("string", "Subject + body", "主旨＋內文"), "account": ("string", "Account", "信箱"),
    "category": ("string", "Bucket", "分類"), "lane": ("string", "Triage lane", "分流"),
    "label": ("list", "Label", "標籤"), "unread": ("bool", "Unread", "未讀"),
    "has_attachment": ("bool", "Has attachment", "有附件"), "replied": ("bool", "You replied", "你已回覆"),
    "age_days": ("number", "Age (days)", "信件天數"),
}
OPS = {
    "string": ("contains", "not_contains", "equals", "not_equals", "starts_with", "ends_with", "regex", "in", "not_in"),
    "list": ("contains", "not_contains"),
    "bool": ("is",),
    "number": ("gte", "lte", "gt", "lt", "equals"),
}
OP_TEXT = {
    "contains": ("contains", "包含"), "not_contains": ("does not contain", "不包含"), "equals": ("equals", "等於"),
    "not_equals": ("is not", "不等於"), "starts_with": ("starts with", "開頭是"), "ends_with": ("ends with", "結尾是"),
    "regex": ("matches regex", "符合正規表示式"), "in": ("is one of", "是其中之一"), "not_in": ("is none of", "都不是"),
    "is": ("is", "是"), "gte": ("≥", "≥"), "lte": ("≤", "≤"), "gt": (">", ">"), "lt": ("<", "<"),
}
ACTIONS = {
    "label": ("Add label", "加標籤", ["label"]),
    "archive": ("Archive (local)", "封存（本機）", []),
    "mark_read": ("Mark read", "標為已讀", []),
    "draft_reply": ("Draft a reply (local draft)", "起草回覆（本機草稿）", ["template", "template_zh", "instruction"]),
    "task": ("Add a task", "加任務", ["action", "note"]),
}
STATUS_TEXT = {
    "planned": ("would run", "將執行"), "applied": ("applied", "已套用"), "already": ("already done", "先前已做"),
    "skipped": ("skipped", "略過"), "error": ("error", "錯誤"),
}


def _zh(lang) -> bool:
    return str(lang or "").lower().startswith("zh")


def _lang(req) -> str:
    return "zh-Hant" if req.lang_zh() else "en"


def _tx(pair, lang) -> str:
    return pair[1] if _zh(lang) else pair[0]


def _rel(p) -> str:
    try:
        return str(p.relative_to(yhbmail.ROOT))
    except ValueError:
        return str(p)


# ───────────────────────── storage ─────────────────────────

def ensure_tables() -> None:
    yhbmail.init_db()
    con = yhbmail.db()
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS rule_marks (
            email_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            value TEXT NOT NULL,
            rule_id TEXT,
            at TEXT,
            PRIMARY KEY (email_id, kind, value)
        );
        CREATE TABLE IF NOT EXISTS rule_applied (
            email_id TEXT NOT NULL,
            rule_id TEXT NOT NULL,
            action_key TEXT NOT NULL,
            result TEXT,
            run_id INTEGER,
            at TEXT,
            PRIMARY KEY (email_id, rule_id, action_key)
        );
        CREATE TABLE IF NOT EXISTS rule_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            at TEXT,
            dry_run INTEGER,
            source TEXT,
            rules INTEGER,
            matched INTEGER,
            planned INTEGER,
            applied INTEGER,
            errors INTEGER
        );
        """
    )
    con.commit()
    con.close()


# ───────────────────────── validation ─────────────────────────

def validate(doc, lang: str = "en") -> tuple[dict, list[dict]]:
    """(clean document, errors). Errors carry the rule index and id so the editor can point at them."""
    zh = _zh(lang)
    errors: list[dict] = []

    def err(i, rid, en, zh_text):
        errors.append({"rule": i, "id": rid, "message": zh_text if zh else en})

    if isinstance(doc, list):
        doc = {"rules": doc}
    if not isinstance(doc, dict) or not isinstance(doc.get("rules"), list):
        return {"version": 1, "rules": []}, [{"rule": None, "id": "", "message":
                                             "最外層要是 {\"rules\": [...]}" if zh else 'top level must be {"rules": [...]}'}]
    if len(doc["rules"]) > MAX_RULES:
        err(None, "", f"at most {MAX_RULES} rules", f"最多 {MAX_RULES} 條規則")
    clean, seen = [], set()
    for i, r in enumerate(doc["rules"][:MAX_RULES]):
        if not isinstance(r, dict):
            err(i, "", "a rule must be an object", "每條規則要是物件")
            continue
        rid = str(r.get("id") or "")
        n_errors = len(errors)
        if not ID_RE.match(rid):
            err(i, rid, "id: lowercase letters, digits, - or _ (max 40)", "id 只能用小寫英數、- 或 _（最多 40 字）")
        elif rid in seen:
            err(i, rid, f"duplicate id {rid}", f"id 重複：{rid}")
        seen.add(rid)
        match = r.get("match") or "all"
        if match not in ("all", "any"):
            err(i, rid, "match must be all or any", "match 只能是 all 或 any")
        conds = r.get("conditions")
        if not isinstance(conds, list) or not conds:
            err(i, rid, "conditions must be a non-empty list", "conditions 要是非空陣列")
            conds = []
        if len(conds) > MAX_CONDITIONS:
            err(i, rid, f"at most {MAX_CONDITIONS} conditions", f"條件最多 {MAX_CONDITIONS} 個")
        clean_conds = []
        for c in conds[:MAX_CONDITIONS]:
            if not isinstance(c, dict):
                err(i, rid, "a condition must be an object", "每個條件要是物件")
                continue
            field, op, value = c.get("field"), c.get("op"), c.get("value")
            if field not in FIELDS:
                err(i, rid, f"unknown field {field!r}; use one of {', '.join(FIELDS)}",
                    f"不認得的欄位 {field!r}；可用：{', '.join(FIELDS)}")
                continue
            ftype = FIELDS[field][0]
            if op not in OPS[ftype]:
                err(i, rid, f"{field}: op must be one of {', '.join(OPS[ftype])}",
                    f"{field} 的 op 只能是：{', '.join(OPS[ftype])}")
                continue
            if ftype == "bool":
                if not isinstance(value, bool):
                    err(i, rid, f"{field}: value must be true or false", f"{field} 的 value 要是 true 或 false")
                    continue
            elif ftype == "number":
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    err(i, rid, f"{field}: value must be a number", f"{field} 的 value 要是數字")
                    continue
            elif op in ("in", "not_in"):
                if not isinstance(value, list) or not value or not all(isinstance(v, str) for v in value):
                    err(i, rid, f"{field} {op}: value must be a list of strings", f"{field} {op} 的 value 要是字串陣列")
                    continue
                value = [v[:200] for v in value[:50]]
            else:
                if not isinstance(value, str) or not value.strip():
                    err(i, rid, f"{field}: value must be a non-empty string", f"{field} 的 value 要是非空字串")
                    continue
                value = value[:200]
                if op == "regex":
                    try:
                        re.compile(value)
                    except re.error as e:
                        err(i, rid, f"{field}: bad regex ({e})", f"{field} 的正規表示式有誤（{e}）")
                        continue
            clean_conds.append({"field": field, "op": op, "value": value})
        acts = r.get("actions")
        if not isinstance(acts, list) or not acts:
            err(i, rid, "actions must be a non-empty list", "actions 要是非空陣列")
            acts = []
        if len(acts) > MAX_ACTIONS:
            err(i, rid, f"at most {MAX_ACTIONS} actions", f"動作最多 {MAX_ACTIONS} 個")
        clean_acts = []
        for a in acts[:MAX_ACTIONS]:
            kind = a.get("type") if isinstance(a, dict) else None
            if kind not in ACTIONS:
                err(i, rid, f"unknown action {kind!r}; use one of {', '.join(ACTIONS)}",
                    f"不認得的動作 {kind!r}；可用：{', '.join(ACTIONS)}")
                continue
            out = {"type": kind}
            if kind == "label":
                label = str(a.get("label") or "").strip()
                if not label or len(label) > 40:
                    err(i, rid, "label: 1 to 40 characters", "label 要 1 到 40 字")
                    continue
                out["label"] = label
            elif kind == "draft_reply":
                for key in ("template", "template_zh", "instruction"):
                    if a.get(key) is not None:
                        if not isinstance(a[key], str):
                            err(i, rid, f"draft_reply.{key} must be a string", f"draft_reply.{key} 要是字串")
                            continue
                        out[key] = a[key][:4000]
            elif kind == "task":
                action = a.get("action") or "follow_up"
                if triage is None or action not in triage.ACTIONS:
                    err(i, rid, f"task.action must be one of {', '.join(triage.ACTIONS) if triage else '(triage missing)'}",
                        f"task.action 只能是：{', '.join(triage.ACTIONS) if triage else '（缺少 triage 模組）'}")
                    continue
                out["action"] = action
                if a.get("note"):
                    out["note"] = str(a["note"])[:300]
            clean_acts.append(out)
        if len(errors) > n_errors:
            # a half-valid rule can match far more mail than its author meant
            continue
        clean.append({
            "id": rid, "name": str(r.get("name") or rid)[:80], "description": str(r.get("description") or "")[:300],
            "enabled": r.get("enabled", True) is not False, "match": match if match in ("all", "any") else "all",
            "conditions": clean_conds, "actions": clean_acts, "stop": bool(r.get("stop")),
        })
    return {"version": 1, "rules": clean}, errors


def load_rules(lang: str = "en") -> dict:
    path = RULES_PATH if RULES_PATH.exists() else DEMO_RULES
    source = "file" if path == RULES_PATH else "demo"
    if not path.exists():
        return {"version": 1, "rules": [], "source": "none", "path": _rel(RULES_PATH), "errors": []}
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return {"version": 1, "rules": [], "source": source, "path": _rel(path),
                "errors": [{"rule": None, "id": "", "message": f"{_rel(path)}: {e}"}]}
    doc, errors = validate(raw, lang)
    return {**doc, "source": source, "path": _rel(path), "errors": errors}


def save_rules(doc, lang: str = "en") -> tuple[dict, int]:
    clean, errors = validate(doc, lang)
    if errors:
        return {"ok": False, "errors": errors}, 400
    tmp = RULES_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(clean, ensure_ascii=False, indent=2) + "\n")
    os.replace(tmp, RULES_PATH)
    return {"ok": True, **load_rules(lang)}, 200


# ───────────────────────── matching ─────────────────────────

def marks_for(ids) -> dict:
    ids = [i for i in ids if i]
    ensure_tables()
    out = {i: {"labels": [], "archived": False} for i in ids}
    if not ids:
        return out
    con = yhbmail.db()
    for chunk in range(0, len(ids), 500):
        part = ids[chunk:chunk + 500]
        marks = ",".join("?" for _ in part)
        for r in con.execute(f"SELECT email_id, kind, value FROM rule_marks WHERE email_id IN ({marks}) ORDER BY at", part):
            if r["kind"] == "label":
                out[r["email_id"]]["labels"].append(r["value"])
            elif r["kind"] == "archived":
                out[r["email_id"]]["archived"] = True
    con.close()
    return out


def archived_ids() -> set:
    ensure_tables()
    con = yhbmail.db()
    out = {r[0] for r in con.execute("SELECT email_id FROM rule_marks WHERE kind='archived'")}
    con.close()
    return out


def _sender(row: dict) -> str:
    raw = row.get("from_addr") or ""
    m = re.search(r"<([^>]+)>", raw)
    return (m.group(1) if m else raw).strip().lower()


def field_value(row: dict, field: str, ctx: dict):
    if field == "from":
        return row.get("from_addr") or ""
    if field == "to":
        return row.get("to_addr") or ""
    if field == "subject":
        return row.get("subject") or ""
    if field == "body":
        return row.get("body_text") or row.get("snippet") or ""
    if field == "text":
        return f"{row.get('subject') or ''}\n{row.get('snippet') or ''}\n{row.get('body_text') or ''}"
    if field == "account":
        return row.get("account") or ""
    if field == "category":
        return row.get("category") or ""
    if field == "lane":
        return triage.lane_of(row) if triage else (row.get("category") or "")
    if field == "label":
        return list(row.get("labels") or []) + ctx["marks"].get(row["id"], {}).get("labels", [])
    if field == "unread":
        return bool(row.get("unread"))
    if field == "has_attachment":
        if triage:
            return bool(triage.attachment_info(row)["has"])
        return bool(row.get("has_attachment"))
    if field == "replied":
        if ctx.get("replied") is None:
            ctx["replied"] = followup.replied_received_ids(ctx["now_ts"]) if followup else set()
        return row["id"] in ctx["replied"]
    if field == "age_days":
        ts = row.get("date_ts") or 0
        return round((ctx["now_ts"] - ts) / 86400, 2) if ts else 0
    return None


def test_condition(row: dict, cond: dict, ctx: dict) -> bool:
    value = field_value(row, cond["field"], ctx)
    op, want = cond["op"], cond["value"]
    ftype = FIELDS[cond["field"]][0]
    if ftype == "bool":
        return bool(value) is want
    if ftype == "number":
        value = float(value or 0)
        return {"gte": value >= want, "lte": value <= want, "gt": value > want, "lt": value < want,
                "equals": value == want}[op]
    if ftype == "list":
        hit = any(str(v).lower() == want.lower() for v in value)
        return hit if op == "contains" else not hit
    text = str(value or "").lower()
    if op == "regex":
        return bool(re.search(want, str(value or ""), re.I))
    if op in ("in", "not_in"):
        hit = text.strip() in {w.lower().strip() for w in want}
        return hit if op == "in" else not hit
    w = want.lower()
    return {"contains": w in text, "not_contains": w not in text, "equals": text.strip() == w.strip(),
            "not_equals": text.strip() != w.strip(), "starts_with": text.startswith(w),
            "ends_with": text.rstrip().endswith(w)}[op]


def matches(row: dict, rule: dict, ctx: dict) -> bool:
    if not rule["conditions"]:
        return False
    results = (test_condition(row, c, ctx) for c in rule["conditions"])
    return all(results) if rule["match"] == "all" else any(results)


# ───────────────────────── actions ─────────────────────────

def action_key(action: dict) -> str:
    if action["type"] == "label":
        return f"label:{action['label'].lower()}"
    if action["type"] == "task":
        return f"task:{action['action']}"
    return action["type"]


def describe_action(action: dict, lang: str) -> str:
    text = _tx(ACTIONS[action["type"]][:2], lang)
    if action["type"] == "label":
        return f"{text}「{action['label']}」" if _zh(lang) else f"{text} “{action['label']}”"
    if action["type"] == "task" and triage:
        return f"{text} · {triage.ACTIONS[action['action']]['zh' if _zh(lang) else 'en']}"
    return text


def _row_lang(row: dict) -> str:
    return "zh-Hant" if CJK_RE.search(f"{row.get('subject') or ''} {row.get('body_text') or ''}") else "en"


def fill_template(template: str, row: dict, lang: str) -> str:
    name, addr = "", _sender(row)
    m = re.match(r'^\s*"?([^"<]*?)"?\s*<', row.get("from_addr") or "")
    if m:
        name = m.group(1).strip()
    first = compose.first_name(row.get("from_addr") or "") if compose else (name.split()[0] if name else "")
    values = {"first_name": first, "sender": name or addr, "subject": row.get("subject") or "",
              "date": (row.get("date_raw") or "")[:10], "tbd": "[待填]" if _zh(lang) else "[TBD]"}
    return re.sub(r"\{(first_name|sender|subject|date|tbd)\}", lambda mm: values[mm.group(1)], template)


def draft_text(row: dict, action: dict) -> tuple[str, str, str]:
    """(text, source, lang) for a draft_reply action, without saving anything."""
    lang = _row_lang(row)
    template = action.get("template_zh") if _zh(lang) and action.get("template_zh") else action.get("template")
    if template:
        return fill_template(template, row, lang), "template", lang
    if compose is not None:
        out, status = compose.ai_write({"kind": "reply", "item_id": row["id"],
                                        "instruction": action.get("instruction") or ""}, lang)
        if status == 200:
            return out["text"], out["source"], lang
    tbd = "[待填]" if _zh(lang) else "[TBD]"
    return (f"你好：\n\n{tbd}\n\n謝謝！" if _zh(lang) else f"Hi,\n\n{tbd}\n\nThanks,"), "heuristic", lang


def _existing_reply_draft(email_id: str) -> int | None:
    con = yhbmail.db()
    cols = {r[1] for r in con.execute("PRAGMA table_info(drafts)")}
    sql = "SELECT id FROM drafts WHERE in_reply_to=?" + (" OR source_id=?" if "source_id" in cols else "")
    row = con.execute(sql, (email_id, email_id) if "source_id" in cols else (email_id,)).fetchone()
    con.close()
    return row[0] if row else None


def check_action(row: dict, action: dict) -> tuple[str, str]:
    """('planned' | 'already' | 'skipped', reason) for one action on one mail, before anything runs."""
    kind = action["type"]
    if kind == "mark_read" and not row.get("unread"):
        return "already", "already read"
    if kind == "draft_reply":
        if any(x in _sender(row) for x in yhbmail.NOISE_FROM):
            return "skipped", "no-reply sender"
        existing = _existing_reply_draft(row["id"])
        if existing:
            return "already", f"draft #{existing}"
    return "planned", ""


def apply_action(row: dict, rule: dict, action: dict, lang: str) -> dict:
    kind, now = action["type"], yhbmail.now_iso()
    if kind in ("label", "archive"):
        con = yhbmail.db()
        con.execute("INSERT OR IGNORE INTO rule_marks(email_id, kind, value, rule_id, at) VALUES (?,?,?,?,?)",
                    (row["id"], "label" if kind == "label" else "archived",
                     action["label"] if kind == "label" else "1", rule["id"], now))
        con.commit()
        con.close()
        return {}
    if kind == "mark_read":
        yhbmail.set_unread(row["id"], False)
        return {}
    if kind == "draft_reply":
        text, source, dlang = draft_text(row, action)
        subject = row.get("subject") or ""
        subject = subject if re.match(r"^\s*re\s*[:：]", subject, re.I) else f"Re: {subject}".strip()
        if compose is not None:
            out, status = compose.save_draft({
                "kind": "reply", "source_id": row["id"], "account": row.get("account") or "",
                "to": _sender(row), "subject": subject, "text": text,
                "quote": compose.reply_quote(row, dlang)}, dlang)
            if status not in (200, 201):
                raise RuntimeError(out.get("error") or f"draft failed ({status})")
            return {"draft_id": out["draft"]["id"], "source": source}
        out = yhbmail.save_draft(row.get("account") or "", _sender(row), subject, text, dlang)
        return {"draft_id": out["id"], "source": source}
    if kind == "task":
        out, status = triage.create_task(row["id"], action["action"], action.get("note") or "", lang)
        if status != 201:
            raise RuntimeError(out.get("error") or f"task failed ({status})")
        return {"task_id": out["id"]}
    raise RuntimeError(f"unknown action {kind}")


# ───────────────────────── run ─────────────────────────

def _applied_ledger() -> set:
    ensure_tables()
    con = yhbmail.db()
    out = {(r[0], r[1], r[2]) for r in con.execute("SELECT email_id, rule_id, action_key FROM rule_applied")}
    con.close()
    return out


def run(doc=None, dry_run: bool = True, rule_ids=None, ids=None, limit: int = 500, lang: str = "en",
        now=None, source: str = "api") -> tuple[dict, int]:
    """Evaluate rules against cached mail. dry_run=True (the default) only reports the plan."""
    zh = _zh(lang)
    if doc is not None and not dry_run:
        return {"error": "inline rules can only be dry-run; save them first"}, 400
    if doc is None:
        loaded = load_rules(lang)
        rules, errors = loaded["rules"], loaded["errors"]
        if errors and not dry_run:
            return {"ok": False, "dry_run": False, "errors": errors,
                    "error": f"{loaded['path']} 有錯誤，修好之前不套用任何規則" if zh
                    else f"{loaded['path']} has errors; no rule is applied until they are fixed"}, 400
    else:
        clean, errors = validate(doc, lang)
        if errors:
            return {"ok": False, "errors": errors}, 400
        rules = clean["rules"]
    rules = [r for r in rules if r["enabled"] and (not rule_ids or r["id"] in rule_ids)]
    rows = yhbmail.list_emails(limit=max(1, min(5000, int(limit or 500))))
    if ids:
        wanted = set(ids)
        rows = [r for r in rows if r["id"] in wanted]
    now_ts = followup.parse_now(now) if followup else int(datetime.now(yhbmail.TZ).timestamp())
    ctx = {"marks": marks_for([r["id"] for r in rows]), "now_ts": now_ts, "replied": None}
    ledger = _applied_ledger()
    ensure_tables()
    run_id = None
    if not dry_run:
        con = yhbmail.db()
        run_id = con.execute("INSERT INTO rule_runs(at, dry_run, source, rules) VALUES (?,?,?,?)",
                             (yhbmail.now_iso(), 0, source, len(rules))).lastrowid
        con.commit()
        con.close()
    matched, counts = [], {"planned": 0, "applied": 0, "already": 0, "skipped": 0, "error": 0}
    per_rule = {r["id"]: 0 for r in rules}
    for row in rows:
        for rule in rules:
            if not matches(row, rule, ctx):
                continue
            per_rule[rule["id"]] += 1
            acts = []
            for action in rule["actions"]:
                key = action_key(action)
                if (row["id"], rule["id"], key) in ledger:
                    status, detail = "already", {"reason": "applied before"}
                else:
                    status, reason = check_action(row, action)
                    detail = {"reason": reason} if reason else {}
                    if status == "planned" and action["type"] == "draft_reply" and action.get("template"):
                        detail["preview"] = draft_text(row, action)[0][:600]
                    if status == "planned" and not dry_run:
                        try:
                            detail = apply_action(row, rule, action, lang)
                            status = "applied"
                        except Exception as e:
                            status, detail = "error", {"reason": f"{type(e).__name__}: {e}"[:300]}
                        if status == "applied":
                            con = yhbmail.db()
                            con.execute("INSERT OR IGNORE INTO rule_applied(email_id, rule_id, action_key, result, "
                                        "run_id, at) VALUES (?,?,?,?,?,?)",
                                        (row["id"], rule["id"], key, json.dumps(detail, ensure_ascii=False),
                                         run_id, yhbmail.now_iso()))
                            con.commit()
                            con.close()
                            ledger.add((row["id"], rule["id"], key))
                counts[status] += 1
                acts.append({"type": action["type"], "key": key, "label": describe_action(action, lang),
                             "status": status, "status_label": _tx(STATUS_TEXT[status], lang), "detail": detail})
            matched.append({"email_id": row["id"], "subject": row.get("subject") or "",
                            "from_addr": row.get("from_addr") or "", "date_raw": row.get("date_raw") or "",
                            "rule_id": rule["id"], "rule_name": rule["name"], "actions": acts})
            if rule["stop"]:
                break
    emails = len({m["email_id"] for m in matched})
    if not dry_run:
        con = yhbmail.db()
        con.execute("UPDATE rule_runs SET matched=?, planned=?, applied=?, errors=? WHERE id=?",
                    (emails, counts["planned"], counts["applied"], counts["error"], run_id))
        con.commit()
        con.close()
    if dry_run:
        note = (f"Dry-run：{len(rules)} 條規則符合 {emails} 封信，預計 {counts['planned']} 個動作；什麼都還沒改。"
                if zh else f"Dry run: {len(rules)} rules match {emails} emails, {counts['planned']} actions planned; "
                           "nothing was changed.")
    else:
        note = (f"已套用 {counts['applied']} 個動作（{emails} 封信）；只改本機，不碰遠端信箱、不寄信。"
                if zh else f"Applied {counts['applied']} actions on {emails} emails; local only, "
                           "the remote mailbox is untouched and nothing is sent.")
    return {"ok": counts["error"] == 0, "dry_run": dry_run, "run_id": run_id, "rules": len(rules),
            "emails_checked": len(rows), "emails_matched": emails, "matched": matched, "counts": counts,
            "per_rule": per_rule, "errors": errors, "note": note, "generated_at": yhbmail.now_iso()}, 200


def list_runs(limit: int = 20) -> list[dict]:
    ensure_tables()
    con = yhbmail.db()
    rows = [dict(r) for r in con.execute("SELECT * FROM rule_runs ORDER BY id DESC LIMIT ?", (limit,))]
    con.close()
    return rows


def remove_mark(email_id: str, kind: str, value: str = "") -> int:
    ensure_tables()
    con = yhbmail.db()
    if kind == "archived":
        n = con.execute("DELETE FROM rule_marks WHERE email_id=? AND kind='archived'", (email_id,)).rowcount
    else:
        n = con.execute("DELETE FROM rule_marks WHERE email_id=? AND kind='label' AND value=?",
                        (email_id, value)).rowcount
    con.commit()
    con.close()
    return n


def schema(lang: str) -> dict:
    return {
        "fields": [{"id": k, "type": v[0], "label": _tx(v[1:], lang), "ops": list(OPS[v[0]])} for k, v in FIELDS.items()],
        "ops": {k: _tx(v, lang) for k, v in OP_TEXT.items()},
        "actions": [{"id": k, "label": _tx(v[:2], lang), "params": v[2]} for k, v in ACTIONS.items()],
        "placeholders": ["{first_name}", "{sender}", "{subject}", "{date}", "{tbd}"],
    }


# ───────────────────────── routes ─────────────────────────

def _flag(value, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() not in ("0", "false", "no", "")
    return bool(value)


@get("/api/rules")
def rules_get(req):
    lang = _lang(req)
    return {**load_rules(lang), "schema": schema(lang), "file": _rel(RULES_PATH)}


@post("/api/rules")
def rules_save(req):
    if not local_origin(req):
        return refuse(req.lang_zh())
    doc = req.body.get("doc") if "doc" in req.body else {"rules": req.body.get("rules")}
    return save_rules(doc, _lang(req))


@post("/api/rules/validate")
def rules_validate(req):
    doc = req.body.get("doc") if "doc" in req.body else {"rules": req.body.get("rules")}
    clean, errors = validate(doc, _lang(req))
    return {"ok": not errors, "errors": errors, "doc": clean}


@post("/api/rules/run")
def rules_run(req):
    b = req.body
    dry_run = _flag(b.get("dry_run"), True)
    if not dry_run and not local_origin(req):
        return refuse(req.lang_zh())
    doc = None
    if "doc" in b or "rules" in b:
        if not dry_run:
            return {"error": "inline rules can only be dry-run; save them first"}, 400
        doc = b.get("doc") if "doc" in b else {"rules": b.get("rules")}
    rule_ids = b.get("rule_ids") if isinstance(b.get("rule_ids"), list) else None
    ids = b.get("ids") if isinstance(b.get("ids"), list) else None
    try:
        limit = int(b.get("limit") or 500)
    except (TypeError, ValueError):
        limit = 500
    return run(doc, dry_run, rule_ids, ids, limit, _lang(req), b.get("now"))


@get("/api/rules/runs")
def rules_runs(req):
    return {"runs": list_runs()}


@post("/api/rules/marks")
def rules_marks(req):
    ids = req.body.get("ids") or []
    if not isinstance(ids, list):
        return {"error": "ids must be a list"}, 400
    return {"marks": marks_for([str(i) for i in ids][:1000])}


@post("/api/rules/marks/remove")
def rules_marks_remove(req):
    if not local_origin(req):
        return refuse(req.lang_zh())
    kind = req.body.get("kind")
    if kind not in ("label", "archived"):
        return {"error": "kind must be label or archived"}, 400
    email_id = str(req.body.get("email_id") or "")
    if not email_id:
        return {"error": "missing email_id"}, 400
    return {"ok": True, "removed": remove_mark(email_id, kind, str(req.body.get("value") or ""))}
