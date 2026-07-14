from __future__ import annotations

import re

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

class BuilderQueryLogMixin:
    def _load_known_urls(self) -> None:
        """Cache existing source_url values for O(1) skip-existing checks."""
        try:
            self._known_urls = self.db.existing_source_urls()
        except Exception:
            self._known_urls = set()


    def _ensure_query_log(self) -> None:
        """Track completed NSOPW API queries (first + last token) for resume support.

        Ethnicity is stored for audit only. Skip decisions key on (first, last)
        because the NSOPW name API is not ethnicity-filtered — re-running the same
        first/last under another ethnicity would be a duplicate network search.
        """
        self.db._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS nsopw_query_log (
                first_prefix TEXT NOT NULL,
                surname TEXT NOT NULL,
                ethnicity TEXT NOT NULL DEFAULT '',
                completed_at TEXT NOT NULL,
                hit_count INTEGER DEFAULT 0,
                PRIMARY KEY (first_prefix, surname, ethnicity)
            )
            """
        )
        # Fast lookup by API identity (first + last), any ethnicity
        self.db._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_nsopw_query_log_api
            ON nsopw_query_log (first_prefix, surname)
            """
        )
        self.db._conn.commit()
        # In-memory set of completed (first_upper, last_lower); filled by _load_completed_queries
        self._completed_queries: Set[Tuple[str, str]] = set()


    @staticmethod
    def _query_key(first: str, surname: str) -> Tuple[str, str]:
        """Canonical API search identity: (FIRST, last)."""
        return ((first or "").strip().upper(), (surname or "").strip().lower())


    def _load_completed_queries(self) -> Set[Tuple[str, str]]:
        """Load all completed (first, last) pairs from the DB (any ethnicity)."""
        try:
            rows = self.db._conn.execute(
                "SELECT first_prefix, surname FROM nsopw_query_log"
            ).fetchall()
        except Exception:
            return set()
        out: Set[Tuple[str, str]] = set()
        for row in rows:
            out.add(self._query_key(row[0], row[1]))
        self._completed_queries = out
        return out


    def _state_stats(self, state: str) -> StateReportStats:
        key = (state or "UNK").upper()[:12] or "UNK"
        if key not in self.stats.by_state:
            self.stats.by_state[key] = StateReportStats()
        return self.stats.by_state[key]


    def _query_done(self, first: str, surname: str, ethnicity: str = "") -> bool:
        """True if this first+last API query was completed (ethnicity ignored)."""
        key = self._query_key(first, surname)
        if key in getattr(self, "_completed_queries", ()):
            return True
        # DB fallback (and when set not preloaded)
        row = self.db._conn.execute(
            """
            SELECT 1 FROM nsopw_query_log
            WHERE first_prefix = ? AND surname = ?
            LIMIT 1
            """,
            key,
        ).fetchone()
        if row is not None:
            self._completed_queries.add(key)
            return True
        return False


    def _mark_query_done(
        self, first: str, surname: str, ethnicity: str = "", hit_count: int = 0
    ) -> None:
        from datetime import datetime, timezone

        fp, sn = self._query_key(first, surname)
        if not fp or not sn:
            return
        eth = (ethnicity or "").strip().lower()
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        self.db._conn.execute(
            """
            INSERT INTO nsopw_query_log (first_prefix, surname, ethnicity, completed_at, hit_count)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(first_prefix, surname, ethnicity) DO UPDATE SET
                completed_at = excluded.completed_at,
                hit_count = excluded.hit_count
            """,
            (fp, sn, eth, now, int(hit_count)),
        )
        self.db._conn.commit()
        self._completed_queries.add((fp, sn))


    @staticmethod
    def _html_path_for(url: str, html_dir: Path, jurisdiction: str) -> Path:
        jur = re.sub(r"[^A-Za-z0-9_-]", "", (jurisdiction or "UNK").upper())[:12] or "UNK"
        digest = sha1(url.encode("utf-8", errors="replace")).hexdigest()[:16]
        return Path(html_dir) / jur / f"{digest}.html"


    def _existing_html_path(self, url: str, jurisdiction: str) -> Optional[str]:
        """Return local HTML path if already archived for this URL."""
        if not url:
            return None
        # Prefer DB path if present and file exists
        row = self.db._conn.execute(
            """
            SELECT report_html_path FROM offenders
            WHERE source_url = ? AND report_html_path IS NOT NULL AND report_html_path != ''
            LIMIT 1
            """,
            (url,),
        ).fetchone()
        if row and row["report_html_path"]:
            p = Path(row["report_html_path"])
            if p.is_file() and p.stat().st_size > 100:
                return str(p)
        # Digest path used by ReportFetcher (original URL)
        candidate = self._html_path_for(url, self.html_dir, jurisdiction)
        if candidate.is_file() and candidate.stat().st_size > 100:
            try:
                return str(candidate.relative_to(Path.cwd()))
            except ValueError:
                return str(candidate)
        return None


