from __future__ import annotations

import re

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

class DedupeMergeFieldsMixin:
    @staticmethod
    def _row_richness(row: Dict[str, Any]) -> int:
        """How complete a record is — higher is better when choosing a survivor."""
        score = 0
        for col, weight in (
            ("race", 3),
            ("crime", 2),
            ("offense_description", 2),
            ("offense_type", 1),
            ("photo_path", 3),
            ("report_html_path", 2),
            ("source_url", 2),
            ("photo_url", 1),
            ("ethnicity", 1),
            ("date_of_birth", 1),
            ("address", 1),
            ("county", 1),
            ("city", 1),
            ("gender", 1),
            ("risk_level", 1),
            ("state", 1),
        ):
            val = row.get(col)
            if val is not None and str(val).strip():
                score += weight
                # Slight boost for already-merged multi-value fields
                if _MERGE_SEP in str(val):
                    score += 1
        return score


    @staticmethod
    def _normalize_dup_key_part(value: Any) -> str:
        return " ".join(str(value or "").strip().lower().split())


    @staticmethod
    def _split_merged_values(value: Any) -> List[str]:
        """Split a field that may already contain ' | ' unions into distinct parts."""
        raw = str(value or "").strip()
        if not raw:
            return []
        parts: List[str] = []
        seen: set = set()
        for chunk in raw.split(_MERGE_SEP):
            # Also accept semicolon / newline lists from older scrapes
            for piece in re.split(r"[;\n]+", chunk):
                p = " ".join(piece.strip().split())
                if not p:
                    continue
                key = p.casefold()
                if key in seen:
                    continue
                seen.add(key)
                parts.append(p)
        return parts


    @classmethod
    def _union_field_values(cls, *values: Any) -> str:
        """Union distinct non-empty values, preserving first-seen order."""
        parts: List[str] = []
        seen: set = set()
        for v in values:
            for p in cls._split_merged_values(v):
                key = p.casefold()
                if key in seen:
                    continue
                seen.add(key)
                parts.append(p)
        return _MERGE_SEP.join(parts)


