from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from scraper.searcher_race import (  # noqa: F401
    SearchResults,
    Misclassification,
    _ETHNICITY_COMPATIBLE_RACES,
    _RACE_ALIASES,
    _canonical_race_key,
    format_race_label,
    _ethnicity_family,
    _is_other_or_other_asian,
    _has_hispanic_ethnicity,
    _is_compatible,
    _last_name_from_record,
    _first_name_from_record,
    _middle_name_from_record,
)



class SearcherExportMixin:
    def export_misclassifications(
        self,
        output_path: str,
        min_confidence: float = 0.5,
        limit: int = 10000,
        ethnicity_filter: Optional[str] = None,
    ) -> int:
        """Export misclassified records to CSV."""
        import csv

        misclassifications = self.analyze_ethnicities(
            min_confidence=min_confidence,
            limit=limit,
            ethnicity_filter=ethnicity_filter,
        )

        if not misclassifications:
            return 0

        headers = [
            "first_name", "middle_name", "last_name", "full_name", "race",
            "likely_ethnicity", "confidence", "matching_names", "state", "county",
            "address", "age", "gender", "offense_type",
        ]

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()

            for mc in misclassifications:
                row = {
                    "first_name": mc.record.get("first_name"),
                    "middle_name": mc.record.get("middle_name") or _middle_name_from_record(mc.record or {}),
                    "last_name": mc.record.get("last_name"),
                    "full_name": mc.record.get("full_name"),
                    "race": mc.expected_race,
                    "likely_ethnicity": mc.likely_ethnicity,
                    "confidence": round(mc.confidence, 3),
                    "matching_names": "; ".join(mc.matching_names),
                    "state": mc.record.get("state"),
                    "county": mc.record.get("county"),
                    "address": mc.record.get("address"),
                    "age": mc.record.get("age"),
                    "gender": mc.record.get("gender"),
                    "offense_type": mc.record.get("offense_type"),
                }
                writer.writerow(row)

        return len(misclassifications)


    def export_filtered(
        self,
        output_path: str,
        filters: Dict[str, Any]
    ) -> int:
        """Export filtered records to CSV."""
        return self.db.export_to_csv(output_path, filters=filters)


