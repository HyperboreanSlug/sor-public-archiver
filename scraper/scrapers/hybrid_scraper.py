"""Hybrid scraper - uses direct downloads when available, falls back to HTML/API."""

import csv
from typing import List, Dict, Any

import requests
from bs4 import BeautifulSoup

from .base import BaseScraper


class HybridScraper(BaseScraper):
    """Combines direct downloads with HTML scraping for maximum coverage."""

    def __init__(self, state_abbr: str, delay: float = 2.0):
        super().__init__(state_abbr, delay)

    def scrape(self) -> List[Dict[str, Any]]:
        """Try direct download first, then fall back to HTML scraping."""
        from ..config import get_registry_by_abbr
        registry = get_registry_by_abbr(self.state_abbr)
        if not registry:
            return []

        # Try direct downloads first
        records = self._try_direct_download(registry.direct_downloads)
        if records:
            print(f"  [{self.state_abbr}] Got {len(records)} records from direct download")
            return records

        # Fall back to HTML scraping
        records = self._scrape_html(registry.registry_url)
        if records:
            print(f"  [{self.state_abbr}] Got {len(records)} records from HTML scrape")
            return records

        return []

    def _try_direct_download(self, urls: List[str]) -> List[Dict[str, Any]]:
        """Try to download and parse direct CSV/JSON files."""
        for url in urls:
            try:
                resp = self._get(url)
                content_type = resp.headers.get("Content-Type", "").lower()
                url_lower = url.lower()
                if "json" in content_type or url_lower.endswith(".json"):
                    return self._parse_json(resp.json())
                if "csv" in content_type or url_lower.endswith(".csv") or "text/" in content_type:
                    return self._parse_csv_text(resp.text)
                # Fallbacks
                try:
                    return self._parse_json(resp.json())
                except ValueError:
                    return self._parse_csv_text(resp.text)

            except requests.RequestException as e:
                print(f"  [{self.state_abbr}] Direct download failed for {url}: {e}")

        # Also check the download_page if available
        from ..config import get_registry_by_abbr
        registry = get_registry_by_abbr(self.state_abbr)
        if registry and registry.download_page:
            try:
                resp = self._get(registry.download_page)
                soup = BeautifulSoup(resp.text, "html.parser")

                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if any(ext in href.lower() for ext in (".csv", ".xlsx")):
                        full_url = self._resolve_url(href, registry.download_page)
                        resp2 = self._get(full_url)
                        return self._parse_csv_text(resp2.text)

            except requests.RequestException as e:
                print(f"  [{self.state_abbr}] Download page error: {e}")

        return []

    def _scrape_html(self, url: str) -> List[Dict[str, Any]]:
        """Scrape offender data from HTML tables."""
        try:
            resp = self._get(url)
            soup = BeautifulSoup(resp.text, "html.parser")

            records = []
            for table in soup.find_all("table"):
                header_cells = table.find_all("th")
                if header_cells:
                    headers = [th.get_text(strip=True).lower() for th in header_cells]
                else:
                    first_row = table.find("tr")
                    if not first_row:
                        continue
                    headers = [td.get_text(strip=True).lower() for td in first_row.find_all("td")]

                if not headers or not any(headers):
                    continue

                rows = table.find_all("tr")
                for row in rows[1:]:
                    cells = [td.get_text(strip=True) for td in row.find_all("td")]
                    if not cells:
                        continue
                    if len(cells) >= len(headers):
                        record = dict(zip(headers, cells[:len(headers)]))
                        records.append(record)

            return records

        except requests.RequestException as e:
            print(f"  [{self.state_abbr}] HTML scrape error: {e}")
            return []

    def _parse_json(self, data) -> List[Dict[str, Any]]:
        """Parse JSON response."""
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            for key in ("results", "data", "records", "items", "offenders"):
                if key in data and isinstance(data[key], list):
                    return data[key]
            return [data]
        return []

    def _parse_csv_text(self, text: str) -> List[Dict[str, Any]]:
        """Parse CSV text."""
        reader = csv.DictReader(text.splitlines())
        records = []
        for row in reader:
            cleaned = {}
            for k, v in row.items():
                if k is not None and v is not None:
                    cleaned[k.strip()] = str(v).strip()
            records.append(cleaned)
        return records

    def _resolve_url(self, href: str, base_url: str) -> str:
        """Resolve relative URLs."""
        from urllib.parse import urljoin
        return urljoin(base_url, href)

    def get_direct_download_urls(self) -> List[str]:
        """Return direct download URLs."""
        from ..config import get_registry_by_abbr
        registry = get_registry_by_abbr(self.state_abbr)
        urls = list(registry.direct_downloads) if registry else []
        if registry and registry.download_page:
            urls.append(registry.download_page)
        return urls