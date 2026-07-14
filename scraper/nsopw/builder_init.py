from __future__ import annotations

import time
import threading

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

class BuilderInitMixin:
    def __init__(
        self,
        db_path: str = "data/offenders.db",
        delay: float = DEFAULT_SEARCH_DELAY,
        report_delay: float = DEFAULT_REPORT_DELAY,
        html_dir: str = "data/report_pages",
        cancel_check: Optional[Callable[[], bool]] = None,
        # Clients sleep themselves only if >0; builder RateLimiters are primary.
        client_owned_delay: bool = False,
        # Number of parallel report-fetch worker threads. 1 = sequential (old
        # behavior). Each worker gets its own HTTP session and no two workers
        # ever fetch from the same state website at the same time.
        report_threads: int = DEFAULT_REPORT_THREADS,
    ):
        self.db = Database(db_path)
        self.ethnic_db = get_ethnic_database()
        search_delay = max(DEFAULT_MIN_SEARCH_INTERVAL, float(delay))
        report_delay = max(DEFAULT_MIN_REPORT_INTERVAL, float(report_delay))
        self.search_delay = search_delay
        self.report_delay = report_delay
        try:
            self.report_threads = max(1, min(int(report_threads), MAX_REPORT_THREADS))
        except (TypeError, ValueError):
            self.report_threads = DEFAULT_REPORT_THREADS
        # Guards BuildStats mutations made from report worker threads.
        self._stats_lock = threading.Lock()
        # Avoid double-delay: either builder limiter OR client sleep, not both.
        client_search_sleep = search_delay if client_owned_delay else 0.0
        client_report_sleep = report_delay if client_owned_delay else 0.0
        self.client = NSOPWClient(delay=client_search_sleep)
        # Shared cookie jar + captcha queue (manual browser solve → import cookies)
        from scraper.cookie_jar import CaptchaQueue, CookieJarStore

        self.cookie_store = CookieJarStore()
        self.captcha_queue = CaptchaQueue()
        self.reports = ReportFetcher(
            delay=client_report_sleep,
            cookie_store=self.cookie_store,
            captcha_queue=self.captcha_queue,
            use_saved_cookies=True,
        )
        self.search_limiter = RateLimiter(0.0 if client_owned_delay else search_delay)
        self.report_limiter = RateLimiter(0.0 if client_owned_delay else report_delay)
        self.html_dir = Path(html_dir)
        self.html_dir.mkdir(parents=True, exist_ok=True)
        self.cancel_check = cancel_check or (lambda: False)
        self.stats = BuildStats()
        self._known_urls: Set[str] = set()
        self._ensure_query_log()


    def close(self) -> None:
        self.client.close()
        self.reports.close()
        self.db.close()


    def _make_report_fetcher(self) -> ReportFetcher:
        """Build a report fetcher with its own HTTP session for a worker thread.

        Workers share the cookie jar / captcha queue (thread-safe) but must not
        share a session. delay=0 because the pool owns per-state pacing.
        """
        return ReportFetcher(
            delay=0.0,
            cookie_store=self.cookie_store,
            captcha_queue=self.captcha_queue,
            use_saved_cookies=True,
        )


    def _worker_fetch(self, job: ReportJob, fetcher: ReportFetcher) -> None:
        """Fetch one offender's report + photo (runs on a report worker thread).

        Only performs network + file I/O and mutates ``job.record`` (owned by
        this job). Never touches sqlite or aggregate counters other than the
        lock-guarded ``photos_saved``. Per-jurisdiction serialization guarantees
        no two workers hit the same state website at once.
        """
        record = job.record
        demo = fetcher.fetch_demographics(
            job.url,
            save_html=job.save_html,
            html_dir=self.html_dir,
            jurisdiction=job.jurisdiction,
        )
        self._merge_demographics(record, demo)
        if demo.get("report_html_path"):
            record["report_html_path"] = demo["report_html_path"]
        if demo.get("photo_path"):
            record["photo_path"] = demo["photo_path"]
        if demo.get("photo_url") and not record.get("photo_url"):
            record["photo_url"] = demo["photo_url"]
        record["source_url"] = demo.get("report_final_url") or job.url
        # Photo download uses this worker's own session so it stays inside the
        # jurisdiction lock (never a second concurrent hit to the same state).
        self._ensure_photo(record, job.hit, job.jurisdiction, fetcher=fetcher)
        job.demo = demo


    def _apply_report_result_stats(
        self,
        record: Dict[str, Any],
        demo: Dict[str, Any],
        st: str,
        log: Callable[[str], None],
    ) -> None:
        """Fold a completed report fetch into aggregate stats + logs.

        Runs on the calling (main) thread — never in a worker — so BuildStats
        and per-state counters stay single-threaded.
        """
        sst = self._state_stats(st)
        if demo.get("report_fetch_ok"):
            sst.reports_ok += 1
        if demo.get("race"):
            self.stats.reports_with_race += 1
            sst.with_race += 1
        if demo.get("race") or demo.get("ethnicity"):
            self.stats.reports_with_demographics += 1
        if demo.get("report_html_path"):
            self.stats.html_saved += 1
            sst.html_saved += 1
        block = demo.get("report_block_reason") or ""
        status = str(demo.get("report_fetch_status") or "")
        if block or status.startswith("blocked:") or status.startswith("error:"):
            reason = block or status
            sst.blocks[reason] = sst.blocks.get(reason, 0) + 1
            if status.startswith("error:"):
                sst.errors += 1
        if demo.get("needs_manual_captcha"):
            log(
                "    ↳ CAPTCHA/WAF wall — queued for manual browser solve "
                "(Settings → Access assistance: open URL, complete challenge, "
                "import cookies, re-run / requeue)"
            )
        if not demo.get("report_fetch_ok"):
            log(
                f"    ↳ no demographics "
                f"(status={demo.get('report_fetch_status')}"
                f"{', ' + block if block else ''})"
            )
        else:
            crime_snip = (record.get("crime") or demo.get("crime") or "")[:40]
            log(
                f"    ↳ race={demo.get('race') or '—'} "
                f"eth={demo.get('ethnicity') or '—'} "
                f"gender={demo.get('gender') or '—'}"
                f"{' · crime=' + crime_snip if crime_snip else ''}"
                f"{' · photo' if record.get('photo_path') else ''}"
            )


