"""Shared helpers for the tpi-mailops tests: fictional extra mail and a clean reset."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

import _tpi_server as srv

yhbmail = srv.yhbmail
DEMO = "you@example.com"


def mid(n: int) -> str:
    return f"demo:{DEMO}:m{n}"


def add_mail(item_id: str, account: str, subject: str, unread: bool = True, body: str = "", labels=None,
             date_raw: str = "2026-09-20 09:00", thread_id: str = "") -> None:
    con = yhbmail.db()
    yhbmail.upsert_email(con, {
        "id": item_id, "account": account, "platform": "imap", "thread_id": thread_id or item_id,
        "subject": subject, "snippet": body[:80], "from_addr": f"Sam Rivera <sam@{account.split('@')[1]}>",
        "to_addr": account, "date_raw": date_raw, "unread": unread, "labels": labels or ["INBOX"],
        "body_text": body,
    })
    con.commit()
    con.close()


def request_with_headers(method: str, path: str, body, headers: dict):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(srv.BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def reset() -> None:
    yhbmail.ACCOUNTS_PATH.unlink(missing_ok=True)
    (yhbmail.ROOT / "agent.json").unlink(missing_ok=True)
    con = yhbmail.db()
    con.execute("DROP TABLE IF EXISTS mail_state")
    con.execute("DELETE FROM emails WHERE platform != 'demo'")
    con.execute("DELETE FROM drafts")
    con.commit()
    con.close()
    srv.reseed()
