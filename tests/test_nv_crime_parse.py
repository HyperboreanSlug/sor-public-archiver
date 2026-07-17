"""NV sexoffenders.nv.gov offense table + RowHead county parsing."""
from __future__ import annotations

import unittest

from scraper.reports.fetcher import ReportFetcher
from scraper.reports.fetcher_crime import extract_crime_from_tables
from bs4 import BeautifulSoup


_NV_HTML = """
<html><body>
<div class="Row"><div class="RowHead">County:</div> Out of State</div>
<div class="Row"><div class="RowHead">Start Date:</div> 5/14/2026 12:00:00 AM</div>
<div class="Row"><div class="RowHead">Race:</div> White</div>
<div class="header">Offenses:</div>
<table id="ctl00_ContentPlaceHolder1_OffenderDetails1_offenses">
<tr>
  <th>Conviction Date</th>
  <th>Conviction Description</th>
  <th>Court Name</th>
  <th>Conviction Name</th>
  <th>Offense Location</th>
  <th>Institution Name</th>
</tr>
<tr class="RowStyle">
  <td>06/05/2009</td>
  <td><a>288 (A) LEWD OR LASCIVIOUS ACTS W/ CHILD UNDER 14</a></td>
  <td>SAN DIEGO SUPERIOR COURT</td>
  <td>EHAB ABDALLAH ALAWI</td>
  <td>SAN DIEGO, CA</td>
  <td>DEPT OF CORRECTIONS</td>
</tr>
</table>
</body></html>
"""


class NvCrimeParseTests(unittest.TestCase):
    def test_extract_crime_description_only(self):
        soup = BeautifulSoup(_NV_HTML, "html.parser")
        crime = extract_crime_from_tables(soup)
        self.assertIn("LEWD OR LASCIVIOUS", crime.upper())
        self.assertNotIn("SUPERIOR COURT", crime.upper())
        self.assertNotIn("ALAWI", crime.upper())
        self.assertNotIn("DEPT OF CORRECTIONS", crime.upper())

    def test_from_html_crime_and_county(self):
        f = ReportFetcher.__new__(ReportFetcher)
        found = f._from_html(_NV_HTML, "https://sexoffenders.nv.gov/")
        self.assertEqual(
            found.get("crime"),
            "288 (A) LEWD OR LASCIVIOUS ACTS W/ CHILD UNDER 14",
        )
        self.assertEqual(found.get("county"), "Out of State")
        self.assertNotIn("Start Date", str(found.get("county") or ""))


if __name__ == "__main__":
    unittest.main()
