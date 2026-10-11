"""Calendar week / month views: ranges, titles, extra time-zone columns, event placement and settings."""
from __future__ import annotations

import unittest

import _tpi_server as srv


def view(**q) -> dict:
    qs = "&".join(f"{k}={v}" for k, v in q.items())
    status, data = srv.get(f"/api/cal/view?{qs}")
    assert status == 200, data
    return data


def day_of(data: dict, iso: str) -> dict:
    return next(d for d in data["days"] if d["date"] == iso)


def titles(day: dict) -> list[str]:
    return [e["title"] for e in day["all_day"] + day["timed"]]


class WeekViewTest(unittest.TestCase):
    def test_range_title_and_days(self):
        en = view(view="week", date="2026-09-16")
        self.assertEqual((en["start"], en["end"]), ("2026-09-14", "2026-09-21"))
        self.assertEqual(en["title"], "Sep 14 – 20, 2026")
        self.assertEqual([d["weekday"] for d in en["days"]], ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
        self.assertEqual((en["prev"], en["next"]), ("2026-09-13", "2026-09-21"))
        zh = view(view="week", date="2026-09-16", lang="zh-Hant")
        self.assertEqual(zh["title"], "2026 年 9 月 14 日 – 20 日")
        self.assertEqual(zh["days"][0]["weekday"], "週一")
        sunday = view(view="week", date="2026-09-16", week_start=0)
        self.assertEqual(sunday["start"], "2026-09-13")
        self.assertEqual(view(view="week", date="2026-12-30")["title"], "Dec 28, 2026 – Jan 3, 2027")

    def test_extra_time_zone_columns(self):
        d = view(view="week", date="2026-09-16")
        self.assertEqual([z["tz"] for z in d["zones"]], ["Asia/Taipei", "America/New_York", "Europe/London"])
        self.assertEqual([z["offset"] for z in d["zones"]], ["UTC+8", "UTC−4", "UTC+1"])
        nine = d["hours"][9]["labels"]
        self.assertEqual([(x["label"], x["shift"]) for x in nine], [("09:00", 0), ("21:00", -1), ("02:00", 0)])
        winter = view(view="week", date="2026-11-04")
        self.assertEqual([z["offset"] for z in winter["zones"]], ["UTC+8", "UTC−5", "UTC"],
                         "zone headers follow DST for the shown week")
        custom = view(view="week", date="2026-09-16", extra="Asia/Tokyo,Australia/Sydney,Mars/Base")
        self.assertEqual([z["tz"] for z in custom["zones"]], ["Asia/Taipei", "Asia/Tokyo", "Australia/Sydney"])

    def test_events_are_placed_in_the_primary_zone(self):
        d = view(view="week", date="2026-09-16")
        thu = day_of(d, "2026-09-17")
        office = next(e for e in thu["timed"] if e["title"].startswith("Northwind partner office hours"))
        self.assertEqual((office["top"], office["bottom"], office["time_label"]), (480, 540, "08:00"),
                         "20:00 in New York is 08:00 the next day in Taipei")
        self.assertEqual(office["tz"], "America/New_York")
        self.assertIn("Vendor renewal (Byte Cloud)", [e["title"] for e in day_of(d, "2026-09-20")["all_day"]])
        self.assertIn("Weekly planning", titles(day_of(d, "2026-09-14")))
        ny = view(view="week", date="2026-09-16", tz="America/New_York")
        wed = day_of(ny, "2026-09-16")
        office = next(e for e in wed["timed"] if e["title"].startswith("Northwind partner office hours"))
        self.assertEqual(office["time_label"], "20:00")

    def test_rsvp_status_on_every_item(self):
        d = view(view="week", date="2026-09-16")
        status = {e["title"]: e["my_status"] for day in d["days"] for e in day["all_day"] + day["timed"]}
        self.assertEqual(status["Weekly planning"], "organizer")
        self.assertEqual(status["Byte Cloud renewal walkthrough"], "declined")
        self.assertEqual(status["Northwind partner office hours (New York)"], "tentative")
        self.assertIn(status["Design review with Maya"], ("needs-action", "accepted", "tentative", "declined"))
        zh = view(view="week", date="2026-09-16", lang="zh-Hant")
        labels = {e["title"]: e["my_status_label"] for day in zh["days"] for e in day["timed"]}
        self.assertEqual(labels["Byte Cloud renewal walkthrough"], "已婉拒")

    def test_today_marker(self):
        d = view(view="week", date="2026-09-16", today="2026-09-16T10:30")
        self.assertEqual(d["now"], {"date": "2026-09-16", "minute": 630})
        self.assertEqual([x["date"] for x in d["days"] if x["is_today"]], ["2026-09-16"])

    def test_overlaps_get_columns_and_overnight_events_split(self):
        made = []
        for title, start, end in (("Layout A", "2027-03-02T10:00", "2027-03-02T11:00"),
                                  ("Layout B", "2027-03-02T10:30", "2027-03-02T11:30"),
                                  ("Layout late", "2027-03-03T23:00", "2027-03-04T01:00")):
            status, out = srv.post("/api/cal/event", {"title": title, "start": start, "end": end, "tz": "Asia/Taipei"})
            self.assertEqual(status, 201, out)
            made.append(out["event"]["id"])
        self.addCleanup(lambda: [srv.post("/api/cal/event/delete", {"id": i}) for i in made])
        d = view(view="week", date="2027-03-02")
        tue = {e["title"]: e for e in day_of(d, "2027-03-02")["timed"] if e["title"].startswith("Layout")}
        self.assertEqual({(e["col"], e["ncols"]) for e in tue.values()}, {(0, 2), (1, 2)})
        wed = next(e for e in day_of(d, "2027-03-03")["timed"] if e["title"] == "Layout late")
        thu = next(e for e in day_of(d, "2027-03-04")["timed"] if e["title"] == "Layout late")
        self.assertEqual((wed["top"], wed["bottom"], wed["continues_after"]), (1380, 1440, True))
        self.assertEqual((thu["top"], thu["bottom"], thu["continues_before"]), (0, 60, True))


class MonthViewTest(unittest.TestCase):
    def test_grid_and_recurring_events(self):
        d = view(view="month", date="2026-09-10")
        self.assertEqual((d["start"], d["end"], len(d["days"])), ("2026-08-31", "2026-10-05", 35))
        self.assertEqual(d["title"], "September 2026")
        self.assertFalse(day_of(d, "2026-08-31")["in_month"])
        self.assertTrue(day_of(d, "2026-09-30")["in_month"])
        mondays = [day["date"] for day in d["days"] if any(i["title"] == "Weekly planning" for i in day["items"])]
        self.assertEqual(mondays, ["2026-09-14", "2026-09-21", "2026-09-28"])
        self.assertEqual((d["prev"], d["next"]), ("2026-08-01", "2026-10-01"))
        zh = view(view="month", date="2026-09-10", lang="zh-Hant")
        self.assertEqual(zh["title"], "2026 年 9 月")
        self.assertEqual(len(view(view="month", date="2026-11-10")["days"]) % 7, 0)

    def test_bad_params(self):
        self.assertEqual(srv.get("/api/cal/view?view=year")[0], 400)
        self.assertEqual(srv.get("/api/cal/view?view=week&date=soon")[0], 400)


class SettingsTest(unittest.TestCase):
    def setUp(self):
        _, self.before = srv.get("/api/cal/settings")
        self.addCleanup(srv.post, "/api/cal/settings", {k: self.before[k] for k in
                                                         ("tz", "extra_tzs", "week_start", "view")})

    def test_defaults_and_choices(self):
        s = self.before
        self.assertEqual(s["tz"], "Asia/Taipei")
        self.assertLessEqual(len(s["extra_tzs"]), 3)
        self.assertIn("America/New_York", s["timezones"])
        self.assertEqual(s["statuses"], ["accepted", "tentative", "declined", "needs-action"])
        _, zones = srv.get("/api/cal/timezones")
        self.assertIn("Europe/Berlin", zones["all"])

    def test_save_and_validate(self):
        status, s = srv.post("/api/cal/settings", {"tz": "Europe/Berlin", "extra_tzs": "Asia/Tokyo, UTC",
                                                   "week_start": 0, "view": "month"})
        self.assertEqual(status, 200, s)
        self.assertEqual((s["tz"], s["extra_tzs"], s["week_start"], s["view"]),
                         ("Europe/Berlin", ["Asia/Tokyo", "UTC"], 0, "month"))
        d = view(view="week", date="2026-09-16")
        self.assertEqual(d["start"], "2026-09-13")
        self.assertEqual([z["tz"] for z in d["zones"]], ["Europe/Berlin", "Asia/Tokyo", "UTC"])
        for bad in ({"tz": "Mars/Base"}, {"extra_tzs": ["UTC", "Asia/Tokyo", "Asia/Seoul", "Europe/Paris"]},
                    {"extra_tzs": ["Nowhere/City"]}, {"week_start": 3}, {"view": "year"},
                    {"work_start": 18, "work_end": 9}):
            self.assertEqual(srv.post("/api/cal/settings", bad)[0], 400, bad)


if __name__ == "__main__":
    unittest.main()
