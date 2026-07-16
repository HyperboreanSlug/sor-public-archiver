"""Source list upsert rules: keep CSV and HTML report charts distinct."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# Bulk/CSV must never collapse into live report HTML (or vice versa) by URL alone.
_REPORT_TYPES = frozenset({"report_html", "nsopw_report"})
_BULK_TYPES = frozenset({"csv_bulk", "inferred", "nsopw"})
_PROTECTED_DEMO_FIELDS = frozenset(
    {
        "race",
        "ethnicity",
        "gender",
        "height",
        "weight",
        "eye_color",
        "hair_color",
        "date_of_birth",
        "age",
    }
)


def _norm_str(val: Any) -> str:
    if val is None:
        return ""
    return str(val).strip()


def source_types_compatible(a: Any, b: Any) -> bool:
    """True when two source entries may be treated as the same chart."""
    ta = str(a or "unknown").strip().lower() or "unknown"
    tb = str(b or "unknown").strip().lower() or "unknown"
    if ta == tb:
        return True
    if ta in _REPORT_TYPES and tb in _REPORT_TYPES:
        return True
    # Unknown may match anything of the same jurisdiction path only via id
    return False


def find_merge_index(
    sources: List[Dict[str, Any]],
    new_src: Dict[str, Any],
) -> Optional[int]:
    """Index of existing source to upsert into, or None to append."""
    new_id = _norm_str(new_src.get("id")).lower()
    new_url = _norm_str(new_src.get("source_url")).lower()
    new_ext = _norm_str(new_src.get("external_id")).lower()
    new_type = str(new_src.get("type") or "unknown").strip().lower()
    new_jur = _norm_str(new_src.get("jurisdiction")).upper()

    for i, s in enumerate(sources):
        if not isinstance(s, dict):
            continue
        sid = _norm_str(s.get("id")).lower()
        if new_id and sid == new_id:
            return i
        cur_type = str(s.get("type") or "unknown").strip().lower()
        if not source_types_compatible(new_type, cur_type):
            continue
        if new_url and _norm_str(s.get("source_url")).lower() == new_url:
            return i
        if (
            new_ext
            and _norm_str(s.get("external_id")).lower() == new_ext
            and _norm_str(s.get("jurisdiction")).upper() == new_jur
        ):
            return i
    return None


def merge_source_fields(
    cur: Dict[str, Any],
    new_src: Dict[str, Any],
    *,
    prefer_new_fields: bool,
    utc_now_iso: str,
) -> Dict[str, Any]:
    """
    Merge *new_src* into existing source dict *cur*.

    HTML-verified demographics are protected from bulk CSV overwrite.
    """
    cur = dict(cur)
    cur_verified = bool(cur.get("html_verified"))
    new_verified = bool(new_src.get("html_verified"))
    new_is_bulk = str(new_src.get("type") or "").lower() in _BULK_TYPES
    protect = cur_verified and not new_verified

    for key in (
        "type",
        "jurisdiction",
        "label",
        "origin",
        "external_id",
        "source_url",
        "html_path",
        "html_status",
    ):
        nv = new_src.get(key)
        if nv is None or not str(nv).strip():
            continue
        # Never demote a verified report chart to bulk CSV metadata
        if protect and key in ("type", "label", "origin", "html_status", "html_path"):
            continue
        if prefer_new_fields or not _norm_str(cur.get(key)):
            cur[key] = nv

    if new_verified:
        cur["html_verified"] = True
    elif "html_verified" in new_src and not cur.get("html_verified"):
        cur["html_verified"] = bool(new_src.get("html_verified"))

    cur_fields = dict(cur.get("fields") or {})
    new_fields = dict(new_src.get("fields") or {})
    for k, v in new_fields.items():
        if v is None or (isinstance(v, str) and not str(v).strip()):
            continue
        old = cur_fields.get(k)
        if protect and k in _PROTECTED_DEMO_FIELDS and old is not None and str(old).strip():
            # Keep live-scrape values over bulk codes
            continue
        if new_is_bulk and cur_verified and k in _PROTECTED_DEMO_FIELDS and old:
            continue
        if prefer_new_fields or old is None or not str(old).strip():
            cur_fields[k] = v
    cur["fields"] = cur_fields
    cur["updated_at"] = utc_now_iso
    if new_src.get("id") and not protect:
        cur["id"] = new_src["id"]
    elif new_src.get("id") and not cur.get("id"):
        cur["id"] = new_src["id"]
    return cur
