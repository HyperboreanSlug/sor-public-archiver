"""Reports confirmation verdict normalize / filter / labels."""
from __future__ import annotations

import json
import unittest

from gui_app.tabs.browse.reports.grid_meta import ReportsGridMetaMixin
from gui_app.tabs.browse.reports.verdict_filter import ReportsVerdictFilterMixin
from gui_app.tabs.browse.reports.verdict_store import ReportsVerdictStoreMixin


class _Mc:
    def __init__(self, rid, flags=None):
        self.record = {
            "id": rid,
            "flags": flags,
            "first_name": "Test",
            "last_name": "User",
        }
        self.expected_race = "White"
        self.likely_ethnicity = "Hispanic"
        self.confidence = 0.9
        self.matching_names = []


class _Store(ReportsVerdictStoreMixin):
    def __init__(self):
        self._report_verdicts = {}
        self.db_path = "data/offenders.db"


class ReportVerdictTests(unittest.TestCase):
    def test_normalize_incorrect_to_confirmed(self):
        n = ReportsVerdictStoreMixin._normalize_report_verdict
        self.assertEqual(n("incorrect"), "confirmed")
        self.assertEqual(n("confirmed"), "confirmed")
        self.assertEqual(n("correct"), "correct")
        self.assertEqual(n("skip"), "skip")
        self.assertEqual(n(""), "unreviewed")

    def test_verdict_for_mc_flags_incorrect(self):
        t = _Store()
        flags = json.dumps({"ethnicity_review": "incorrect"})
        self.assertEqual(t._verdict_for_mc(_Mc(1, flags)), "confirmed")
        flags_c = json.dumps({"ethnicity_review": "correct"})
        self.assertEqual(t._verdict_for_mc(_Mc(2, flags_c)), "correct")

    def test_verdict_for_mc_json_legacy_incorrect(self):
        t = _Store()
        t._report_verdicts["id:3"] = "incorrect"
        self.assertEqual(t._verdict_for_mc(_Mc(3)), "confirmed")

    def test_filter_accepts_incorrect_as_confirmed(self):
        p = ReportsVerdictFilterMixin._reports_verdict_passes_filter
        self.assertTrue(p("incorrect", "confirmed"))
        self.assertTrue(p("confirmed", "confirmed"))
        self.assertFalse(p("incorrect", "unreviewed"))
        self.assertFalse(p("correct", "confirmed"))

    def test_labels_for_incorrect(self):
        short = ReportsGridMetaMixin._reports_verdict_label_short
        full = ReportsGridMetaMixin._reports_verdict_label
        self.assertIn("Incorrect", short("incorrect"))
        self.assertIn("Incorrect", short("confirmed"))
        self.assertIn("incorrect", full("incorrect").lower())


if __name__ == "__main__":
    unittest.main()
