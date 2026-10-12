"""Mail operations on the local cache.

    folders        Inbox / Starred / Drafts / Sent / Archive / Trash
    actions        star, archive, trash, move, restore, purge, read / unread
    mark-all-read  every account at once (or one account / one folder)
    print view     /mailops/print?id=... — a clean page for the browser's "Save as PDF"
    translate      inline translation through the BYO agent; no LLM -> a clear notice
    new-since      /api/new-since polling cursor for the Notification API
    accounts       add / remove / reorder / set primary, written to accounts.json
    signatures     one per account, typed in or imported from a .txt / .md / .html file

All of it is local state: `mail_state` in data/openinbox.db and accounts.json.
The remote mailbox is never written to and nothing is ever sent.
"""
from __future__ import annotations

import html
import json
import os
import re
import threading
import time
from html.parser import HTMLParser

import agent_bridge
import yhbmail
from features import Raw, get, post

FOLDERS = ("inbox", "starred", "drafts", "sent", "archive", "trash")
FOLDER_NAMES = {
    "inbox": ("Inbox", "收件匣"), "starred": ("Starred", "已加星號"), "drafts": ("Drafts", "草稿"),
    "sent": ("Sent", "寄件備份"), "archive": ("Archive", "封存"), "trash": ("Trash", "垃圾桶"),
}
MOVE_TARGETS = ("inbox", "archive", "trash")
PURGED = "purged"
ACTIONS = ("star", "unstar", "archive", "trash", "restore", "move", "purge", "read", "unread")
DRIVERS = ("demo", "gog", "gsk", "imap")
DRIVER_PLATFORM = {"demo": "demo", "gog": "gmail", "gsk": "outlook", "imap": "imap"}
IMAP_KEYS = ("host", "port", "security", "provider", "password_env", "mailbox", "username")
EMAIL_RE = re.compile(r"^[^@\s<>\"']+@[^@\s<>\"']+\.[^@\s<>\"']+$")
ENV_RE = re.compile(r"^[A-Z_][A-Z0-9_]{0,63}$")
SIG_MAX = 4000
SIG_FILE_MAX = 200_000
SIG_EXTS = (".txt", ".text", ".md", ".sig", ".html", ".htm")
TRANSLATE_MAX = 12000
LANGS = {
    "zh-Hant": ("Traditional Chinese (Taiwan)", "繁體中文"), "en": ("English", "英文"),
    "ja": ("Japanese", "日文"), "ko": ("Korean", "韓文"), "zh-Hans": ("Simplified Chinese", "簡體中文"),
    "es": ("Spanish", "西班牙文"), "fr": ("French", "法文"), "de": ("German", "德文"),
}
SENT_FIXTURE = yhbmail.ROOT / "fixtures" / "demo_sent.json"
_cfg_lock = threading.Lock()


def _zh(lang) -> bool:
    return str(lang or "").lower().startswith("zh")


def _msg(en: str, zh: str, lang) -> str:
    return zh if _zh(lang) else en


def _lang(req) -> str:
    return "zh-Hant" if req.lang_zh() else "en"


def _bad(en: str, zh: str, lang, status: int = 400):
    return {"ok": False, "error": _msg(en, zh, lang)}, status


def _local_origin(req) -> bool:
    """True for no Origin (curl, scripts) or this server's own UI; any other page is refused."""
    handler = req.handler
    origin = handler.headers.get("Origin") if handler is not None else None
    if origin is None:
        return True
    try:
        port = handler.server.server_address[1]
    except (AttributeError, IndexError, TypeError):
        port = int(os.environ.get("OPENINBOX_PORT", "8770"))
    return origin.strip().lower().rstrip("/") in (f"http://127.0.0.1:{port}", f"http://localhost:{port}")


def _guard(req):
    if _local_origin(req):
        return None
    return _bad("cross-origin request refused: use this app's own page",
                "拒絕跨來源請求：請從本機 App 介面操作", _lang(req), 403)


# ───────────────────────── local state ─────────────────────────

def ensure(con) -> None:
    con.execute(
        """CREATE TABLE IF NOT EXISTS mail_state (
            id TEXT PRIMARY KEY,
            folder TEXT,
            starred INTEGER,
            read INTEGER,
            read_at TEXT,
            updated_at TEXT
        )""")


def db():
    con = yhbmail.db()
    ensure(con)
    return con


def is_demo() -> bool:
    return (yhbmail.load_cfg().get("mode") or "demo") == "demo"


def default_folder(labels) -> str:
    labels = set(labels or [])
    if "TRASH" in labels:
        return "trash"
    if "DRAFT" in labels:
        return "drafts"
    if "SENT" in labels:
        return "sent"
    return "inbox"


def _sent_fixture() -> list[dict]:
    """Demo mode only: the fictional sent mail, shown read-only in Sent."""
    if not is_demo() or not SENT_FIXTURE.exists():
        return []
    try:
        sent = json.loads(SENT_FIXTURE.read_text()).get("sent") or []
    except (OSError, json.JSONDecodeError):
        return []
    rows = []
    for s in sent:
        body = s.get("body_text") or ""
        rows.append({
            "id": s["id"], "account": s.get("account") or "", "platform": "demo",
            "thread_id": s.get("thread_id") or s["id"], "subject": s.get("subject") or "",
            "snippet": " ".join(body.split())[:160], "from_addr": s.get("from_addr") or "",
            "to_addr": s.get("to_addr") or "", "cc_addr": s.get("cc_addr") or "",
            "date_raw": s.get("date_raw") or "", "date_ts": yhbmail.parse_date_ts(s.get("date_raw") or ""),
            "unread": 0, "has_attachment": 0, "labels": ["SENT"], "body_text": body,
            "category": "fyi", "flag_reason": "", "source": "sent_fixture",
        })
    return rows


def _reapply_reads(con) -> None:
    """A re-sync copies the remote unread flag back; a local "read" made earlier wins."""
    con.execute(
        """UPDATE emails SET unread=0 WHERE unread=1 AND id IN (
               SELECT s.id FROM mail_state s
               WHERE s.read=1 AND s.read_at IS NOT NULL AND s.read_at <= emails.synced_at)""")
    con.commit()


def _decorate(row: dict, st: dict | None) -> dict:
    if "labels" not in row:
        row["labels"] = json.loads(row.pop("labels_json", None) or "[]")
    row.pop("labels_json", None)
    st = st or {}
    row["folder"] = st.get("folder") or default_folder(row["labels"])
    starred = st.get("starred")
    row["starred"] = bool(starred) if starred is not None else "STARRED" in row["labels"]
    row["unread"] = bool(row.get("unread"))
    row.setdefault("source", "cache")
    return row


def _states(con) -> dict:
    return {r["id"]: dict(r) for r in con.execute("SELECT * FROM mail_state")}


def _all_rows(con, account: str = "", q: str = "", with_body: bool = False) -> list[dict]:
    cols = "*" if with_body else ("id, account, platform, thread_id, subject, snippet, from_addr, to_addr, "
                                  "date_raw, date_ts, unread, has_attachment, labels_json, category, flag_reason")
    sql, args = f"SELECT {cols} FROM emails WHERE 1=1", []
    if account:
        sql += " AND account=?"
        args.append(account)
    if q:
        like = f"%{q}%"
        sql += " AND (subject LIKE ? OR snippet LIKE ? OR from_addr LIKE ? OR to_addr LIKE ? OR body_text LIKE ?)"
        args += [like] * 5
    rows = [dict(r) for r in con.execute(sql, args)]
    for v in _sent_fixture():
        if account and v["account"] != account:
            continue
        if q and q.lower() not in " ".join(str(v.get(k) or "") for k in
                                           ("subject", "snippet", "from_addr", "to_addr", "body_text")).lower():
            continue
        if not with_body:
            v.pop("body_text", None)
        rows.append(v)
    states = _states(con)
    return [_decorate(r, states.get(r["id"])) for r in rows]


def in_folder(row: dict, folder: str) -> bool:
    if folder == "starred":
        return row["starred"] and row["folder"] not in ("trash", PURGED)
    return row["folder"] == folder


def _draft_rows(account: str = "", q: str = "") -> list[dict]:
    con = yhbmail.db()
    rows = [dict(r) for r in con.execute("SELECT * FROM drafts ORDER BY id DESC")]
    con.close()
    out = []
    for d in rows:
        if account and d.get("account") != account:
            continue
        body = d.get("body") or ""
        if q and q.lower() not in f"{d.get('subject') or ''} {d.get('to_addr') or ''} {body}".lower():
            continue
        out.append({
            "id": f"draft:{d['id']}", "draft_id": d["id"], "kind": "draft", "draft_kind": d.get("kind") or "new",
            "account": d.get("account") or "", "from_addr": d.get("account") or "", "to_addr": d.get("to_addr") or "",
            "subject": d.get("subject") or "", "snippet": " ".join(body.split())[:160], "body": body,
            "date_raw": d.get("created_at") or "", "date_ts": yhbmail.parse_date_ts(d.get("created_at") or ""),
            "category": "fyi", "unread": False, "starred": False, "folder": "drafts", "labels": ["DRAFT"],
            "source": "local_draft",
        })
    return out


def list_folder(folder: str, account: str = "", category: str = "", q: str = "", limit: int = 120) -> list[dict]:
    con = db()
    _reapply_reads(con)
    rows = [r for r in _all_rows(con, account, q) if in_folder(r, folder)]
    con.close()
    if category and category != "all":
        rows = [r for r in rows if r.get("category") == category]
    if folder == "drafts":
        rows += _draft_rows(account, q)
    rows.sort(key=lambda r: r.get("date_ts") or 0, reverse=True)
    return rows[:limit]


def folder_counts(account: str = "") -> dict:
    con = db()
    _reapply_reads(con)
    rows = _all_rows(con, account)
    con.close()
    out = {}
    for f in FOLDERS:
        hit = [r for r in rows if in_folder(r, f)]
        out[f] = {"total": len(hit), "unread": sum(1 for r in hit if r["unread"])}
    out["drafts"]["total"] += len(_draft_rows(account))
    return out


def get_item(item_id: str) -> dict | None:
    con = db()
    row = con.execute("SELECT * FROM emails WHERE id=?", (item_id,)).fetchone()
    item = dict(row) if row else next((v for v in _sent_fixture() if v["id"] == item_id), None)
    if item is None:
        con.close()
        return None
    st = con.execute("SELECT * FROM mail_state WHERE id=?", (item_id,)).fetchone()
    con.close()
    return _decorate(item, dict(st) if st else None)


def _set(con, item_id: str, **fields) -> None:
    now = yhbmail.now_iso()
    con.execute("INSERT OR IGNORE INTO mail_state(id, updated_at) VALUES (?, ?)", (item_id, now))
    sets = ", ".join(f"{k}=?" for k in fields)
    con.execute(f"UPDATE mail_state SET {sets}, updated_at=? WHERE id=?", (*fields.values(), now, item_id))


def apply(ids: list[str], action: str, folder: str = "") -> dict:
    """Apply one action to known mail ids; unknown ids are reported, not created."""
    con = db()
    known = {r[0] for r in con.execute(
        f"SELECT id FROM emails WHERE id IN ({','.join('?' * len(ids))})", ids)} if ids else set()
    known |= {v["id"] for v in _sent_fixture() if v["id"] in ids}
    changed = []
    for item_id in ids:
        if item_id not in known:
            continue
        if action in ("star", "unstar"):
            _set(con, item_id, starred=1 if action == "star" else 0)
        elif action in ("archive", "trash"):
            _set(con, item_id, folder=action)
        elif action == "move":
            _set(con, item_id, folder=folder)
        elif action == "restore":
            _set(con, item_id, folder=None)
        elif action == "purge":
            _set(con, item_id, folder=PURGED)
        elif action in ("read", "unread"):
            read = action == "read"
            con.execute("UPDATE emails SET unread=? WHERE id=?", (0 if read else 1, item_id))
            _set(con, item_id, read=1 if read else 0, read_at=yhbmail.now_iso())
        changed.append(item_id)
    con.commit()
    con.close()
    return {"changed": changed, "unknown": [i for i in ids if i not in known]}


def empty_trash(account: str = "") -> list[str]:
    con = db()
    ids = [r["id"] for r in _all_rows(con, account) if r["folder"] == "trash"]
    for item_id in ids:
        _set(con, item_id, folder=PURGED)
    con.commit()
    con.close()
    return ids


def mark_all_read(account: str = "", folder: str = "") -> dict:
    con = db()
    _reapply_reads(con)
    rows = [r for r in _all_rows(con, account) if r["unread"] and r["folder"] != PURGED
            and (not folder or in_folder(r, folder))]
    now = yhbmail.now_iso()
    per_account: dict[str, int] = {}
    for r in rows:
        con.execute("UPDATE emails SET unread=0 WHERE id=?", (r["id"],))
        _set(con, r["id"], read=1, read_at=now)
        per_account[r["account"]] = per_account.get(r["account"], 0) + 1
    con.commit()
    con.close()
    return {"marked": len(rows), "accounts": per_account}


def new_since(cursor: str = "", since: str = "", account: str = "", limit: int = 20) -> dict:
    """Unread inbox mail that reached the local cache after `cursor` (the emails rowid)
    or, with `since` (unix seconds), mail dated after it. No cursor = a fresh baseline."""
    con = db()
    _reapply_reads(con)
    top = con.execute("SELECT COALESCE(MAX(rowid), 0) FROM emails").fetchone()[0]
    now = int(time.time())
    base = {"cursor": top, "now": now}
    sql = ("SELECT rowid AS seq, id, account, subject, snippet, from_addr, date_raw, date_ts, unread, "
           "labels_json, category FROM emails WHERE unread=1")
    args: list = []
    if cursor.strip().isdigit():
        c = int(cursor)
        if c > top:
            con.close()
            return {**base, "count": 0, "emails": [], "reset": True}
        sql += " AND rowid > ?"
        args.append(c)
    elif since.strip().isdigit():
        sql += " AND date_ts > ?"
        args.append(int(since))
    else:
        con.close()
        return {**base, "count": 0, "emails": [], "baseline": True}
    if account:
        sql += " AND account=?"
        args.append(account)
    states = _states(con)
    rows = [_decorate(dict(r), states.get(r["id"])) for r in con.execute(sql + " ORDER BY rowid", args)]
    con.close()
    rows = [r for r in rows if r["folder"] == "inbox"]
    return {**base, "count": len(rows), "emails": [
        {k: r.get(k) for k in ("id", "account", "subject", "snippet", "from_addr", "date_raw", "date_ts", "category")}
        for r in rows[-limit:]]}


# ───────────────────────── print view ─────────────────────────

def _thread(item: dict) -> list[dict]:
    con = db()
    rows = [dict(r) for r in con.execute(
        "SELECT * FROM emails WHERE account=? AND thread_id=? ORDER BY date_ts", (item["account"], item["thread_id"]))]
    con.close()
    rows += [v for v in _sent_fixture() if v["account"] == item["account"] and v["thread_id"] == item["thread_id"]]
    seen, out = set(), []
    for r in sorted(rows, key=lambda r: r.get("date_ts") or 0):
        if r["id"] not in seen:
            seen.add(r["id"])
            out.append(r)
    return out or [item]


def print_html(item: dict, lang: str = "en", auto: bool = False, thread: bool = True) -> str:
    zh = _zh(lang)
    e = html.escape
    L = (lambda en, z: z if zh else en)
    msgs = _thread(item) if thread else [item]
    parts = []
    for m in msgs:
        rows = [(L("From", "寄件者"), m.get("from_addr")), (L("To", "收件者"), m.get("to_addr")),
                (L("Cc", "副本"), m.get("cc_addr")), (L("Date", "日期"), m.get("date_raw")),
                (L("Account", "帳號"), m.get("account"))]
        head = "".join(f"<tr><th>{e(k)}</th><td>{e(str(v))}</td></tr>" for k, v in rows if v)
        body = m.get("body_text") or m.get("snippet") or ""
        cls = " sel" if m["id"] == item["id"] and len(msgs) > 1 else ""
        parts.append(f'<article class="msg{cls}"><h2>{e(m.get("subject") or "—")}</h2>'
                     f'<table class="hd">{head}</table><div class="body">{e(body)}</div></article>')
    auto_js = "<script>window.addEventListener('load',()=>setTimeout(()=>window.print(),150));</script>" if auto else ""
    count = L(f"{len(msgs)} message(s)", f"共 {len(msgs)} 封")
    return f"""<!DOCTYPE html>
<html lang="{'zh-Hant' if zh else 'en'}"><head><meta charset="utf-8">
<title>{e(item.get('subject') or 'TooPowerInbox')}</title>
<style>
  body {{ font: 14px/1.65 -apple-system, "Segoe UI", "Noto Sans TC", "PingFang TC", sans-serif; color: #111; max-width: 780px; margin: 24px auto; padding: 0 18px; }}
  .bar {{ display: flex; gap: 8px; align-items: center; padding: 10px 0 14px; border-bottom: 1px solid #ccc; margin-bottom: 16px; }}
  .bar button {{ font: inherit; padding: 6px 14px; border: 1px solid #888; border-radius: 6px; background: #f4f1ea; cursor: pointer; }}
  .bar .muted {{ color: #666; font-size: 12px; }}
  .brand {{ color: #666; font-size: 12px; letter-spacing: .05em; }}
  h1 {{ font-size: 20px; margin: 4px 0 12px; }}
  h2 {{ font-size: 16px; margin: 0 0 8px; }}
  .msg {{ border-top: 1px solid #ddd; padding: 14px 0; page-break-inside: auto; }}
  .msg.sel h2 {{ text-decoration: underline; }}
  table.hd {{ border-collapse: collapse; margin-bottom: 10px; font-size: 13px; }}
  table.hd th {{ text-align: left; color: #555; font-weight: 600; padding: 1px 14px 1px 0; vertical-align: top; white-space: nowrap; }}
  table.hd td {{ padding: 1px 0; word-break: break-word; }}
  .body {{ white-space: pre-wrap; word-break: break-word; overflow-wrap: anywhere; }}
  @media print {{ .bar {{ display: none; }} body {{ margin: 0; max-width: none; }} @page {{ margin: 16mm; }} }}
</style></head><body>
<div class="bar"><button onclick="window.print()">{e(L('Print / Save as PDF', '列印／存成 PDF'))}</button>
<span class="muted">{e(L('In the print dialog pick "Save as PDF" as the destination.', '在列印對話框把目的地選成「另存為 PDF」。'))}</span></div>
<div class="brand">TooPowerInbox · {e(count)}</div>
<h1>{e(item.get('subject') or '—')}</h1>
{''.join(parts)}
{auto_js}
</body></html>"""


# ───────────────────────── translate (BYO agent) ─────────────────────────

def norm_target(target: str, lang: str) -> str:
    """Canonical LANGS key, the UI language when empty, or "" when unsupported."""
    t = str(target or "").strip().lower().replace("_", "-")
    if not t:
        return "zh-Hant" if _zh(lang) else "en"
    aliases = {k.lower(): k for k in LANGS}
    aliases.update({"zh": "zh-Hant", "zh-tw": "zh-Hant", "zh-cn": "zh-Hans", "en-us": "en", "en-gb": "en"})
    return aliases.get(t, "")


def ask_agent(system: str, prompt: str, lang: str) -> tuple[str, str, str | None]:
    """One prompt through the configured BYO agent. Returns (text, driver, error)."""
    cfg = agent_bridge.load_agent_cfg()
    driver = cfg.get("driver") or "local"
    if driver == "local":
        return "", "local", None
    try:
        if driver == "openai_compatible":
            block = cfg.get("openai_compatible") or {}
            base = (block.get("base_url") or "").rstrip("/")
            key = os.environ.get(block.get("api_key_env") or "OPENAI_API_KEY") or ""
            body = json.dumps({
                "model": block.get("model") or "gpt-4.1-mini",
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                "temperature": 0.1,
            }).encode()
            data = agent_bridge._post_json(
                f"{base}/chat/completions",
                {"Content-Type": "application/json", **({"Authorization": f"Bearer {key}"} if key else {})},
                body, timeout=110, allow_private=bool(block.get("allow_private")))
            text = data["choices"][0]["message"]["content"] or ""
        elif driver in ("cli", "http"):
            pack = {"ask": system + "\n\n" + prompt, "lang": "zh-Hant" if _zh(lang) else "en", "mode": "translate"}
            text = agent_bridge._cli(pack, cfg) if driver == "cli" else agent_bridge._http(pack, cfg)
        else:
            return "", driver, f"unknown agent driver {driver}"
    except Exception as e:
        return "", driver, f"{type(e).__name__}: {e}"[:300]
    text = (text or "").strip()
    fence = re.match(r"^```[\w-]*\n(.*?)\n```$", text, re.S)
    if fence:
        text = fence.group(1).strip()
    return text, driver, None if text else "agent returned an empty answer"


def translate(item: dict, target: str, lang: str) -> dict:
    name_en, name_zh = LANGS[target]
    driver = agent_bridge.load_agent_cfg().get("driver") or "local"
    base = {"id": item["id"], "target": target, "target_name": name_zh if _zh(lang) else name_en, "driver": driver}
    if driver == "local":
        return {**base, "ok": False, "needs_agent": True, "note": _msg(
            "No LLM is wired, so nothing was translated. TooPowerInbox does not ship a translator: set "
            '"driver" in agent.json to openai_compatible, cli or http (your own model) and try again.',
            "未接 LLM，所以沒有翻譯。TooPowerInbox 不內建翻譯引擎：請在 agent.json 把 driver 設成 "
            "openai_compatible、cli 或 http（接你自己的模型）後再試。", lang)}
    body = (item.get("body_text") or item.get("snippet") or "")[:TRANSLATE_MAX]
    system = (f"Translate the email below into {name_en}. Output only the translation: no preface, no notes, "
              "no markdown. Keep names, numbers, amounts, dates, email addresses and URLs exactly as written, "
              "and keep the line breaks.")
    prompt = f"Subject: {item.get('subject') or ''}\n\n{body}"
    text, used, error = ask_agent(system, prompt, lang)
    if error:
        return {**base, "ok": False, "driver": used, "error": error, "note": _msg(
            f"The agent ({used}) failed; the original is unchanged.",
            f"Agent（{used}）呼叫失敗，原文未變動。", lang)}
    subject, _, rest = text.partition("\n")
    m = re.match(r"^\s*(subject|主旨)\s*[:：]\s*(.*)$", subject, re.I)
    out = {**base, "ok": True, "driver": used, "text": rest.strip() if m else text}
    if m:
        out["subject"] = m.group(2).strip()
    out["note"] = _msg(f"Machine translation by your agent ({used}); check names and figures against the original.",
                       f"由你的 agent（{used}）機器翻譯；人名與數字請對照原文。", lang)
    return out


# ───────────────────────── accounts.json ─────────────────────────

def _write_cfg(cfg: dict) -> None:
    path = yhbmail.ACCOUNTS_PATH
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n")
    os.replace(tmp, path)


def account_view(acc: dict, i: int) -> dict:
    email_addr = acc.get("email") or ""
    driver = acc.get("driver") or "demo"
    view = {"email": email_addr, "label": acc.get("label") or email_addr.split("@")[0], "driver": driver,
            "platform": acc.get("platform") or DRIVER_PLATFORM.get(driver, ""), "primary": i == 0,
            "signature": acc.get("signature") or ""}
    for k in IMAP_KEYS:
        if acc.get(k) not in (None, ""):
            view[k] = acc[k]
    return view


def settings() -> dict:
    cfg = yhbmail.load_cfg()
    return {"mode": cfg.get("mode") or "demo", "path": "accounts.json",
            "exists": yhbmail.ACCOUNTS_PATH.exists(),
            "drivers": list(DRIVERS),
            "accounts": [account_view(a, i) for i, a in enumerate(cfg.get("accounts") or [])]}


def _fix_mode(cfg: dict) -> str | None:
    live = any((a.get("driver") or "demo") != "demo" for a in cfg.get("accounts") or [])
    mode = cfg.get("mode") or "demo"
    if live and mode == "demo":
        cfg["mode"] = "live"
    elif not live and mode != "demo":
        cfg["mode"] = "demo"
    return cfg["mode"] if cfg.get("mode") != mode else None


def add_account(b: dict, lang: str):
    if "password" in b:
        return _bad("never put a password here; name an environment variable in password_env instead",
                    "不可在這裡填密碼；請改用 password_env 填環境變數名稱", lang)
    email_addr = str(b.get("email") or "").strip()
    if not EMAIL_RE.match(email_addr):
        return _bad("not a valid email address", "信箱格式不正確", lang)
    driver = str(b.get("driver") or "demo").strip()
    if driver not in DRIVERS:
        return _bad(f"unknown driver; use one of {', '.join(DRIVERS)}", f"不支援的 driver，可用：{'、'.join(DRIVERS)}", lang)
    acc = {"email": email_addr, "driver": driver,
           "label": str(b.get("label") or "").strip()[:60] or email_addr.split("@")[0],
           "platform": str(b.get("platform") or "").strip()[:30] or DRIVER_PLATFORM[driver]}
    if driver == "imap":
        for k in IMAP_KEYS:
            v = b.get(k)
            if v in (None, ""):
                continue
            if k == "port":
                try:
                    v = int(v)
                except (TypeError, ValueError):
                    return _bad("port must be a number", "port 必須是數字", lang)
                if not 0 < v < 65536:
                    return _bad("port out of range", "port 超出範圍", lang)
            elif k == "password_env":
                v = str(v).strip()
                if not ENV_RE.match(v):
                    return _bad("password_env must be an environment variable name like TPI_IMAP_PASSWORD",
                                "password_env 要填環境變數名稱，例如 TPI_IMAP_PASSWORD", lang)
            else:
                v = str(v).strip()[:200]
            acc[k] = v
    with _cfg_lock:
        cfg = yhbmail.load_cfg()
        accounts = list(cfg.get("accounts") or [])
        if any((a.get("email") or "").lower() == email_addr.lower() for a in accounts):
            return _bad("that account is already in accounts.json", "accounts.json 已有這個帳號", lang, 409)
        if b.get("primary"):
            accounts.insert(0, acc)
        else:
            accounts.append(acc)
        cfg["accounts"] = accounts
        mode = _fix_mode(cfg)
        _write_cfg(cfg)
    note = _msg("Saved to accounts.json. Hit Sync to fetch its mail.", "已寫入 accounts.json，按「同步」抓這個帳號的信。", lang)
    if mode:
        note += _msg(f" Mode switched to {mode}.", f"模式已切換為 {mode}。", lang)
    return {"ok": True, "note": note, **settings()}, 201


def _mutate(lang: str, email_addr: str, fn):
    with _cfg_lock:
        cfg = yhbmail.load_cfg()
        accounts = list(cfg.get("accounts") or [])
        idx = next((i for i, a in enumerate(accounts) if (a.get("email") or "") == email_addr), None)
        if idx is None:
            return _bad("account not in accounts.json", "帳號不在 accounts.json", lang, 404)
        err = fn(accounts, idx)
        if err:
            return err
        cfg["accounts"] = accounts
        _fix_mode(cfg)
        _write_cfg(cfg)
    return {"ok": True, **settings()}


def html_to_text(src: str) -> str:
    class P(HTMLParser):
        BLOCK = {"p", "div", "br", "tr", "li", "table", "h1", "h2", "h3", "h4", "section"}

        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.out, self.skip = [], 0

        def handle_starttag(self, tag, attrs):
            if tag in ("script", "style", "head", "title"):
                self.skip += 1
            elif tag in self.BLOCK:
                self.out.append("\n")

        def handle_endtag(self, tag):
            if tag in ("script", "style", "head", "title"):
                self.skip = max(0, self.skip - 1)
            elif tag in self.BLOCK and tag != "br":
                self.out.append("\n")

        def handle_data(self, data):
            if not self.skip:
                self.out.append(re.sub(r"[ \t\r\n]+", " ", data))

    p = P()
    p.feed(src)
    p.close()
    lines = [ln.strip() for ln in "".join(p.out).split("\n")]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def clean_signature(text: str, filename: str = "") -> str:
    text = str(text or "").replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    looks_html = filename.lower().endswith((".html", ".htm")) or re.search(
        r"<(html|body|div|p|br|table|span|a)\b", text[:2000], re.I)
    if looks_html:
        text = re.sub(r"\n{2,}", "\n", html_to_text(text).replace("\xa0", " "))
    lines = [ln.rstrip() for ln in text.split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and lines[0].strip() in ("--", "-- "):
        lines.pop(0)
    return "\n".join(lines).strip()[:SIG_MAX]


def set_signature(email_addr: str, signature: str, lang: str):
    def fn(accounts, idx):
        acc = dict(accounts[idx])
        if signature:
            acc["signature"] = signature
        else:
            acc.pop("signature", None)
        accounts[idx] = acc
    out = _mutate(lang, email_addr, fn)
    if isinstance(out, dict):
        out["signature"] = signature
        out["note"] = _msg("Signature saved to accounts.json.", "簽名已存到 accounts.json。", lang) if signature else \
            _msg("Signature removed.", "簽名已移除。", lang)
    return out


# ───────────────────────── routes ─────────────────────────

def _folder_names(lang) -> list[dict]:
    return [{"id": f, "name": FOLDER_NAMES[f][1 if _zh(lang) else 0]} for f in FOLDERS]


def _limit(v, default=120) -> int:
    try:
        return max(1, min(1000, int(v or default)))
    except ValueError:
        return default


@get("/api/mailops/folders")
def r_folders(req):
    account = req.query.get("account") or ""
    counts = folder_counts(account)
    return {"folders": [{**f, **counts[f["id"]]} for f in _folder_names(_lang(req))],
            "move_targets": list(MOVE_TARGETS), "account": account}


@get("/api/mailops/list")
def r_list(req):
    folder = req.query.get("folder") or "inbox"
    if folder not in FOLDERS:
        return _bad(f"unknown folder; use one of {', '.join(FOLDERS)}", "沒有這個資料夾", _lang(req))
    emails = list_folder(folder, req.query.get("account") or "", req.query.get("category") or "",
                         (req.query.get("q") or "").strip(), _limit(req.query.get("limit")))
    return {"folder": folder, "emails": emails, "count": len(emails)}


@get("/api/mailops/item")
def r_item(req):
    item = get_item(req.query.get("id") or "")
    if not item:
        return _bad("not found", "找不到這封信", _lang(req), 404)
    return item


@post("/api/mailops/action")
def r_action(req):
    if (bad := _guard(req)):
        return bad
    lang, b = _lang(req), req.body
    action = str(b.get("action") or "")
    if action not in ACTIONS:
        return _bad(f"unknown action; use one of {', '.join(ACTIONS)}", "不支援的動作", lang)
    ids = b.get("ids") if isinstance(b.get("ids"), list) else ([b["id"]] if b.get("id") else [])
    ids = [str(i) for i in ids if isinstance(i, str) and i][:500]
    if not ids:
        return _bad("missing ids", "缺少信件 id", lang)
    folder = str(b.get("folder") or "")
    if action == "move" and folder not in MOVE_TARGETS:
        return _bad(f"move target must be one of {', '.join(MOVE_TARGETS)}", "只能移到收件匣、封存或垃圾桶", lang)
    out = apply(ids, action, folder)
    if not out["changed"]:
        return {"ok": False, **out, "error": _msg("no such mail in the local cache", "本機快取找不到這些信", lang)}, 404
    return {"ok": True, "action": action, **out, "note": _msg(
        "Local state only; the remote mailbox is untouched.", "只改本機狀態，遠端信箱不變。", lang)}


@post("/api/mailops/empty-trash")
def r_empty_trash(req):
    if (bad := _guard(req)):
        return bad
    ids = empty_trash(str(req.body.get("account") or ""))
    return {"ok": True, "purged": len(ids), "note": _msg(
        "Hidden from every folder on this machine; the remote mailbox is untouched.",
        "已從本機所有資料夾隱藏；遠端信箱不變。", _lang(req))}


@post("/api/mailops/mark-all-read")
def r_mark_all_read(req):
    if (bad := _guard(req)):
        return bad
    lang = _lang(req)
    folder = str(req.body.get("folder") or "")
    if folder and folder not in FOLDERS:
        return _bad("unknown folder", "沒有這個資料夾", lang)
    out = mark_all_read(str(req.body.get("account") or ""), folder)
    n, k = out["marked"], len(out["accounts"])
    return {"ok": True, **out, "note": _msg(f"Marked {n} read across {k} account(s) (local state).",
                                            f"已把 {k} 個帳號共 {n} 封標為已讀（本機狀態）。", lang)}


@get("/api/new-since")
def r_new_since(req):
    q = req.query
    return new_since(q.get("cursor") or "", q.get("since") or "", q.get("account") or "", _limit(q.get("limit"), 20))


@get("/mailops/print")
def r_print(req):
    lang = req.query.get("lang") or "en"
    item = get_item(req.query.get("id") or "")
    if not item:
        msg = _msg("Not found", "找不到這封信", lang)
        return Raw(f"<!DOCTYPE html><meta charset=utf-8><p>{html.escape(msg)}</p>".encode(),
                   "text/html; charset=utf-8", 404)
    page = print_html(item, lang, auto=req.query.get("auto") == "1", thread=req.query.get("thread") != "0")
    return Raw(page.encode(), "text/html; charset=utf-8")


@post("/api/mailops/translate")
def r_translate(req):
    lang = _lang(req)
    item = get_item(str(req.body.get("id") or ""))
    if not item:
        return _bad("not found", "找不到這封信", lang, 404)
    target = norm_target(str(req.body.get("target") or ""), lang)
    if not target:
        return _bad(f"unsupported language; use one of {', '.join(LANGS)}", "不支援的語言", lang)
    return translate(item, target, lang)


@get("/api/mailops/languages")
def r_languages(req):
    zh = req.lang_zh()
    return {"languages": [{"id": k, "name": v[1] if zh else v[0]} for k, v in LANGS.items()]}


@get("/api/mailops/accounts")
def r_accounts(req):
    return settings()


@post("/api/mailops/accounts/add")
def r_accounts_add(req):
    if (bad := _guard(req)):
        return bad
    return add_account(req.body, _lang(req))


@post("/api/mailops/accounts/remove")
def r_accounts_remove(req):
    if (bad := _guard(req)):
        return bad

    def fn(accounts, idx):
        accounts.pop(idx)
    return _mutate(_lang(req), str(req.body.get("email") or ""), fn)


@post("/api/mailops/accounts/primary")
def r_accounts_primary(req):
    if (bad := _guard(req)):
        return bad

    def fn(accounts, idx):
        accounts.insert(0, accounts.pop(idx))
    return _mutate(_lang(req), str(req.body.get("email") or ""), fn)


@post("/api/mailops/accounts/reorder")
def r_accounts_reorder(req):
    if (bad := _guard(req)):
        return bad
    lang = _lang(req)
    order = req.body.get("order")
    if not isinstance(order, list) or not order:
        return _bad("order must be the full list of account emails", "order 要是完整的帳號清單", lang)
    with _cfg_lock:
        cfg = yhbmail.load_cfg()
        accounts = list(cfg.get("accounts") or [])
        by_email = {a.get("email"): a for a in accounts}
        if sorted(map(str, order)) != sorted(by_email) or len(set(order)) != len(order):
            return _bad("order must list every account exactly once", "order 必須剛好列出每個帳號一次", lang)
        cfg["accounts"] = [by_email[e] for e in order]
        _write_cfg(cfg)
    return {"ok": True, **settings()}


@get("/api/mailops/signature")
def r_signature(req):
    addr = req.query.get("account") or ""
    accounts = yhbmail.load_cfg().get("accounts") or []
    acc = next((a for a in accounts if a.get("email") == addr), None) or (accounts[0] if accounts and not addr else None)
    return {"account": (acc or {}).get("email") or addr, "signature": (acc or {}).get("signature") or ""}


@post("/api/mailops/signature")
def r_signature_save(req):
    if (bad := _guard(req)):
        return bad
    lang = _lang(req)
    sig = req.body.get("signature")
    if not isinstance(sig, str):
        return _bad("signature must be text", "簽名必須是文字", lang)
    return set_signature(str(req.body.get("email") or ""), clean_signature(sig), lang)


@post("/api/mailops/signature/import")
def r_signature_import(req):
    if (bad := _guard(req)):
        return bad
    lang, b = _lang(req), req.body
    content, filename = b.get("content"), str(b.get("filename") or "")
    if not isinstance(content, str) or not content.strip():
        return _bad("the file is empty", "檔案是空的", lang)
    if len(content) > SIG_FILE_MAX:
        return _bad("file too large for a signature (200 KB max)", "檔案太大，簽名檔上限 200 KB", lang)
    if (filename and not filename.lower().endswith(SIG_EXTS)) or "\x00" in content:
        return _bad("use a .txt, .md, .sig or .html file", "請用 .txt、.md、.sig 或 .html 檔", lang)
    sig = clean_signature(content, filename)
    if not sig:
        return _bad("no text found in the file", "檔案裡找不到文字", lang)
    out = set_signature(str(b.get("email") or ""), sig, lang)
    if isinstance(out, dict):
        out["imported_from"] = os.path.basename(filename)[:120]
    return out
