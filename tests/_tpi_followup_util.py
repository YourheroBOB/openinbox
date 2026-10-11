"""Shared helpers for the follow-up / rules / overnight tests: extra fictional mail and a full reset."""
from __future__ import annotations

import json
import shutil
import urllib.error
import urllib.request

import _tpi_server as srv
import yhbmail

NOW = "2026-09-19 09:00"
ME = "Alex Chen <you@example.com>"
OWN_TABLES = ("followup_settings", "followup_state", "followup_nudges", "rule_marks", "rule_applied", "rule_runs",
              "overnight_runs", "overnight_drafts")


def demo_id(n: str) -> str:
    return f"demo:you@example.com:{n}"


def add_email(item_id: str, subject: str, from_addr: str, date_raw: str, body: str = "", thread_id: str = "",
              to_addr: str = ME, unread: bool = False) -> str:
    con = yhbmail.db()
    yhbmail.upsert_email(con, {
        "id": item_id, "account": "you@example.com", "platform": "demo", "thread_id": thread_id or item_id,
        "subject": subject, "snippet": body[:120], "from_addr": from_addr, "to_addr": to_addr,
        "date_raw": date_raw, "unread": unread, "body_text": body, "labels": ["INBOX"],
    })
    con.commit()
    con.close()
    return item_id


class Baseline:
    """Snapshot before a test so everything it created can be removed afterwards.

    Drafts left by other suites are parked for the test and put back on restore,
    so "a reply draft already exists" never depends on test order.
    """

    def __init__(self):
        con = yhbmail.db()
        cur = con.execute("SELECT * FROM drafts")
        self.draft_cols = [c[0] for c in cur.description]
        self.drafts = cur.fetchall()
        con.execute("DELETE FROM drafts")
        con.commit()
        has_tasks = con.execute("SELECT 1 FROM sqlite_master WHERE name='triage_tasks'").fetchone()
        self.task = con.execute("SELECT COALESCE(MAX(id), 0) FROM triage_tasks").fetchone()[0] if has_tasks else 0
        self.emails = {r[0] for r in con.execute("SELECT id FROM emails")}
        con.close()

    def restore(self):
        con = yhbmail.db()
        con.execute("DELETE FROM drafts")
        if self.drafts:
            cols = ", ".join(self.draft_cols)
            marks = ", ".join("?" * len(self.draft_cols))
            con.executemany(f"INSERT INTO drafts ({cols}) VALUES ({marks})", self.drafts)
        if con.execute("SELECT 1 FROM sqlite_master WHERE name='triage_tasks'").fetchone():
            con.execute("DELETE FROM triage_tasks WHERE id>?", (self.task,))
            con.execute("DELETE FROM triage_history WHERE task_id>?", (self.task,))
        for (item_id,) in list(con.execute("SELECT id FROM emails")):
            if item_id not in self.emails:
                con.execute("DELETE FROM emails WHERE id=?", (item_id,))
        for table in OWN_TABLES:
            if con.execute("SELECT 1 FROM sqlite_master WHERE name=?", (table,)).fetchone():
                con.execute(f"DELETE FROM {table}")
        con.commit()
        con.close()
        for name in ("rules.json", "rules.json.tmp"):
            (srv.ROOT / name).unlink(missing_ok=True)
        shutil.rmtree(srv.ROOT / "data" / "briefs", ignore_errors=True)
        srv.reseed()


def post_from(path: str, body: dict, origin: str):
    req = urllib.request.Request(srv.BASE + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Origin": origin})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def local_origin() -> str:
    return srv.BASE
