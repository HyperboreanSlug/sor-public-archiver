"""Online listing availability (dead URL / 404) for Reports."""
from __future__ import annotations

import json
import unittest

from scraper.online_listing import (
    UNAVAILABLE_ONLINE_LABEL,
    listing_unavailable_online,
    online_status_label,
)


class OnlineListingTests(unittest.TestCase):
    def test_jacinto_style_dead_fdle_error_page(self):
        """Stored URL is the FDLE error404 landing — truly not available."""
        rec = {
            "full_name": "Jacinto Calderon",
            "state": "FL",
            "source_state": "FL",
            "source_url": (
                "https://offender.fdle.state.fl.us/offender/error/error404.jsf"
            ),
            "flags": json.dumps(
                [
                    "multi_source",
                    "blocked:http_404",
                    "identity_html_mismatch",
                ]
            ),
            "sources_json": json.dumps(
                [
                    {
                        "html_status": "blocked:http_404",
                        "source_url": (
                            "https://offender.fdle.state.fl.us/offender/"
                            "error/error404.jsf"
                        ),
                    }
                ]
            ),
        }
        self.assertTrue(listing_unavailable_online(rec))
        self.assertEqual(online_status_label(rec), UNAVAILABLE_ONLINE_LABEL)

    def test_live_listing_ok(self):
        rec = {
            "source_url": (
                "https://offender.fdle.state.fl.us/offender/sops/flyer.jsf"
                "?personId=139323"
            ),
            "flags": json.dumps(["photo_archived", "html_archived"]),
        }
        self.assertFalse(listing_unavailable_online(rec))
        self.assertEqual(online_status_label(rec), "")

    def test_error404_url(self):
        rec = {
            "state": "FL",
            "source_url": (
                "https://offender.fdle.state.fl.us/offender/error/error404.jsf"
            ),
        }
        self.assertTrue(listing_unavailable_online(rec))

    def test_html_404_flag_but_live_detail_url_still_online(self):
        """Photos often come from photo_url while HTML enrich got a 404 once.

        Sticky blocked:http_404 / sources html_status must not hide a stored
        person detail URL (bot 404 ≠ no listing; mugshot may still be online).
        """
        rec = {
            "full_name": "ALBERT ADAMCYK",
            "state": "IL",
            "source_state": "IL",
            "source_url": (
                "https://sor.isp.illinois.gov/sorpublic/details/X23A1728?type=sor"
            ),
            "photo_path": r"data\report_pages\IL\photos\6acd16b2abcba4b9.jpg",
            "photo_url": (
                "https://sor.isp.illinois.gov/sor-server/public/offender/"
                "X23A1728/image"
            ),
            "flags": json.dumps(
                [
                    "nsopw",
                    "report_link_saved",
                    "blocked:http_404",
                    "photo_archived",
                    "multi_source",
                ]
            ),
            "sources_json": json.dumps(
                [
                    {
                        "html_status": "blocked:http_404",
                        "source_url": (
                            "https://sor.isp.illinois.gov/sorpublic/details/"
                            "X23A1728?type=sor"
                        ),
                    }
                ]
            ),
        }
        self.assertFalse(listing_unavailable_online(rec))
        self.assertEqual(online_status_label(rec), "")

    def test_multi_source_dead_fdle_live_il_still_online(self):
        """One dead FDLE source must not offline a live IL detail + photo."""
        rec = {
            "full_name": "HAMZA ALAMOURI",
            "state": "FL | IL",
            "source_state": "FL | IL",
            "source_url": (
                "https://offender.fdle.state.fl.us/offender/error/error404.jsf"
                " | https://sor.isp.illinois.gov/sorpublic/details/X22A0963?type=sor"
            ),
            "photo_path": r"data\report_pages\IL\photos\d0d1820af54bc416.jpg",
            "photo_url": (
                "https://sor.isp.illinois.gov/sor-server/public/offender/"
                "X22A0963/image"
            ),
            "flags": json.dumps(["blocked:http_404", "photo_archived", "multi_source"]),
        }
        self.assertFalse(listing_unavailable_online(rec))

    def test_flyer_with_sticky_404_flag_still_online_if_person_url(self):
        """Sticky flag + FDLE flyer personId + CallImage photo ≠ unavailable.

        Report HTML may have 404'd once while CallImage photo was archived and
        the flyer URL remains the stored person link.
        """
        rec = {
            "state": "FL",
            "source_url": (
                "https://offender.fdle.state.fl.us/offender/sops/flyer.jsf"
                "?personId=112183"
            ),
            "photo_url": (
                "https://offender.fdle.state.fl.us/offender/CallImage?imgID=5177593"
            ),
            "flags": json.dumps(
                ["blocked:http_404", "photo_archived", "report_enriched"]
            ),
            "sources_json": json.dumps(
                [
                    {
                        "html_status": "ok",
                        "source_url": (
                            "https://offender.fdle.state.fl.us/offender/sops/"
                            "flyer.jsf?personId=112183"
                        ),
                    }
                ]
            ),
        }
        self.assertFalse(listing_unavailable_online(rec))

    def test_sources_json_404_with_no_person_url(self):
        """Dead evidence + no person-specific openable URL → unavailable."""
        rec = {
            "state": "FL",
            "source_url": "",
            "sources_json": json.dumps(
                [
                    {
                        "html_status": "blocked:http_404",
                        "source_url": (
                            "https://offender.fdle.state.fl.us/offender/"
                            "error/error404.jsf"
                        ),
                    }
                ]
            ),
            "flags": json.dumps(["blocked:http_404"]),
        }
        self.assertTrue(listing_unavailable_online(rec))

    def test_404_flag_alone_without_url_is_unavailable(self):
        """Proven 404 with nowhere else to open → banner is correct."""
        rec = {
            "flags": json.dumps(["blocked:http_404", "photo_archived"]),
            "photo_path": "data/report_pages/FL/photos/x.jpg",
            "source_url": "",
        }
        self.assertTrue(listing_unavailable_online(rec))

    def test_photo_without_url_or_404_is_not_unavailable(self):
        """Missing link ≠ dead listing; photo may be NSOPW-only archive."""
        rec = {
            "photo_path": "data/report_pages/TX/photos/x.jpg",
            "photo_url": "https://example.com/img.jpg",
            "flags": json.dumps(["photo_archived", "nsopw"]),
            "source_url": "",
        }
        self.assertFalse(listing_unavailable_online(rec))

    def test_tx_rapsheet_is_person_listing_not_search_home(self):
        """TX /PublicSite/Search/Rapsheet?sid= is a person page, not Search home."""
        rec = {
            "state": "TX",
            "source_url": (
                "https://sor.dps.texas.gov/PublicSite/Search/Rapsheet?sid=06128833"
            ),
            "flags": json.dumps(["blocked:http_404", "photo_archived"]),
            "photo_url": (
                "https://offender.fdle.state.fl.us/offender/CallImage?imgID=3161571"
            ),
        }
        self.assertFalse(listing_unavailable_online(rec))

    def test_empty_record(self):
        self.assertFalse(listing_unavailable_online(None))
        self.assertFalse(listing_unavailable_online({}))


if __name__ == "__main__":
    unittest.main()
