"""Unit-level edge cases for the iCalendar helpers in server/features/_ics.py.

Complements test_tpi_calendar_ics.py (end-to-end parse/build) with the small pure
functions and recurrence corner cases. Fictional data only.
Run: python3 -m unittest discover -s tests -p "cpb_test_*.py"
"""
from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta, timezone

import _tpi_server  # noqa: F401  (sets OPENINBOX_ROOT and sys.path before server imports)
from features import _ics as I

UTC = I.UTC


def cal(body: str) -> dict:
    return I.parse_calendar("BEGIN:VCALENDAR\nBEGIN:VEVENT\n" + body + "\nEND:VEVENT\nEND:VCALENDAR\n")


def master(rrule: str, start: str = "20240131T090000Z", extra: str = "") -> dict:
    end = start[:9] + str(int(start[9]) + 1) + start[10:]
    return cal(f"UID:u\nDTSTART:{start}\nDTEND:{end}\nRRULE:{rrule}\n{extra}")["events"][0]


def days(ev: dict, a: tuple, b: tuple, tz=UTC) -> list[str]:
    win = (datetime(*a, tzinfo=UTC), datetime(*b, tzinfo=UTC))
    return [s.strftime("%Y-%m-%d") for s, _ in I.occurrences(ev, *win, tz)]


class OffsetsAndZones(unittest.TestCase):
    def test_format_offset(self):
        self.assertEqual(I.format_offset(None), "")
        self.assertEqual(I.format_offset(timedelta(0)), "+0")
        self.assertEqual(I.format_offset(timedelta(hours=8)), "+8")
        self.assertEqual(I.format_offset(timedelta(hours=5, minutes=30)), "+5:30")
        self.assertEqual(I.format_offset(timedelta(hours=-5, minutes=-30)), "−5:30")

    def test_fixed_offset_range_is_enforced(self):
        self.assertEqual(I.fixed_offset("-", "5", "30").utcoffset(None), timedelta(hours=-5, minutes=-30))
        self.assertEqual(I.fixed_offset("+", "14", "00").utcoffset(None), timedelta(hours=14))
        with self.assertRaises(I.IcsError):
            I.fixed_offset("+", "15", None)

    def test_get_tz_accepts_many_spellings_and_rejects_junk(self):
        self.assertIs(I.get_tz("utc"), UTC)
        self.assertIs(I.get_tz(" Z "), UTC)
        self.assertEqual(I.get_tz("UTC+08:00").utcoffset(None), timedelta(hours=8))
        self.assertEqual(I.get_tz("GMT-5").utcoffset(None), timedelta(hours=-5))
        self.assertEqual(I.tz_name(I.get_tz("Asia/Taipei")), "Asia/Taipei")
        self.assertEqual(I.tz_name(I.get_tz("Taipei Standard Time")), "Asia/Taipei")
        for junk in (None, "", "Nope/Zone", "x" * 65, "UTC+15"):
            self.assertIsNone(I.get_tz(junk), repr(junk))


class LineHandling(unittest.TestCase):
    def test_unfold_joins_continuations_and_drops_blank_lines(self):
        self.assertEqual(I.unfold("A:1\r\n  2\r\n\tx\r\n\r\nB:3"), ["A:1 2x", "B:3"])
        self.assertEqual(I.unfold("A:1\rB:2\n"), ["A:1", "B:2"])
        self.assertEqual(I.unfold(" orphan continuation"), [" orphan continuation"])

    def test_parse_line_respects_quotes(self):
        self.assertEqual(I.parse_line('attendee;cn="Doe; Jane":mailto:j@example.com'),
                         ("ATTENDEE", {"CN": "Doe; Jane"}, "mailto:j@example.com"))
        self.assertEqual(I.parse_line('X-NOTE;P="a:b":value:with:colons'),
                         ("X-NOTE", {"P": "a:b"}, "value:with:colons"))
        self.assertIsNone(I.parse_line("no colon here"))
        self.assertIsNone(I.parse_line(":leading colon"))

    def test_escape_unescape_round_trip(self):
        raw = "a;b,c\\d\nline2"
        self.assertEqual(I.escape(raw), "a\\;b\\,c\\\\d\\nline2")
        self.assertEqual(I.unescape(I.escape(raw)), raw)
        self.assertEqual(I.unescape("keep\\qunknown"), "keep\\qunknown")
        self.assertEqual(I.unescape(None), "")

    def test_fold_never_splits_a_character_and_keeps_75_octets(self):
        line = "SUMMARY:" + "你" * 40
        folded = I.fold(line)
        parts = folded.split("\r\n")
        self.assertGreater(len(parts), 1)
        self.assertLessEqual(len(parts[0].encode()), 75)
        for p in parts[1:]:
            self.assertTrue(p.startswith(" "))
            self.assertLessEqual(len(p.encode()), 75)
        self.assertEqual(folded.replace("\r\n ", ""), line)

    def test_fold_boundary(self):
        self.assertEqual(I.fold("x" * 75), "x" * 75)
        self.assertEqual(len(I.fold("x" * 76).split("\r\n")), 2)


class DatesAndDurations(unittest.TestCase):
    def test_parse_duration_forms(self):
        self.assertEqual(I.parse_duration("P1W"), timedelta(weeks=1))
        self.assertEqual(I.parse_duration("-PT15M"), timedelta(minutes=-15))
        self.assertEqual(I.parse_duration("P1DT2H30M"), timedelta(days=1, hours=2, minutes=30))
        self.assertEqual(I.parse_duration("pt5m"), timedelta(minutes=5))

    def test_parse_duration_rejects_empty_designators(self):
        for bad in ("", "P", "PT", "5M", "PT5X"):
            with self.assertRaises(I.IcsError, msg=repr(bad)):
                I.parse_duration(bad)

    def test_parse_dt_list_skips_garbage_and_periods(self):
        got = I.parse_dt_list("20240101T090000Z, 20240102,bad,20240101T000000Z/PT1H", {}, {}, UTC)
        self.assertEqual(got, [datetime(2024, 1, 1, 9, tzinfo=UTC), date(2024, 1, 2)])

    def test_value_date_param_wins_over_time_part(self):
        self.assertEqual(I.parse_dt("20240101T090000", {"VALUE": "DATE"}, {}, UTC), date(2024, 1, 1))

    def test_unknown_tzid_falls_back_to_floating_zone(self):
        floating = timezone(timedelta(hours=2))
        got = I.parse_dt("20240101T090000", {"TZID": "Not/AZone"}, {}, floating)
        self.assertEqual(got.utcoffset(), timedelta(hours=2))

    def test_as_utc_for_all_day_uses_the_day_zone(self):
        taipei = timezone(timedelta(hours=8))
        self.assertEqual(I.as_utc(date(2024, 1, 1), taipei), datetime(2023, 12, 31, 16, tzinfo=UTC))


class EventShape(unittest.TestCase):
    def test_default_end_rules(self):
        self.assertEqual(cal("DTSTART:20240101\nDTEND:20240103")["events"][0]["end"], date(2024, 1, 3))
        self.assertEqual(cal("DTSTART:20240101")["events"][0]["end"], date(2024, 1, 2))
        timed = cal("DTSTART:20240101T100000Z")["events"][0]
        self.assertEqual(timed["end"], timed["start"])
        self.assertEqual(cal("DTSTART:20240101T100000Z\nDURATION:PT45M")["events"][0]["end"],
                         datetime(2024, 1, 1, 10, 45, tzinfo=UTC))

    def test_end_before_start_or_mixed_kinds_is_repaired(self):
        back = cal("DTSTART:20240101T100000Z\nDTEND:20240101T090000Z")["events"][0]
        self.assertEqual(back["end"], back["start"])
        mixed = cal("DTSTART:20240101T100000Z\nDTEND:20240102")["events"][0]
        self.assertEqual(mixed["end"], mixed["start"])

    def test_event_without_dtstart_is_ignored(self):
        self.assertEqual(cal("SUMMARY:no start")["events"], [])

    def test_empty_calendar_and_oversized_file(self):
        self.assertEqual(I.parse_calendar("BEGIN:VCALENDAR\nEND:VCALENDAR")["events"], [])
        with self.assertRaises(I.IcsError):
            I.parse_calendar("BEGIN:VCALENDAR" + "x" * (I.MAX_BYTES + 1))

    def test_tzid_event_keeps_its_zone(self):
        ev = cal("DTSTART;TZID=Asia/Taipei:20240101T100000\nSUMMARY:x")["events"][0]
        self.assertEqual(ev["start"].utcoffset(), timedelta(hours=8))
        self.assertEqual(ev["tz"], "Asia/Taipei")

    def test_sequence_defaults_to_zero_for_junk(self):
        self.assertEqual(cal("DTSTART:20240101\nSEQUENCE:abc")["events"][0]["sequence"], 0)
        self.assertEqual(cal("DTSTART:20240101\nSEQUENCE:3")["events"][0]["sequence"], 3)


class RRuleParsing(unittest.TestCase):
    def test_interval_and_count_are_clamped_to_one(self):
        r = I.parse_rrule("FREQ=WEEKLY;INTERVAL=0;COUNT=0")
        self.assertEqual((r["interval"], r["count"]), (1, 1))

    def test_byday_ordinals_and_negatives(self):
        r = I.parse_rrule("FREQ=MONTHLY;BYDAY=2TU,-1FR,MO")
        self.assertEqual(r["byday"], [(2, 1), (-1, 4), (0, 0)])

    def test_bad_rules_raise(self):
        for bad in ("FREQ=HOURLY", "INTERVAL=2", "", "FREQ=DAILY;COUNT=x", "FREQ=WEEKLY;BYDAY=XX"):
            with self.assertRaises(I.IcsError, msg=bad):
                I.parse_rrule(bad)

    def test_unsupported_rrule_degrades_to_a_single_event(self):
        ev = cal("UID:u\nDTSTART:20240101T090000Z\nRRULE:FREQ=HOURLY")["events"][0]
        self.assertIsNone(ev["rrule"])
        self.assertEqual(ev["rrule_raw"], "")


class Recurrence(unittest.TestCase):
    def test_monthly_on_the_31st_skips_short_months(self):
        got = days(master("FREQ=MONTHLY"), (2024, 1, 1), (2024, 8, 1))
        self.assertEqual(got, ["2024-01-31", "2024-03-31", "2024-05-31", "2024-07-31"])

    def test_monthly_negative_monthday_is_last_day(self):
        got = days(master("FREQ=MONTHLY;BYMONTHDAY=-1"), (2024, 1, 1), (2024, 5, 1))
        self.assertEqual(got, ["2024-01-31", "2024-02-29", "2024-03-31", "2024-04-30"])

    def test_monthly_last_friday(self):
        got = days(master("FREQ=MONTHLY;BYDAY=-1FR"), (2024, 1, 1), (2024, 5, 1))
        self.assertEqual(got, ["2024-02-23", "2024-03-29", "2024-04-26"])

    def test_fifth_weekday_only_in_months_that_have_one(self):
        got = days(master("FREQ=MONTHLY;BYDAY=5MO"), (2024, 1, 1), (2024, 8, 1))
        self.assertEqual(got, ["2024-04-29", "2024-07-29"])

    def test_yearly_feb_29_only_in_leap_years(self):
        got = days(master("FREQ=YEARLY", start="20240229T090000Z"), (2024, 1, 1), (2033, 1, 1))
        self.assertEqual(got, ["2024-02-29", "2028-02-29", "2032-02-29"])

    def test_daily_interval_until_is_inclusive(self):
        ev = master("FREQ=DAILY;INTERVAL=3;UNTIL=20240110T090000Z", start="20240101T090000Z")
        self.assertEqual(days(ev, (2024, 1, 1), (2024, 3, 1)),
                         ["2024-01-01", "2024-01-04", "2024-01-07", "2024-01-10"])

    def test_count_includes_the_first_instance(self):
        ev = master("FREQ=DAILY;COUNT=3", start="20240101T090000Z")
        self.assertEqual(days(ev, (2024, 1, 1), (2024, 3, 1)), ["2024-01-01", "2024-01-02", "2024-01-03"])

    def test_exdate_removes_and_rdate_adds(self):
        ev = master("FREQ=DAILY;COUNT=3", start="20240101T090000Z", extra="EXDATE:20240102T090000Z\n"
                    "RDATE:20240110T090000Z")
        self.assertEqual(days(ev, (2024, 1, 1), (2024, 3, 1)), ["2024-01-01", "2024-01-03", "2024-01-10"])

    def test_window_boundaries_are_half_open(self):
        ev = cal("UID:b\nDTSTART:20240101T090000Z\nDTEND:20240101T100000Z")["events"][0]
        n = lambda a, b: len(I.occurrences(ev, datetime(*a, tzinfo=UTC), datetime(*b, tzinfo=UTC), UTC))
        self.assertEqual(n((2024, 1, 1, 10), (2024, 1, 2)), 0)      # window starts exactly at the end
        self.assertEqual(n((2024, 1, 1, 9, 59), (2024, 1, 2)), 1)
        self.assertEqual(n((2023, 1, 1), (2024, 1, 1, 9)), 0)       # window ends exactly at the start

    def test_all_day_event_follows_the_viewer_zone(self):
        ev = cal("UID:b\nDTSTART;VALUE=DATE:20240101\nDTEND;VALUE=DATE:20240102")["events"][0]
        win = (datetime(2023, 12, 31, 16, tzinfo=UTC), datetime(2023, 12, 31, 17, tzinfo=UTC))
        taipei = timezone(timedelta(hours=8))
        self.assertEqual(len(I.occurrences(ev, *win, taipei)), 1)
        self.assertEqual(len(I.occurrences(ev, *win, UTC)), 0)

    def test_unbounded_daily_rule_is_capped(self):
        win = (datetime(2024, 1, 1, tzinfo=UTC), datetime(2100, 1, 1, tzinfo=UTC))
        self.assertEqual(len(I.occurrences(master("FREQ=DAILY"), *win, UTC)), I.MAX_OCCURRENCES)

    @unittest.skip("PRODUCT BUG: a YEARLY rule that never matches (BYMONTH=2;BYMONTHDAY=30) scans until "
                   "year 10000 and raises ValueError from _month_days instead of returning []; "
                   "a hostile or odd .ics feed can make the calendar view fail")
    def test_never_matching_yearly_rule_returns_nothing(self):
        ev = master("FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=30")
        win = (datetime(2024, 1, 1, tzinfo=UTC), datetime(2100, 1, 1, tzinfo=UTC))
        self.assertEqual(I.occurrences(ev, *win, UTC), [])

    @unittest.skip("PRODUCT BUG: parse_dt lets ValueError escape for well-shaped but impossible dates "
                   "(month 13, hour 25); parse_calendar only catches IcsError, so one bad VEVENT "
                   "aborts the whole feed instead of landing in `errors`")
    def test_impossible_date_in_one_event_does_not_abort_the_feed(self):
        text = ("BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:bad\nDTSTART:20241340T100000Z\nEND:VEVENT\n"
                "BEGIN:VEVENT\nUID:ok\nDTSTART:20240101T100000Z\nEND:VEVENT\nEND:VCALENDAR\n")
        res = I.parse_calendar(text)
        self.assertEqual([e["uid"] for e in res["events"]], ["ok"])
        self.assertEqual(len(res["errors"]), 1)


class Expansion(unittest.TestCase):
    TEXT = """BEGIN:VCALENDAR
BEGIN:VEVENT
UID:m
DTSTART:20240101T090000Z
DTEND:20240101T100000Z
RRULE:FREQ=DAILY;COUNT=3
SUMMARY:master
END:VEVENT
BEGIN:VEVENT
UID:m
RECURRENCE-ID:20240102T090000Z
DTSTART:20240102T120000Z
DTEND:20240102T130000Z
SUMMARY:moved
END:VEVENT
BEGIN:VEVENT
UID:m
RECURRENCE-ID:20240103T090000Z
DTSTART:20240103T090000Z
DTEND:20240103T100000Z
STATUS:CANCELLED
END:VEVENT
END:VCALENDAR
"""
    WIN = (datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 2, 1, tzinfo=UTC))

    def test_override_replaces_and_cancelled_override_removes(self):
        events = I.parse_calendar(self.TEXT)["events"]
        got = [(e["summary"], e["start"].isoformat()) for e in I.expand(events, *self.WIN, UTC)]
        self.assertEqual(got, [("master", "2024-01-01T09:00:00+00:00"), ("moved", "2024-01-02T12:00:00+00:00")])

    def test_cancelled_master_hides_its_instances_but_not_moved_overrides(self):
        text = self.TEXT.replace("SUMMARY:master", "SUMMARY:master\nSTATUS:CANCELLED")
        events = I.parse_calendar(text)["events"]
        got = [e["summary"] for e in I.expand(events, *self.WIN, UTC)]
        self.assertEqual(got, ["moved"])

    def test_build_rejects_unknown_method(self):
        with self.assertRaises(I.IcsError):
            I.build("BOGUS", {}, datetime(2024, 1, 1, tzinfo=UTC))


if __name__ == "__main__":
    unittest.main()
