from __future__ import annotations

import re

from typing import Any, Dict, List, Optional, Tuple

from scraper.database.csv_helpers import *  # noqa: F401,F403
from scraper.database.constants import (
    SCHEMA_VERSION,
    DUPLICATE_STRATEGIES,
    DEFAULT_DEDUPE_STRATEGIES,
    _VOLATILE_URL_PARAMS,
    _MERGE_SEP,
    _MERGE_UNION_FIELDS,
    DEFAULT_DB_PATH,
    _OFFENDER_INSERT_COLUMNS,
    _OFFENDER_INSERT_SQL,
    _record_to_insert_tuple,
    _utc_now_iso,
    _escape_like,
)

class BackfillSourcesCsvMixin:
    def backfill_sources(
        self,
        *,
        limit: Optional[int] = None,
        only_missing: bool = True,
        log: Optional[Any] = None,
    ) -> Dict[str, int]:
        """
        Tag existing offender rows with at least one sources_json entry.

        Infers origin from URL / flags / bulk race-code fingerprint so legacy
        imports (e.g. FL SOR letter races) are provenance-tagged.
        """
        from scraper.database.sources import (
            apply_sources_to_record,
            infer_source_type,
            parse_sources,
            source_from_record_snapshot,
            jurisdiction_from_url,
            attach_source_to_record,
            make_source,
        )

        def _log(msg: str) -> None:
            if log:
                log(msg)

        sql = "SELECT * FROM offenders"
        if only_missing:
            sql += (
                " WHERE sources_json IS NULL OR TRIM(sources_json) = '' "
                "OR sources_json = '[]' OR sources_json = 'null'"
            )
        sql += " ORDER BY id ASC"
        params: Tuple = ()
        if limit and int(limit) > 0:
            sql += " LIMIT ?"
            params = (int(limit),)

        rows = self._conn.execute(sql, params).fetchall()
        updated = 0
        multi = 0
        for row in rows:
            rec = dict(row)
            existing = parse_sources(rec.get("sources_json"))
            if only_missing and existing:
                continue

            stype, origin, html_status = infer_source_type(rec)
            race = str(rec.get("race") or "").strip()
            height = str(rec.get("height") or "").strip()
            letter_race = bool(re.fullmatch(r"[WBAIU]", race.upper()))
            bulk_height = bool(re.fullmatch(r"\d{3}", height))
            looks_like_fl_bulk = letter_race and bulk_height

            urls = [
                u.strip()
                for u in str(rec.get("source_url") or "").split(" | ")
                if u.strip()
            ]

            # Case: bulk demographics (FL letter race) later enriched with a
            # jurisdiction URL (e.g. CO). Keep two sources so race is not
            # falsely attributed to the CO HTML link.
            if looks_like_fl_bulk and urls:
                bulk_fields = {
                    k: rec.get(k)
                    for k in (
                        "race", "height", "weight", "eye_color", "hair_color",
                        "gender", "date_of_birth",
                    )
                    if rec.get(k) not in (None, "")
                }
                bulk = make_source(
                    source_type="csv_bulk",
                    jurisdiction="FL",
                    origin="fl_sor",
                    label="FL SOR CSV (inferred)",
                    external_id=str(rec.get("external_id") or ""),
                    fields=bulk_fields,
                    html_verified=False,
                    html_status="no_url",
                )
                attach_source_to_record(rec, bulk, prefer_new_fields=False, apply_display=False)

                for u in urls:
                    j = jurisdiction_from_url(u) or str(rec.get("state") or "")
                    if " | " in str(j):
                        j = str(j).split(" | ", 1)[0].strip()
                    # URL-side source: location/identity, not bulk letter race
                    url_fields = {
                        k: rec.get(k)
                        for k in (
                            "gender", "date_of_birth", "age", "city", "address",
                            "zip_code", "county", "state", "photo_url", "photo_path",
                            "report_html_path", "crime",
                        )
                        if rec.get(k) not in (None, "")
                    }
                    # Prefer full-word races already on the row if not letter-only
                    if race and not letter_race:
                        url_fields["race"] = race
                    url_src = make_source(
                        source_type="nsopw_report" if "nsopw" in str(rec.get("flags") or "").lower() else "report_html",
                        jurisdiction=j or "UNK",
                        origin="source_url",
                        source_url=u,
                        external_id=str(rec.get("external_id") or ""),
                        fields=url_fields,
                        html_path=str(rec.get("report_html_path") or "") or None,
                        html_verified=False,
                        html_status="pending",
                    )
                    attach_source_to_record(
                        rec, url_src, prefer_new_fields=False, apply_display=False
                    )
                apply_sources_to_record(rec)
            elif len(urls) > 1:
                for u in urls:
                    j = jurisdiction_from_url(u) or str(rec.get("state") or "")
                    src = source_from_record_snapshot(
                        {**rec, "source_url": u, "state": j, "source_state": j},
                        source_type=stype,
                        jurisdiction=j,
                        origin=origin,
                        html_verified=False,
                        html_status="pending",
                    )
                    attach_source_to_record(
                        rec, src, prefer_new_fields=False, apply_display=False
                    )
                apply_sources_to_record(rec)
            else:
                jur = (
                    str(rec.get("source_state") or "").strip()
                    or jurisdiction_from_url(str(rec.get("source_url") or ""))
                    or str(rec.get("state") or "").strip()
                )
                if " | " in jur:
                    jur = jur.split(" | ", 1)[0].strip()
                html_verified = html_status == "ok"
                src = source_from_record_snapshot(
                    rec,
                    source_type=stype,
                    jurisdiction=jur,
                    origin=origin,
                    html_verified=html_verified,
                    html_status=html_status if urls else "no_url",
                )
                if origin == "fl_sor_style" or looks_like_fl_bulk:
                    src["label"] = "FL SOR CSV (inferred)"
                    src["jurisdiction"] = "FL"
                    src["origin"] = "fl_sor"
                    src["type"] = "csv_bulk"
                elif origin == "ga_sor_style":
                    src["label"] = "GA SOR CSV (inferred)"
                    src["jurisdiction"] = src.get("jurisdiction") or "GA"
                    src["origin"] = "sor"
                    src["type"] = "csv_bulk"
                attach_source_to_record(rec, src, prefer_new_fields=False)

            patch = {
                "sources_json": rec.get("sources_json"),
                "race": rec.get("race"),
                "flags": rec.get("flags"),
            }
            if self.update_offender(int(rec["id"]), patch):
                updated += 1
                if "multi_source_race" in str(rec.get("flags") or ""):
                    multi += 1
            if updated and updated % 10000 == 0:
                _log(f"  backfill_sources: {updated} rows…")

        _log(f"backfill_sources: updated={updated} multi_source_race≈{multi}")
        return {"updated": updated, "scanned": len(rows), "multi_source_race": multi}

