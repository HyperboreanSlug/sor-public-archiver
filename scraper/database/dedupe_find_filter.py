from __future__ import annotations

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

class DedupeFindFilterMixin:
    @classmethod
    def _corroboration_token(cls, record: Dict[str, Any]) -> str:
        """Shared address or photo identity used to soft-confirm name+state dups."""
        photo = cls.normalize_identity_url(record.get("photo_url") or "")
        if photo:
            return f"photo:{photo}"
        addr = " ".join(
            str(record.get("address") or "").strip().lower().split()
        )
        city = " ".join(str(record.get("city") or "").strip().lower().split())
        if addr and len(addr) >= 6:
            return f"addr:{addr}|{city}"
        return ""


    @classmethod
    def _filter_name_state_soft_members(
        cls, members: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Keep the largest subset that shares a photo_url or address token.

        Prevents collapsing different people who only share a common name+state.
        """
        buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for m in members:
            tok = cls._corroboration_token(m)
            if tok:
                buckets[tok].append(m)
        if not buckets:
            return []
        best = max(buckets.values(), key=len)
        return best if len(best) >= 2 else []


