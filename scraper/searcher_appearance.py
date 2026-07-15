"""Eye/hair color signals for ethnic misclassification review.

Brown eyes + brown (or black) hair often corroborate Hispanic, South Asian,
MENA, Asian, and African American surname hits when race is recorded as White
(or another mismatch). Light eyes + blond/red hair can reduce confidence that
a non-European surname means a race mismatch.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Canonical color buckets
_EYE_MAP = {
    "bro": "brown",
    "brn": "brown",
    "brown": "brown",
    "blk": "black",
    "black": "black",
    "blu": "blue",
    "blue": "blue",
    "grn": "green",
    "green": "green",
    "haz": "hazel",
    "hazel": "hazel",
    "gry": "gray",
    "gray": "gray",
    "grey": "gray",
    "xxx": "unknown",
    "unk": "unknown",
    "unknown": "unknown",
}
_HAIR_MAP = {
    "bro": "brown",
    "brn": "brown",
    "brown": "brown",
    "blk": "black",
    "black": "black",
    "bln": "blond",
    "blond": "blond",
    "blonde": "blond",
    "red": "red",
    "aub": "red",
    "auburn": "red",
    "sd": "blond",
    "sandy": "blond",
    "gry": "gray",
    "gray": "gray",
    "grey": "gray",
    "whi": "gray",
    "white": "gray",
    "bal": "bald",
    "bald": "bald",
    "xxx": "unknown",
    "unk": "unknown",
    "unknown": "unknown",
}

_DARK_EYES = frozenset({"brown", "black", "hazel"})
_LIGHT_EYES = frozenset({"blue", "green", "gray"})
_DARK_HAIR = frozenset({"brown", "black"})
_LIGHT_HAIR = frozenset({"blond", "red"})


def normalize_color(raw: Any, *, kind: str = "eye") -> str:
    """Map registry codes (BRO, BLK, …) and free text to a color bucket."""
    if raw is None:
        return "unknown"
    text = str(raw).strip().lower()
    if not text or text in ("n/a", "na", "none", "-", "null"):
        return "unknown"
    # Take first token / strip punctuation
    token = re.split(r"[\s,/|;]+", text)[0]
    token = re.sub(r"[^a-z]", "", token)
    table = _EYE_MAP if kind == "eye" else _HAIR_MAP
    if token in table:
        return table[token]
    for key, val in table.items():
        if key in text or text.startswith(key[:3]):
            return val
    return "other"


def _from_raw_json(record: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    raw = record.get("raw_json") or record.get("raw_data_json")
    if not raw:
        return None, None
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return None, None
    if not isinstance(data, dict):
        return None, None
    fields = data.get("fields") if isinstance(data.get("fields"), dict) else data
    eye = hair = None
    for k, v in fields.items():
        lk = str(k).strip().lower().rstrip(":")
        if lk in ("eye", "eyes", "eye color", "eye_color", "eyecolor") and v:
            eye = eye or str(v)
        if lk in ("hair", "hair color", "hair_color", "haircolor") and v:
            hair = hair or str(v)
    return eye, hair


def eye_hair_from_record(record: Optional[Dict[str, Any]]) -> Tuple[str, str]:
    """Return (eye_bucket, hair_bucket) from common column / raw_json shapes."""
    if not record:
        return "unknown", "unknown"
    eye_raw = (
        record.get("eye_color")
        or record.get("eyes")
        or record.get("Eye Color")
        or record.get("Eyes")
    )
    hair_raw = (
        record.get("hair_color")
        or record.get("hair")
        or record.get("Hair Color")
        or record.get("Hair")
    )
    if not eye_raw or not hair_raw:
        j_eye, j_hair = _from_raw_json(record)
        eye_raw = eye_raw or j_eye
        hair_raw = hair_raw or j_hair
    return normalize_color(eye_raw, kind="eye"), normalize_color(hair_raw, kind="hair")


def appearance_label(eye: str, hair: str) -> str:
    if eye == "unknown" and hair == "unknown":
        return ""
    parts = []
    if eye != "unknown":
        parts.append(f"{eye} eyes")
    if hair != "unknown":
        parts.append(f"{hair} hair")
    return " + ".join(parts)


def appearance_adjustment(
    family: str,
    recorded_race_key: str,
    eye: str,
    hair: str,
) -> Tuple[float, List[str]]:
    """
    Confidence delta and human-readable tags for eye/hair vs name family.

    Positive = phenotype supports the name-based ethnicity mismatch.
    Negative = phenotype weakens it (more Northern-European looking).
    """
    if eye == "unknown" and hair == "unknown":
        return 0.0, []
    fam = (family or "").strip().lower()
    race = (recorded_race_key or "").strip().upper()
    tags: List[str] = []
    delta = 0.0
    label = appearance_label(eye, hair)
    dark_pair = eye in _DARK_EYES and hair in _DARK_HAIR
    brown_brown = eye == "brown" and hair == "brown"
    brown_black = eye == "brown" and hair == "black"
    light_pair = eye in _LIGHT_EYES and hair in _LIGHT_HAIR

    # Mismatch context: recorded White (common under-coding for Hispanic/Indian/etc.)
    white_ish = race in ("WHITE", "CAUCASIAN", "W")

    if fam in ("hispanic", "portuguese"):
        if brown_brown:
            delta += 0.10 if white_ish else 0.06
            tags.append("brown eyes + brown hair")
        elif brown_black or (eye == "brown" and hair == "black"):
            delta += 0.12 if white_ish else 0.07
            tags.append("brown eyes + black hair")
        elif dark_pair:
            delta += 0.06 if white_ish else 0.04
            tags.append(label)
        elif light_pair:
            delta -= 0.14
            tags.append(f"light phenotype ({label})")
        elif eye in _LIGHT_EYES:
            delta -= 0.08
            tags.append(f"{eye} eyes")
    elif fam in ("indian", "mena"):
        if brown_black or (eye == "brown" and hair == "black"):
            delta += 0.12 if white_ish else 0.07
            tags.append("brown eyes + black hair")
        elif brown_brown:
            delta += 0.09 if white_ish else 0.05
            tags.append("brown eyes + brown hair")
        elif dark_pair:
            delta += 0.05
            tags.append(label)
        elif light_pair:
            delta -= 0.16
            tags.append(f"light phenotype ({label})")
        elif eye in _LIGHT_EYES:
            delta -= 0.10
            tags.append(f"{eye} eyes")
    elif fam in ("african_american", "african"):
        if brown_black or hair == "black":
            delta += 0.10 if white_ish else 0.05
            tags.append(label or "black hair")
        elif brown_brown:
            delta += 0.06 if white_ish else 0.03
            tags.append("brown eyes + brown hair")
        elif light_pair or eye in _LIGHT_EYES and hair in _LIGHT_HAIR:
            delta -= 0.12
            tags.append(f"light phenotype ({label})")
    elif fam == "asian":
        if hair == "black" and eye in _DARK_EYES:
            delta += 0.10 if white_ish else 0.05
            tags.append(label)
        elif brown_brown:
            delta += 0.06 if white_ish else 0.03
            tags.append("brown eyes + brown hair")
        elif light_pair:
            delta -= 0.14
            tags.append(f"light phenotype ({label})")
    elif fam in ("european", "jewish"):
        # Light phenotype supports European; dark is weak contrary signal only
        if light_pair:
            delta += 0.04
            tags.append(label)
        elif brown_brown or dark_pair:
            # Not a strong contradiction for European (Mediterranean etc.)
            pass

    # Deduplicate tags, keep order
    seen = set()
    uniq = []
    for t in tags:
        if t and t not in seen:
            seen.add(t)
            uniq.append(t)
    return round(delta, 3), uniq


def apply_appearance_signals(
    record: Dict[str, Any],
    likely_ethnicity: str,
    confidence: float,
    matching_names: Optional[Sequence[str]] = None,
    *,
    family: Optional[str] = None,
    race_key: Optional[str] = None,
) -> Tuple[float, List[str], Dict[str, Any]]:
    """
    Adjust confidence and matching_names using eye/hair.

    Returns (new_confidence, new_matching_names, meta).
    """
    from scraper.searcher_race import _canonical_race_key, _ethnicity_family

    names = list(matching_names or [])
    eye, hair = eye_hair_from_record(record)
    fam = family or _ethnicity_family(likely_ethnicity)
    race = race_key or _canonical_race_key(record.get("race") or "")
    delta, tags = appearance_adjustment(fam, race, eye, hair)
    new_conf = round(max(0.05, min(1.0, float(confidence) + delta)), 3)
    for tag in tags:
        note = f"appearance: {tag}"
        if note not in names:
            names.append(note)
    meta = {
        "eye": eye,
        "hair": hair,
        "delta": delta,
        "tags": tags,
        "label": appearance_label(eye, hair),
    }
    if tags:
        record["_appearance_note"] = "; ".join(tags)
        record["_appearance_eye"] = eye
        record["_appearance_hair"] = hair
    return new_conf, names, meta
