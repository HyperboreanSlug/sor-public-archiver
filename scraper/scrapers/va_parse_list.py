"""Map vspsor.com searchRegistry list rows into SORPA records."""
from __future__ import annotations

import re
from typing import Any, Dict, List
from urllib.parse import urljoin

from scraper.reports.util import _clean_value

BASE = "https://www.vspsor.com"
_BR_SPLIT = re.compile(r"<br\s*/?>", re.I)


def _all_segments(value: Any) -> List[str]:
    if value is None:
        return []
    text = str(value)
    parts = _BR_SPLIT.split(text) if "<br" in text.lower() else text.split("\n")
    out: List[str] = []
    for p in parts:
        c = _clean_value(p)
        if c:
            out.append(c)
    return out


def _first_segment(value: Any) -> str:
    parts = _all_segments(value)
    return parts[0] if parts else ""


def list_row_to_record(row: Dict[str, Any], *, state: str = "VA") -> Dict[str, Any]:
    """Convert one searchRegistry offender object into a record dict."""
    oid = str(row.get("id") or "").strip()
    first = _clean_value(row.get("firstName")) or ""
    middle = _clean_value(row.get("middleName")) or ""
    last = _clean_value(row.get("lastName")) or ""
    full = _clean_value(row.get("fullName")) or ""
    if not full:
        full = " ".join(p for p in (first, middle, last) if p).strip()

    photo = row.get("imageUrl") or ""
    if photo and not str(photo).startswith("http"):
        photo = urljoin(BASE + "/", str(photo))

    addr_parts = _all_segments(row.get("location"))
    city_parts = _all_segments(row.get("city"))
    zip_parts = _all_segments(row.get("postalCode"))
    county_parts = _all_segments(row.get("county"))

    rec: Dict[str, Any] = {
        "first_name": first or None,
        "middle_name": middle or None,
        "last_name": last or None,
        "full_name": full or None,
        "age": row.get("age"),
        "address": addr_parts[0] if addr_parts else None,
        "city": city_parts[0] if city_parts else None,
        "zip_code": zip_parts[0] if zip_parts else None,
        "county": county_parts[0] if county_parts else None,
        "state": state,
        "source_state": state,
        "photo_url": photo or None,
        "external_id": oid or None,
        "source_url": f"{BASE}/Offender/Details/{oid}" if oid else None,
    }
    extra = {
        "address_type": _first_segment(row.get("addressType")) or None,
        "all_addresses": " | ".join(addr_parts) if len(addr_parts) > 1 else None,
        "all_cities": " | ".join(city_parts) if len(city_parts) > 1 else None,
        "all_counties": " | ".join(county_parts) if len(county_parts) > 1 else None,
        "vspsor_id": oid or None,
    }
    rec["raw_data_json"] = {k: v for k, v in extra.items() if v}
    return rec
