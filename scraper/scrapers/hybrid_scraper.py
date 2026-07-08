"""Hybrid scraper: direct downloads → download page discovery → static HTML."""

from __future__ import annotations

from typing import Any, Dict, List
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .base import BaseScraper
from .normalize import normalize_records


class HybridScraper(BaseScraper):
    """Try bulk files, then discover links on download_page, then static HTML tables."""

    def scrape(self) -> List[Dict[str, Any]]:
        from ..config import get_registry_by_abbr

        registry = get_registry_by_abbr(self.state_abbr)
        if not registry:
            return []

        # 1) Configured direct URLs
        if registry.direct_downloads:
            from .direct_download import DirectDownloadScraper

            records = DirectDownloadScraper(self.state_abbr, delay=self.delay).scrape()
            if records:
                print(f"  [{self.state_abbr}] Got {len(records)} records from direct download")
                return records

        # 2) Discover CSV links on download_page (no CAPTCHA automation)
        if registry.download_page:
            discovered = self._discover_file_links(registry.download_page)
            if discovered:
                print(f"  [{self.state_abbr}] Found download links: {discovered}")
                # Only auto-fetch plain .csv/.json without captcha walls
                for url in discovered:
                    if self._looks_like_direct_file(url):
                        try:
                            from .direct_download import DirectDownloadScraper

                            # Temporarily use discovered URL via a one-off get
                            scraper = DirectDownloadScraper(self.state_abbr, delay=self.delay)
                            batch = scraper._download_and_parse(url)
                            if batch:
                                print(f"  [{self.state_abbr}] Got {len(batch)} from {url}")
                                return normalize_records(batch, state=self.state_abbr)
                        except requests.RequestException as e:
                            print(f"  [{self.state_abbr}] Could not fetch {url}: {e}")
            print(
                f"  [{self.state_abbr}] Download page requires interactive steps "
                f"(CAPTCHA/email/form). Open: {registry.download_page}"
            )

        # 3) Static HTML tables on registry URL
        records = self._scrape_html_tables(registry.registry_url)
        if records:
            print(f"  [{self.state_abbr}] Got {len(records)} records from HTML tables")
            return normalize_records(records, state=self.state_abbr)

        print(f"  [{self.state_abbr}] No automated bulk source available.")
        return []

    def _looks_like_direct_file(self, url: str) -> bool:
        lower = url.lower().split("?")[0]
        return lower.endswith((".csv", ".json", ".txt", ".zip"))

    def _discover_file_links(self, page_url: str) -> List[str]:
        try:
            resp = self._get(page_url)
        except requests.RequestException as e:
            print(f"  [{self.state_abbr}] Download page error: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        urls: List[str] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            full = urljoin(page_url, href)
            text = (a.get_text(strip=True) or "").lower()
            blob = (href + " " + text).lower()
            if any(
                token in blob
                for token in (".csv", ".xlsx", ".xls", ".json", ".zip", "datafile", "data file", "download")
            ):
                urls.append(full)

        # de-dupe
        seen = set()
        out = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                out.append(u)
        return out

    def _scrape_html_tables(self, url: str) -> List[Dict[str, Any]]:
        try:
            resp = self._get(url)
        except requests.RequestException as e:
            print(f"  [{self.state_abbr}] HTML scrape error: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
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
            header_blob = " ".join(h.lower() for h in headers)
            if not any(t in header_blob for t in ("name", "offender", "address", "race", "county")):
                continue

            rows = table.find_all("tr")
            for row in rows[1:]:
                cells = [td.get_text(strip=True) for td in row.find_all("td")]
                if len(cells) >= len(headers) and len(cells) >= 2:
                    records.append(dict(zip(headers, cells[: len(headers)])))
        return records

    def get_direct_download_urls(self) -> List[str]:
        from ..config import get_registry_by_abbr

        registry = get_registry_by_abbr(self.state_abbr)
        urls = list(registry.direct_downloads) if registry else []
        if registry and registry.download_page:
            urls.append(registry.download_page)
        return urls
