"""FTS5 index and /api/search over the fictional fixtures (plus temporary fictional CJK mail)."""
from __future__ import annotations

import unittest
from urllib.parse import quote

import _tpi_server as srv
import features.search as search

M = "demo:you@example.com:"
ZH_MAIL = {
    "id": "test:search:zh1", "account": "you@example.com", "platform": "demo",
    "subject": "合約草稿第二版", "snippet": "請確認附件的保密條款。",
    "from_addr": "王小明 <xiaoming@example.com>", "to_addr": "you@example.com, 陳小華 <xiaohua@example.com>",
    "date_raw": "2026-09-10 10:00", "unread": True, "has_attachment": False,
    "body_text": "請確認附件的保密條款，週五前回覆。檔名 draft-v2.pdf",
}


def ids(data):
    return [e["id"].removeprefix(M) for e in data["emails"]]


def find(q, **params):
    extra = "".join(f"&{k}={quote(str(v))}" for k, v in params.items())
    status, data = srv.get(f"/api/search?q={quote(q)}{extra}")
    assert status == 200, data
    return data


def add_zh_mail():
    con = srv.yhbmail.db()
    srv.yhbmail.upsert_email(con, ZH_MAIL)
    con.commit()
    con.close()


def drop_test_mail():
    con = srv.yhbmail.db()
    con.execute("DELETE FROM emails WHERE id LIKE 'test:search:%'")
    con.commit()
    con.close()


class FixtureSearchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        drop_test_mail()
        srv.reseed()

    def test_keywords_use_fts5(self):
        d = find("samira deck")
        self.assertEqual(d["engine"], "fts5")
        self.assertEqual(ids(d), ["m1"])
        self.assertEqual(d["sort"], "relevance")
        self.assertIn("investor call", find("investor")["emails"][0]["highlight"])
        self.assertEqual(ids(find("term sheet")), ["m7"])
        self.assertEqual(ids(find("renew")), ["m8"])

    def test_or_exclude_and_category(self):
        self.assertEqual(sorted(ids(find("receipt OR renewal"))), ["m3", "m8"])
        self.assertEqual(ids(find("unsubscribe -cables")), ["m5"])
        self.assertEqual(sorted(ids(find("newsletter"))), ["m5", "m6"])
        self.assertEqual(sorted(ids(find("unread", category="needs_you"))), ["m1", "m2"])

    def test_sender_attachment_unread(self):
        self.assertEqual(ids(find("from:samira")), ["m1", "m7"])
        d = find("has:attachment")
        self.assertTrue({"m3", "m7"} <= set(ids(d)))
        self.assertTrue(all(e["has_attachment"] for e in d["emails"]))
        self.assertEqual(ids(find("samira with attachments")), ["m7"])
        self.assertEqual(sorted(ids(find("unread from maya"))), ["m4"])
        self.assertNotIn("m3", ids(find("-has:attachment")))

    def test_dates_follow_today_param(self):
        self.assertEqual(len(ids(find("last week", today="2026-09-22"))), 8)
        self.assertEqual(ids(find("last week", today="2026-09-16")), [])
        self.assertEqual(sorted(ids(find("yesterday", today="2026-09-16"))), ["m4", "m5", "m6"])
        self.assertEqual(sorted(ids(find("9月14日"))), ["m7", "m8"])
        self.assertEqual(ids(find("renewal 2026-09-14之後")), ["m8"])

    def test_demo_anchor_is_newest_mail(self):
        d = find("today")
        self.assertEqual((d["anchor"], d["anchor_source"]), ("2026-09-16", "demo"))
        self.assertEqual(sorted(ids(d)), ["m1", "m2", "m3"])

    def test_empty_query_lists_by_date_with_paging(self):
        d = find("", limit=3, offset=3)
        self.assertEqual(d["total"], srv.N_EMAILS)
        self.assertEqual(ids(d), ["m4", "m5", "m6"])
        self.assertEqual(d["sort"], "date")

    def test_explain_and_parse_endpoint(self):
        d = find("上週 Samira 寄來有附件的信", today="2026-09-22", lang="zh-Hant")
        self.assertEqual(ids(d), ["m7"])
        texts = [c["text"] for c in d["explain"]]
        self.assertIn("有附件", texts)
        self.assertTrue(any(t.startswith("寄件人：Samira") for t in texts))
        status, p = srv.get("/api/search/parse?q=" + quote("unread newsletters since Sep 15") + "&today=2026-09-16")
        self.assertEqual(status, 200)
        self.assertEqual(p["canonical"], "after:2026-09-15 is:unread category:other")

    def test_post_and_validation(self):
        status, d = srv.post("/api/search", {"q": "term sheet", "lang": "en"})
        self.assertEqual(status, 200)
        self.assertEqual(ids(d), ["m7"])
        status, d = srv.post("/api/search", {"q": ["nope"]})
        self.assertEqual(status, 400)

    def test_like_fallback_gives_same_answers(self):
        saved = dict(search._index)
        search._index["engine"] = "like"
        try:
            for q in ("term sheet", "from:samira", "has:attachment", "unsubscribe -cables"):
                like = search.run_search(search.parse_query(q))
                self.assertEqual(like["engine"], "like")
                search._index.update(saved)
                fts = search.run_search(search.parse_query(q))
                search._index["engine"] = "like"
                self.assertEqual(sorted(e["id"] for e in like["emails"]),
                                 sorted(e["id"] for e in fts["emails"]), q)
        finally:
            search._index.update(saved)


class IndexMaintenanceTest(unittest.TestCase):
    def setUp(self):
        drop_test_mail()
        self.addCleanup(drop_test_mail)

    def docs(self):
        con = srv.yhbmail.db()
        n = con.execute("SELECT COUNT(*) FROM search_docs").fetchone()[0]
        con.close()
        return n

    def test_chinese_mail_is_indexed_incrementally(self):
        find("")
        add_zh_mail()
        self.assertEqual(ids(find("保密條款")), ["test:search:zh1"])
        self.assertEqual(ids(find("合約")), ["test:search:zh1"])
        self.assertEqual(ids(find("幫我找王小明寄來的合約")), ["test:search:zh1"])
        self.assertEqual(ids(find("約")), ["test:search:zh1"])
        self.assertIn("test:search:zh1", ids(find("有附件")))
        status, st = srv.get("/api/search/status")
        self.assertEqual(status, 200)
        self.assertTrue(st["fresh"])
        self.assertEqual(st["indexed"], st["emails"])

    def test_updated_mail_is_reindexed(self):
        add_zh_mail()
        self.assertEqual(ids(find("保密條款")), ["test:search:zh1"])
        con = srv.yhbmail.db()
        srv.yhbmail.upsert_email(con, {**ZH_MAIL, "subject": "報價單", "snippet": "新版報價",
                                       "body_text": "新版報價", "date_raw": "2026-09-10 10:01"})
        con.execute("UPDATE emails SET synced_at='2099-01-01T00:00:00+08:00' WHERE id=?", (ZH_MAIL["id"],))
        con.commit()
        con.close()
        self.assertEqual(ids(find("保密條款")), [])
        self.assertEqual(ids(find("報價")), ["test:search:zh1"])

    def test_deleting_mail_drops_its_index_row(self):
        add_zh_mail()
        find("合約")
        before = self.docs()
        drop_test_mail()
        self.assertEqual(self.docs(), before - 1)

    def test_cache_clear_empties_index_and_reindex_restores(self):
        find("")
        status, _ = srv.post("/api/cache/clear", {})
        self.assertEqual(status, 200)
        try:
            self.assertEqual(self.docs(), 0)
            self.assertEqual(find("term sheet")["total"], 0)
        finally:
            srv.reseed()
        status, out = srv.post("/api/search/reindex")
        self.assertEqual(status, 200)
        self.assertEqual(out["indexed"], srv.N_EMAILS)
        self.assertEqual(ids(find("term sheet")), ["m7"])


if __name__ == "__main__":
    unittest.main()
