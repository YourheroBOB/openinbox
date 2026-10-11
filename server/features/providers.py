"""Unified inbox accounts: every configured box (gog / gsk / imap / demo) with its
driver, per-account mail counts and last sync result, plus a read-only IMAP
login check. Secrets never appear here: only the *name* of the env var.
"""
from __future__ import annotations

import yhbmail
from features import get, post
from features import imap

DRIVERS = {
    "demo": {"zh": "示範資料", "en": "Demo data"},
    "gog": {"zh": "Gmail（gog）", "en": "Gmail (gog)"},
    "gsk": {"zh": "Outlook（gsk）", "en": "Outlook (gsk)"},
    "imap": {"zh": "IMAP 唯讀", "en": "IMAP read-only"},
}


def _counts() -> dict:
    con = yhbmail.db()
    rows = con.execute(
        "SELECT account, COUNT(*), SUM(unread), GROUP_CONCAT(DISTINCT platform) FROM emails GROUP BY account")
    out = {r[0]: {"total": r[1], "unread": r[2] or 0, "platforms": sorted((r[3] or "").split(","))}
           for r in rows}
    con.close()
    return out


def _last_by_email() -> dict:
    return {a.get("email"): a for a in yhbmail.LAST_SYNC.get("accounts") or []}


def account_view(acc: dict, counts: dict, last: dict) -> dict:
    email_addr = acc.get("email") or ""
    driver = acc.get("driver") or "demo"
    c = counts.get(email_addr) or {}
    view = {
        "email": email_addr, "label": acc.get("label") or email_addr.split("@")[0],
        "driver": driver, "platform": acc.get("platform") or "", "configured": True,
        "total": c.get("total", 0), "unread": c.get("unread", 0),
        "readonly": True, "driver_supported": driver in DRIVERS,
    }
    if driver == "imap":
        provider = imap.provider_of(acc)
        view.update({
            "provider": provider, "platform": "icloud" if provider == "icloud" else "imap",
            "host": acc.get("host") or imap.PRESETS[provider]["host"],
            "mailbox": acc.get("mailbox") or "INBOX",
            "password_env": imap.password_env_name(acc),
            "credentials": imap.credential_status(acc),
        })
    hit = last.get(email_addr)
    if hit:
        view["last_sync"] = {k: hit[k] for k in ("count", "seconds", "error") if k in hit}
    return view


def accounts() -> list[dict]:
    cfg = yhbmail.load_cfg()
    counts, last = _counts(), _last_by_email()
    out = [account_view(a, counts, last) for a in cfg.get("accounts") or []]
    seen = {a["email"] for a in out}
    for addr, c in sorted(counts.items()):
        if addr not in seen:
            out.append({"email": addr, "label": addr.split("@")[0], "driver": "", "platform": ",".join(c["platforms"]),
                        "configured": False, "total": c["total"], "unread": c["unread"], "readonly": True})
    return out


@get("/api/providers")
def list_providers(req):
    zh = req.lang_zh()
    return {
        "mode": yhbmail.load_cfg().get("mode") or "demo",
        "drivers": [{"id": k, "name": v["zh" if zh else "en"]} for k, v in DRIVERS.items()],
        "imap_presets": [{"id": k, "name": v["name"], "host": v["host"], "port": v["port"]}
                         for k, v in imap.PRESETS.items()],
        "accounts": accounts(),
        "last_sync": yhbmail.LAST_SYNC.get("at"),
    }


@post("/api/providers/check")
def check_account(req):
    zh = req.lang_zh()
    addr = (req.body.get("email") or "").strip()
    acc = next((a for a in yhbmail.load_cfg().get("accounts") or [] if a.get("email") == addr), None)
    if not acc:
        return {"ok": False, "error": "帳號不在 accounts.json" if zh else "account not in accounts.json"}, 404
    if acc.get("driver") != "imap":
        return {"ok": False, "error": "只有 IMAP 帳號可以測試連線" if zh else "only IMAP accounts can be checked"}, 400
    try:
        out = imap.check(acc)
    except Exception as e:
        return {"ok": False, "email": addr, "error": str(e)[:300]}
    note = f"連線成功（唯讀），{out['mailbox']} 有 {out['exists']} 封" if zh else \
        f"Connected read-only; {out['mailbox']} has {out['exists']} messages"
    return {**out, "email": addr, "note": note}
