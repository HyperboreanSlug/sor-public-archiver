"""Tests for cookie jar + captcha queue (manual access assistance)."""
import json
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scraper.cookie_jar import CaptchaQueue, CookieJarStore


class CookieJarTests(unittest.TestCase):
    def test_import_json_and_apply(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "cookies.json"
            store = CookieJarStore(path)
            n = store.import_cookies(
                json.dumps(
                    [
                        {
                            "name": "session",
                            "value": "abc123",
                            "domain": "offender.fdle.state.fl.us",
                            "path": "/",
                        }
                    ]
                )
            )
            self.assertEqual(n, 1)
            self.assertIn("offender.fdle.state.fl.us", store.summary())
            cookies = store.cookies_for_url(
                "https://offender.fdle.state.fl.us/offender/sops/flyer.jsf"
            )
            self.assertEqual(len(cookies), 1)
            self.assertEqual(cookies[0]["value"], "abc123")

    def test_import_netscape(self):
        with tempfile.TemporaryDirectory() as td:
            store = CookieJarStore(Path(td) / "c.json")
            raw = (
                "# Netscape HTTP Cookie File\n"
                ".example.com\tTRUE\t/\tFALSE\t0\tsid\txyz\n"
            )
            n = store.import_cookies(raw)
            self.assertEqual(n, 1)
            self.assertEqual(store.summary().get("example.com"), 1)

    def test_captcha_queue_dedupe(self):
        with tempfile.TemporaryDirectory() as td:
            q = CaptchaQueue(Path(td) / "q.json")
            q.add("https://example.gov/r/1", jurisdiction="NY", reason="captcha")
            q.add("https://example.gov/r/1", jurisdiction="NY", reason="captcha")
            self.assertEqual(len(q.list_items()), 1)
            q.add("https://example.gov/r/2", jurisdiction="CA", reason="waf_datadome")
            self.assertEqual(len(q.list_items()), 2)
            self.assertTrue(q.remove_url("https://example.gov/r/1"))
            self.assertEqual(len(q.list_items()), 1)


if __name__ == "__main__":
    unittest.main()
