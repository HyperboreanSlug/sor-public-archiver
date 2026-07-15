"""Display confidence: name-only or name + DeepFace combined.

When a DeepFace scan is available, blend surname confidence with face support
for the same ethnicity (same weights as ``mugshot_ethnicity.verify``):

    combined = 0.45 * name_confidence + 0.55 * face_support

Face support is the max score among face labels that match the name ethnicity
(from ``scores_json``), falling back to top-label confidence when that label
aligns with the name family.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Mapping, Optional, Tuple

# Match scraper.mugshot_ethnicity.verify combine weights.
NAME_WEIGHT = 0.45
FACE_WEIGHT = 0.55


def _as_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def deepface_scores(scan: Optional[Mapping[str, Any]]) -> Dict[str, float]:
    """Normalize scan scores dict (keys lowercased)."""
    if not scan:
        return {}
    raw = scan.get("scores")
    if raw is None:
        raw = scan.get("scores_json")
    if isinstance(raw, str) and raw.strip():
        try:
            raw = json.loads(raw)
        except (TypeError, json.JSONDecodeError, ValueError):
            raw = {}
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, float] = {}
    for k, v in raw.items():
        key = str(k or "").strip().lower().replace(" ", "_")
        if not key:
            continue
        out[key] = _as_float(v, 0.0)
    return out


def face_support_for_name_ethnicity(
    name_ethnicity: str,
    scan: Optional[Mapping[str, Any]],
) -> Optional[float]:
    """
    Face confidence that the mugshot supports *name_ethnicity*.

    Returns ``None`` when there is no usable DeepFace scan (caller should show
    name-only confidence). Returns ``0.0`` when a scan exists but face does not
    support the name ethnicity.
    """
    if not scan:
        return None
    # Treat failed / no-face scans as unavailable for combining.
    err = str(scan.get("error") or "").strip()
    if err and not scan.get("face_detected", True):
        return None
    if scan.get("face_detected") in (0, False, "0"):
        # Still allow scores if present
        scores = deepface_scores(scan)
        if not scores and _as_float(scan.get("top_confidence")) <= 0:
            return None

    from scraper.mugshot_ethnicity.labels import (
        name_ethnicity_to_face_labels,
        normalize_face_label,
    )

    expected = name_ethnicity_to_face_labels(name_ethnicity or "")
    scores = deepface_scores(scan)
    if expected and scores:
        best = 0.0
        for lab in expected:
            best = max(best, scores.get(lab, 0.0))
            # also plain keys without underscore variants
            best = max(best, scores.get(lab.replace("_", ""), 0.0))
        if best > 0:
            return round(min(1.0, best), 4)

    top = normalize_face_label(
        str(scan.get("top_label") or scan.get("predicted_label") or "")
    )
    top_c = _as_float(scan.get("top_confidence"), 0.0)
    if expected and top in expected and top_c > 0:
        return round(min(1.0, top_c), 4)
    if not expected and top_c > 0:
        # No mapping — use top face conf as weak face signal
        return round(min(1.0, top_c), 4)
    # Scan present but does not support name ethnicity
    return 0.0


def combine_name_face_confidence(
    name_confidence: float,
    *,
    name_ethnicity: str = "",
    deepface: Optional[Mapping[str, Any]] = None,
    name_weight: float = NAME_WEIGHT,
    face_weight: float = FACE_WEIGHT,
) -> Tuple[float, bool]:
    """
    Return ``(display_confidence, is_combined)``.

    *is_combined* is True only when a usable DeepFace scan was blended in.
    """
    name_c = max(0.0, min(1.0, _as_float(name_confidence, 0.0)))
    face_c = face_support_for_name_ethnicity(name_ethnicity, deepface)
    if face_c is None:
        return round(name_c, 4), False
    nw = max(0.0, float(name_weight))
    fw = max(0.0, float(face_weight))
    total = nw + fw
    if total <= 0:
        return round(name_c, 4), False
    nw, fw = nw / total, fw / total
    combined = min(1.0, nw * name_c + fw * max(0.0, min(1.0, face_c)))
    return round(combined, 4), True


def format_display_confidence(
    score: float,
    is_combined: bool = False,
    *,
    digits: int = 3,
) -> str:
    """Human-readable confidence; marks combined scores explicitly."""
    try:
        s = float(score)
    except (TypeError, ValueError):
        return "—"
    text = f"{s:.{int(digits)}f}"
    if is_combined:
        return f"{text} (combined)"
    return text


def display_confidence_for_record(
    record: Optional[Mapping[str, Any]],
    *,
    name_confidence: Optional[float] = None,
    name_ethnicity: Optional[str] = None,
    digits: int = 3,
) -> Tuple[float, bool, str]:
    """
    Resolve display confidence from a misclass/sidebar record.

    Prefers explicit name conf args, then record fields. Uses ``_deepface`` or
    nested scan payloads when present.
    """
    rec = dict(record or {})
    if name_confidence is None:
        # Prefer raw surname conf (never a previously formatted combined string).
        for key in ("_misclass_name_conf", "name_confidence"):
            if rec.get(key) is not None:
                try:
                    name_confidence = float(rec[key])
                    break
                except (TypeError, ValueError):
                    continue
        if name_confidence is None:
            name_confidence = _as_float(
                rec.get("confidence") if rec.get("confidence") is not None else rec.get("_misclass_conf"),
                0.0,
            )
    if name_ethnicity is None:
        name_ethnicity = str(
            rec.get("_misclass_likely")
            or rec.get("likely_ethnicity")
            or ""
        )
    deepface = rec.get("_deepface")
    if not isinstance(deepface, dict):
        deepface = None
    score, combined = combine_name_face_confidence(
        float(name_confidence or 0.0),
        name_ethnicity=str(name_ethnicity or ""),
        deepface=deepface,
    )
    return score, combined, format_display_confidence(score, combined, digits=digits)
