"""iCrimeWatch offense rows: Description label vs charge text."""
from __future__ import annotations

import unittest

from scraper.reports.fetcher_crime import (
    is_demographic_crime_junk,
    is_label_chrome_value,
)
from scraper.reports.fetcher_parse import FetcherParseMixin


_SAMPLE = """
<html><body><table>
<tr><td class="sectionHeading" colspan="4"><span class="style2">Offenses</span></td></tr>
<tr>
  <td><strong><span class="offenseLabel">• Description:</span></strong></td>
  <td colspan="3">76-4-401 - ENTICING A MINOR/2ND DEGREE FELONY</td>
</tr>
<tr>
  <td><strong><span class="offenseLabel">• Date Convicted:</span></strong></td>
  <td colspan="3">01/26/2024</td>
</tr>
</table></body></html>
"""


class ICrimeWatchCrimeParseTests(unittest.TestCase):
    def test_label_chrome_detection(self):
        self.assertTrue(is_label_chrome_value("• Description:"))
        self.assertTrue(is_label_chrome_value("Description:"))
        self.assertTrue(is_demographic_crime_junk("• Description:"))
        self.assertFalse(
            is_label_chrome_value("76-4-401 - ENTICING A MINOR/2ND DEGREE FELONY")
        )

    def test_parses_description_charge_not_label(self):
        class T(FetcherParseMixin):
            pass

        found = T()._from_html(_SAMPLE, "https://www.icrimewatch.net/")
        crime = found.get("crime") or ""
        self.assertIn("ENTICING A MINOR", crime.upper())
        self.assertNotIn("Description", crime)


if __name__ == "__main__":
    unittest.main()
