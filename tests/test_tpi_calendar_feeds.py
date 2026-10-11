"""Colleague ICS feeds (F17): URL import / refresh through the URL guard, Origin check, and free/busy privacy."""
from __future__ import annotations

import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import _tpi_server as srv
from features import _ics as ics


def vcal(*events: str) -> str:
    return "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//test//EN\r\n" + "".join(events) + "END:VCALENDAR\r\n"


def vevent(uid: str, summary: str, start: str, end: str, extra: str = "") -> str:
    dt = "DTSTART;VALUE=DATE:{}\r\nDTEND;VALUE=DATE:{}\r\n" if len(start) == 8 else \
        "DTSTART;TZID=Asia/Taipei:{}\r\nDTEND;TZID=Asia/Taipei:{}\r\n"
    return (f"BEGIN:VEVENT\r\nUID:{uid}@feeds-test.example.com\r\n" + dt.format(start, end)
            + f"SUMMARY:{summary}\r\n{extra}END:VEVENT\r\n")


ONE = vcal(vevent("a", "Design review", "20270802T100000", "20270802T110000"))
TWO = vcal(vevent("a", "Design review", "20270802T100000", "20270802T110000"),
           vevent("b", "Hiring sync", "20270802T140000", "20270802T150000"))


class IcsHost:
    """A tiny local calendar host: path -> (status, headers, body); every hit is recorded."""

    def __init__(self):
        self.routes: dict[str, tuple[int, dict, bytes]] = {}
        self.hits: list[str] = []
        host = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                host.hits.append(self.path)
                status, headers, body = host.routes.get(self.path, (404, {}, b"missing"))
                self.send_response(status)
                for k, v in headers.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def serve(self, path: str, text: str | bytes, status: int = 200, headers: dict | None = None) -> str:
        body = text.encode() if isinstance(text, str) else text
        self.routes[path] = (status, {"Content-Type": "text/calendar", **(headers or {})}, body)
        return self.base + path

    def redirect(self, path: str, to: str, status: int = 302) -> str:
        return self.serve(path, b"", status, {"Location": to})

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def post_with(path: str, body: dict, headers: dict) -> tuple[int, dict]:
    req = urllib.request.Request(srv.BASE + path, data=json.dumps(body).encode(), method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


class FeedTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.host = IcsHost()

    @classmethod
    def tearDownClass(cls):
        cls.host.close()

    def setUp(self):
        self.host.hits.clear()

    def add(self, body: dict) -> tuple[int, dict]:
        status, out = srv.post("/api/cal/feeds", body)
        if status == 201:
            self.addCleanup(srv.post, "/api/cal/feed/delete", {"id": out["feed"]["id"]})
        return status, out


class UrlImportTest(FeedTestBase):
    def test_private_address_needs_allow_private(self):
        url = self.host.serve("/guarded.ics", ONE)
        status, out = self.add({"url": url, "name": "Guarded"})
        self.assertEqual(status, 502, out)
        self.assertIn("private", out["error"])
        self.assertNotIn("agent.json", out["error"], "the hint points at the feed's own allow_private box")
        self.assertEqual(self.host.hits, [], "nothing is fetched from a private host without allow_private")
        self.assertNotIn("Guarded", [f["name"] for f in srv.get("/api/cal/feeds")[1]["feeds"]])

    def test_import_and_refresh_with_allow_private(self):
        url = self.host.serve("/team.ics", ONE)
        status, out = self.add({"url": url, "name": "Team", "email": "team@feeds-test.example.com",
                                "allow_private": True})
        self.assertEqual(status, 201, out)
        feed = out["feed"]
        self.assertEqual((feed["kind"], feed["url"], feed["events"], feed["allow_private"]), ("url", url, 1, True))
        self.assertEqual(self.host.hits, ["/team.ics"])

        self.host.serve("/team.ics", TWO)
        status, out = srv.post("/api/cal/feed/refresh", {"id": feed["id"]})
        self.assertEqual(status, 200, out)
        self.assertEqual((out["feed"]["events"], out["feed"]["error"]), (2, ""))

        self.host.serve("/team.ics", "gone", status=500)
        status, out = srv.post("/api/cal/feed/refresh", {"id": feed["id"]})
        self.assertEqual(status, 502)
        self.assertIn("HTTP 500", out["error"])
        self.assertEqual(out["feed"]["events"], 2, "a failed refresh keeps the last good copy")

    def test_webcal_scheme_is_fetched_over_https(self):
        status, out = self.add({"url": "webcal://127.0.0.1:1/x.ics", "allow_private": True})
        self.assertEqual(status, 502, out)

    def test_file_feeds_cannot_be_refreshed(self):
        status, out = self.add({"ics": ONE, "filename": "one.ics"})
        self.assertEqual(status, 201, out)
        self.assertEqual(srv.post("/api/cal/feed/refresh", {"id": out["feed"]["id"]})[0], 400)
        self.assertEqual(srv.post("/api/cal/feed/refresh", {"id": 999999})[0], 404)

    def test_redirects_are_followed_and_capped(self):
        target = self.host.serve("/moved.ics", ONE)
        hop = self.host.redirect("/hop2", target, 301)
        url = self.host.redirect("/hop1", hop.replace(self.host.base, ""), 302)
        status, out = self.add({"url": url, "allow_private": True})
        self.assertEqual(status, 201, out)
        self.assertEqual(out["feed"]["events"], 1)
        self.assertEqual(self.host.hits, ["/hop1", "/hop2", "/moved.ics"], "relative Location is resolved")

        self.host.hits.clear()
        loop = self.host.redirect("/loop", "/loop")
        status, out = self.add({"url": loop, "allow_private": True})
        self.assertEqual(status, 502, out)
        self.assertIn("too many redirects", out["error"])
        self.assertEqual(len(self.host.hits), 4)

    def test_two_megabyte_cap(self):
        pad = "X-PAD:" + "x" * 70 + "\r\n"
        body = vcal(vevent("big", "Big", "20270802T100000", "20270802T110000", pad * (ics.MAX_BYTES // len(pad) + 10)))
        self.assertGreater(len(body.encode()), ics.MAX_BYTES)
        status, out = self.add({"url": self.host.serve("/big.ics", body), "allow_private": True})
        self.assertEqual(status, 502, out)
        self.assertIn("2 MB", out["error"])

    def test_bad_scheme_and_non_calendar(self):
        self.assertEqual(self.add({"url": "ftp://example.com/x.ics"})[0], 400)
        status, out = self.add({"url": self.host.serve("/page.html", "<html>hi</html>"), "allow_private": True})
        self.assertEqual(status, 400, out)


class OriginTest(FeedTestBase):
    def test_cross_origin_pages_are_refused(self):
        url = self.host.serve("/intranet.ics", ONE)
        body = {"url": url, "allow_private": True}
        port = srv.SERVER.server_address[1]
        for origin in ("http://evil.example", "null", f"http://127.0.0.1:{port + 1}",
                       f"https://127.0.0.1:{port}", f"http://127.0.0.1.evil.example:{port}"):
            for ctype in ("application/json", "text/plain"):
                status, out = post_with("/api/cal/feeds", body, {"Origin": origin, "Content-Type": ctype})
                self.assertEqual(status, 403, (origin, ctype, out))
        self.assertEqual(self.host.hits, [], "a refused request never reaches the intranet host")

    def test_refresh_is_guarded_too(self):
        status, out = self.add({"url": self.host.serve("/ok.ics", ONE), "allow_private": True})
        self.assertEqual(status, 201, out)
        self.host.hits.clear()
        status, out = post_with("/api/cal/feed/refresh", {"id": out["feed"]["id"]},
                                {"Origin": "http://evil.example", "Content-Type": "text/plain"})
        self.assertEqual(status, 403, out)
        self.assertIn("cross-origin", out["error"])
        self.assertEqual(self.host.hits, [])

    def test_own_ui_origins_are_accepted(self):
        port = srv.SERVER.server_address[1]
        url = self.host.serve("/mine.ics", ONE)
        for origin in (f"http://127.0.0.1:{port}", f"http://localhost:{port}/"):
            status, out = post_with("/api/cal/feeds", {"url": url, "allow_private": True, "lang": "zh-Hant"},
                                    {"Origin": origin, "Content-Type": "application/json"})
            self.assertEqual(status, 201, (origin, out))
            self.addCleanup(srv.post, "/api/cal/feed/delete", {"id": out["feed"]["id"]})
            self.assertEqual(post_with("/api/cal/feed/refresh", {"id": out["feed"]["id"]},
                                       {"Origin": origin, "Content-Type": "application/json"})[0], 200)


class FreeBusyPrivacyTest(FeedTestBase):
    FEED = vcal(
        vevent("pub", "Budget review", "20270802T090000", "20270802T100000"),
        vevent("priv", "Doctor appointment", "20270802T130000", "20270802T140000", "CLASS:PRIVATE\r\n"),
        vevent("conf", "Legal call", "20270802T150000", "20270802T160000", "CLASS:CONFIDENTIAL\r\n"),
        vevent("ooo", "Out of office", "20270803", "20270804"),
        vevent("zh", "特休", "20270804", "20270805"),
        vevent("info", "Company picnic", "20270805", "20270806"),
        vevent("free", "Focus (free)", "20270806T090000", "20270806T170000", "TRANSP:TRANSPARENT\r\n"),
    )

    def freebusy(self):
        status, feed = self.add({"ics": self.FEED, "name": "Privacy Tester", "email": "priv@feeds-test.example.com"})
        self.assertEqual(status, 201, feed)
        status, fb = srv.get(f"/api/cal/freebusy?start=2027-08-02&days=5&tz=Asia/Taipei&me=0"
                             f"&feeds={feed['feed']['id']}&minutes=60")
        self.assertEqual(status, 200, fb)
        self.assertEqual([p["name"] for p in fb["people"]], ["Privacy Tester"])
        return fb, fb["people"][0]["days"]

    def test_private_titles_are_hidden(self):
        fb, days = self.freebusy()
        monday = [(s["start"][11:16], s["end"][11:16], s["title"]) for s in days[0]]
        self.assertEqual(monday, [("09:00", "10:00", "Budget review"), ("13:00", "14:00", ""), ("15:00", "16:00", "")])
        text = json.dumps(fb, ensure_ascii=False)
        self.assertNotIn("Doctor appointment", text)
        self.assertNotIn("Legal call", text)

    def test_out_of_office_all_day_is_busy(self):
        fb, days = self.freebusy()
        for i in (1, 2):
            self.assertEqual([(s["from_min"], s["to_min"]) for s in days[i]], [(0, 1440)], fb["days"][i])
        self.assertEqual(days[3], [], "an all-day event that is not time off counts as free")
        self.assertEqual(days[4], [], "TRANSP:TRANSPARENT is free")
        slot_days = {s["date"] for s in fb["free_slots"]}
        self.assertNotIn("2027-08-03", slot_days)
        self.assertNotIn("2027-08-04", slot_days)
        self.assertIn("2027-08-05", slot_days)


if __name__ == "__main__":
    unittest.main()
