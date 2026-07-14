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

class ImportCsvDirectoryCsvMixin:
    def import_csv_directory(
        self,
        directory: str,
        *,
        skip_existing_urls: bool = True,
        merge_sources: bool = True,
        pattern: str = "*.csv",
    ) -> Dict[str, Any]:
        """Import all CSVs in a directory (e.g. data/downloads)."""
        root = Path(directory)
        if not root.is_dir():
            raise NotADirectoryError(str(root))
        files = sorted(root.glob(pattern))
        summary = {
            "files": 0,
            "imported": 0,
            "skipped": 0,
            "merged": 0,
            "total_rows": 0,
            "errors": [],
        }
        for f in files:
            try:
                st = self._infer_csv_jurisdiction(f.stem, None) or None
                r = self.import_csv(
                    str(f),
                    state=st,
                    skip_existing_urls=skip_existing_urls,
                    merge_sources=merge_sources,
                )
                summary["files"] += 1
                summary["imported"] += r.get("imported", 0)
                summary["skipped"] += r.get("skipped", 0)
                summary["merged"] += r.get("merged", 0)
                summary["total_rows"] += r.get("total_rows", 0)
            except Exception as e:
                summary["errors"].append(f"{f.name}: {e}")
        return summary

