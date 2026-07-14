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

class BuildNameMergeIndexCsvMixin:
    def _build_name_merge_index(self) -> Dict[str, List[int]]:
        """Map ``LAST|FIRST`` → list of row ids (for CSV merge-into-existing)."""
        idx: Dict[str, List[int]] = defaultdict(list)
        cur = self._conn.execute(
            "SELECT id, first_name, last_name FROM offenders "
            "WHERE last_name IS NOT NULL AND TRIM(last_name) != ''"
        )
        for row in cur:
            last = str(row[2] or "").strip().casefold()
            first = str(row[1] or "").strip().casefold()
            if not last:
                continue
            key = f"{last}|{first.split()[0] if first else ''}"
            idx[key].append(int(row[0]))
        return idx

