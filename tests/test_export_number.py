"""Export card numbers: assign once, persist, peek without consuming."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from gui_app.shared.export_card_release import (
    format_export_badge,
    peek_release_number,
    person_card_key,
    release_number_for,
)


class ExportNumberTests(unittest.TestCase):
    def test_assign_once_and_reuse(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "card_release.json"
            a = {
                "id": 101,
                "first_name": "A",
                "last_name": "Test",
                "state": "FL",
                "external_id": "abc101",
            }
            b = {
                "id": 102,
                "first_name": "B",
                "last_name": "Test",
                "state": "FL",
                "external_id": "abc102",
            }
            n1 = release_number_for(a, path=store, persist_db=False)
            n2 = release_number_for(a, path=store, persist_db=False)
            n3 = release_number_for(b, path=store, persist_db=False)
            self.assertEqual(n1, n2)
            self.assertNotEqual(n1, n3)
            self.assertEqual(a.get("export_number"), n1)
            self.assertEqual(peek_release_number(a, path=store), n1)
            # Peek must not invent numbers for unknowns
            c = {"id": 999, "first_name": "Z", "last_name": "Nope", "external_id": "zz"}
            self.assertIsNone(peek_release_number(c, path=store))

    def test_db_value_wins_and_syncs_json(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "card_release.json"
            rec = {
                "id": 55,
                "first_name": "Pre",
                "last_name": "Set",
                "export_number": 42,
                "external_id": "pre42",
            }
            n = release_number_for(rec, path=store, persist_db=False)
            self.assertEqual(n, 42)
            data = json.loads(store.read_text(encoding="utf-8"))
            key = person_card_key(rec)
            self.assertEqual(data["people"].get(key), 42)
            self.assertGreaterEqual(int(data["next"]), 43)

    def test_badge_format(self):
        self.assertEqual(format_export_badge(7), "export #7")
        self.assertEqual(format_export_badge(None), "")
        self.assertEqual(format_export_badge(0), "")

    def test_footer_peek_does_not_mint(self):
        """assign=False only peeks; assign=True is the deliberate export path."""
        from unittest.mock import patch

        from gui_app.shared.export_card_fields import arrest_datetime

        rec = {"id": 777, "first_name": "No", "last_name": "Mint"}
        with patch(
            "gui_app.shared.export_card_release.release_number_for"
        ) as mint, patch(
            "gui_app.shared.export_card_release.peek_release_number",
            return_value=None,
        ):
            self.assertEqual(arrest_datetime(rec, assign=False), "")
            mint.assert_not_called()

        with patch(
            "gui_app.shared.export_card_release.release_number_for",
            return_value=5,
        ) as mint:
            self.assertEqual(arrest_datetime(rec, assign=True), "No. 5")
            mint.assert_called_once()

    def test_footer_shows_existing_without_assign(self):
        from gui_app.shared.export_card_fields import arrest_datetime

        rec = {"id": 1, "export_number": 9, "first_name": "Has", "last_name": "Num"}
        self.assertEqual(arrest_datetime(rec, assign=False), "No. 9")


if __name__ == "__main__":
    unittest.main()
