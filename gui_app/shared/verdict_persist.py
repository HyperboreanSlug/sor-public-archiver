"""Persist ethnicity classification confirmations to offenders.flags."""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from gui_app.shared.record_sidebar_flags import merge_ethnicity_review_flags
from scraper.database import Database
from scraper.ethnicity_review import ethnicity_review_verdict


def persist_ethnicity_verdict(
    db_path: str,
    record: Dict[str, Any],
    verdict: str,
) -> Tuple[bool, Optional[str], str]:
    """
    Write ``ethnicity_review`` into flags and verify the round-trip.

    Returns ``(ok, flags_json, error_message)``. On success, *record* is
    updated in-place with ``id`` and ``flags``.
    """
    verdict = (verdict or "").strip().lower()
    if verdict not in ("correct", "incorrect"):
        return False, None, f"Invalid verdict: {verdict!r}"

    flags_json = merge_ethnicity_review_flags(record.get("flags"), verdict)
    rid = record.get("id")
    source_url = str(record.get("source_url") or "").strip()

    db = Database(db_path)
    try:
        if rid is None and source_url:
            row = db._conn.execute(
                "SELECT id, flags FROM offenders WHERE source_url = ? LIMIT 1",
                (source_url,),
            ).fetchone()
            if row:
                rid = row["id"] if hasattr(row, "keys") else row[0]
                existing = row["flags"] if hasattr(row, "keys") else row[1]
                flags_json = merge_ethnicity_review_flags(existing, verdict)

        if rid is None:
            return False, flags_json, "Record has no database id — import first."

        rid_i = int(rid)
        # Always write; treat missing row as failure after SELECT
        db.update_offender(rid_i, {"flags": flags_json})

        row = db._conn.execute(
            "SELECT flags FROM offenders WHERE id = ?",
            (rid_i,),
        ).fetchone()
        if not row:
            return False, flags_json, f"No offender row for id={rid_i}."
        saved = (
            row["flags"]
            if hasattr(row, "keys")
            else (row[0] if row else None)
        )
        if ethnicity_review_verdict({"flags": saved}) != verdict:
            return (
                False,
                saved if isinstance(saved, str) else flags_json,
                "Save did not stick — flags mismatch after write.",
            )

        record["id"] = rid_i
        record["flags"] = saved if isinstance(saved, str) else flags_json
        return True, record["flags"], ""
    finally:
        db.close()
