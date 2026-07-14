from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple


from scraper.nsopw.builder_types import *  # noqa: F401,F403
from scraper.database import Database
from scraper.ethnic_names import get_ethnic_database
from scraper.reports.fetcher import ReportFetcher
from scraper.nsopw.client import (
    DEFAULT_JURISDICTIONS,
    NSOPWClient,
    NSOPWOffender,
    normalize_jurisdiction_code,
)
from scraper.nsopw.parallel import JurisdictionReportPool, ReportJob

class BuilderRequeueIncMixin:
    def requeue_incomplete(
        self,
        *,
        need_race: bool = True,
        need_crime: bool = True,
        need_photo: bool = True,
        need_html: bool = False,
        limit: int = 100,
        state: Optional[str] = None,
        source_scope: str = "all",
        ethnicity_filter: Optional[str] = None,
        min_confidence: float = 0.5,
        save_html: bool = True,
        log: Optional[Callable[[str], None]] = None,
        on_update: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_progress: Optional[Callable[[int, int], None]] = None,
    ) -> Dict[str, Any]:
        """
        Re-fetch jurisdiction reports for DB rows missing race/crime/photo/HTML.

        Updates existing offender rows in place (does not insert duplicates).
        on_progress(done, total) is called after each attempt when provided.

        source_scope:
          - ``all`` (default): any record with a source URL
          - ``external_imports``: bulk/direct CSV imports only
          - ``nsopw``: NSOPW-scraped rows only

        ethnicity_filter:
          When set (e.g. ``hispanic``, ``indian``), only rows whose surname
          classifies into that family at *min_confidence* are processed.
        """
        from scraper.database.enrich_scope import filter_records_for_enrich

        def _log(msg: str) -> None:
            if log:
                log(msg)
            else:
                print(msg)

        fetch_limit = max(int(limit), 1)
        scope = (source_scope or "all").strip().lower()
        eth_filt = (ethnicity_filter or "").strip().lower() or None
        if eth_filt == "all":
            eth_filt = None
        if scope != "all" or eth_filt:
            # Over-fetch then filter so the final batch still reaches *limit*.
            fetch_limit = min(max(fetch_limit * 8, fetch_limit), 5000)

        rows = self.db.find_incomplete_reports(
            need_race=need_race,
            need_crime=need_crime,
            need_photo=need_photo,
            need_html=need_html,
            require_url=True,
            limit=fetch_limit,
            state=state,
        )
        filtered, skipped_scope = filter_records_for_enrich(
            rows,
            source_scope=scope,
            ethnicity_filter=eth_filt,
            min_confidence=min_confidence,
            ethnic_db=self.ethnic_db,
        )
        if int(limit) > 0:
            filtered = filtered[: int(limit)]

        summary = {
            "queued": len(filtered),
            "skipped_scope": skipped_scope,
            "attempted": 0,
            "updated": 0,
            "with_race": 0,
            "with_crime": 0,
            "with_photo": 0,
            "with_html": 0,
            "errors": 0,
        }
        total_q = len(filtered)
        scope_note = ""
        if scope != "all" or eth_filt:
            scope_note = (
                f" scope={scope}"
                + (f" ethnicity={eth_filt}" if eth_filt else "")
                + f" (skipped {skipped_scope} by filter)"
            )
        _log(
            f"Requeue incomplete reports: {len(filtered)} candidates "
            f"(need race={need_race} crime={need_crime} photo={need_photo} html={need_html})"
            f"{scope_note}"
        )
        if on_progress:
            try:
                on_progress(0, total_q or 1)
            except Exception:
                pass
        for rec in filtered:
            if self.cancel_check():
                _log("Requeue cancelled.")
                break
            url = (rec.get("source_url") or "").strip()
            if not url:
                continue
            rid = rec.get("id")
            st = (rec.get("state") or rec.get("source_state") or "UNK").upper()
            summary["attempted"] += 1
            if self.report_limiter.wait(self.cancel_check):
                _log("Requeue cancelled (during delay).")
                break
            if self.cancel_check():
                _log("Requeue cancelled.")
                break
            name = (
                (rec.get("full_name") or "").strip()
                or f"{rec.get('first_name') or ''} {rec.get('last_name') or ''}".strip()
                or f"id={rid}"
            )
            fetch_url = self._primary_fetch_url(url, st)
            if not fetch_url:
                summary["errors"] += 1
                _log(f"  [{summary['attempted']}/{total_q}] skip [{st}] {name[:50]} — bad URL")
                continue
            _log(f"  [{summary['attempted']}/{total_q}] Re-fetch [{st}] {name[:50]}")
            try:
                demo = self.reports.fetch_demographics(
                    fetch_url,
                    save_html=save_html,
                    html_dir=self.html_dir,
                    jurisdiction=st,
                )
            except Exception as e:
                summary["errors"] += 1
                _log(f"    ↳ error: {e}")
                continue

            # Build patch from demo + existing
            patch: Dict[str, Any] = {}
            record = dict(rec)
            self._merge_demographics(record, demo)
            if demo.get("report_html_path"):
                record["report_html_path"] = demo["report_html_path"]
            if demo.get("photo_path"):
                record["photo_path"] = demo["photo_path"]
            # Photo from NSOPW-style url on record
            class _Hit:
                image_uri = rec.get("photo_url") or ""

            self._ensure_photo(record, _Hit(), st)

            for key in (
                "race", "ethnicity", "gender", "height", "weight",
                "eye_color", "hair_color", "crime", "offense_type",
                "offense_description", "report_html_path", "photo_path", "photo_url",
                "county", "city", "address", "risk_level",
                "sources_json", "flags",
            ):
                new_v = record.get(key)
                old_v = rec.get(key)
                if new_v is None or new_v == "":
                    continue
                if key in ("sources_json", "flags", "race"):
                    # Always persist multi-source rewrites
                    if new_v != old_v:
                        patch[key] = new_v
                    continue
                if new_v and (not old_v or (key in ("crime",) and new_v != old_v)):
                    # Fill empty; crime may update; race handled above via sources
                    if not old_v or key in (
                        "ethnicity", "crime", "photo_path", "report_html_path"
                    ):
                        if new_v != old_v:
                            patch[key] = new_v

            if patch and rid is not None:
                ok = self.db.update_offender(int(rid), patch)
                if ok:
                    summary["updated"] += 1
                    merged = dict(rec)
                    merged.update(patch)
                    if merged.get("race"):
                        summary["with_race"] += 1
                    if merged.get("crime") or merged.get("offense_description") or merged.get("offense_type"):
                        summary["with_crime"] += 1
                    if merged.get("photo_path"):
                        summary["with_photo"] += 1
                    if merged.get("report_html_path"):
                        summary["with_html"] += 1
                    _log(
                        f"    ↳ updated id={rid} "
                        f"race={patch.get('race') or '—'} "
                        f"crime={(patch.get('crime') or '—')[:40]} "
                        f"{'photo ' if patch.get('photo_path') else ''}"
                        f"{'html' if patch.get('report_html_path') else ''}"
                    )
                    if on_update:
                        try:
                            on_update(merged)
                        except Exception:
                            pass
                else:
                    _log(f"    ↳ no DB change for id={rid}")
            else:
                _log(
                    f"    ↳ no new fields "
                    f"(status={demo.get('report_fetch_status')} "
                    f"{demo.get('report_block_reason') or ''})"
                )

            if on_progress:
                try:
                    on_progress(summary["attempted"], total_q or 1)
                except Exception:
                    pass

        _log(
            f"Requeue done: attempted={summary['attempted']} updated={summary['updated']} "
            f"errors={summary['errors']}"
        )
        return summary


