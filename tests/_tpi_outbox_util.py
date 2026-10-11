"""Shared helpers for the outbox tests: a clean slate, no background ticker, fictional drafts only."""
from __future__ import annotations

import shutil
import unittest
from datetime import datetime, timedelta

import _tpi_server as srv
from features import compose
from features import outbox

outbox.stop_ticker()

M1 = "demo:you@example.com:m1"


def reset() -> None:
    outbox.ensure_tables()
    con = srv.yhbmail.db()
    for table in ("outbox", "outbox_settings", "outbox_log", "drafts"):
        con.execute(f"DELETE FROM {table}")
    con.commit()
    con.close()
    shutil.rmtree(outbox.outbox_dir(), ignore_errors=True)


def make_draft(**over) -> int:
    data = {"kind": "new", "account": "you@example.com", "to": "maya@example.com", "cc": "", "bcc": "",
            "subject": "Design review notes", "text": "Hi Maya,\n\nThe notes are ready for Friday.\n\nBest,"}
    data.update(over)
    out, status = compose.save_draft(data, "en")
    assert status in (200, 201), out
    return out["draft"]["id"]


def at(hours: float = 0, base: datetime | None = None) -> datetime:
    return (base or outbox.now_dt()) + timedelta(hours=hours)


class OutboxCase(unittest.TestCase):
    def setUp(self):
        outbox.stop_ticker()
        reset()

    def prepared(self, draft_id=None, lang="en", **fields):
        body = {"draft_id": draft_id if draft_id is not None else make_draft(**fields)}
        out, status = outbox.prepare(body, lang)
        self.assertEqual(status, 201, out)
        return out

    def confirmed(self, mode="now", send_at=None, now=None, lang="en", **fields):
        p = self.prepared(lang=lang, **fields)
        body = {"id": p["item"]["id"], "token": p["token"], "ack": True, "mode": mode}
        if send_at is not None:
            body["send_at"] = send_at
        out, status = outbox.confirm(body, lang, now=now)
        self.assertEqual(status, 200, out)
        return out["item"]
