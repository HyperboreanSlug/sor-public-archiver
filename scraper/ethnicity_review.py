"""Read ethnicity classification confirmations from offenders.flags."""
from __future__ import annotations

import json
from typing import Any, Dict, Optional


def ethnicity_review_verdict(record: Optional[Dict[str, Any]]) -> str:
    """Return ``correct`` / ``incorrect`` / ``""`` from offenders.flags JSON."""
    if not record:
        return ""
    flags = record.get("flags")
    if isinstance(flags, str) and flags.strip():
        try:
            flags = json.loads(flags)
        except (TypeError, json.JSONDecodeError, ValueError):
            return ""
    if not isinstance(flags, dict):
        return ""
    return str(flags.get("ethnicity_review") or "").strip().lower()
