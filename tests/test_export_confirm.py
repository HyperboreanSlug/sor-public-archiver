"""Export card auto-marks confirmed incorrect."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class ExportConfirmTests(unittest.TestCase):
    def test_mark_writes_flags_and_verdict_json(self):
        from gui_app.shared.export_card_confirm import (
            mark_export_confirmed_incorrect,
        )

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "data").mkdir(parents=True, exist_ok=True)
            rec = {"id": 42, "first_name": "TEST", "last_name": "PERSON"}

            with patch(
                "gui_app.shared.verdict_persist.persist_ethnicity_verdict",
                return_value=(True, '{"ethnicity_review":"incorrect"}', ""),
            ), patch(
                "scraper.paths.project_root",
                return_value=root,
            ):
                ok = mark_export_confirmed_incorrect(
                    rec, db_path=str(root / "offenders.db")
                )
            self.assertTrue(ok)
            self.assertIn("incorrect", str(rec.get("flags") or ""))
            verdicts = root / "data" / "report_verdicts.json"
            self.assertTrue(verdicts.is_file())
            data = json.loads(verdicts.read_text(encoding="utf-8"))
            self.assertEqual(data.get("id:42"), "confirmed")


if __name__ == "__main__":
    unittest.main()
