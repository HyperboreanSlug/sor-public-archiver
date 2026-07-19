"""Registry HTML name extraction must prefer Name: labels over chrome."""
from __future__ import annotations

import unittest

from scraper.reports.identity_gate import (
    extract_person_name_from_html,
    record_name_matches_html,
)


class IdentityNameExtractTests(unittest.TestCase):
    def test_mo_dps_name_label_over_about_dps(self):
        html = """
        <html><body>
        <h2>Main Navigation</h2>
        <h3>About DPS</h3>
        <h3>Safety &amp; Security</h3>
        <table class="dataTable">
        <tr>
          <td>Name:&nbsp;&nbsp;&nbsp;</td>
          <td class="nameData" nowrap="">John David Barnett </td>
        </tr>
        <tr>
          <td>Race:</td>
          <td style="font-weight:bold">White&nbsp;</td>
        </tr>
        </table>
        </body></html>
        """
        name = extract_person_name_from_html(html)
        self.assertEqual(name, "John David Barnett")
        rec = {
            "first_name": "JOHN",
            "middle_name": "DAVID",
            "last_name": "BARNETT",
            "full_name": "JOHN DAVID BARNETT",
        }
        self.assertTrue(record_name_matches_html(rec, name))

    def test_rejects_chrome_as_name(self):
        for junk in (
            "About DPS",
            "Main Navigation",
            "Submit a Tip",
            "State of Mississippi",
            "Mailing Address",
            "Get Connected",
        ):
            self.assertIsNone(
                extract_person_name_from_html(f"<h3>{junk}</h3>"),
                msg=junk,
            )


if __name__ == "__main__":
    unittest.main()
