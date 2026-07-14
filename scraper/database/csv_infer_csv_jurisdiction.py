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

class InferCsvJurisdictionCsvMixin:
    @staticmethod
    def _infer_csv_jurisdiction(path_stem: str, state: Optional[str] = None) -> str:
        """Map filename stem → jurisdiction code (fl_sor → FL, sor → GA, …)."""
        if state and str(state).strip():
            return str(state).strip().upper()
        stem = (path_stem or "").lower().strip()
        stem = stem.replace("_offenders", "").replace("_data", "").replace("-", "_")
        aliases = {
            "fl": "FL",
            "fl_sor": "FL",
            "florida": "FL",
            "florida_sor": "FL",
            "ga": "GA",
            "ga_sor": "GA",
            "sor": "GA",  # GA GBI bulk often named sor.csv
            "georgia": "GA",
            "az": "AZ",
            "dc": "DC",
            "co": "CO",
        }
        if stem in aliases:
            return aliases[stem]
        if len(stem) == 2 and stem.isalpha():
            return stem.upper()
        # fl_sor_export → FL
        for key, code in aliases.items():
            if stem.startswith(key + "_") or stem.endswith("_" + key):
                return code
        return ""

