"""NSOPW ethnic database builder, requeue, and enrich."""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from hashlib import sha1
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import threading

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
from scraper.nsopw.search_plan import *  # noqa: F403

# Report fetching can run on multiple worker threads. Default 1 keeps the
# original sequential behavior; >1 fetches state report pages in parallel
# while never hitting the same state website from two threads at once.
DEFAULT_REPORT_THREADS = 1
MAX_REPORT_THREADS = 16


@dataclass
class StateReportStats:
    hits: int = 0
    reports_attempted: int = 0
    reports_ok: int = 0
    with_race: int = 0
    html_saved: int = 0
    blocks: Dict[str, int] = field(default_factory=dict)
    errors: int = 0


@dataclass
class BuildStats:
    searches: int = 0
    searches_skipped: int = 0
    search_hits: int = 0
    search_hits_matched: int = 0
    search_hits_other: int = 0
    unique_offenders: int = 0
    inserted: int = 0
    inserted_matched: int = 0
    inserted_other: int = 0
    updated: int = 0
    skipped_existing: int = 0
    reports_fetched: int = 0
    reports_skipped_existing_file: int = 0
    reports_with_demographics: int = 0
    reports_with_race: int = 0
    html_saved: int = 0
    photos_saved: int = 0
    errors: List[str] = field(default_factory=list)
    by_state: Dict[str, StateReportStats] = field(default_factory=dict)


class RateLimiter:
    """Minimum interval between *starts* of operations (caller waits then works)."""

    # Poll cancel this often while sleeping (keeps Cancel responsive under 3s+ delays)
    CANCEL_POLL_S = 0.05

    def __init__(self, min_interval: float):
        self.min_interval = max(0.0, float(min_interval))
        self._last = 0.0

    def set_interval(self, min_interval: float) -> None:
        """Update pacing (e.g. GUI changed search/report delay mid-run)."""
        self.min_interval = max(0.0, float(min_interval))

    def wait(self, cancel_check: Optional[Callable[[], bool]] = None) -> bool:
        """
        Wait for min_interval since last operation.

        Returns True if *cancel_check* fired mid-wait (caller should abort).
        Sleeps in short slices so Cancel is felt in ~50ms, not after a full delay.
        """
        if cancel_check and cancel_check():
            return True
        if self.min_interval <= 0:
            self._last = time.monotonic()
            return bool(cancel_check and cancel_check())
        now = time.monotonic()
        remaining = self.min_interval - (now - self._last)
        if remaining <= 0:
            self._last = time.monotonic()
            return bool(cancel_check and cancel_check())
        end = now + remaining
        poll = max(0.02, float(self.CANCEL_POLL_S))
        while True:
            if cancel_check and cancel_check():
                return True
            now = time.monotonic()
            left = end - now
            if left <= 0:
                break
            time.sleep(left if left < poll else poll)
        self._last = time.monotonic()
        return bool(cancel_check and cancel_check())


