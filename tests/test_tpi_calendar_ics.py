"""Calendar ICS engine: parsing, time zones, recurrence expansion, free/busy periods and invite drafts."""
from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import _tpi_server  # noqa: F401  (sets OPENINBOX_ROOT before server modules import)
from features import _ics as ics

REPO = Path(__file__).resolve().parents[1]
TPE = ics.get_tz("Asia/Taipei")
UTC = timezone.utc


def window(d1: date, d2: date):
    return datetime(d1.year, d1.month, d1.day, tzinfo=TPE), datetime(d2.year, d2.month, d2.day, tzinfo=TPE)


def fixture(name: str) -> dict:
    return ics.parse_calendar((REPO / "fixtures" / "ics" / name).read_text(), TPE)


def local_starts(instances) -> list[str]:
    return [i["start"].astimezone(TPE).strftime("%m-%d %H:%M") if isinstance(i["start"], datetime)
            else i["start"].isoformat() for i in instances]


class TimeZoneTest(unittest.TestCase):
    def test_names_offsets_and_windows_ids(self):
        self.assertEqual(ics.tz_name(ics.get_tz("America/New_York")), "America/New_York")
        self.assertEqual(ics.tz_name(ics.get_tz("Taipei Standard Time")), "Asia/Taipei")
        self.assertIs(ics.get_tz("UTC"), UTC)
        self.assertEqual(ics.get_tz("UTC+05:30").utcoffset(None), timedelta(hours=5, minutes=30))
        self.assertEqual(ics.get_tz("GMT-3").utcoffset(None), timedelta(hours=-3))
        for bad in ("", "Mars/Olympus", "UTC+15", "x" * 80, None):
            self.assertIsNone(ics.get_tz(bad), bad)

    def test_unknown_tzid_falls_back_to_vtimezone_offset(self):
        text = ("BEGIN:VCALENDAR\r\nBEGIN:VTIMEZONE\r\nTZID:Custom Office Zone\r\nBEGIN:STANDARD\r\n"
                "DTSTART:19700101T000000\r\nTZOFFSETFROM:+0900\r\nTZOFFSETTO:+0900\r\nEND:STANDARD\r\n"
                "END:VTIMEZONE\r\nBEGIN:VEVENT\r\nUID:a@example.com\r\n"
                "DTSTART;TZID=\"Custom Office Zone\":20260915T100000\r\n"
                "DTEND;TZID=\"Custom Office Zone\":20260915T110000\r\nSUMMARY:x\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
        ev = ics.parse_calendar(text, TPE)["events"][0]
        self.assertEqual(ev["start"].astimezone(UTC), datetime(2026, 9, 15, 1, 0, tzinfo=UTC))


class ParseTest(unittest.TestCase):
    def test_folding_escapes_params_and_people(self):
        text = ("BEGIN:VCALENDAR\nX-WR-CALNAME:Demo\\, team\nMETHOD:REQUEST\nBEGIN:VEVENT\nUID:u1@example.com\n"
                "DTSTART:20260915T020000Z\nDURATION:PT45M\nSUMMARY:Plan\\; review\\, Q4\\nsecond line\n"
                "DESCRIPTION:long text that is \n folded across lines\n"
                "ORGANIZER;CN=\"Pat: Example\":mailto:PAT@example.com\n"
                "ATTENDEE;CN=Lee Sample;PARTSTAT=TENTATIVE:mailto:lee@example.com\n"
                "ATTENDEE:mailto:you@example.com\nCLASS:PRIVATE\nEND:VEVENT\nEND:VCALENDAR\n")
        cal = ics.parse_calendar(text, TPE)
        self.assertEqual((cal["name"], cal["method"]), ("Demo, team", "REQUEST"))
        ev = cal["events"][0]
        self.assertEqual(ev["summary"], "Plan; review, Q4\nsecond line")
        self.assertEqual(ev["description"], "long text that is folded across lines")
        self.assertEqual(ev["end"] - ev["start"], timedelta(minutes=45))
        self.assertEqual(ev["organizer"], {"email": "pat@example.com", "name": "Pat: Example",
                                           "status": "NEEDS-ACTION", "role": "REQ-PARTICIPANT"})
        self.assertEqual([(a["email"], a["status"]) for a in ev["attendees"]],
                         [("lee@example.com", "TENTATIVE"), ("you@example.com", "NEEDS-ACTION")])
        self.assertEqual(ev["class"], "PRIVATE")

    def test_all_day_and_floating_times(self):
        text = ("BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:d@example.com\nDTSTART;VALUE=DATE:20260921\nSUMMARY:Off\n"
                "END:VEVENT\nBEGIN:VEVENT\nUID:f@example.com\nDTSTART:20260921T090000\nDTEND:20260921T100000\n"
                "SUMMARY:Floating\nEND:VEVENT\nEND:VCALENDAR\n")
        day, floating = ics.parse_calendar(text, TPE)["events"]
        self.assertTrue(day["all_day"])
        self.assertEqual((day["start"], day["end"]), (date(2026, 9, 21), date(2026, 9, 22)))
        self.assertEqual(floating["start"].astimezone(UTC).hour, 1, "floating time is read in the given zone")

    def test_rejects_non_calendars(self):
        for text in ("hello", "BEGIN:VEVENT\nEND:VEVENT", "x" * (ics.MAX_BYTES + 10)):
            with self.assertRaises(ics.IcsError):
                ics.parse_calendar(text)

    def test_bad_components_are_reported_not_fatal(self):
        text = ("BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:bad@example.com\nDTSTART:2026-09-15\nEND:VEVENT\n"
                "BEGIN:VEVENT\nUID:ok@example.com\nDTSTART:20260915T020000Z\nSUMMARY:ok\nEND:VEVENT\nEND:VCALENDAR\n")
        cal = ics.parse_calendar(text)
        self.assertEqual([e["uid"] for e in cal["events"]], ["ok@example.com"])
        self.assertEqual(len(cal["errors"]), 1)


class RecurrenceTest(unittest.TestCase):
    def test_colleague_feed_with_dst_zone_exdate_and_override(self):
        cal = fixture("pat-example.ics")
        ws, we = window(date(2026, 9, 14), date(2026, 9, 23))
        inst = ics.expand(cal["events"], ws, we, TPE)
        starts = list(zip(local_starts(inst), [i["summary"] for i in inst]))
        self.assertIn(("09-14 21:00", "Team standup"), starts, "09:00 EDT is 21:00 in Taipei")
        self.assertIn(("09-15 10:00", "APAC review (moved)"), starts, "RECURRENCE-ID override replaces the slot")
        self.assertNotIn(("09-17 09:00", "APAC review (late shift)"), starts, "EXDATE removes the 16 Sep slot")
        self.assertIn(("09-22 09:00", "APAC review (late shift)"), starts)
        self.assertIn(("09-18 10:00", "Customer call"), starts)
        self.assertNotIn("Cancelled sync", [s for _, s in starts])
        self.assertIn(("2026-09-21", "Out of office"), starts)
        call = next(i for i in inst if i["summary"] == "Customer call")
        self.assertEqual(call["end"] - call["start"], timedelta(minutes=90))

    def test_windows_tzid_daily_byday(self):
        cal = fixture("lee-example.ics")
        ws, we = window(date(2026, 9, 14), date(2026, 9, 21))
        lunches = [i for i in ics.expand(cal["events"], ws, we, TPE) if i["summary"] == "Lunch"]
        self.assertEqual(local_starts(lunches), [f"09-{d} 12:00" for d in (14, 15, 16, 17, 18)])

    def test_count_until_interval_monthly(self):
        def run(rule, start=datetime(2026, 1, 31, 9, 0, tzinfo=TPE), end=date(2027, 1, 1)):
            ev = {"start": start, "end": start + timedelta(hours=1), "rrule": ics.parse_rrule(rule),
                  "exdates": [], "rdates": []}
            if ev["rrule"].get("until_raw"):
                ev["rrule"]["until"] = ics.parse_dt(ev["rrule"]["until_raw"], {}, {}, TPE)
            return [s.astimezone(TPE).date().isoformat() for s, _ in
                    ics.occurrences(ev, start - timedelta(days=1), datetime(end.year, end.month, end.day, tzinfo=TPE), TPE)]

        self.assertEqual(run("FREQ=DAILY;COUNT=3"), ["2026-01-31", "2026-02-01", "2026-02-02"])
        self.assertEqual(run("FREQ=WEEKLY;INTERVAL=2;UNTIL=20260302T000000Z"),
                         ["2026-01-31", "2026-02-14", "2026-02-28"])
        self.assertEqual(run("FREQ=MONTHLY;COUNT=4"), ["2026-01-31", "2026-03-31", "2026-05-31", "2026-07-31"],
                         "months without a 31st are skipped")
        self.assertEqual(run("FREQ=MONTHLY;BYDAY=-1FR;COUNT=3"), ["2026-02-27", "2026-03-27", "2026-04-24"])
        self.assertEqual(run("FREQ=MONTHLY;BYMONTHDAY=-1;COUNT=2"), ["2026-01-31", "2026-02-28"])
        self.assertEqual(run("FREQ=YEARLY;COUNT=2", end=date(2028, 6, 1)), ["2026-01-31", "2027-01-31"])
        with self.assertRaises(ics.IcsError):
            ics.parse_rrule("FREQ=SECONDLY")
        with self.assertRaises(ics.IcsError):
            ics.parse_rrule("FREQ=WEEKLY;BYDAY=XX")

    def test_vfreebusy_periods(self):
        fb = fixture("lee-example.ics")["freebusy"]
        self.assertEqual(fb, [(datetime(2026, 9, 17, 1, 0, tzinfo=UTC), datetime(2026, 9, 17, 3, 0, tzinfo=UTC), "BUSY")],
                         "FBTYPE=FREE periods are dropped, durations are applied")


class BuildTest(unittest.TestCase):
    EV = {"uid": "draft-1@toopowerinbox.example", "sequence": 2, "title": "Roadmap; Q4, 回顧與規劃 " * 4,
          "start": datetime(2026, 9, 15, 15, 0, tzinfo=TPE), "end": datetime(2026, 9, 15, 15, 45, tzinfo=TPE),
          "all_day": False, "location": "Room 3", "description": "line one\nline two",
          "organizer": {"email": "you@example.com", "name": "Alex Chen"},
          "attendees": [{"email": "pat@example.com", "name": "Pat, Example", "status": "NEEDS-ACTION",
                         "role": "REQ-PARTICIPANT"}],
          "rrule_raw": "FREQ=WEEKLY;BYDAY=TU"}

    def test_request_is_valid_crlf_folded_and_round_trips(self):
        text = ics.build("REQUEST", self.EV, datetime(2026, 9, 1, tzinfo=UTC))
        self.assertTrue(text.endswith("\r\n"))
        self.assertNotIn("\n", text.replace("\r\n", ""))
        for line in text.split("\r\n"):
            self.assertLessEqual(len(line.encode("utf-8")), 75, line)
        for needle in ("METHOD:REQUEST", "DTSTART:20260915T070000Z", "DTEND:20260915T074500Z", "SEQUENCE:2",
                       "RRULE:FREQ=WEEKLY;BYDAY=TU", "STATUS:CONFIRMED", "DESCRIPTION:line one\\nline two"):
            self.assertIn(needle, text.replace("\r\n ", ""))
        cal = ics.parse_calendar(text)
        ev = cal["events"][0]
        self.assertEqual(ev["summary"], self.EV["title"].strip())
        self.assertEqual(ev["start"], self.EV["start"])
        self.assertEqual(ev["attendees"][0]["name"], "Pat, Example")
        self.assertEqual(ev["organizer"]["email"], "you@example.com")
        self.assertTrue(ev["rrule"])

    def test_cancel_and_reply(self):
        cancel = ics.build("CANCEL", self.EV, datetime(2026, 9, 1, tzinfo=UTC))
        self.assertIn("METHOD:CANCEL", cancel)
        self.assertIn("STATUS:CANCELLED", cancel)
        reply = ics.build("REPLY", {**self.EV, "reply_as": {"email": "you@example.com", "name": "", "status": "ACCEPTED"}},
                          datetime(2026, 9, 1, tzinfo=UTC))
        self.assertIn("ATTENDEE;ROLE=REQ-PARTICIPANT;PARTSTAT=ACCEPTED:mailto:you@example.com", reply)
        self.assertNotIn("pat@example.com", reply)
        self.assertNotIn("RRULE", reply)
        with self.assertRaises(ics.IcsError):
            ics.build("SEND", self.EV, datetime(2026, 9, 1, tzinfo=UTC))

    def test_all_day_and_injection_safe(self):
        ev = {**self.EV, "all_day": True, "start": date(2026, 9, 21), "end": date(2026, 9, 22), "rrule_raw": "",
              "title": "x\r\nATTENDEE:mailto:evil@example.com", "attendees": [],
              "organizer": {"email": "you@example.com", "name": 'A"b;c'}}
        text = ics.build("REQUEST", ev, datetime(2026, 9, 1, tzinfo=UTC))
        self.assertIn("DTSTART;VALUE=DATE:20260921", text)
        self.assertIn("SUMMARY:x\\nATTENDEE:mailto:evil@example.com", text)
        self.assertNotIn("\r\nATTENDEE", text)
        self.assertIn('ORGANIZER;CN="Ab;c":mailto:you@example.com', text)


if __name__ == "__main__":
    unittest.main()
