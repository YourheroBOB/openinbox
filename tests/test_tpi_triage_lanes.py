"""Super Agent lanes: five core buckets mapped onto Needs You / Upcoming Today / FYI / Other."""
from __future__ import annotations

import unittest

import _tpi_server as srv
import features.triage as triage

LANES = ["needs_you", "upcoming_today", "fyi", "other"]


def ids_by_lane(data):
    return {lane["id"]: [i["id"].rsplit(":", 1)[-1] for i in lane["items"]] for lane in data["lanes"]}


class TriageLanesTest(unittest.TestCase):
    def setUp(self):
        srv.reseed()

    def test_route_registered(self):
        _, feats = srv.get("/api/features")
        self.assertIn("triage", feats["features"])
        self.assertFalse([e for e in feats["errors"] if e["feature"] == "triage"])
        paths = {(r["method"], r["path"]) for r in feats["routes"] if r["feature"] == "triage"}
        for p in ("/api/triage", "/api/triage/digest", "/api/triage/tasks", "/api/triage/history"):
            self.assertIn(("GET", p), paths)

    def test_every_bucket_maps_to_a_lane(self):
        buckets = {t["id"] for t in srv.yhbmail.TAXONOMY}
        self.assertEqual(set(triage.BUCKET_TO_LANE), buckets)
        self.assertEqual(set(triage.BUCKET_TO_LANE.values()), set(LANES))
        self.assertEqual(triage.BUCKET_TO_LANE["worth_a_look"], "fyi")
        self.assertEqual(triage.BUCKET_TO_LANE["upcoming"], "upcoming_today")

    def test_demo_mail_lands_in_four_lanes(self):
        status, data = srv.get("/api/triage?today=2026-09-18")
        self.assertEqual(status, 200)
        self.assertEqual([lane["id"] for lane in data["lanes"]], LANES)
        lanes = ids_by_lane(data)
        self.assertEqual(sorted(lanes["needs_you"]), ["m1", "m2"])
        self.assertEqual(lanes["upcoming_today"], ["m4"])
        self.assertEqual(sorted(lanes["fyi"]), ["m3", "m7", "m8"])
        self.assertEqual(sorted(lanes["other"]), ["m5", "m6"])
        self.assertEqual(sum(data["counts"].values()), srv.N_EMAILS)
        self.assertEqual(data["counts"]["needs_you"], 2)
        self.assertEqual(data["mapping"]["other"], "other")

    def test_high_priority_first_in_fyi(self):
        _, data = srv.get("/api/triage")
        fyi = next(lane for lane in data["lanes"] if lane["id"] == "fyi")
        self.assertEqual([i["bucket"] for i in fyi["items"]], ["worth_a_look", "worth_a_look", "fyi"])
        self.assertEqual(fyi["items"][0]["priority"], "high")

    def test_unread_counted_per_lane(self):
        _, data = srv.get("/api/triage")
        needs = next(lane for lane in data["lanes"] if lane["id"] == "needs_you")
        self.assertEqual(needs["unread"], 2)
        srv.post("/api/read", {"id": "demo:you@example.com:m1", "unread": False})
        _, data = srv.get("/api/triage")
        needs = next(lane for lane in data["lanes"] if lane["id"] == "needs_you")
        self.assertEqual(needs["unread"], 1)
        srv.post("/api/read", {"id": "demo:you@example.com:m1", "unread": True})

    def test_upcoming_today_lists_todays_events(self):
        _, data = srv.get("/api/triage?today=2026-09-18")
        up = next(lane for lane in data["lanes"] if lane["id"] == "upcoming_today")
        self.assertEqual([e["title"] for e in up["events"]], ["Design review with Maya"])
        self.assertEqual([e["id"] for e in up["next_events"]], ["cal:demo-cal-1", "cal:demo-cal-3"])
        self.assertEqual(data["today"], "2026-09-18")
        _, data = srv.get("/api/triage?today=2026-09-20")
        up = next(lane for lane in data["lanes"] if lane["id"] == "upcoming_today")
        self.assertEqual([e["title"] for e in up["events"]], ["Vendor renewal (Byte Cloud)"])
        self.assertTrue(up["events"][0]["all_day"])
        _, data = srv.get("/api/triage?today=2030-01-01")
        up = next(lane for lane in data["lanes"] if lane["id"] == "upcoming_today")
        self.assertEqual(up["events"], [])
        self.assertEqual(up["next_events"], [])

    def test_lane_names_in_both_languages(self):
        _, en = srv.get("/api/triage?lang=en")
        _, zh = srv.get("/api/triage?lang=zh-Hant")
        self.assertEqual([lane["name"] for lane in en["lanes"]], ["Needs You", "Upcoming Today", "FYI", "Other"])
        self.assertEqual([lane["name"] for lane in zh["lanes"]], ["需要你", "今日行程", "僅供參考", "其他"])
        self.assertEqual(zh["lang"], "zh-Hant")

    def test_account_filter(self):
        _, data = srv.get("/api/triage?account=you@example.com")
        self.assertEqual(sum(data["counts"].values()), srv.N_EMAILS)
        _, data = srv.get("/api/triage?account=nobody@example.com")
        self.assertEqual(sum(data["counts"].values()), 0)

    def test_fyi_newsletter_moves_to_other(self):
        row = {"category": "fyi", "from_addr": "Studio Weekly <hello@studio.example>", "subject": "Issue 12"}
        self.assertEqual(triage.lane_of(row), "other")
        row = {"category": "fyi", "from_addr": "Pat <pat@studio.example>", "subject": "Notes from today"}
        self.assertEqual(triage.lane_of(row), "fyi")
        row = {"category": "needs_you", "from_addr": "Weekly <w@studio.example>", "subject": "Weekly sign-off"}
        self.assertEqual(triage.lane_of(row), "needs_you")

    def test_bad_query_values_do_not_crash(self):
        status, data = srv.get("/api/triage?limit=abc&today=not-a-date")
        self.assertEqual(status, 200)
        self.assertEqual(len(data["lanes"]), 4)


if __name__ == "__main__":
    unittest.main()
