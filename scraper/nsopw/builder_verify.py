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

class BuilderVerifyMixin:
    def verify_all_sources(
        self,
        *,
        limit: int = 100,
        state: Optional[str] = None,
        only_unverified: bool = True,
        save_html: bool = True,
        log: Optional[Callable[[str], None]] = None,
        on_progress: Optional[Callable[[int, int], None]] = None,
    ) -> Dict[str, Any]:
        """
        For each offender, attempt HTML verification of every source that has a URL.

        Updates sources_json html_verified / html_status / fields from the live
        (or archived) report page so bulk CSV values stay tagged separately from
        jurisdiction HTML values.
        """
        from scraper.database.sources import (
            dumps_sources,
            jurisdiction_from_url,
            make_source,
            parse_sources,
            apply_sources_to_record,
        )

        def _log(msg: str) -> None:
            if log:
                log(msg)
            else:
                print(msg)

        def _split_urls(raw: str) -> List[str]:
            try:
                from scraper.public_links import split_source_urls as _split

                parts = _split(raw or "")
                if parts:
                    return list(parts)
            except Exception:
                pass
            return [u.strip() for u in str(raw or "").split(" | ") if u.strip()]

        sql = "SELECT * FROM offenders WHERE 1=1"
        params: List[Any] = []
        if state:
            sql = self.db._append_state_filter(sql, params, state)  # type: ignore[attr-defined]
        sql += " ORDER BY id ASC"
        if limit and int(limit) > 0:
            sql += " LIMIT ?"
            params.append(int(limit))

        rows = [dict(r) for r in self.db._conn.execute(sql, params).fetchall()]
        summary = {
            "rows": len(rows),
            "sources_attempted": 0,
            "sources_verified": 0,
            "sources_failed": 0,
            "rows_updated": 0,
            "errors": 0,
        }
        total = len(rows)
        _log(
            f"Verify sources HTML: {total} rows "
            f"(only_unverified={only_unverified})"
        )
        if on_progress:
            try:
                on_progress(0, total or 1)
            except Exception:
                pass

        for i, rec in enumerate(rows):
            if self.cancel_check():
                _log("Verify sources cancelled.")
                break

            sources = parse_sources(rec.get("sources_json"))
            urls = _split_urls(str(rec.get("source_url") or ""))

            existing_urls = {
                str(s.get("source_url") or "").strip().lower()
                for s in sources
                if s.get("source_url")
            }
            for u in urls:
                if u.strip().lower() not in existing_urls:
                    j = jurisdiction_from_url(u) or str(rec.get("state") or "")
                    sources.append(
                        make_source(
                            source_type="report_html",
                            jurisdiction=j,
                            origin="source_url",
                            source_url=u,
                            fields={},
                            html_verified=False,
                            html_status="pending",
                        )
                    )

            if not sources:
                if on_progress:
                    try:
                        on_progress(i + 1, total or 1)
                    except Exception:
                        pass
                continue

            record = dict(rec)
            record["sources_json"] = dumps_sources(sources)
            changed = False

            for src in list(sources):
                if self.cancel_check():
                    break
                surl = str(src.get("source_url") or "").strip()
                if not surl:
                    if src.get("html_status") != "no_url":
                        src["html_status"] = "no_url"
                        changed = True
                    continue
                if only_unverified and src.get("html_verified"):
                    continue

                st = (
                    str(src.get("jurisdiction") or rec.get("state") or "UNK")
                    .split(" | ")[0]
                    .strip()
                    .upper()
                )
                summary["sources_attempted"] += 1
                if self.report_limiter.wait(self.cancel_check):
                    break
                _log(
                    f"  [{i+1}/{total}] verify [{st}] "
                    f"{(rec.get('first_name') or '')} {(rec.get('last_name') or '')} "
                    f"← {surl[:80]}"
                )
                try:
                    demo = self.reports.fetch_demographics(
                        surl,
                        save_html=save_html,
                        html_dir=self.html_dir,
                        jurisdiction=st,
                    )
                except Exception as e:
                    summary["errors"] += 1
                    summary["sources_failed"] += 1
                    src["html_status"] = f"error:{e}"
                    src["html_verified"] = False
                    changed = True
                    _log(f"    ↳ error: {e}")
                    continue

                self._merge_demographics(record, demo)
                # _merge_demographics already attached report source; refresh flags
                changed = True
                if demo.get("report_fetch_ok"):
                    summary["sources_verified"] += 1
                    _log(
                        f"    ↳ ok race={demo.get('race') or '—'} "
                        f"html={demo.get('report_html_path') or '—'}"
                    )
                else:
                    summary["sources_failed"] += 1
                    _log(
                        f"    ↳ fail status={demo.get('report_fetch_status')} "
                        f"{demo.get('report_block_reason') or ''}"
                    )

            if changed:
                apply_sources_to_record(record)
                patch = {
                    k: record.get(k)
                    for k in (
                        "sources_json", "race", "flags", "report_html_path",
                        "photo_path", "photo_url", "crime", "ethnicity",
                        "gender", "height", "weight", "eye_color", "hair_color",
                        "county", "city", "address",
                    )
                    if record.get(k) is not None and record.get(k) != rec.get(k)
                }
                if patch and rec.get("id") is not None:
                    if self.db.update_offender(int(rec["id"]), patch):
                        summary["rows_updated"] += 1

            if on_progress:
                try:
                    on_progress(i + 1, total or 1)
                except Exception:
                    pass

        _log(
            f"Verify sources done: attempted={summary['sources_attempted']} "
            f"verified={summary['sources_verified']} failed={summary['sources_failed']} "
            f"rows_updated={summary['rows_updated']}"
        )
        return summary


