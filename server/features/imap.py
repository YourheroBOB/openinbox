"""Read-only IMAP driver (iCloud, Fastmail, Yahoo, Zoho, or any IMAP host).

accounts.json entry:

    {"email": "you@example.com", "driver": "imap", "provider": "icloud",
     "label": "iCloud", "password_env": "TPI_IMAP_ICLOUD_PASSWORD"}

Optional keys: host, port, security ("ssl" | "starttls" | "none", loopback only),
username / username_env, mailbox (default INBOX), max_bytes, timeout.

The password is only ever read from the environment: the variable named by
`password_env`, or `TPI_IMAP_PASSWORD_<EMAIL>` (upper-cased, non-alphanumerics
as `_`). A plaintext password in accounts.json is refused, never used.

Read-only by construction: the mailbox is opened with EXAMINE and messages are
fetched with BODY.PEEK, so nothing on the server changes (not even \\Seen).
"""
from __future__ import annotations

import email
import email.policy
import html
import imaplib
import os
import re
import ssl
import time
from datetime import datetime
from email.utils import parsedate_to_datetime

import yhbmail

PRESETS = {
    "icloud": {"name": "iCloud", "host": "imap.mail.me.com", "port": 993, "security": "ssl"},
    "fastmail": {"name": "Fastmail", "host": "imap.fastmail.com", "port": 993, "security": "ssl"},
    "yahoo": {"name": "Yahoo", "host": "imap.mail.yahoo.com", "port": 993, "security": "ssl"},
    "zoho": {"name": "Zoho", "host": "imap.zoho.com", "port": 993, "security": "ssl"},
    "custom": {"name": "IMAP", "host": "", "port": 993, "security": "ssl"},
}
ICLOUD_DOMAINS = ("icloud.com", "me.com", "mac.com")
PLAINTEXT_KEYS = ("password", "pass", "passwd", "app_password", "secret")
LOOPBACK = ("127.0.0.1", "::1", "localhost")
DEFAULT_MAX_BYTES = 65536
FETCH_BATCH = 25
FETCH_ITEM = re.compile(rb"UID (\d+)")
FLAGS_ITEM = re.compile(rb"FLAGS \(([^)]*)\)")


class ConfigError(ValueError):
    pass


def provider_of(acc: dict) -> str:
    p = (acc.get("provider") or "").strip().lower()
    if p:
        return p if p in PRESETS else "custom"
    if acc.get("host"):
        return "custom"
    domain = (acc.get("email") or "").rsplit("@", 1)[-1].lower()
    return "icloud" if domain in ICLOUD_DOMAINS else "custom"


def default_password_env(acc: dict) -> str:
    return "TPI_IMAP_PASSWORD_" + re.sub(r"[^A-Z0-9]", "_", (acc.get("email") or "").upper())


def password_env_name(acc: dict) -> str:
    return (acc.get("password_env") or "").strip() or default_password_env(acc)


def credential_status(acc: dict) -> str:
    """`plaintext_rejected`, `missing`, or `env` — never the secret itself."""
    if any(k in acc for k in PLAINTEXT_KEYS):
        return "plaintext_rejected"
    return "env" if os.environ.get(password_env_name(acc)) else "missing"


def settings(acc: dict) -> dict:
    if not acc.get("email"):
        raise ConfigError("imap account needs an email")
    if any(k in acc for k in PLAINTEXT_KEYS):
        raise ConfigError("plaintext password in accounts.json is not allowed; set password_env "
                          "and export that environment variable instead")
    provider = provider_of(acc)
    preset = PRESETS[provider]
    host = (acc.get("host") or preset["host"]).strip()
    if not host:
        raise ConfigError("imap account needs a host (or a known provider: "
                          + ", ".join(p for p in PRESETS if p != "custom") + ")")
    security = (acc.get("security") or preset["security"]).strip().lower()
    if security not in ("ssl", "starttls", "none"):
        raise ConfigError(f"unknown security {security!r}; use ssl, starttls or none")
    if security == "none" and host not in LOOPBACK:
        raise ConfigError("security none is only allowed for a loopback host")
    port = int(acc.get("port") or (993 if security == "ssl" else 143))
    user_env = (acc.get("username_env") or "").strip()
    username = (os.environ.get(user_env) if user_env else None) or acc.get("username") or acc["email"]
    return {
        "provider": provider, "host": host, "port": port, "security": security,
        "username": username, "password_env": password_env_name(acc),
        "mailbox": acc.get("mailbox") or "INBOX",
        "max_bytes": int(acc.get("max_bytes") or DEFAULT_MAX_BYTES),
        "timeout": float(acc.get("timeout") or 30),
    }


def _password(cfg: dict) -> str:
    pw = os.environ.get(cfg["password_env"]) or ""
    if not pw:
        raise ConfigError(f"missing password: export {cfg['password_env']}")
    return pw


def open_connection(cfg: dict):
    if cfg["security"] == "ssl":
        return imaplib.IMAP4_SSL(cfg["host"], cfg["port"], ssl_context=ssl.create_default_context(),
                                 timeout=cfg["timeout"])
    conn = imaplib.IMAP4(cfg["host"], cfg["port"], timeout=cfg["timeout"])
    if cfg["security"] == "starttls":
        conn.starttls(ssl_context=ssl.create_default_context())
    return conn


def quote_mailbox(name: str) -> str:
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _scrub(text: str, secret: str) -> str:
    return text.replace(secret, "***") if secret else text


def _check(typ, data, what: str):
    if typ != "OK":
        detail = b" ".join(d for d in (data or []) if isinstance(d, bytes)).decode(errors="replace")
        raise RuntimeError(f"IMAP {what} failed: {detail or typ}")
    return data


def _login(cfg: dict):
    pw = _password(cfg)
    conn = open_connection(cfg)
    try:
        _check(*conn.login(cfg["username"], pw), "login")
        typ, data = conn.select(quote_mailbox(cfg["mailbox"]), readonly=True)
        _check(typ, data, f"examine {cfg['mailbox']}")
        return conn, pw, int((data or [b"0"])[0] or 0)
    except Exception as e:
        _logout(conn)
        if isinstance(e, imaplib.IMAP4.error):
            raise RuntimeError(_scrub(f"IMAP error: {e}", pw)) from None
        raise RuntimeError(_scrub(str(e), pw)) from None


def _logout(conn) -> None:
    try:
        conn.logout()
    except Exception:
        pass


def check(acc: dict) -> dict:
    """Log in, EXAMINE the mailbox, log out. Reports the message count only."""
    cfg = settings(acc)
    conn, _, exists = _login(cfg)
    _logout(conn)
    return {"ok": True, "host": cfg["host"], "mailbox": cfg["mailbox"], "exists": exists}


def _text_of(msg) -> str:
    try:
        part = msg.get_body(preferencelist=("plain", "html"))
        if part is None:
            return ""
        text = part.get_content()
        if part.get_content_subtype() == "html":
            text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", text)
            text = html.unescape(re.sub(r"(?s)<[^>]+>", " ", text))
    except Exception:
        return ""
    return text if isinstance(text, str) else ""


def _has_attachment(msg) -> bool:
    try:
        return any(p.get_content_disposition() == "attachment" or p.get_filename()
                   for p in msg.walk() if not p.is_multipart())
    except Exception:
        return False


def _header(msg, name: str) -> str:
    try:
        return str(msg.get(name) or "").strip()
    except Exception:
        return ""


def _when(msg, internaldate: bytes | None) -> datetime | None:
    raw = _header(msg, "Date")
    if raw:
        try:
            dt = parsedate_to_datetime(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=yhbmail.TZ)
            return dt.astimezone(yhbmail.TZ)
        except (TypeError, ValueError, IndexError):
            pass
    if internaldate:
        tt = imaplib.Internaldate2tuple(internaldate)
        if tt:
            return datetime.fromtimestamp(time.mktime(tt), yhbmail.TZ)
    return None


def parse_message(raw: bytes, *, account: str, mailbox: str, uidvalidity: str, uid: str,
                  flags: list[str], provider: str, internaldate: bytes | None = None) -> dict:
    msg = email.message_from_bytes(raw or b"", policy=email.policy.default)
    body = _text_of(msg).strip()
    when = _when(msg, internaldate)
    msgid = _header(msg, "Message-ID")
    refs = (_header(msg, "References") or _header(msg, "In-Reply-To")).split()
    platform = "icloud" if provider == "icloud" else "imap"
    labels = [mailbox] + [f.lstrip("\\").upper() for f in flags if f.lower() not in ("\\seen", "\\recent")]
    return {
        "id": f"imap:{account}:{mailbox}:{uidvalidity}:{uid}",
        "account": account, "platform": platform,
        "thread_id": (refs[0] if refs else msgid) or f"{mailbox}:{uid}",
        "subject": _header(msg, "Subject"),
        "snippet": re.sub(r"\s+", " ", body)[:200],
        "from_addr": _header(msg, "From"), "to_addr": _header(msg, "To"),
        "date_raw": when.strftime("%Y-%m-%d %H:%M") if when else "",
        "date_ts": int(when.timestamp()) if when else 0,
        "unread": not any(f.lower() == "\\seen" for f in flags),
        "has_attachment": _has_attachment(msg),
        "labels": labels, "body_text": body[:20000],
    }


def _fetched(data) -> list[tuple[str, list[str], bytes | None, bytes]]:
    out = []
    for item in data or []:
        if not isinstance(item, tuple) or len(item) < 2:
            continue
        meta, raw = item[0], item[1]
        uid = FETCH_ITEM.search(meta)
        if not uid:
            continue
        fl = FLAGS_ITEM.search(meta)
        flags = fl.group(1).decode(errors="replace").split() if fl else []
        idate = re.search(rb'INTERNALDATE "[^"]+"', meta)
        out.append((uid.group(1).decode(), flags, idate.group(0) if idate else None, raw))
    return out


def fetch(acc: dict, limit: int = 25) -> list[dict]:
    cfg = settings(acc)
    conn, pw, _ = _login(cfg)
    try:
        uidvalidity = "0"
        _, val = conn.response("UIDVALIDITY")
        if val and val[0]:
            uidvalidity = val[0].decode() if isinstance(val[0], bytes) else str(val[0])
        uids = _check(*conn.uid("SEARCH", None, "ALL"), "search")
        uids = (uids[0] or b"").split() if uids else []
        uids = [u.decode() for u in uids][-max(1, int(limit)):]
        rows = []
        part = f"BODY.PEEK[]<0.{cfg['max_bytes']}>"
        for i in range(0, len(uids), FETCH_BATCH):
            batch = ",".join(uids[i:i + FETCH_BATCH])
            data = _check(*conn.uid("FETCH", batch, f"(UID FLAGS INTERNALDATE {part})"), "fetch")
            for uid, flags, idate, raw in _fetched(data):
                rows.append(parse_message(raw, account=acc["email"], mailbox=cfg["mailbox"],
                                          uidvalidity=uidvalidity, uid=uid, flags=flags,
                                          provider=cfg["provider"], internaldate=idate))
        return rows
    except imaplib.IMAP4.error as e:
        raise RuntimeError(_scrub(f"IMAP error: {e}", pw)) from None
    finally:
        _logout(conn)


yhbmail.DRIVERS["imap"] = fetch
