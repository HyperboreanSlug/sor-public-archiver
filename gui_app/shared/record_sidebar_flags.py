"""Merge helpers for arrests.flags ethnicity review / race manual markers."""
from __future__ import annotations

from typing import Any, Dict


def merge_ethnicity_review_flags(raw_flags: Any, verdict: str) -> str:
    """Merge ``ethnicity_review`` into the arrests.flags JSON blob."""
    import json
    from datetime import datetime, timezone

    if isinstance(raw_flags, dict):
        flags: Dict[str, Any] = dict(raw_flags)
    elif isinstance(raw_flags, str) and raw_flags.strip():
        try:
            parsed = json.loads(raw_flags)
            flags = dict(parsed) if isinstance(parsed, dict) else {"notes": raw_flags}
        except Exception:
            flags = {"notes": raw_flags}
    else:
        flags = {}
    flags["ethnicity_review"] = verdict
    flags["ethnicity_reviewed_at"] = datetime.now(timezone.utc).isoformat()
    return json.dumps(flags, ensure_ascii=False, sort_keys=True)


def merge_race_manual_flags(raw_flags: Any) -> str:
    """Mark a manual actual-race override in the arrests.flags JSON blob."""
    import json
    from datetime import datetime, timezone

    if isinstance(raw_flags, dict):
        flags: Dict[str, Any] = dict(raw_flags)
    elif isinstance(raw_flags, str) and raw_flags.strip():
        try:
            parsed = json.loads(raw_flags)
            flags = dict(parsed) if isinstance(parsed, dict) else {"notes": raw_flags}
        except Exception:
            flags = {"notes": raw_flags}
    else:
        flags = {}
    flags["race_manual"] = True
    flags["race_manual_at"] = datetime.now(timezone.utc).isoformat()
    return json.dumps(flags, ensure_ascii=False, sort_keys=True)


def race_manual_override(record_or_flags: Any) -> bool:
    """True when arrests.flags records a manual actual-race override."""
    import json

    raw = record_or_flags
    if isinstance(record_or_flags, dict) and "flags" in record_or_flags:
        raw = record_or_flags.get("flags")
    if isinstance(raw, str) and raw.strip():
        try:
            raw = json.loads(raw)
        except Exception:
            return False
    if not isinstance(raw, dict):
        return False
    return bool(raw.get("race_manual"))
