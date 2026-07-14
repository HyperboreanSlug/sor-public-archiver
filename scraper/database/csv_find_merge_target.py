from __future__ import annotations

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

class FindMergeTargetCsvMixin:
    def _find_merge_target(
        self,
        rec: Dict[str, Any],
        name_index: Dict[str, List[int]],
    ) -> Optional[int]:
        """
        Find an existing row that is the same person as *rec*.

        Uses multi-identifier scoring (``scraper.database.identity``):
          - external_id match (if no DOB/middle hard conflict)
          - first + last + DOB / middle / height+weight / location
          - **never** first+last alone
          - hard-reject on conflicting DOB or middle names
            (e.g. NIRAJ V + 1978  vs  NIRAJ RASHMIBABU + 1973)
        """
        from scraper.database.identity import should_merge_records, score_identity_match

        ext = str(rec.get("external_id") or "").strip()
        if ext:
            rows = self._conn.execute(
                "SELECT * FROM offenders WHERE external_id = ? LIMIT 5",
                (ext,),
            ).fetchall()
            if len(rows) == 1:
                existing = dict(rows[0])
                ok, _score, reasons = should_merge_records(
                    rec, existing, min_score=5, unique_name_candidate=True
                )
                # Same registry id: allow unless hard reject
                _, _, hard = score_identity_match(rec, existing)
                if not hard:
                    return int(existing["id"])
                return None
            if len(rows) > 1:
                # Prefer best multi-id score among same-ext rows
                best_id, best_sc = None, -1
                for r in rows:
                    existing = dict(r)
                    ok, sc, _ = should_merge_records(rec, existing, min_score=5)
                    _, _, hard = score_identity_match(rec, existing)
                    if hard:
                        continue
                    if sc > best_sc:
                        best_sc, best_id = sc, int(existing["id"])
                return best_id

        last = str(rec.get("last_name") or "").strip().casefold()
        first = str(rec.get("first_name") or "").strip().casefold()
        if not last or not first:
            return None
        key = f"{last}|{first.split()[0]}"
        candidates = name_index.get(key) or []
        if not candidates:
            return None

        placeholders = ",".join("?" * len(candidates[:80]))
        rows = self._conn.execute(
            f"SELECT * FROM offenders WHERE id IN ({placeholders})",
            candidates[:80],
        ).fetchall()
        unique_name = len(candidates) == 1
        best_id = None
        best_score = -1
        for r in rows:
            existing = dict(r)
            ok, sc, reasons = should_merge_records(
                rec,
                existing,
                min_score=6,
                unique_name_candidate=unique_name,
            )
            if not ok:
                continue
            if sc > best_score:
                best_score = sc
                best_id = int(existing["id"])
        return best_id

