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

class DedupeUrlFlagsMixin:
    @classmethod
    def _url_has_stable_offender_id(cls, url: str) -> bool:
        """True if URL carries a person-specific Id (not a bare portal landing)."""
        raw = (url or "").strip()
        if not raw:
            return False
        try:
            p = urlparse(raw)
            qs = {k.lower(): v for k, v in parse_qsl(p.query, keep_blank_values=True)}
        except Exception:
            return False
        for key in (
            "id", "offenderid", "offender_id", "offenderid", "personid",
            "registrantid", "subjectid",
        ):
            val = (qs.get(key) or "").strip()
            if val and val.lower() not in ("0", "null", "none", "undefined"):
                return True
        # path …/offenders/12345
        path = (p.path or "").strip("/")
        if re.search(r"(?:^|/)(\d{3,})(?:/|$)", path):
            return True
        return False


    @classmethod
    def is_generic_source_url(cls, url: str, *, group_count: int = 1) -> bool:
        """
        True when *url* is likely a shared portal/CAPTCHA page, not a unique
        offender report. High fan-out groups are treated as generic too.

        Portal path markers (e.g. ``sort_public``) alone do **not** mark a URL
        generic when it includes a stable offender ``Id=`` query — those are
        real person pages that may only differ by session ``uid``.
        """
        u = (url or "").strip().lower()
        if not u:
            return True
        # Person-specific Id wins over portal path markers
        if cls._url_has_stable_offender_id(url):
            # Still unsafe if absurd fan-out (shared Id mis-scrape)
            if group_count >= 25:
                return True
            return False
        compact = re.sub(r"[\s_\-]+", "", u)
        for m in cls._GENERIC_URL_MARKERS:
            if m.replace("-", "").replace("_", "").replace(" ", "") in compact:
                return True
            if m in u:
                return True
        # Bare search home pages (no query / id segment)
        if group_count >= 8:
            return True
        # Extremely short path after host → landing page
        try:
            path = (urlparse(u).path or "").strip("/")
            if path.count("/") == 0 and len(path) < 12 and group_count > 2:
                return True
        except Exception:
            pass
        return False


