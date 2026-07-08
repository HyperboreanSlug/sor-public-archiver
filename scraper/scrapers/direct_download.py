"""Direct download scraper - downloads bulk CSV/JSON files from state registries."""

import csv
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

import requests

from .base import BaseScraper


class DirectDownloadScraper(BaseScraper):
    """Scrapes data by downloading direct bulk files from state registries."""

    def __init__(self, state_abbr: str, delay: float = 2.0):
        super().__init__(state_abbr, delay)

    def get_direct_download_urls(self) -> List[str]:
        """Return URLs for direct downloads (from config)."""
        from ..config import get_registry_by_abbr
        registry = get_registry_by_abbr(self.state_abbr)
        return registry.direct_downloads if registry else []

    def scrape(self) -> List[Dict[str, Any]]:
        """Download and parse all direct download files."""
        urls = self.get_direct_download_urls()
        records: List[Dict[str, Any]] = []

        for url in urls:
            try:
                # Use the shared session (polite delay + retries)
                resp = self._get(url)
                content_type = resp.headers.get("Content-Type", "").lower()
                url_lower = url.lower()

                if "json" in content_type or url_lower.endswith(".json"):
                    data = resp.json()
                    records.extend(self._parse_json(data))
                elif "csv" in content_type or url_lower.endswith(".csv") or "text/" in content_type:
                    records.extend(self._parse_csv_text(resp.text))
                else:
                    # Try JSON first, fall back to CSV
                    try:
                        data = json.loads(resp.text)
                        records.extend(self._parse_json(data))
                    except json.JSONDecodeError:
                        records.extend(self._parse_csv_text(resp.text))

            except requests.RequestException as e:
                print(f"  Error downloading {url}: {e}")

        return records

    def _parse_json(self, data) -> List[Dict[str, Any]]:
        """Parse JSON response into list of record dicts."""
        if isinstance(data, dict):
            # Look for common array fields
            for key in ("results", "data", "records", "offenders", "items"):
                if key in data and isinstance(data[key], list):
                    return data[key]
            return [data]

        elif isinstance(data, list):
            return data

        return []

    def _parse_csv_text(self, text: str) -> List[Dict[str, Any]]:
        """Parse CSV text into list of record dicts."""
        reader = csv.DictReader(text.splitlines())
        records = []
        for row in reader:
            # Clean up values
            cleaned = {}
            for k, v in row.items():
                if k is not None and v is not None:
                    cleaned[k.strip()] = str(v).strip()
            records.append(cleaned)
        return records

    def scrape_to_file(self, output_dir: Path, filename: Optional[str] = None) -> List[Path]:
        """Download all files to the output directory (raw bytes, not re-parsed)."""
        urls = self.get_direct_download_urls()
        paths: List[Path] = []
        output_dir.mkdir(parents=True, exist_ok=True)

        for i, url in enumerate(urls):
            try:
                resp = self._get(url)
                raw_name = Path(url.split("?")[0]).name
                if filename and len(urls) == 1:
                    fname = filename
                elif raw_name:
                    fname = raw_name
                else:
                    fname = f"{self.state_abbr.lower()}_data_{i + 1}.csv"
                dest = output_dir / fname
                dest.write_bytes(resp.content)
                paths.append(dest)
            except requests.RequestException as e:
                print(f"  Error downloading {url}: {e}")

        return paths