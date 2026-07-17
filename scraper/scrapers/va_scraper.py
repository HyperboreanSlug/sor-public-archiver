"""Virginia vspsor.com bulk scraper (list API + optional detail enrich)."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence

from .base import BaseScraper
from .normalize import normalize_records
from .va_client import VaVspsorClient
from .va_parse import list_row_to_record, merge_detail_into_record, parse_detail_html

# Public filters from the vspsor Search form.
VALID_FILTERS = frozenset(
    {
        "None",  # All Offenders
        "Homeless",
        "NotIncarcerated",
        "CivillyCommitted",
        "Incarcerated",
        "Wanted",
    }
)


class VAScraper(BaseScraper):
    """
    Harvest Virginia offenders from vspsor.com.

    List data comes from POST ``/search/searchRegistry`` (server-side DataTables).
    Optional per-id GET ``/Offender/Details/{uuid}`` fills race, crime, tier, etc.

    Defaults:
      - filter ``None`` (all public offenders)
      - page size 100
      - detail enrichment on (set fetch_details=False for list-only speed)
    """

    PAGE_SIZE = 100

    def __init__(
        self,
        state_abbr: str = "VA",
        delay: float = 1.0,
        *,
        filter_name: str = "None",
        page_size: int = PAGE_SIZE,
        fetch_details: bool = True,
        max_records: int = 0,
        counties: Optional[Sequence[str]] = None,
        verify_ssl: bool = False,
    ):
        super().__init__(state_abbr or "VA", delay=delay)
        filt = (filter_name or "None").strip()
        if filt not in VALID_FILTERS:
            # Accept lowercase from callers.
            mapped = next((f for f in VALID_FILTERS if f.lower() == filt.lower()), None)
            filt = mapped or "None"
        self.filter_name = filt
        self.page_size = max(1, min(int(page_size or self.PAGE_SIZE), 100))
        self.fetch_details = bool(fetch_details)
        self.max_records = max(0, int(max_records or 0))
        self.counties: Optional[List[str]] = (
            [c.strip() for c in counties if c and str(c).strip()]
            if counties
            else None
        )
        self.verify_ssl = bool(verify_ssl)
        self._client = VaVspsorClient(
            delay=delay, verify_ssl=self.verify_ssl
        )

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass
        super().close()

    def get_direct_download_urls(self) -> List[str]:
        return []

    def scrape(self) -> List[Dict[str, Any]]:
        scopes = self._iter_scopes()
        by_id: Dict[str, Dict[str, Any]] = {}
        for scope_label, county in scopes:
            batch = self._scrape_scope(county=county, label=scope_label)
            for rec in batch:
                oid = str(rec.get("external_id") or "").strip()
                if oid:
                    by_id[oid] = rec
                else:
                    # Should not happen for vspsor rows; keep anyway.
                    by_id[f"_anon_{len(by_id)}"] = rec
            if self.max_records and len(by_id) >= self.max_records:
                break

        records = list(by_id.values())
        if self.max_records and len(records) > self.max_records:
            records = records[: self.max_records]

        if self.fetch_details and records:
            records = self._enrich_details(records)

        # Serialize raw_data_json if still a dict (DB expects text/JSON string).
        for rec in records:
            raw = rec.get("raw_data_json")
            if isinstance(raw, dict):
                rec["raw_data_json"] = json.dumps(raw, ensure_ascii=False)

        print(f"  [VA] Done: {len(records)} records (filter={self.filter_name})")
        return normalize_records(records, state="VA")

    def _iter_scopes(self) -> List[tuple]:
        """Return (label, county_or_empty) scopes to query."""
        if self.counties:
            return [(c, c) for c in self.counties]
        return [("statewide", "")]

    def _scrape_scope(self, *, county: str, label: str) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        start = 0
        total: Optional[int] = None
        page = 0
        while True:
            page += 1
            try:
                data = self._client.search_page(
                    start=start,
                    length=self.page_size,
                    filter_name=self.filter_name,
                    county=county,
                    draw=page,
                )
            except Exception as e:
                print(f"  [VA] {label} page@{start} error: {e}")
                break

            offenders = data.get("offenders") or data.get("data") or []
            if not isinstance(offenders, list):
                offenders = []
            if total is None:
                for key in ("recordsTotal", "recordsFiltered", "totalItems"):
                    if data.get(key) is not None:
                        try:
                            total = int(data[key])
                        except (TypeError, ValueError):
                            total = None
                        if total is not None:
                            break

            added = 0
            for row in offenders:
                if not isinstance(row, dict):
                    continue
                rec = list_row_to_record(row, state="VA")
                if not (rec.get("external_id") or rec.get("full_name")):
                    continue
                records.append(rec)
                added += 1
                if self.max_records and len(records) >= self.max_records:
                    break

            got = len(offenders)
            shown = len(records)
            tot_s = str(total) if total is not None else "?"
            print(
                f"  [VA] {label}: start={start} +{added} "
                f"(scope {shown}/{tot_s})"
            )

            if self.max_records and len(records) >= self.max_records:
                records = records[: self.max_records]
                break
            if got == 0:
                break
            start += got
            if total is not None and start >= total:
                break
            if got < self.page_size:
                break
            # Safety cap (statewide ~26k as of 2026)
            if start > 500_000:
                print(f"  [VA] Safety cap hit at start={start}")
                break
        return records

    def _enrich_details(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        n = len(records)
        for i, rec in enumerate(records, 1):
            oid = str(rec.get("external_id") or "").strip()
            if not oid:
                out.append(rec)
                continue
            try:
                html, final_url = self._client.fetch_detail_html(oid)
            except Exception as e:
                print(f"  [VA] detail {oid[:8]}… error: {e}")
                out.append(rec)
                continue
            if not html:
                out.append(rec)
                continue
            detail = parse_detail_html(html, base_url=final_url or "")
            merged = merge_detail_into_record(rec, detail)
            if final_url and not merged.get("source_url"):
                merged["source_url"] = final_url
            out.append(merged)
            if i % 50 == 0 or i == n:
                print(f"  [VA] Details {i}/{n}")
        return out
