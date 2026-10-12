"""Outbox robustness: a long history never hides new mail, a reschedule always beats a pending release,
and a release interrupted mid-write (process killed) recovers with exactly one .eml."""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import time
import unittest
from datetime import timedelta
from unittest import mock

import _tpi_server as srv
from _tpi_outbox_util import OutboxCase, at
from features import outbox

OUTBOX_VIEW = ["ready", "done", "cancelled"]


def _emls(item_id: int) -> list:
    folder = outbox.outbox_dir()
    return sorted(folder.glob(f"*-{item_id:04d}-*.eml*")) if folder.exists() else []


def _set(item_id: int, **cols) -> None:
    con = srv.yhbmail.db()
    con.execute(f"UPDATE outbox SET {', '.join(f'{k}=?' for k in cols)} WHERE id=?", (*cols.values(), item_id))
    con.commit()
    con.close()


def _stale(item_id: int, seconds: float = outbox.RELEASE_STALE + 30) -> None:
    _set(item_id, updated_at=outbox._iso(outbox.now_dt() - timedelta(seconds=seconds)))


class HistoryLimitTest(OutboxCase):
    def add_history(self, n: int = 330) -> None:
        """Old released mail plus discarded confirmations; their release times are all older than new mail,
        but their released_at is later, so only a ready-first ORDER BY keeps the new message on top."""
        base = outbox.now_dt()
        con = srv.yhbmail.db()
        for i in range(n):
            old = base - timedelta(days=1, minutes=i)
            later = outbox._iso(base + timedelta(days=30, minutes=-i))
            state, eml = (("done", f"data/outbox/old-{i}.eml") if i % 3 else ("cancelled", ""))
            con.execute("INSERT INTO outbox(state, created_by, account, to_addr, subject, body, text, mode, "
                        "release_ts, release_at, released_at, eml_path, created_at, updated_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (state, "user", "you@example.com", "maya@example.com", f"Old {i}", "x", "x", "now",
                         old.timestamp(), outbox._iso(old), later if eml else "", eml, later, later))
        con.commit()
        con.close()

    def release_one(self, subject="Fresh one") -> dict:
        now = outbox.now_dt()
        item = self.confirmed("now", now=now, subject=subject)
        self.assertEqual(len(outbox.release_due(now + timedelta(seconds=11))), 1)
        return item

    def test_new_ready_mail_is_listed_above_a_long_history(self):
        self.add_history()
        item = self.release_one()
        listed = outbox.list_items(OUTBOX_VIEW, "en", 200)
        self.assertEqual(len(listed), 200)
        self.assertEqual((listed[0]["id"], listed[0]["state"]), (item["id"], "ready"))
        self.assertNotIn("cancelled", {x["state"] for x in listed}, "discarded confirmations (no .eml) are hidden")
        history = [x["released_at"] for x in listed[1:]]
        self.assertEqual(history, sorted(history, reverse=True), "history is newest first")

    def test_cancelled_after_release_stays_in_the_outbox_view(self):
        a = self.release_one("Alpha")
        self.assertEqual(outbox.cancel(a["id"], "en")[1], 200)
        self.assertIn(a["id"], [x["id"] for x in outbox.list_items(OUTBOX_VIEW, "en")])
        p = self.prepared()
        outbox.discard(p["item"]["id"], "en")
        self.assertNotIn(p["item"]["id"], [x["id"] for x in outbox.list_items(OUTBOX_VIEW, "en")])
        self.assertIn(p["item"]["id"], [x["id"] for x in outbox.list_items(["cancelled"], "en")])

    def test_new_ready_mail_over_http(self):
        self.add_history()
        item = self.release_one()
        status, out = srv.get("/api/outbox/items?state=ready,done,cancelled&limit=200")
        self.assertEqual(status, 200, out)
        self.assertEqual(len(out["items"]), 200)
        self.assertEqual((out["items"][0]["id"], out["items"][0]["state"]), (item["id"], "ready"))


class RescheduleRaceTest(OutboxCase):
    def test_release_after_reschedule_to_the_future_does_nothing(self):
        item = self.confirmed("schedule", send_at=at(5).isoformat())
        self.assertEqual(outbox.reschedule(item["id"], at(30).isoformat(), "en")[1], 200)
        self.assertIsNone(outbox._release(item["id"], at(6)))
        self.assertEqual(outbox._row(item["id"])["state"], "scheduled")
        self.assertEqual(_emls(item["id"]), [])

    def test_ids_picked_before_a_reschedule_are_not_written_early(self):
        item = self.confirmed("schedule", send_at=at(5).isoformat())
        real_release = outbox._release

        def reschedule_first(outbox_id, now):
            self.assertEqual(outbox.reschedule(outbox_id, at(30).isoformat(), "en")[1], 200)
            return real_release(outbox_id, now)

        with mock.patch.object(outbox, "_release", reschedule_first):
            self.assertEqual(outbox.release_due(at(6)), [])
        self.assertEqual(outbox._row(item["id"])["state"], "scheduled")
        self.assertEqual(_emls(item["id"]), [])
        self.assertEqual(len(outbox.release_due(at(31))), 1)


class InterruptedReleaseTest(OutboxCase):
    def stuck(self, mode="now", write_file=False, tmp_file=False) -> dict:
        """A message a dead process left in `releasing`, optionally with its .eml or a partial .eml.tmp."""
        if mode == "now":
            item = self.confirmed("now")
        else:
            item = self.confirmed("schedule", send_at=at(2).isoformat())
        _set(item["id"], state="releasing", release_ts=time.time() - 5)
        _stale(item["id"])
        row = outbox._row(item["id"])
        when, path = outbox._eml_path(row, outbox.now_dt())
        path.parent.mkdir(parents=True, exist_ok=True)
        if write_file:
            path.write_bytes(outbox.build_eml(row, when))
        if tmp_file:
            path.with_suffix(".eml.tmp").write_bytes(b"partial")
        return row

    def test_stuck_before_the_file_is_retried_once(self):
        row = self.stuck(tmp_file=True)
        released = outbox.release_due()
        self.assertEqual([r["id"] for r in released], [row["id"]])
        self.assertEqual(outbox._row(row["id"])["state"], "ready")
        files = _emls(row["id"])
        self.assertEqual([p.suffix for p in files], [".eml"], "one .eml, the partial .tmp is gone")
        events = [h["event"] for h in outbox.history(row["id"])]
        self.assertEqual(events[-2:], ["release_retry", "released"])

    def test_stuck_after_the_file_is_marked_ready_without_a_second_file(self):
        row = self.stuck(write_file=True)
        self.assertEqual(outbox.recover_releasing(), [row["id"]])
        after = outbox._row(row["id"])
        self.assertEqual(after["state"], "ready")
        self.assertEqual(outbox.release_due(), [])
        self.assertEqual(len(_emls(row["id"])), 1)
        self.assertEqual(srv.yhbmail.ROOT / after["eml_path"], _emls(row["id"])[0])

    def test_stuck_scheduled_mail_goes_back_to_the_scheduled_folder(self):
        row = self.stuck("schedule")
        self.assertEqual(outbox.recover_releasing(), [row["id"]])
        self.assertEqual(outbox._row(row["id"])["state"], "scheduled")
        out, status = outbox.cancel(row["id"], "en")
        self.assertEqual(status, 200, out)
        self.assertEqual(outbox.release_due(), [])
        self.assertEqual(_emls(row["id"]), [])

    def test_a_fresh_claim_is_left_alone(self):
        row = self.stuck()
        _set(row["id"], updated_at=outbox._iso(outbox.now_dt()))
        self.assertEqual(outbox.recover_releasing(), [])
        self.assertEqual(outbox._row(row["id"])["state"], "releasing")

    def test_a_late_writer_that_lost_its_claim_leaves_no_file(self):
        item = self.confirmed("schedule", send_at=at(2).isoformat())
        real_build = outbox.build_eml

        def recovered_then_cancelled(row, when):
            _set(item["id"], state="cancelled")
            return real_build(row, when)

        with mock.patch.object(outbox, "build_eml", recovered_then_cancelled):
            self.assertIsNone(outbox._release(item["id"], at(3)))
        self.assertEqual(outbox._row(item["id"])["state"], "cancelled")
        self.assertEqual(_emls(item["id"]), [])

    def test_process_killed_mid_release_recovers_after_restart(self):
        for crash_at in ("build_eml", "transport"):
            with self.subTest(crash_at=crash_at):
                item = self.confirmed("now")
                _set(item["id"], release_ts=time.time() - 5)
                target = "outbox.build_eml" if crash_at == "build_eml" else "outbox.transport.get"
                script = textwrap.dedent(f"""
                    import os, sys
                    sys.path.insert(0, {str(srv.REPO / "server")!r})
                    import features
                    features.load_all()
                    from features import outbox
                    assert outbox._ticker["thread"] is None, "loading features must not start the ticker"
                    {target} = lambda *a, **k: os._exit(17)
                    outbox.release_due()
                    os._exit(0)
                """)
                env = {**os.environ, "OPENINBOX_ROOT": str(srv.ROOT), "OPENINBOX_OUTBOX_TICK": "1"}
                proc = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True, timeout=60)
                self.assertEqual(proc.returncode, 17, proc.stderr.decode()[-2000:])
                self.assertEqual(outbox._row(item["id"])["state"], "releasing")
                self.assertEqual(len(_emls(item["id"])), 1 if crash_at == "transport" else 0)
                self.assertEqual(outbox.release_due(), [], "a fresh claim may still be writing")
                _stale(item["id"])
                status, out = srv.post("/api/outbox/tick", {})
                self.assertEqual(status, 200, out)
                after = outbox._row(item["id"])
                self.assertEqual(after["state"], "ready")
                files = _emls(item["id"])
                self.assertEqual(len(files), 1)
                self.assertEqual(files[0].suffix, ".eml")
                self.assertEqual(srv.yhbmail.ROOT / after["eml_path"], files[0])


if __name__ == "__main__":
    unittest.main()
