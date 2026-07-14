from __future__ import annotations

from html import unescape
from typing import Any, Dict, List, Optional, Sequence

from scraper.nsopw.client_types import (  # noqa: F401
    BROWSER_UA,
    DEFAULT_DELAY,
    DEFAULT_JURISDICTIONS,
    NSOPW_OFFLINE_URL,
    NSOPW_ORIGIN,
    NSOPW_SEARCH_PAGE,
    NSOPW_SEARCH_URL,
    NSOPWOffender,
    REQUEST_TIMEOUT,
    _CF_BACKOFF_SECONDS,
    _is_cloudflare_block,
    _make_http_session,
    _stable_external_id,
    _stable_source_url,
    _token_starts_with,
    _last_starts_with_prefix,
    normalize_jurisdiction_code,
    offender_matches_name_prefixes,
)

class NSOPWClientParseMixin:
    def _parse_offender(self, obj: Dict[str, Any]) -> NSOPWOffender:
        name = obj.get("name") or {}
        given = (name.get("givenName") or "").strip()
        middle = (name.get("middleName") or "").strip()
        sur = (name.get("surName") or "").strip()
        parts = [p for p in (given, middle, sur) if p]
        full = " ".join(parts)

        aliases: List[str] = []
        for a in obj.get("aliases") or []:
            if not isinstance(a, dict):
                continue
            ap = [p for p in (a.get("givenName"), a.get("middleName"), a.get("surName")) if p]
            if ap:
                aliases.append(" ".join(str(x) for x in ap))

        # Prefer residential location
        loc = {}
        for candidate in obj.get("locations") or []:
            if isinstance(candidate, dict):
                loc = candidate
                if (candidate.get("type") or "").upper() == "R":
                    break

        dob = obj.get("dob") or ""
        if isinstance(dob, str) and "T" in dob:
            dob = dob.split("T", 1)[0]

        age = obj.get("age")
        try:
            age = int(age) if age is not None else None
        except (TypeError, ValueError):
            age = None

        lat = loc.get("latitude")
        lon = loc.get("longitude")
        try:
            lat = float(lat) if lat is not None else None
            lon = float(lon) if lon is not None else None
            if lat == 0 and lon == 0:
                lat = lon = None
        except (TypeError, ValueError):
            lat = lon = None

        jur = normalize_jurisdiction_code(
            loc.get("state"),
            obj.get("jurisdictionId"),
        )
        jur_id = normalize_jurisdiction_code(
            obj.get("jurisdictionId"),
            loc.get("state"),
        ) or (obj.get("jurisdictionId") or "").strip().upper()

        return NSOPWOffender(
            first_name=given,
            middle_name=middle,
            last_name=sur,
            full_name=full,
            gender=(obj.get("gender") or "").strip(),
            date_of_birth=dob,
            age=age,
            # Prefer real state; never store NSOPW junk like "YY"
            state=jur or jur_id,
            city=(loc.get("city") or "").strip(),
            address=(loc.get("streetAddress") or "").strip(),
            zip_code=str(loc.get("zipCode") or "").strip(),
            latitude=lat,
            longitude=lon,
            jurisdiction_id=jur_id or jur,
            offender_uri=unescape((obj.get("offenderUri") or "").strip()),
            image_uri=unescape((obj.get("imageUri") or "").strip()),
            absconder=bool(obj.get("absconder")),
            aliases=aliases,
            raw=obj,
        )


