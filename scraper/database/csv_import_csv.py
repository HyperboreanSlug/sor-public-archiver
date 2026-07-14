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

class ImportCsvCsvMixin:
    def import_csv(
        self,
        csv_path: str,
        state: Optional[str] = None,
        *,
        skip_existing_urls: bool = True,
        merge_sources: bool = True,
    ) -> Dict[str, int]:
        """
        Import records from a CSV file.

        Returns dict: {imported, skipped, merged, total_rows}.
        When skip_existing_urls is True, rows with a source_url already in the DB
        are skipped (or source-merged when merge_sources is True).
        """
        import csv as csv_module

        path = Path(csv_path)
        if not path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")

        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            reader = csv_module.DictReader(f)
            raw_rows = [dict(row) for row in reader]

        st = state
        if not st:
            st = self._infer_csv_jurisdiction(path.stem, None) or None

        return self.import_records(
            raw_rows,
            state=st,
            skip_existing_urls=skip_existing_urls,
            source_hint=path.stem,
            merge_sources=merge_sources,
        )

