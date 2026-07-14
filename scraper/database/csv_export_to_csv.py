from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from scraper.database.csv_helpers import *  # noqa: F401,F403
from scraper.database.constants import (
    SCHEMA_VERSION,
    DUPLICATE_STRATEGIES,
    DEFAULT_DEDUPE_STRATEGIES,
    _VOLATILE_URL_PARAMS,
    _MERGE_SEP,
    _MERGE_UNION_FIELDS,
    DEFAULT_DB_PATH,
    _OFFENDER_INSERT_COLUMNS,
    _OFFENDER_INSERT_SQL,
    _record_to_insert_tuple,
    _utc_now_iso,
    _escape_like,
)

class ExportToCsvCsvMixin:
    def export_to_csv(
        self,
        output_path: str,
        filters: Optional[Dict[str, Any]] = None
    ) -> int:
        """Export records to CSV. Returns count exported."""
        import csv as csv_module

        query = "SELECT * FROM offenders"
        params: List[Any] = []

        if filters:
            conditions = []
            if filters.get("state") and str(filters["state"]).upper() != "ALL":
                conditions.append("UPPER(state) = UPPER(?)")
                params.append(filters["state"])
            if filters.get("race"):
                conditions.append("UPPER(race) = UPPER(?)")
                params.append(filters["race"])
            if filters.get("name"):
                conditions.append(
                    "(full_name LIKE ? ESCAPE '\\' OR first_name LIKE ? ESCAPE '\\' "
                    "OR last_name LIKE ? ESCAPE '\\')"
                )
                term = f"%{_escape_like(str(filters['name']))}%"
                params.extend([term, term, term])
            if conditions:
                query += " WHERE " + " AND ".join(conditions)

        rows = self._conn.execute(query, params).fetchall()
        if not rows:
            # Write header-only file from known columns so callers don't crash
            fieldnames = ["id", *_OFFENDER_INSERT_COLUMNS, "scraped_at"]
            with open(output_path, "w", newline="", encoding="utf-8") as f:
                writer = csv_module.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
            return 0

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv_module.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            for row in rows:
                writer.writerow(dict(row))

        return len(rows)

