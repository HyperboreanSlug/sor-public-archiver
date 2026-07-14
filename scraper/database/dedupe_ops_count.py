from __future__ import annotations

import time

from typing import Any, Dict, List, Optional, Set, Tuple

from scraper.database.dedupe_keys import *  # noqa: F401,F403
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

class DedupeOpsCountMixin:
    def count_duplicates(
        self,
        strategies: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Summary of duplicate groups/rows per strategy.

        Returns {
          total_offenders,
          by_strategy: {name: {groups, extra_rows, safe_groups, safe_extra_rows, unsafe_groups}},
          total_extra_rows, total_safe_extra_rows
        }
        """
        strats = list(strategies) if strategies else list(DEFAULT_DEDUPE_STRATEGIES)
        total = self.get_total_count()
        by: Dict[str, Dict[str, int]] = {}
        total_extra = 0
        total_safe_extra = 0
        for s in strats:
            try:
                groups = self.find_duplicate_groups(s, include_unsafe=True)
            except ValueError:
                continue
            groups_n = len(groups)
            extra = sum(max(0, g["count"] - 1) for g in groups)
            safe_groups = [g for g in groups if g.get("safe", True)]
            unsafe_groups = groups_n - len(safe_groups)
            safe_extra = sum(max(0, g["count"] - 1) for g in safe_groups)
            by[s] = {
                "groups": groups_n,
                "extra_rows": extra,
                "safe_groups": len(safe_groups),
                "safe_extra_rows": safe_extra,
                "unsafe_groups": unsafe_groups,
            }
            total_extra += extra
            total_safe_extra += safe_extra
        return {
            "total_offenders": total,
            "by_strategy": by,
            "total_extra_rows": total_extra,
            "total_safe_extra_rows": total_safe_extra,
        }


    def find_misclassifications(
        self,
        expected_race: str,
        likely_ethnicities: Optional[List[str]] = None,
        min_confidence: float = 0.5,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """Find offenders whose stored likely_ethnicity differs from recorded race.

        Note: most analysis uses SexOffenderSearcher.analyze_ethnicities() which
        classifies names at query time. This method only queries pre-computed columns.
        """
        params: List[Any] = [min_confidence]
        if likely_ethnicities is None:
            query = """
                SELECT * FROM offenders
                WHERE likely_ethnicity IS NOT NULL
                    AND name_confidence >= ?
                    AND (race IS NULL OR UPPER(likely_ethnicity) != UPPER(race))
                ORDER BY name_confidence DESC
                LIMIT ?
            """
            params.append(limit)
        else:
            placeholders = ",".join(["?"] * len(likely_ethnicities))
            query = f"""
                SELECT * FROM offenders
                WHERE likely_ethnicity IN ({placeholders})
                    AND name_confidence >= ?
                ORDER BY name_confidence DESC
                LIMIT ?
            """
            params = list(likely_ethnicities) + [min_confidence, limit]
        rows = self._conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]


