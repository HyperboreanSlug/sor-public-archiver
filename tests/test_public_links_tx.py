"""Texas DPS SOR URL canonicalization + openable links."""
from __future__ import annotations

import unittest

from scraper.public_links import openable_url_for_record, resolve_public_source_url
from scraper.public_links_tx import (
    TX_SOR_RAPSHEET_BASE,
    TX_SOR_SEARCH_HOME,
    extract_tx_sid,
    normalize_tx_dps_url,
    tx_rapsheet_url,
)
from scraper.database import Database
from scraper.scrapers.base import ScraperFactory
from scraper.scrapers.tx_scraper import TXScraper
from scraper.scrapers.tx_client import parse_rapsheet_xml


_SID = "50423617"
_XML = f"""<?xml version="1.0"?>
<INDV>
  <DPS_NBR>{_SID}</DPS_NBR>
  <SEX_COD_LIT>Female</SEX_COD_LIT>
  <RAC_COD_LIT>White</RAC_COD_LIT>
  <HGT_QTY_formatted>4'10"</HGT_QTY_formatted>
  <WGT_QTY>140</WGT_QTY>
  <Names><Name><TYP_COD>B</TYP_COD><NAM_TXT>ADAMS,AMANDIKA SY</NAM_TXT></Name></Names>
  <Birthdates><Birthdate><DOB_DTE_formatted>02/03/1990</DOB_DTE_formatted></Birthdate></Birthdates>
  <Offenses><Offense>
    <LEN_TXT>UNLAWFUL SEXUAL CONDUCT</LEN_TXT>
    <CIT_TXT>OHIO REVISED CODE 2907.04</CIT_TXT>
  </Offense></Offenses>
</INDV>
"""


class TxUrlTests(unittest.TestCase):
    def test_publicsite_to_sor_host(self):
        old = (
            "https://publicsite.dps.texas.gov/SexOffenderRegistry/"
            f"Search/Rapsheet?sid={_SID}"
        )
        out = normalize_tx_dps_url(old)
        self.assertEqual(out, f"{TX_SOR_RAPSHEET_BASE}?sid={_SID}")
        self.assertIn("sor.dps.texas.gov", out)
        self.assertNotIn("publicsite", out)

    def test_bare_rapsheet_falls_back_to_search(self):
        bare = "https://publicsite.dps.texas.gov/sexoffenderregistry/search/rapsheet"
        self.assertEqual(normalize_tx_dps_url(bare), TX_SOR_SEARCH_HOME)

    def test_extract_sid(self):
        self.assertEqual(
            extract_tx_sid(f"https://x/Rapsheet?sid={_SID}"),
            _SID,
        )

    def test_openable_prefers_tx_when_state_tx(self):
        multi = (
            f"https://offender.fdle.state.fl.us/offender/sops/flyer.jsf?personId=1 | "
            f"https://publicsite.dps.texas.gov/SexOffenderRegistry/Search/Rapsheet?sid={_SID}"
        )
        out = resolve_public_source_url(multi, state="TX")
        self.assertEqual(out, tx_rapsheet_url(_SID))

    def test_openable_for_record(self):
        rec = {
            "source_state": "TX",
            "state": "TX",
            "source_url": (
                "https://publicsite.dps.texas.gov/SexOffenderRegistry/"
                f"Search/Rapsheet?sid={_SID}"
            ),
        }
        self.assertEqual(openable_url_for_record(rec), tx_rapsheet_url(_SID))

    def test_identity_normalize(self):
        old = (
            "https://publicsite.dps.texas.gov/SexOffenderRegistry/"
            f"Search/Rapsheet?sid={_SID}"
        )
        norm = Database.normalize_identity_url(old)
        self.assertIn("sor.dps.texas.gov", norm)
        self.assertIn(f"sid={_SID}", norm.lower())

    def test_factory_tx(self):
        s = ScraperFactory.create("TX", delay=0.5)
        try:
            self.assertIsInstance(s, TXScraper)
        finally:
            s.close()

    def test_parse_rapsheet_xml(self):
        rec = parse_rapsheet_xml(_XML, sid=_SID)
        self.assertEqual(rec.get("external_id"), _SID)
        self.assertEqual(rec.get("first_name"), "AMANDIKA")
        self.assertEqual(rec.get("last_name"), "ADAMS")
        self.assertIn("UNLAWFUL SEXUAL CONDUCT", rec.get("crime") or "")
        self.assertIn("sor.dps.texas.gov", rec.get("source_url") or "")


if __name__ == "__main__":
    unittest.main()
