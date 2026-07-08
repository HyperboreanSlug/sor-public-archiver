"""HTML-based scraper for state registries that serve data via web pages."""

import re
from typing import List, Dict, Any

import requests
from bs4 import BeautifulSoup

from .base import BaseScraper


class HTMLScraper(BaseScraper):
    """Scrapes data from state registries that serve data via HTML pages."""

    def __init__(self, state_abbr: str, delay: float = 2.0):
        super().__init__(state_abbr, delay)

    def scrape(self) -> List[Dict[str, Any]]:
        """Scrape offender records from the registry's HTML page."""
        from ..config import get_registry_by_abbr
        registry = get_registry_by_abbr(self.state_abbr)
        if not registry:
            return []

        url = registry.registry_url
        records = []

        try:
            resp = self._get(url)
            soup = BeautifulSoup(resp.text, "html.parser")

            # Try to find offender data in various HTML structures
            records.extend(self._extract_from_tables(soup))
            records.extend(self._extract_from_lists(soup))
            records.extend(self._extract_from_cards(soup))

        except requests.RequestException as e:
            print(f"  [{self.state_abbr}] Error scraping {url}: {e}")

        return records

    def _extract_from_tables(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract offender data from HTML tables."""
        records = []

        for table in soup.find_all("table"):
            # Prefer explicit header cells; avoid grabbing the whole <thead> block
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
            start = 1 if rows else 0
            for row in rows[start:]:
                cells = [td.get_text(strip=True) for td in row.find_all("td")]
                if not cells:
                    continue
                if len(cells) >= len(headers):
                    record = dict(zip(headers, cells[:len(headers)]))
                    records.append(record)

        return records

    def _extract_from_lists(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract offender data from HTML lists."""
        records = []

        for li in soup.find_all("li"):
            text = li.get_text(strip=True)
            if len(text) > 10 and any(kw in text.lower() for kw in ("offender", "name", "address")):
                record = {"text": text}
                records.append(record)

        return records

    def _extract_from_cards(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract offender data from card-style layouts."""
        records = []

        for card in soup.find_all(class_=re.compile(r"card|offender|profile", re.I)):
            text = card.get_text(strip=True)
            if len(text) > 50:
                record = {"text": text}
                # Try to extract name (first line or bold text)
                for tag in card.find_all(["h1", "h2", "h3", "b", "strong"]):
                    name_text = tag.get_text(strip=True)
                    if len(name_text) > 3:
                        record["name"] = name_text
                        break
                records.append(record)

        return records

    def get_direct_download_urls(self) -> List[str]:
        """Look for download links in the HTML."""
        from urllib.parse import urljoin
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
                if any(ext in href.lower() for ext in (".csv", ".xlsx", ".xls")):
                    urls.append(urljoin(registry.registry_url, href))
        except requests.RequestException:
            pass

        # Preserve order while deduplicating
        seen = set()
        unique = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                unique.append(u)
        return unique