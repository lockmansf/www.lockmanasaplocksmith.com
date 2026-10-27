"""Offline tests. Run: python3 -m unittest discover -s tests -t ."""
import datetime as dt
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

from publisher import common, originality, publish, recheck

TZ = ZoneInfo("America/Los_Angeles")


class Sandbox(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "content" / "articles").mkdir(parents=True)
        shutil.copy(common.ROOT / "config.json", self.tmp / "config.json")
        shutil.copy(common.TOPICS_FILE, self.tmp / "content" / "topics.json")
        self.patches = [
            mock.patch.object(common, "ROOT", self.tmp),
            mock.patch.object(common, "ARTICLES_DIR", self.tmp / "content" / "articles"),
            mock.patch.object(common, "REMOVED_DIR", self.tmp / "content" / "removed"),
            mock.patch.object(common, "LOG_FILE", self.tmp / "content" / "publish_log.json"),
            mock.patch.object(common, "TOPICS_FILE", self.tmp / "content" / "topics.json"),
            mock.patch.dict(os.environ, {"LOCKMAN_MOCK": "1"}),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp)

    def published(self):
        return common.load_articles()


class TestSchedule(Sandbox):
    def test_hour_in_window_and_different_each_day(self):
        prev = None
        day = dt.date(2026, 1, 1)
        for _ in range(400):
            h = publish.target_hour(day, prev, 8, 20)
            self.assertTrue(8 <= h <= 20)
            self.assertNotEqual(h, prev)
            prev, day = h, day + dt.timedelta(days=1)

    def test_waits_until_target_hour(self):
        early = dt.datetime(2026, 10, 27, 0, 30, tzinfo=TZ)
        publish.run(now=early)
        self.assertEqual(self.published(), [])
        self.assertEqual(common.load_log()["days"]["2026-10-27"]["attempts"], 0)

    def test_publishes_once_per_day(self):
        late = dt.datetime(2026, 10, 27, 23, 0, tzinfo=TZ)
        publish.run(now=late)
        publish.run(now=late)
        self.assertEqual(len(self.published()), 1)
        log = common.load_log()
        self.assertEqual(log["days"]["2026-10-27"]["attempts"], 1)


class TestFailuresPublishNothing(Sandbox):
    def run_failing(self, mode):
        with mock.patch.dict(os.environ, {"LOCKMAN_MOCK": mode}):
            publish.run(force_now=True, now=dt.datetime(2026, 10, 27, 12, tzinfo=TZ))
        self.assertEqual(self.published(), [])
        day = common.load_log()["days"]["2026-10-27"]
        self.assertEqual(day["attempts"], 3)  # capped: no endless retries
        self.assertEqual(len(day["failures"]), 3)
        self.assertIsNone(day["published"])

    def test_web_match_blocks_publish(self):
        self.run_failing("fail-copyscape")

    def test_gemini_failure_blocks_publish(self):
        self.run_failing("fail-gemini")

    def test_no_copyscape_credentials_means_not_original(self):
        with mock.patch.dict(os.environ, {"LOCKMAN_MOCK": ""}, clear=False):
            os.environ.pop("COPYSCAPE_USER", None)
            ok, detail = originality.check("some text", "lockmanasaplocksmith.com", 5, 25)
        self.assertFalse(ok)
        self.assertIn("refusing", detail)

    def test_too_similar_to_own_article_is_rejected(self):
        publish.run(force_now=True, now=dt.datetime(2026, 10, 27, 12, tzinfo=TZ))
        publish.run(force_now=True, now=dt.datetime(2026, 10, 28, 12, tzinfo=TZ))
        self.assertEqual(len(self.published()), 1)  # mock articles share most of their text
        fails = common.load_log()["days"]["2026-10-28"]["failures"]
        self.assertTrue(all("too similar" in f["reason"] for f in fails))


class TestCopyscapeParsing(unittest.TestCase):
    def fake_response(self, xml):
        resp = mock.MagicMock()
        resp.__enter__.return_value.read.return_value = xml.encode()
        return resp

    def check(self, xml):
        env = {"LOCKMAN_MOCK": "", "COPYSCAPE_USER": "u", "COPYSCAPE_KEY": "k"}
        with mock.patch.dict(os.environ, env), mock.patch("urllib.request.urlopen", return_value=self.fake_response(xml)):
            return originality.check("text", "lockmanasaplocksmith.com", 5, 25)

    def test_ignores_own_site_and_small_matches(self):
        ok, _ = self.check("""<response><count>2</count>
<result><url>https://lockmanasaplocksmith.com/articles/x/</url><minwordsmatched>900</minwordsmatched><percentmatched>100</percentmatched></result>
<result><url>https://other.com/a</url><minwordsmatched>9</minwordsmatched><percentmatched>1</percentmatched></result></response>""")
        self.assertTrue(ok)

    def test_flags_real_match(self):
        ok, detail = self.check("""<response><count>1</count>
<result><url>https://other.com/a</url><minwordsmatched>60</minwordsmatched><percentmatched>8</percentmatched></result></response>""")
        self.assertFalse(ok)
        self.assertIn("other.com", detail)

    def test_api_error_is_not_original(self):
        ok, _ = self.check("<response><error>Insufficient credit</error></response>")
        self.assertFalse(ok)


class TestRecheck(Sandbox):
    def test_copied_article_is_removed_and_replaced(self):
        publish.run(force_now=True, now=dt.datetime(2026, 10, 20, 12, tzinfo=TZ))
        first = self.published()[0]["slug"]
        calls = iter([(False, "Similar text found online: https://copy.com (80 words, 12%)")])
        real = originality.check

        def flaky(*a, **k):
            return next(calls, None) or real(*a, **k)

        with mock.patch.object(originality, "check", side_effect=flaky):
            recheck.run()
        slugs = [a["slug"] for a in self.published()]
        self.assertNotIn(first, slugs)
        self.assertEqual(len(slugs), 1)  # replacement written
        self.assertTrue((common.REMOVED_DIR / f"{first}.json").exists())


class TestBuild(unittest.TestCase):
    def test_build_outputs(self):
        import build
        tmp = Path(tempfile.mkdtemp())
        try:
            with mock.patch.object(build, "DIST", tmp / "dist"):
                build.build()
            dist = tmp / "dist"
            for f in ["index.html", "sitemap.xml", "robots.txt", "privacy/index.html", "404.html", "CNAME",
                      "services/lockout/index.html", "articles/index.html"]:
                self.assertTrue((dist / f).exists(), f)
            home = (dist / "index.html").read_text()
            self.assertIn('"@type": "Locksmith"', home)
            self.assertIn("wa-float", home)
            self.assertIn('rel="canonical"', home)
            self.assertEqual(home.count("<h1"), 1)
            sm = (dist / "sitemap.xml").read_text()
            self.assertIn("https://lockmanasaplocksmith.com/services/lockout/", sm)
            self.assertNotIn("404", sm)
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
