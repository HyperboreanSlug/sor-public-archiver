from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple


from scraper.nsopw.builder_types import *  # noqa: F401,F403
from scraper.database import Database
from scraper.ethnic_names import get_ethnic_database
from scraper.reports.fetcher import ReportFetcher
from scraper.nsopw.client import (
    DEFAULT_JURISDICTIONS,
    NSOPWClient,
    NSOPWOffender,
    normalize_jurisdiction_code,
)
from scraper.nsopw.parallel import JurisdictionReportPool, ReportJob

class BuilderEnrichNeedMixin:
    @staticmethod
    def record_needs_enrichment(rec: Dict[str, Any]) -> bool:
        """True if race, crime, photo, URL, or archived HTML is still missing."""
        if not rec:
            return False
        photo = (rec.get("photo_path") or "").strip()
        has_photo = bool(photo) and Path(photo).is_file()
        has_race = bool((rec.get("race") or "").strip())
        has_crime = bool(
            (rec.get("crime") or "").strip()
            or (rec.get("offense_description") or "").strip()
            or (rec.get("offense_type") or "").strip()
        )
        has_url = bool((rec.get("source_url") or "").strip())
        has_html = bool((rec.get("report_html_path") or "").strip()) and Path(
            (rec.get("report_html_path") or "").strip()
        ).exists()
        # Need enrich if any core field is missing
        return not (has_photo and has_race and has_crime and has_url)


