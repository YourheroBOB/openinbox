"""AI booking: the agent tool create_event books locally and writes a .ics invite draft; nothing is sent."""
from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime

import _tpi_server as srv
from features import _ics as ics
from features import calendar as cal

NOW = datetime(2027, 5, 3, 9, 0, tzinfo=ics.get_tz("Asia/Taipei"))  # a Monday
FEED = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:slot-busy@example.com\r\n"
        "DTSTART;TZID=Asia/Taipei:20270504T090000\r\nDTEND;TZID=Asia/Taipei:20270504T110000\r\n"
        "SUMMARY:Board prep\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")


def remove(ev_id: str) -> None:
    srv.post("/api/cal/event/delete", {"id": ev_id, "make_cancel": False})


class ParseAskTest(unittest.TestCase):
    CASES = [
        ("Book 45 min with pat@example.com next Tuesday at 3pm about Q4 roadmap",
         {"attendees": ["pat@example.com"], "date": "2027-05-11", "start_time": "15:00", "duration_minutes": 45,
          "title": "Q4 roadmap"}),
        ("下週二下午三點和 lee@example.com 討論招募 45 分鐘",
         {"attendees": ["lee@example.com"], "date": "2027-05-11", "start_time": "15:00", "duration_minutes": 45,
          "title": "討論招募"}),
        ('明天 10:00-11:30 "Budget review" with pat@example.com and lee@example.com in Room 4',
         {"attendees": ["pat@example.com", "lee@example.com"], "date": "2027-05-04", "start_time": "10:00",
          "end_time": "11:30", "location": "Room 4", "title": "Budget review"}),
        ("Call with lee@example.com on May 20 at 9am New York time for 1 hour",
         {"tz": "America/New_York", "date": "2027-05-20", "start_time": "09:00", "duration_minutes": 60}),
        ("週五下午兩點半 視訊 跟 pat@example.com 對帳",
         {"date": "2027-05-07", "start_time": "14:30", "location": "視訊會議", "title": "對帳"}),
        ("明天下午 3:00 到 4:30 討論預算", {"date": "2027-05-04", "start_time": "15:00", "end_time": "16:30"}),
        ("meet pat@example.com in 3 days 2-3pm", {"date": "2027-05-06", "start_time": "14:00", "end_time": "15:00"}),
        ("2027-06-01 14:00 UTC+2 sync", {"tz": "UTC+02:00", "date": "2027-06-01", "start_time": "14:00"}),
        ("找個時間跟 pat@example.com 開會 30 分鐘", {"date": None, "start_time": None, "duration_minutes": 30}),
    ]

    def test_cases(self):
        for ask, want in self.CASES:
            got = cal.parse_ask(ask, NOW, "zh-Hant")
            for key, value in want.items():
                self.assertEqual(got[key], value, f"{ask!r} -> {key}: {got}")

    def test_nothing_is_invented(self):
        got = cal.parse_ask("lunch", NOW, "en")
        self.assertEqual((got["attendees"], got["date"], got["start_time"], got["tz"]), ([], None, None, None))


class CreateEventToolTest(unittest.TestCase):
    def test_listed_as_agent_tools(self):
        _, tools = srv.get("/api/v1/tools")
        names = [t["name"] for t in tools["tools"]]
        self.assertIn("create_event", names)
        self.assertIn("find_free_time", names)
        desc = next(t["description"] for t in tools["tools"] if t["name"] == "create_event")
        self.assertIn("never sent", desc)
        self.assertIn("絕不寄出", desc)

    def test_explicit_args_through_the_agent_bridge(self):
        status, out = srv.post("/api/v1/tools/create_event", {
            "title": "Vendor check-in", "start": "2027-05-12T10:00", "duration_minutes": 30,
            "attendees": ["pat@example.com"], "lang": "zh-Hant"})
        self.assertEqual(status, 200, out)
        self.addCleanup(remove, out["event"]["id"])
        self.assertTrue(out["ok"])
        self.assertFalse(out["sent"])
        self.assertEqual((out["event"]["source"], out["event"]["my_status"]), ("agent", "organizer"))
        self.assertEqual(out["invite"]["method"], "REQUEST")
        self.assertIn("不會寄出", out["note"])
        self.assertIn("DTSTART:20270512T020000Z", out["invite"]["ics"])

    def test_plain_language_booking(self):
        status, out = srv.post("/api/cal/agent/create_event", {
            "ask": "下週二下午三點和 pat@example.com 討論 Q4 規劃 45 分鐘", "now": NOW.isoformat(), "lang": "zh-Hant"})
        self.assertEqual(status, 201, out)
        self.addCleanup(remove, out["event"]["id"])
        ev = out["event"]
        self.assertEqual((ev["title"], ev["tz"]), ("討論 Q4 規劃", "Asia/Taipei"))
        self.assertEqual((out["event"]["start"], out["event"]["end"]),
                         ("2027-05-11T15:00:00+08:00", "2027-05-11T15:45:00+08:00"))
        self.assertEqual([a["email"] for a in ev["attendees"]], ["pat@example.com"])
        self.assertEqual(out["parsed"]["source"], "heuristic")
        self.assertIn("AI 代訂", ev["description"])
        self.assertFalse(out["invite"]["sent"])

    def test_picks_the_first_slot_everyone_is_free(self):
        status, feed = srv.post("/api/cal/feeds", {"ics": FEED, "name": "Slot Tester", "email": "slot-test@example.com"})
        self.assertEqual(status, 201, feed)
        self.addCleanup(srv.post, "/api/cal/feed/delete", {"id": feed["feed"]["id"]})
        _, prop = srv.post("/api/cal/agent/propose", {"ask": "30 min with slot-test@example.com tomorrow",
                                                      "now": "2027-05-03T08:00"})
        self.assertFalse(prop["sent"])
        self.assertEqual(prop["proposal"]["start"], "2027-05-04T11:00", "09:00-11:00 is busy for the colleague")
        self.assertIn("Slot Tester", prop["slot"]["checked"])
        self.assertEqual(prop["conflicts"], [])

        status, out = srv.post("/api/cal/agent/create_event", {
            "title": "Clash", "start": "2027-05-04T09:30", "attendees": "slot-test@example.com"})
        self.addCleanup(remove, out["event"]["id"])
        self.assertEqual([(c["who"], c["title"]) for c in out["conflicts"]], [("Slot Tester", "Board prep")])

        status, fb = srv.post("/api/v1/tools/find_free_time", {"start": "2027-05-04", "days": 1, "minutes": 60,
                                                               "attendees": ["slot-test@example.com"], "now": "2027-05-03T08:00"})
        self.assertEqual(status, 200, fb)
        self.assertEqual([p["name"] for p in fb["people"]][1:], ["Slot Tester"])
        self.assertEqual(fb["free_slots"][0]["start"], "2027-05-04T11:00", "the 09:30 booking ends at 10:00")

    def test_freebusy_accepts_date_like_the_view(self):
        status, fb = srv.get("/api/cal/freebusy?date=2027-05-04&days=2")
        self.assertEqual(status, 200, fb)
        self.assertEqual((fb["start"], [d["date"] for d in fb["days"]]), ("2027-05-04", ["2027-05-04", "2027-05-05"]))
        self.assertEqual(srv.get("/api/cal/freebusy?date=05/04")[0], 400)

    def test_needs_a_start(self):
        status, out = srv.post("/api/cal/agent/create_event", {"title": "No time"})
        self.assertEqual(status, 400)
        self.assertFalse(out["sent"])
        self.assertEqual(srv.post("/api/cal/agent/propose", {"ask": ""})[0], 400)


class AgentDriverTest(unittest.TestCase):
    """The BYO agent fills the JSON; addresses it makes up are dropped."""

    def use_agent(self, reply: str) -> None:
        path = srv.ROOT / "agent.json"
        script = f"import sys; sys.stdin.read(); print({reply!r})"
        path.write_text(json.dumps({"driver": "cli", "cli": {"command": [sys.executable, "-c", script], "timeout_sec": 20}}))
        self.addCleanup(path.unlink)

    def test_llm_fields_are_used_but_not_trusted(self):
        self.use_agent("Sure! " + json.dumps({"title": "Vendor sync", "date": "2027-05-04", "start": "16:00",
                                              "duration_minutes": 25, "tz": "Asia/Tokyo",
                                              "attendees": ["pat@example.com", "ghost@example.com"]}))
        status, prop = srv.post("/api/cal/agent/propose", {"ask": "set up vendor sync with pat@example.com tomorrow",
                                                           "now": NOW.isoformat()})
        self.assertEqual(status, 200, prop)
        self.assertEqual((prop["source"], prop["driver"]), ("agent", "cli"))
        p = prop["proposal"]
        self.assertEqual((p["title"], p["start"], p["end"], p["tz"]),
                         ("Vendor sync", "2027-05-04T16:00", "2027-05-04T16:25", "Asia/Tokyo"))
        self.assertEqual(p["attendees"], ["pat@example.com"])

    def test_bad_llm_output_falls_back_to_the_heuristic(self):
        self.use_agent("I cannot help with that.")
        _, prop = srv.post("/api/cal/agent/propose", {"ask": "lunch tomorrow at noon", "now": NOW.isoformat()})
        self.assertEqual(prop["source"], "heuristic")
        self.assertIn("did not return JSON", prop["error"])
        self.assertEqual(prop["proposal"]["start"], "2027-05-04T12:00")


if __name__ == "__main__":
    unittest.main()
