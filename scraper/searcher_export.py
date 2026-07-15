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
            "likely_ethnicity", "confidence", "matching_names",
            "eye_color", "hair_color", "appearance",
            "state", "county",
            "address", "age", "gender", "offense_type",
        ]

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()

            for mc in misclassifications:
                rec = mc.record or {}
                row = {
                    "first_name": rec.get("first_name"),
                    "middle_name": rec.get("middle_name") or _middle_name_from_record(rec),
                    "last_name": rec.get("last_name"),
                    "full_name": rec.get("full_name"),
                    "race": mc.expected_race,
                    "likely_ethnicity": mc.likely_ethnicity,
                    "confidence": round(mc.confidence, 3),
                    "matching_names": "; ".join(mc.matching_names),
                    "eye_color": rec.get("eye_color") or rec.get("eyes") or "",
                    "hair_color": rec.get("hair_color") or rec.get("hair") or "",
                    "appearance": rec.get("_appearance_note") or "",
                    "state": rec.get("state"),
                    "county": rec.get("county"),
                    "address": rec.get("address"),
                    "age": rec.get("age"),
                    "gender": rec.get("gender"),
                    "offense_type": rec.get("offense_type"),
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


