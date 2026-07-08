"""Direct download scraper — bulk CSV/JSON files from public registry sources."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, unquote

import requests

from .base import BaseScraper
from .normalize import normalize_records


class DirectDownloadScraper(BaseScraper):
    """Download and parse published bulk files (CSV/JSON)."""

    def get_direct_download_urls(self) -> List[str]:
        from ..config import get_registry_by_abbr

        registry = get_registry_by_abbr(self.state_abbr)
        return list(registry.direct_downloads) if registry else []

    def scrape(self) -> List[Dict[str, Any]]:
        urls = self.get_direct_download_urls()
        if not urls:
            print(f"  [{self.state_abbr}] No direct download URLs configured.")
            return []

        records: List[Dict[str, Any]] = []
        errors: List[str] = []

        for url in urls:
            try:
                batch = self._download_and_parse(url)
                if batch:
                    records.extend(batch)
                    print(f"  [{self.state_abbr}] Parsed {len(batch)} records from {url}")
                else:
                    print(f"  [{self.state_abbr}] No records parsed from {url}")
            except requests.HTTPError as e:
                status = e.response.status_code if e.response is not None else "?"
                msg = f"HTTP {status} for {url}"
                if status == 403:
                    msg += " (blocked — site may require a browser download)"
                errors.append(msg)
                print(f"  [{self.state_abbr}] {msg}")
            except requests.RequestException as e:
                msg = f"Request failed for {url}: {e}"
                errors.append(msg)
                print(f"  [{self.state_abbr}] {msg}")

        if not records and errors:
            print(f"  [{self.state_abbr}] All direct downloads failed.")

        return normalize_records(records, state=self.state_abbr)

    def _download_and_parse(self, url: str) -> List[Dict[str, Any]]:
        # Prefer browser-like accept for bulk hosts that gate bots
        resp = self._get(
            url,
            headers={
                "Accept": "text/csv,application/json,application/octet-stream,*/*;q=0.8",
                "Referer": self._referer_for(url),
            },
        )
        content_type = (resp.headers.get("Content-Type") or "").lower()
        # Detect HTML block pages even on 200
        body_start = resp.content[:200].lstrip().lower()
        if body_start.startswith(b"<!doctype") or body_start.startswith(b"<html"):
            raise requests.HTTPError(
                f"Received HTML instead of data file (likely blocked)",
                response=resp,
            )

        url_lower = url.lower()
        text = resp.content.decode("utf-8-sig", errors="replace")

        if "json" in content_type or url_lower.endswith(".json"):
            return self._parse_json(json.loads(text))
        if (
            "csv" in content_type
            or url_lower.endswith(".csv")
            or "text/plain" in content_type
            or "octet-stream" in content_type
            or "text/" in content_type
        ):
            return self._parse_csv_text(text)

        try:
            return self._parse_json(json.loads(text))
        except json.JSONDecodeError:
            return self._parse_csv_text(text)

    def _referer_for(self, url: str) -> str:
        from ..config import get_registry_by_abbr

        registry = get_registry_by_abbr(self.state_abbr)
        if registry and registry.registry_url:
            return registry.registry_url
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}/"

    def _parse_json(self, data: Any) -> List[Dict[str, Any]]:
        if isinstance(data, list):
            return [r for r in data if isinstance(r, dict)]
        if isinstance(data, dict):
            for key in ("results", "data", "records", "offenders", "items", "features"):
                if key in data and isinstance(data[key], list):
                    items = data[key]
                    # ArcGIS-style features
                    if items and isinstance(items[0], dict) and "attributes" in items[0]:
                        return [f["attributes"] for f in items if "attributes" in f]
                    return [r for r in items if isinstance(r, dict)]
            return [data]
        return []

    def _parse_csv_text(self, text: str) -> List[Dict[str, Any]]:
        # utf-8-sig already applied by caller; DictReader handles headers
        reader = csv.DictReader(io.StringIO(text))
        records: List[Dict[str, Any]] = []
        for row in reader:
            cleaned: Dict[str, Any] = {}
            for k, v in row.items():
                if k is None:
                    continue
                key = str(k).replace("\ufeff", "").strip()
                if not key:
                    continue
                cleaned[key] = str(v).strip() if v is not None else None
            if any(cleaned.values()):
                records.append(cleaned)
        return records

    def scrape_to_file(
        self, output_dir: Path, filename: Optional[str] = None
    ) -> List[Path]:
        """Download raw files without re-parsing."""
        urls = self.get_direct_download_urls()
        paths: List[Path] = []
        output_dir.mkdir(parents=True, exist_ok=True)

        for i, url in enumerate(urls):
            try:
                resp = self._get(url, headers={"Referer": self._referer_for(url)})
                raw_name = Path(unquote(urlparse(url).path)).name
                if filename and len(urls) == 1:
                    fname = filename
                elif raw_name and raw_name not in (".", "/"):
                    fname = raw_name
                else:
                    fname = f"{self.state_abbr.lower()}_data_{i + 1}.csv"
                dest = output_dir / fname
                dest.write_bytes(resp.content)
                paths.append(dest)
            except requests.RequestException as e:
                print(f"  [{self.state_abbr}] Error downloading {url}: {e}")

        return paths
