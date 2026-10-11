"""Local calendar events: create / edit / delete, validation, RSVP state and .ics drafts (never sent)."""
from __future__ import annotations

import unittest

import _tpi_server as srv


def create(body: dict, lang: str = "en"):
    return srv.post("/api/cal/event", {"tz": "Asia/Taipei", "lang": lang, **body})


def delete(event_id: str, **extra):
    return srv.post("/api/cal/event/delete", {"id": event_id, **extra})


def week(date: str) -> list[dict]:
    _, d = srv.get(f"/api/cal/view?view=week&date={date}")
    return [e for day in d["days"] for e in day["all_day"] + day["timed"]]


class CreateEditDeleteTest(unittest.TestCase):
    def test_plain_event_round_trip(self):
        status, out = create({"title": "Dentist", "start": "2027-04-06T15:00", "end": "2027-04-06T16:00",
                              "location": "Clinic"})
        self.assertEqual(status, 201, out)
        ev = out["event"]
        self.addCleanup(delete, ev["id"])
        self.assertTrue(ev["id"].startswith("local:"))
        self.assertEqual((ev["source"], ev["editable"], ev["my_status"]), ("local", True, "organizer"))
        self.assertIsNone(out["invite"], "no attendees, no invite draft")
        self.assertFalse(out["sent"])
        self.assertEqual(ev["start"], "2027-04-06T15:00:00+08:00")
        hit = [e for e in week("2027-04-06") if e["id"] == ev["id"]]
        self.assertEqual([(e["start"], e["end"], e["location"]) for e in hit],
                         [("2027-04-06T15:00", "2027-04-06T16:00", "Clinic")])

        status, edited = create({"id": ev["id"], "title": "Dentist (moved)", "start": "2027-04-07T09:00",
                                 "duration_minutes": 45})
        self.assertEqual(status, 200, edited)
        self.assertEqual(edited["event"]["sequence"], 1)
        hit = [e for e in week("2027-04-06") if e["id"] == ev["id"]]
        self.assertEqual([(e["title"], e["start"], e["end"]) for e in hit],
                         [("Dentist (moved)", "2027-04-07T09:00", "2027-04-07T09:45")])

        _, detail = srv.get(f"/api/cal/event/{ev['id']}")
        self.assertEqual([t["tz"] for t in detail["times"]], ["Asia/Taipei", "America/New_York", "Europe/London"])
        self.assertEqual(detail["times"][1]["text"], "2027-04-06 (Tue) 21:00 – 21:45")
        self.assertEqual(detail["edit"]["start"], "2027-04-07T09:00")

        status, gone = delete(ev["id"])
        self.assertEqual((status, gone["deleted"], gone["invite"]), (200, 1, None))
        self.assertEqual(srv.get(f"/api/cal/event/{ev['id']}")[0], 404)
        self.assertEqual(delete(ev["id"])[0], 404)

    def test_event_in_another_zone_and_all_day(self):
        status, out = create({"title": "NY standup", "start": "2027-04-08T09:00", "end": "2027-04-08T09:15",
                              "tz": "America/New_York"})
        self.assertEqual(status, 201, out)
        self.addCleanup(delete, out["event"]["id"])
        hit = next(e for e in week("2027-04-08") if e["id"] == out["event"]["id"])
        self.assertEqual(hit["start"], "2027-04-08T21:00", "shown in the primary zone")
        status, out = create({"title": "Offsite", "all_day": True, "start": "2027-04-08", "end": "2027-04-10"})
        self.assertEqual(status, 201, out)
        self.addCleanup(delete, out["event"]["id"])
        _, d = srv.get("/api/cal/view?view=week&date=2027-04-08")
        days = [day["date"] for day in d["days"] if any(e["title"] == "Offsite" for e in day["all_day"])]
        self.assertEqual(days, ["2027-04-08", "2027-04-09"])

    def test_repeat(self):
        status, out = create({"title": "Gym", "start": "2027-04-05T07:00", "end": "2027-04-05T08:00",
                              "repeat": "weekdays"})
        self.assertEqual(status, 201, out)
        self.addCleanup(delete, out["event"]["id"])
        self.assertEqual(out["event"]["repeat"], "weekdays")
        self.assertEqual(sum(e["title"] == "Gym" for e in week("2027-04-05")), 5)
        create({"id": out["event"]["id"], "title": "Gym", "start": "2027-04-05T07:00", "end": "2027-04-05T08:00",
                "repeat": ""})
        self.assertEqual(sum(e["title"] == "Gym" for e in week("2027-04-05")), 1)

    def test_validation_is_bilingual(self):
        cases = [({"title": "", "start": "2027-04-06T10:00"}, "title is required", "請填標題"),
                 ({"title": "x", "start": "tomorrow"}, "start must be", "開始時間"),
                 ({"title": "x", "start": "2027-04-06T10:00", "end": "2027-04-06T09:00"}, "end must be after", "結束時間要晚於"),
                 ({"title": "x", "start": "2027-04-06T10:00", "tz": "Mars/Base"}, "unknown time zone", "不認得的時區"),
                 ({"title": "x", "start": "2027-04-01T10:00", "end": "2027-04-30T10:00"}, "limited to 14 days", "最長 14 天"),
                 ({"title": "x", "start": "2027-04-06T10:00", "repeat": "hourly"}, "repeat must be", "重複只能選")]
        for body, en, zh in cases:
            status, out = create(body)
            self.assertEqual(status, 400, body)
            self.assertIn(en, out["error"])
            status, out = create(body, lang="zh-Hant")
            self.assertIn(zh, out["error"])

    def test_synced_events_are_read_only(self):
        status, out = create({"id": "sync:demo-cal-1", "title": "x", "start": "2027-04-06T10:00"})
        self.assertEqual(status, 403)
        self.assertEqual(delete("sync:demo-cal-1")[0], 403)

    def test_local_events_survive_a_cache_clear(self):
        status, out = create({"title": "Keep me", "start": "2027-04-09T10:00"})
        self.addCleanup(delete, out["event"]["id"])
        srv.post("/api/cache/clear", {"reseed": True})
        self.assertEqual(srv.get(f"/api/cal/event/{out['event']['id']}")[0], 200)


class InviteDraftTest(unittest.TestCase):
    def test_request_on_create_update_and_cancel_on_delete(self):
        status, out = create({"title": "Q4 planning", "start": "2027-04-13T15:00", "end": "2027-04-13T15:45",
                              "attendees": "Pat Example <pat@example.com>, lee@example.com, not-an-address"})
        self.assertEqual(status, 201, out)
        ev, inv = out["event"], out["invite"]
        self.addCleanup(delete, ev["id"], make_cancel=False)
        self.assertEqual([a["email"] for a in ev["attendees"]], ["pat@example.com", "lee@example.com"])
        self.assertEqual(ev["rsvp_counts"]["needs-action"], 2)
        self.assertEqual(len(out["warnings"]), 1)
        self.assertEqual((inv["method"], inv["sent"], inv["filename"]), ("REQUEST", False, "Q4-planning.ics"))
        self.assertEqual(inv["recipients"], ["pat@example.com", "lee@example.com"])
        self.assertIn("Nothing is sent", out["note"])

        status, headers, raw = srv.request("GET", inv["url"])
        self.assertEqual(status, 200)
        self.assertIn("text/calendar", headers["Content-Type"])
        text = raw.decode().replace("\r\n ", "")
        for needle in ("METHOD:REQUEST", "DTSTART:20270413T070000Z", "SEQUENCE:0", "SUMMARY:Q4 planning",
                       "ORGANIZER", "mailto:you@example.com", "CN=Pat Example", "RSVP=TRUE:mailto:pat@example.com"):
            self.assertIn(needle, text)

        status, upd = create({"id": ev["id"], "title": "Q4 planning", "start": "2027-04-13T16:00",
                              "end": "2027-04-13T16:45"})
        self.assertEqual(upd["invite"]["sequence"], 1)
        _, listed = srv.get(f"/api/cal/invites?event={ev['id']}")
        self.assertEqual([i["method"] for i in listed["invites"]], ["REQUEST", "REQUEST"])
        self.assertNotIn("ics", listed["invites"][0])

        status, gone = delete(ev["id"])
        self.assertEqual(gone["invite"]["method"], "CANCEL")
        status, _, raw = srv.request("GET", gone["invite"]["url"])
        self.assertIn("STATUS:CANCELLED", raw.decode())
        self.assertIn("SEQUENCE:2", raw.decode())

    def test_invite_can_be_switched_off_and_bad_ids(self):
        status, out = create({"title": "Quiet", "start": "2027-04-13T09:00", "attendees": ["pat@example.com"],
                              "make_invite": False})
        self.addCleanup(delete, out["event"]["id"], make_cancel=False)
        self.assertIsNone(out["invite"])
        self.assertEqual(srv.get("/api/cal/invite/999999.ics")[0], 404)
        self.assertEqual(srv.get("/api/cal/invite/abc")[0], 400)


class RsvpTest(unittest.TestCase):
    def status_of(self, title: str, date: str = "2026-09-16") -> str:
        return next(e["my_status"] for e in week(date) if e["title"] == title)

    def test_rsvp_to_a_synced_invite(self):
        self.addCleanup(srv.post, "/api/cal/rsvp", {"id": "sync:demo-cal-2", "status": "needs-action"})
        status, out = srv.post("/api/cal/rsvp", {"id": "sync:demo-cal-2", "status": "accepted", "make_reply": True})
        self.assertEqual(status, 200, out)
        self.assertEqual(out["my_status"], "accepted")
        self.assertFalse(out["sent"])
        self.assertIn("not notified", out["note"])
        self.assertEqual(out["reply"]["method"], "REPLY")
        self.assertEqual(out["reply"]["recipients"], ["maya@studio.example"])
        self.assertIn("PARTSTAT=ACCEPTED:mailto:you@example.com", out["reply"]["ics"].replace("\r\n ", ""))
        self.assertEqual(self.status_of("Design review with Maya"), "accepted")
        self.assertEqual(out["event"]["rsvp_counts"]["accepted"], 2)
        srv.post("/api/cal/rsvp", {"id": "sync:demo-cal-2", "status": "tentative"})
        self.assertEqual(self.status_of("Design review with Maya"), "tentative")

    def test_rsvp_to_a_local_invite(self):
        title = "Northwind partner office hours (New York)"
        ev_id = next(e["id"] for e in week("2026-09-16") if e["title"] == title)
        self.addCleanup(srv.post, "/api/cal/rsvp", {"id": ev_id, "status": "tentative"})
        status, out = srv.post("/api/cal/rsvp", {"id": ev_id, "status": "declined", "lang": "zh-Hant"})
        self.assertEqual(status, 200, out)
        self.assertIn("不會通知主辦人", out["note"])
        self.assertEqual(self.status_of(title, "2026-09-17"), "declined")
        me = next(a for a in out["event"]["attendees"] if a["me"])
        self.assertEqual((me["status"], me["status_label"]), ("declined", "已婉拒"))

    def test_rsvp_errors(self):
        planning = next(e["id"] for e in week("2026-09-16") if e["title"] == "Weekly planning")
        self.assertEqual(srv.post("/api/cal/rsvp", {"id": planning, "status": "accepted"})[0], 400,
                         "organizers do not RSVP")
        self.assertEqual(srv.post("/api/cal/rsvp", {"id": "sync:demo-cal-2", "status": "maybe-later"})[0], 400)
        self.assertEqual(srv.post("/api/cal/rsvp", {"id": "sync:nope", "status": "accepted"})[0], 404)


class ImportInviteTest(unittest.TestCase):
    ICS = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nMETHOD:{method}\r\nBEGIN:VEVENT\r\nUID:imported-1@example.com\r\n"
           "SEQUENCE:{seq}\r\nDTSTART;TZID=Europe/London:20270414T100000\r\nDTEND;TZID=Europe/London:20270414T110000\r\n"
           "SUMMARY:{title}\r\nORGANIZER;CN=Pat Example:mailto:pat@example.com\r\n"
           "ATTENDEE;PARTSTAT=NEEDS-ACTION:mailto:you@example.com\r\n{status}END:VEVENT\r\nEND:VCALENDAR\r\n")

    def test_request_update_cancel(self):
        status, out = srv.post("/api/cal/import", {"ics": self.ICS.format(method="REQUEST", seq=0, title="Vendor demo", status="")})
        self.assertEqual(status, 200, out)
        self.assertEqual(len(out["created"]), 1)
        ev_id = out["created"][0]
        self.addCleanup(delete, ev_id, make_cancel=False)
        hit = next(e for e in week("2027-04-14") if e["id"] == ev_id)
        self.assertEqual((hit["start"], hit["source"], hit["my_status"]), ("2027-04-14T17:00", "ics", "needs-action"))
        self.assertTrue(hit["can_rsvp"])

        status, out = srv.post("/api/cal/import", {"ics": self.ICS.format(method="REQUEST", seq=1, title="Vendor demo v2", status="")})
        self.assertEqual(out["updated"], [ev_id])
        self.assertIn("Vendor demo v2", [e["title"] for e in week("2027-04-14")])

        status, out = srv.post("/api/cal/import", {"ics": self.ICS.format(method="CANCEL", seq=2, title="Vendor demo v2",
                                                                         status="STATUS:CANCELLED\r\n")})
        self.assertEqual(out["cancelled"], [ev_id])
        self.assertNotIn(ev_id, [e["id"] for e in week("2027-04-14")])

    def test_rejects_garbage(self):
        self.assertEqual(srv.post("/api/cal/import", {"ics": "not a calendar"})[0], 400)
        self.assertEqual(srv.post("/api/cal/import", {})[0], 400)


if __name__ == "__main__":
    unittest.main()
