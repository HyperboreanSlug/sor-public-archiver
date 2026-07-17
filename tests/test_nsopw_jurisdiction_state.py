"""Registry jurisdiction beats residential address for NSOPW state labeling."""
from __future__ import annotations

import unittest

from scraper.nsopw.client_types import normalize_jurisdiction_code
from scraper.public_links import openable_url_for_record, resolve_public_source_url


class JurisdictionStateTests(unittest.TestCase):
    def test_normalize_prefers_first_valid(self):
        # Call sites pass jurisdictionId first for out-of-state registrants
        self.assertEqual(
            normalize_jurisdiction_code("GA", "FL"),
            "GA",
        )
        self.assertEqual(
            normalize_jurisdiction_code("YY", "FL"),
            "FL",
        )

    def test_openable_ga_url_not_forced_to_fdle_search(self):
        """Felipe Acevedo-style: source_state GA|FL, only GA URL → open GA."""
        rec = {
            "state": "FL",
            "source_state": "GA | FL",
            "source_url": (
                "https://state.sor.gbi.ga.gov/sort_public/"
                "offenderdetails.aspx?id=37532"
            ),
        }
        url = openable_url_for_record(rec)
        self.assertIn("gbi.ga.gov", url.lower())
        self.assertNotIn("fdle", url.lower())

    def test_multi_state_prefers_url_host(self):
        url = resolve_public_source_url(
            "https://state.sor.gbi.ga.gov/sort_public/offenderdetails.aspx?id=1",
            state="GA | FL",
        )
        self.assertIn("gbi.ga.gov", url.lower())


if __name__ == "__main__":
    unittest.main()
