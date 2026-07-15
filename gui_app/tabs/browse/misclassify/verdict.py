"""Persist Misclassify sidebar classification confirmations."""
from __future__ import annotations

from typing import Any, Dict, Tuple

from gui_app.shared.record_sidebar import merge_race_manual_flags
from gui_app.shared.verdict_persist import persist_ethnicity_verdict
from gui_app.tabs.browse.misclassify.constants import actual_from_stated_race


def apply_misclass_verdict(
    *,
    db_path: str,
    db: Any,
    record: Dict[str, Any],
    verdict: str,
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Persist verification. When *correct*, set actual race from stated race.

    Returns ``(ok, error_or_empty, updated_record)``.
    """
    try:
        ok, flags_json, err = persist_ethnicity_verdict(db_path, record, verdict)
    except Exception as exc:
        return False, str(exc), record
    if not ok:
        return False, err or "unknown error", record
    if flags_json:
        record["flags"] = flags_json

    if verdict == "correct":
        actual = actual_from_stated_race(record.get("race"))
        if actual:
            flags_json = merge_race_manual_flags(record.get("flags"))
            record["flags"] = flags_json
            record["likely_ethnicity"] = actual
            rid = record.get("id")
            if rid is not None:
                try:
                    from scraper.database import Database

                    target = db if db is not None else Database(db_path)
                    close_after = db is None
                    try:
                        target.update_offender(
                            int(rid),
                            {"likely_ethnicity": actual, "flags": flags_json},
                        )
                    finally:
                        if close_after:
                            target.close()
                except Exception as exc:
                    return True, f"actual race not saved: {exc}", record
    return True, "", record
