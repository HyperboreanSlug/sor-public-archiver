"""Identity matching: middle names + multi-identifier merge rules."""
from __future__ import annotations

import unittest

from scraper.database import Database
from scraper.database.identity import (
    dobs_compatible,
    middles_compatible,
    should_merge_records,
    score_identity_match,
)


class IdentityUnitTests(unittest.TestCase):
    def test_middle_v_vs_rashmibabu_conflict(self):
        self.assertIs(middles_compatible("V", "RASHMIBABU"), False)
        self.assertIs(middles_compatible("R", "RASHMIBABU"), True)
        self.assertIs(middles_compatible("Rashmi", "RASHMIBABU"), True)
        self.assertIs(middles_compatible("", "V"), None)

    def test_dob_conflict(self):
        self.assertIs(dobs_compatible("01/09/1978", "1973-10-29"), False)
        self.assertIs(dobs_compatible("1978-01-09", "01/09/1978"), True)
        self.assertIs(dobs_compatible("06/09/1987", "1987-06-09"), True)

    def test_name_dob_dedupe_normalizes_formats(self):
        """US MM/DD/YYYY and ISO YYYY-MM-DD must group as one person."""
        db = Database(":memory:")
        try:
            a = db.insert_offender(
                {
                    "first_name": "Jackson",
                    "last_name": "Alexander",
                    "date_of_birth": "06/09/1987",
                    "state": "FL",
                    "race": "B",
                    "external_id": "70152",
                    "height": "602",
                    "weight": "180",
                    "source_url": (
                        "https://offender.fdle.state.fl.us/offender/sops/"
                        "flyer.jsf?personId=70152"
                    ),
                }
            )
            b = db.insert_offender(
                {
                    "first_name": "JACKSON",
                    "middle_name": "WILLIAM",
                    "last_name": "ALEXANDER",
                    "date_of_birth": "1987-06-09",
                    "state": "FL",
                    "race": "Black",
                    "external_id": "59640",
                    "height": "6'02\"",
                    "weight": "180 lbs",
                    "photo_path": "data/photos/j.jpg",
                    "report_html_path": "data/html/j.html",
                    "source_url": (
                        "https://offender.fdle.state.fl.us/offender/sops/"
                        "flyer.jsf?personId=59640"
                    ),
                }
            )
            groups = db.find_duplicate_groups("name_dob")
            self.assertEqual(len(groups), 1)
            ids = set(groups[0]["ids"])
            self.assertEqual(ids, {a, b})
            # Prefer richer HTML/photo row as survivor
            self.assertEqual(groups[0]["keep_id"], b)
            live = db.remove_duplicates(
                "name_dob", dry_run=False, merge_fields=True, safe_only=True
            )
            self.assertEqual(live["deleted"], 1)
            self.assertEqual(db.get_total_count(), 1)
            kept = db.get_offender_by_id(b)
            assert kept is not None
            self.assertEqual(kept.get("id"), b)
            # DOB still present (either format OK)
            self.assertTrue(dobs_compatible(kept.get("date_of_birth"), "06/09/1987"))
            # Both registry ids retained
            ext = str(kept.get("external_id") or "")
            self.assertIn("59640", ext)
            self.assertIn("70152", ext)
        finally:
            db.close()

    def test_normalize_dob_strips_age_suffix(self):
        from scraper.database.identity import normalize_dob

        self.assertEqual(normalize_dob("5/26/1990 Age: 36"), "19900526")
        self.assertEqual(normalize_dob("06/09/1987"), "19870609")
        self.assertEqual(normalize_dob("1987-06-09"), "19870609")

    def test_fl_vs_co_patel_not_merged(self):
        fl = {
            "first_name": "NIRAJ",
            "middle_name": "V",
            "last_name": "PATEL",
            "date_of_birth": "01/09/1978",
            "height": "600",
            "weight": "202",
            "external_id": "120472",
            "source_state": "FL",
        }
        co = {
            "first_name": "NIRAJ",
            "middle_name": "RASHMIBABU",
            "last_name": "PATEL",
            "date_of_birth": "1973-10-29",
            "height": "600",
            "weight": "202",
            "external_id": "xx40592092",
            "state": "CO",
        }
        ok, score, reasons = should_merge_records(fl, co)
        self.assertFalse(ok)
        self.assertIn("hard_reject", reasons)
        # Even if CO has no middle, DOB conflict still blocks
        co2 = dict(co)
        co2["middle_name"] = ""
        ok2, _, reasons2 = should_merge_records(fl, co2)
        self.assertFalse(ok2)
        self.assertTrue(any("dob" in r or "hard" in r for r in reasons2))

    def test_same_person_fl_reimport(self):
        a = {
            "first_name": "NIRAJ",
            "middle_name": "V",
            "last_name": "PATEL",
            "date_of_birth": "01/09/1978",
            "height": "600",
            "weight": "202",
            "external_id": "120472",
        }
        b = {
            "first_name": "NIRAJ",
            "middle_name": "V",
            "last_name": "PATEL",
            "date_of_birth": "1978-01-09",
            "height": "600",
            "weight": "202",
            "external_id": "120472",
        }
        ok, score, reasons = should_merge_records(a, b)
        self.assertTrue(ok)
        self.assertGreaterEqual(score, 6)

    def test_import_does_not_merge_fl_onto_co(self):
        db = Database(":memory:")
        try:
            rid = db.insert_offender(
                {
                    "first_name": "NIRAJ",
                    "middle_name": "RASHMIBABU",
                    "last_name": "PATEL",
                    "date_of_birth": "1973-10-29",
                    "height": "600",
                    "weight": "202",
                    "race": "Asian or Pacific Islander",
                    "state": "CO",
                    "source_state": "CO",
                    "external_id": "xx40592092",
                    "source_url": (
                        "https://apps.colorado.gov/apps/dps/sor/"
                        "search/search-detail.jsf?id=xx40592092"
                    ),
                }
            )
            import tempfile, csv
            from pathlib import Path

            td = Path(tempfile.mkdtemp())
            p = td / "fl_sor.csv"
            with open(p, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(
                    f,
                    fieldnames=[
                        "FIRST_NAME", "MIDDLE_NAME", "LAST_NAME", "RACE",
                        "HEIGHT", "WEIGHT", "EYE_COLOR", "PERSON_NBR",
                        "SEX", "BIRTH_DATE", "PERM_CITY", "PERM_STATE",
                    ],
                )
                w.writeheader()
                w.writerow(
                    {
                        "FIRST_NAME": "NIRAJ",
                        "MIDDLE_NAME": "V",
                        "LAST_NAME": "PATEL",
                        "RACE": "W",
                        "HEIGHT": "600",
                        "WEIGHT": "202",
                        "EYE_COLOR": "Brown",
                        "PERSON_NBR": "120472",
                        "SEX": "M",
                        "BIRTH_DATE": "01/09/1978",
                        "PERM_CITY": "Cobden",
                        "PERM_STATE": "IL",
                    }
                )
            result = db.import_csv(str(p), state="FL", merge_sources=True)
            # Must insert new FL row, not merge into CO
            self.assertEqual(result["merged"], 0)
            self.assertEqual(result["imported"], 1)
            n = db._conn.execute("SELECT COUNT(*) FROM offenders").fetchone()[0]
            self.assertEqual(n, 2)
            co = db.get_offender_by_id(rid)
            self.assertEqual(co["external_id"], "xx40592092")
            # CO race must not become letter W from FL
            self.assertNotEqual((co.get("race") or "").strip().upper(), "W")
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
