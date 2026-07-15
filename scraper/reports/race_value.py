"""Plausible race-field checks (reject aliases / addresses)."""
from __future__ import annotations

import re

# Tokens that look like real registry race / ethnicity codes or words.
_RACE_TOKEN_OK = frozenset(
    {
        "white", "black", "asian", "hispanic", "latino", "latina", "latinx",
        "indian", "american", "native", "alaskan", "alaska", "alaskannative",
        "pacific", "islander", "hawaiian", "other", "unknown", "undetermined",
        "multi", "multiracial", "biracial", "caucasian", "african", "middle",
        "eastern", "arab", "arabic", "chinese", "korean", "japanese",
        "vietnamese", "filipino", "thai", "cambodian", "hmong", "samoan",
        "am", "ind", "amin", "amind", "or", "of", "the", "and",
        "a", "b", "w", "h", "i", "u", "o", "api", "nhopi",
        "selection", "no", "not", "specified", "declined", "refused",
    }
)
# City, ST ZIP — address mis-captured as race
_ADDR_RACE_RE = re.compile(
    r"^[A-Za-z .'-]+,\s*[A-Z]{2}\s+\d{5}(?:-\d{4})?$",
    re.I,
)
# LAST, FIRST M — alias mis-captured (require no race tokens)
_NAME_RACE_RE = re.compile(
    r"^[A-Z][A-Za-z'.-]+,\s*[A-Z]([A-Za-z'.-]+|\s+[A-Z]\.?){0,3}$",
)


def is_plausible_race_value(raw: str) -> bool:
    """False for alias names, addresses, or other non-race junk in race fields.

    Guards HTML parsers that can false-match mid-word (TERRACE→Race, HORACE→Race).
    """
    s = re.sub(r"\s+", " ", (raw or "").strip())
    if not s or len(s) > 120:
        return False
    low = s.lower().strip()
    if low in ("n/a", "na", "none", "null", "-", "—", "unknown", "no selection"):
        return True
    # Multi-source: accept if any segment is a real race
    parts = re.split(r"\s*\|\s*", s)
    ok_any = False
    for part in parts:
        p = part.strip()
        # Strip provenance tags like "[GA·html✓]"
        p = re.sub(r"\[[^\]]*\]", "", p).strip()
        if not p:
            continue
        if _ADDR_RACE_RE.match(p):
            continue
        tokens = re.findall(r"[A-Za-z]+", p)
        if not tokens:
            continue
        if any(t.lower() in _RACE_TOKEN_OK for t in tokens):
            ok_any = True
            continue
        # Pure name-shaped with no race tokens → junk
        if _NAME_RACE_RE.match(p):
            continue
        # Single unknown long word without race token → reject (e.g. random)
        if len(tokens) == 1 and len(tokens[0]) > 12:
            continue
        # Unknown multi-token without race words → reject
        if len(tokens) >= 2:
            continue
        # Short single token (e.g. codes) keep
        ok_any = True
    return ok_any
