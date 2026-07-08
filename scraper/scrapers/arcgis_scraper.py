"""ArcGIS FeatureServer / MapServer query scraper (paginated)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests

from .base import BaseScraper
from .normalize import normalize_records


class ArcGISScraper(BaseScraper):
    """Pull all features from an ArcGIS REST query endpoint."""

    PAGE_SIZE = 1000

    def get_direct_download_urls(self) -> List[str]:
        from ..config import get_registry_by_abbr

        registry = get_registry_by_abbr(self.state_abbr)
        return list(registry.direct_downloads) if registry else []

    def _query_url(self) -> Optional[str]:
        from ..config import get_registry_by_abbr

        registry = get_registry_by_abbr(self.state_abbr)
        return registry.search_api if registry else None

    def scrape(self) -> List[Dict[str, Any]]:
        query_url = self._query_url()
        if not query_url:
            # Fall back to bulk files if configured
            if self.get_direct_download_urls():
                from .direct_download import DirectDownloadScraper

                return DirectDownloadScraper(self.state_abbr, delay=self.delay).scrape()
            print(f"  [{self.state_abbr}] No ArcGIS query URL configured.")
            return []

        records: List[Dict[str, Any]] = []
        offset = 0

        while True:
            params = {
                "where": "1=1",
                "outFields": "*",
                "returnGeometry": "false",
                "f": "json",
                "resultOffset": offset,
                "resultRecordCount": self.PAGE_SIZE,
            }
            try:
                resp = self._get(query_url, params=params)
                data = resp.json()
            except (requests.RequestException, ValueError) as e:
                print(f"  [{self.state_abbr}] ArcGIS error at offset {offset}: {e}")
                break

            if data.get("error"):
                print(f"  [{self.state_abbr}] ArcGIS API error: {data['error']}")
                break

            features = data.get("features") or []
            if not features:
                break

            for feat in features:
                attrs = feat.get("attributes") if isinstance(feat, dict) else None
                if isinstance(attrs, dict):
                    records.append(attrs)

            print(f"  [{self.state_abbr}] ArcGIS offset {offset}: +{len(features)} (total {len(records)})")

            if not data.get("exceededTransferLimit") and len(features) < self.PAGE_SIZE:
                break
            if len(features) == 0:
                break
            offset += len(features)

            # Safety cap
            if offset > 500_000:
                print(f"  [{self.state_abbr}] Safety cap reached.")
                break

        if not records and self.get_direct_download_urls():
            print(f"  [{self.state_abbr}] ArcGIS empty; trying direct download fallback.")
            from .direct_download import DirectDownloadScraper

            return DirectDownloadScraper(self.state_abbr, delay=self.delay).scrape()

        return normalize_records(records, state=self.state_abbr)
