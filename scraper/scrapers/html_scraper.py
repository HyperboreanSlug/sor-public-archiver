"""HTML scraper for registries that expose tabular data on static pages.

Most state SOR sites are JavaScript search apps (CAPTCHA / disclaimer /
session required). Those are marked scrape_method='interactive' and will
not yield bulk records from this scraper.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .base import BaseScraper
from .normalize import normalize_records


class HTMLScraper(BaseScraper):
    """Best-effort extraction from static HTML tables only."""

    def scrape(self) -> List[Dict[str, Any]]:
        from ..config import get_registry_by_abbr

        registry = get_registry_by_abbr(self.state_abbr)
        if not registry:
            return []

        method = (registry.scrape_method or "").lower()
        if method in ("interactive", "unsupported", "manual"):
            print(
                f"  [{self.state_abbr}] Registry is interactive/search-only "
                f"(no bulk scrape). Visit: {registry.registry_url}"
            )
            if registry.download_page:
                print(f"  [{self.state_abbr}] Manual download page: {registry.download_page}")
            return []

        # Prefer direct bulk when present
        if registry.direct_downloads:
            from .direct_download import DirectDownloadScraper

            return DirectDownloadScraper(self.state_abbr, delay=self.delay).scrape()

        url = registry.registry_url
        try:
            resp = self._get(url)
        except requests.RequestException as e:
            print(f"  [{self.state_abbr}] Error fetching {url}: {e}")
            return []

        # SPA shells rarely contain table data
        soup = BeautifulSoup(resp.text, "html.parser")
        records = self._extract_from_tables(soup)

        if not records:
            print(
                f"  [{self.state_abbr}] No static HTML tables with records found. "
                f"Site likely requires interactive search."
            )
            return []

        return normalize_records(records, state=self.state_abbr)

    def _extract_from_tables(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []

        for table in soup.find_all("table"):
            header_cells = table.find_all("th")
            if header_cells:
                headers = [th.get_text(strip=True) for th in header_cells]
            else:
                first_row = table.find("tr")
                if not first_row:
                    continue
                headers = [td.get_text(strip=True) for td in first_row.find_all("td")]

            if not headers or not any(headers):
                continue

            # Skip tiny nav/layout tables
            rows = table.find_all("tr")
            if len(rows) < 3:
                continue

            # Require name-like or identity headers to avoid garbage tables
            header_blob = " ".join(h.lower() for h in headers)
            if not any(
                token in header_blob
                for token in ("name", "offender", "address", "race", "county", "dob")
            ):
                continue

            for row in rows[1:]:
                cells = [td.get_text(strip=True) for td in row.find_all("td")]
                if not cells or len(cells) < 2:
                    continue
                if len(cells) >= len(headers):
                    records.append(dict(zip(headers, cells[: len(headers)])))

        return records

    def get_direct_download_urls(self) -> List[str]:
        from ..config import get_registry_by_abbr

        registry = get_registry_by_abbr(self.state_abbr)
        urls = list(registry.direct_downloads) if registry else []
        if not registry:
            return urls

        try:
            resp = self._get(registry.registry_url)
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if any(ext in href.lower() for ext in (".csv", ".xlsx", ".xls", ".json")):
                    urls.append(urljoin(registry.registry_url, href))
        except requests.RequestException:
            pass

        seen = set()
        unique = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                unique.append(u)
        return unique
