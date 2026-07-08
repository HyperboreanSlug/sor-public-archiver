"""Base scraper class for all state registries."""

import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Dict, Any, Optional

import requests

from ..config import USER_AGENT, DEFAULT_DELAY, MAX_RETRIES, REQUEST_TIMEOUT


class BaseScraper(ABC):
    """Abstract base class for sex offender registry scrapers."""

    def __init__(self, state_abbr: str, delay: float = DEFAULT_DELAY):
        self.state_abbr = state_abbr
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/json,*/*;q=0.8",
        })

    def _request(self, url: str, method: str = "GET", **kwargs) -> requests.Response:
        """Make a request with retries and polite delays."""
        kwargs.setdefault("timeout", REQUEST_TIMEOUT)
        for attempt in range(MAX_RETRIES):
            try:
                resp = self.session.request(method, url, **kwargs)
                resp.raise_for_status()
                time.sleep(self.delay)
                return resp
            except requests.RequestException:
                if attempt == MAX_RETRIES - 1:
                    raise
                time.sleep(self.delay * (attempt + 1))

    def _get(self, url: str, **kwargs) -> requests.Response:
        """Make a GET request."""
        return self._request(url, method="GET", **kwargs)

    def _post(self, url: str, **kwargs) -> requests.Response:
        """Make a POST request."""
        return self._request(url, method="POST", **kwargs)

    @abstractmethod
    def scrape(self) -> List[Dict[str, Any]]:
        """Scrape offender records from the registry. Returns list of record dicts."""
        ...

    @abstractmethod
    def get_direct_download_urls(self) -> List[str]:
        """Return URLs for direct bulk downloads (if available)."""
        ...

    def scrape_to_file(
        self,
        output_dir: Path,
        filename: Optional[str] = None,
        fmt: str = "csv"
    ) -> Path:
        """Scrape and save to a file. Returns the path (empty Path if nothing scraped)."""
        records = self.scrape()
        if not records:
            return Path()

        output_dir.mkdir(parents=True, exist_ok=True)
        fname = filename or f"{self.state_abbr.lower()}_offenders.{fmt}"
        dest = output_dir / fname

        if fmt == "csv":
            import csv
            fieldnames: List[str] = []
            seen = set()
            for record in records:
                for key in record.keys():
                    if key not in seen:
                        seen.add(key)
                        fieldnames.append(key)
            with open(dest, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                for record in records:
                    writer.writerow(record)

        return dest

    def close(self):
        """Close the session."""
        self.session.close()


class ScraperFactory:
    """Create appropriate scraper based on registry config."""

    @staticmethod
    def create(state_abbr: str, delay: float = DEFAULT_DELAY) -> BaseScraper:
        from ..config import get_registry_by_abbr
        from .direct_download import DirectDownloadScraper
        from .api_scraper import APIScraper
        from .html_scraper import HTMLScraper
        from .hybrid_scraper import HybridScraper

        registry = get_registry_by_abbr(state_abbr)
        if not registry:
            raise ValueError(f"Unknown state abbreviation: {state_abbr}")

        method = (registry.scrape_method or "").lower().strip()

        # Prefer direct bulk files whenever they are configured, regardless of
        # a mis-set scrape_method (common config mistake for AZ/DC/GA).
        if method in ("direct", "direct_download", "download") or (
            registry.direct_downloads and method not in ("hybrid",)
        ):
            if registry.direct_downloads:
                return DirectDownloadScraper(state_abbr, delay=delay)

        if method == "api":
            return APIScraper(state_abbr, delay=delay)
        if method == "html":
            return HTMLScraper(state_abbr, delay=delay)
        if method == "hybrid":
            return HybridScraper(state_abbr, delay=delay)

        # Default: direct download if available, otherwise HTML
        if registry.direct_downloads:
            return DirectDownloadScraper(state_abbr, delay=delay)
        return HTMLScraper(state_abbr, delay=delay)