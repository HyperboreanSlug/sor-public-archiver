"""Unit tests for Virginia vspsor.com scraper (parse + client payload)."""
from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from scraper.scrapers.va_client import DT_COLUMNS, VaVspsorClient
from scraper.scrapers.va_parse import (
    list_row_to_record,
    merge_detail_into_record,
    names_compatible,
    parse_detail_html,
)
from scraper.scrapers.va_scraper import VAScraper
from scraper.scrapers.base import ScraperFactory
from scraper.config import get_registry_by_abbr


_LIST_ROW = {
    "id": "8eaa40d2-e4bc-458f-bc58-3b272353c513",
    "firstName": "AARON",
    "middleName": "ELVIS",
    "lastName": "ABLE",
    "age": 38,
    "imageUrl": "/api/file/image/fc2cea9c-e27d-4f7e-b410-83870c61aeba",
    "addressType": "Home<br/>Work",
    "location": "605 WARRENTON ROAD<br/>10724 CEDAR POST LANE",
    "city": "FREDERICKSBURG<br/>SPOTSYLVANIA COURTHOUSE",
    "postalCode": "22406<br/>22553",
    "county": "FREDERICKSBURG CITY<br/>SPOTSYLVANIA COUNTY",
    "fullName": "AARON ABLE",
}

_DETAIL_HTML = """
<html><body>
<div id="offender-details">
  <h1>AARON ELVIS ABLE</h1>
  <div>Registration Number:</div><div>13139</div>
  <div>Sex:</div><div>MALE</div>
  <div>Race:</div><div>WHITE</div>
  <div>Hair:</div><div>BROWN</div>
  <div>Height:</div><div>5' 6"</div>
  <div>Weight:</div><div>200 lbs</div>
  <div>Eyes:</div><div>BROWN</div>
  <div>Tier:</div><div>Tier 3</div>
</div>
<div id="convictions">
  <div class="card-header gold">
    <span>18.2-374.1:1(C) - POSSESSION OF CHILD PORNOGRAPHY - </span>
  </div>
</div>
<img alt="Photo of offender" src="/api/file/image/fc2cea9c-e27d-4f7e-b410-83870c61aeba"/>
</body></html>
"""


class VaParseTests(unittest.TestCase):
    def test_list_row_primary_address(self):
        rec = list_row_to_record(_LIST_ROW)
        self.assertEqual(rec["external_id"], _LIST_ROW["id"])
        self.assertEqual(rec["first_name"], "AARON")
        self.assertEqual(rec["last_name"], "ABLE")
        self.assertEqual(rec["address"], "605 WARRENTON ROAD")
        self.assertEqual(rec["city"], "FREDERICKSBURG")
        self.assertEqual(rec["county"], "FREDERICKSBURG CITY")
        self.assertTrue(rec["source_url"].endswith(_LIST_ROW["id"]))
        self.assertIn("/api/file/image/", rec["photo_url"])
        self.assertEqual(rec["source_state"], "VA")

    def test_parse_detail_and_merge(self):
        detail = parse_detail_html(_DETAIL_HTML)
        self.assertEqual((detail.get("race") or "").upper(), "WHITE")
        self.assertIn("PORNOGRAPHY", (detail.get("crime") or "").upper())
        self.assertIn("Tier", (detail.get("risk_level") or ""))

        base = list_row_to_record(_LIST_ROW)
        merged = merge_detail_into_record(base, detail)
        self.assertEqual((merged.get("race") or "").upper(), "WHITE")
        self.assertEqual(merged["external_id"], _LIST_ROW["id"])
        raw = merged.get("raw_data_json") or {}
        if isinstance(raw, str):
            raw = json.loads(raw)
        self.assertEqual(str(raw.get("registration_number")), "13139")

    def test_identity_mismatch_skips_demos(self):
        base = list_row_to_record(_LIST_ROW)
        detail = {
            "full_name": "TOTALLY DIFFERENT PERSON",
            "race": "BLACK",
            "crime": "SOMETHING",
        }
        merged = merge_detail_into_record(base, detail)
        self.assertIsNone(merged.get("race"))
        self.assertIn("identity_html_mismatch", str(merged.get("flags") or ""))

    def test_names_compatible(self):
        self.assertTrue(names_compatible("AARON ABLE", "AARON ELVIS ABLE"))
        self.assertFalse(names_compatible("AARON ABLE", "JOSE TRIANA"))


class VaClientTests(unittest.TestCase):
    def test_dt_payload_column_order(self):
        c = VaVspsorClient(delay=0)
        payload = c._dt_payload(start=0, length=100)
        self.assertEqual([col["data"] for col in payload["columns"]], list(DT_COLUMNS))
        self.assertEqual(payload["length"], 100)
        self.assertEqual(payload["start"], 0)
        c.close()


class VaScraperWireTests(unittest.TestCase):
    def test_factory_returns_va_scraper(self):
        reg = get_registry_by_abbr("VA")
        self.assertIsNotNone(reg)
        self.assertEqual(reg.scrape_method, "vspsor")
        scraper = ScraperFactory.create("VA", delay=0.5)
        try:
            self.assertIsInstance(scraper, VAScraper)
        finally:
            scraper.close()

    def test_scrape_pages_with_mocks(self):
        page1 = {
            "recordsTotal": 2,
            "recordsFiltered": 2,
            "offenders": [_LIST_ROW],
        }
        page2 = {
            "recordsTotal": 2,
            "recordsFiltered": 2,
            "offenders": [
                {
                    **_LIST_ROW,
                    "id": "0cc62f7b-fabe-47cf-a637-190c807b0b37",
                    "firstName": "AARON",
                    "lastName": "ALEXANDER",
                    "fullName": "AARON ALEXANDER",
                    "middleName": "LAMONT",
                    "location": "285 SAPONI LANE",
                    "city": "CHARLOTTESVILLE",
                    "postalCode": "22901",
                    "county": "ALBEMARLE COUNTY",
                    "addressType": "Home",
                }
            ],
        }
        empty = {"recordsTotal": 2, "recordsFiltered": 2, "offenders": []}

        scraper = VAScraper(
            "VA", delay=0, fetch_details=True, page_size=1, max_records=0
        )
        try:
            with patch.object(
                scraper._client,
                "search_page",
                side_effect=[page1, page2, empty],
            ) as sp, patch.object(
                scraper._client,
                "fetch_detail_html",
                return_value=(_DETAIL_HTML, "https://www.vspsor.com/Offender/Details/x"),
            ):
                records = scraper.scrape()
            self.assertEqual(sp.call_count, 2)
            self.assertEqual(len(records), 2)
            races = {(r.get("race") or "").upper() for r in records}
            self.assertIn("WHITE", races)
            self.assertTrue(all(r.get("external_id") for r in records))
        finally:
            scraper.close()

    def test_list_only_skips_details(self):
        page = {
            "recordsTotal": 1,
            "recordsFiltered": 1,
            "offenders": [_LIST_ROW],
        }
        scraper = VAScraper("VA", delay=0, fetch_details=False, page_size=100)
        try:
            with patch.object(
                scraper._client, "search_page", return_value=page
            ), patch.object(
                scraper._client, "fetch_detail_html"
            ) as fd:
                records = scraper.scrape()
            fd.assert_not_called()
            self.assertEqual(len(records), 1)
            self.assertFalse(records[0].get("race"))
        finally:
            scraper.close()


if __name__ == "__main__":
    unittest.main()
