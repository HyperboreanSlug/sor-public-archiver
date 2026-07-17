"""Texas DPS SOR scraper — local bulk CSV + optional SID XML enrich."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import BaseScraper
from .normalize import normalize_records
from .tx_client import TxSorClient
from scraper.public_links_tx import (
    extract_tx_sid,
    normalize_tx_dps_url,
    tx_rapsheet_url,
)

# Prefer project downloads folder (existing TX.csv from registry export tooling)
_DEFAULT_CSV_CANDIDATES = (
    Path("data/downloads/TX.csv"),
    Path("data/downloads/tx_offenders.csv"),
    Path("data/downloads/texas_offenders.csv"),
)


class TXScraper(BaseScraper):
    """
    Texas bulk path:

    1. Load ``data/downloads/TX.csv`` when present (registry export already
       normalized into SORPA columns; SIDs in ``external_id`` / ``source_url``).
    2. Rewrite all Texas rapsheet links to live ``sor.dps.texas.gov`` host.
    3. Optionally enrich rows via public GetRapsheetXml (``fetch_details``).

    Full registry ZIP download on the public site requires a free DPS account
    (``/PublicSite/Home/Export``). Place the converted CSV under data/downloads.
    """

    def __init__(
        self,
        state_abbr: str = "TX",
        delay: float = 1.0,
        *,
        csv_path: Optional[str] = None,
        fetch_details: bool = False,
        max_records: int = 0,
        max_xml: int = 0,
    ):
        super().__init__(state_abbr or "TX", delay=delay)
        self.csv_path = Path(csv_path) if csv_path else self._find_csv()
        self.fetch_details = bool(fetch_details)
        self.max_records = max(0, int(max_records or 0))
        self.max_xml = max(0, int(max_xml or 0))
        self._client = TxSorClient(delay=delay)

    def _find_csv(self) -> Optional[Path]:
        for p in _DEFAULT_CSV_CANDIDATES:
            try:
                if p.is_file() and p.stat().st_size > 100:
                    return p
            except OSError:
                continue
        return None

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass
        super().close()

    def get_direct_download_urls(self) -> List[str]:
        return [
            "https://sor.dps.texas.gov/PublicSite/Home/Export",
            "https://sor.dps.texas.gov/PublicSite/Search",
        ]

    def scrape(self) -> List[Dict[str, Any]]:
        records = self._load_csv()
        if not records:
            print(
                "  [TX] No local bulk CSV found. Download registry (free DPS account):\n"
                "       https://sor.dps.texas.gov/PublicSite/Home/Export\n"
                "       Place converted CSV at data/downloads/TX.csv then re-run."
            )
            return []

        if self.max_records:
            records = records[: self.max_records]

        # Always fix dead publicsite rapsheet hosts
        for rec in records:
            self._normalize_tx_fields(rec)

        if self.fetch_details:
            records = self._enrich_xml(records)

        for rec in records:
            raw = rec.get("raw_data_json")
            if isinstance(raw, dict):
                rec["raw_data_json"] = json.dumps(raw, ensure_ascii=False)

        print(f"  [TX] Done: {len(records)} records from {self.csv_path}")
        return normalize_records(records, state="TX")

    def _load_csv(self) -> List[Dict[str, Any]]:
        path = self.csv_path
        if not path or not path.is_file():
            return []
        out: List[Dict[str, Any]] = []
        with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if not row:
                    continue
                rec = {k: (v.strip() if isinstance(v, str) else v) for k, v in row.items() if k}
                # Drop empty strings to None-ish later via normalize
                out.append(rec)
                if self.max_records and len(out) >= self.max_records:
                    break
        print(f"  [TX] Loaded {len(out)} rows from {path}")
        return out

    @staticmethod
    def _normalize_tx_fields(rec: Dict[str, Any]) -> None:
        sid = (
            extract_tx_sid(str(rec.get("source_url") or ""))
            or extract_tx_sid(str(rec.get("external_id") or ""))
            or (str(rec.get("external_id") or "").strip() if str(rec.get("external_id") or "").isdigit() else "")
        )
        if sid and sid.isdigit():
            rec["external_id"] = sid
            rec["source_url"] = tx_rapsheet_url(sid)
        else:
            url = str(rec.get("source_url") or "").strip()
            if url:
                rec["source_url"] = normalize_tx_dps_url(url)
        rec.setdefault("source_state", "TX")
        rec.setdefault("state", "TX")

    def _enrich_xml(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        limit = self.max_xml or len(records)
        done = 0
        for i, rec in enumerate(records):
            if done >= limit:
                break
            sid = str(rec.get("external_id") or "").strip()
            if not sid.isdigit():
                sid = extract_tx_sid(str(rec.get("source_url") or "")) or ""
            if not sid:
                continue
            try:
                detail = self._client.fetch_record(sid)
            except Exception as e:
                print(f"  [TX] XML sid={sid} error: {e}")
                continue
            if not detail:
                continue
            for k, v in detail.items():
                if v in (None, ""):
                    continue
                if k == "external_id":
                    rec[k] = v
                    continue
                if k == "source_url":
                    rec[k] = v
                    continue
                if rec.get(k) in (None, ""):
                    rec[k] = v
            done += 1
            if done % 50 == 0:
                print(f"  [TX] XML enrich {done}/{limit}")
        print(f"  [TX] XML enrich complete: {done}")
        return records
