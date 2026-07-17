from __future__ import annotations

import re
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
        # NSOPW often returns Jr/Sr/II/III in name.suffix — keep on full + last
        suffix = (name.get("suffix") or name.get("nameSuffix") or "").strip()
        suffix = re.sub(r"^[,\s]+", "", suffix).strip() if suffix else ""
        last = " ".join(p for p in (sur, suffix) if p).strip() or sur
        parts = [p for p in (given, middle, last) if p]
        full = " ".join(parts)

        aliases: List[str] = []
        for a in obj.get("aliases") or []:
            if not isinstance(a, dict):
                continue
            a_suf = (a.get("suffix") or a.get("nameSuffix") or "").strip()
            a_suf = re.sub(r"^[,\s]+", "", a_suf).strip() if a_suf else ""
            a_last = " ".join(
                p
                for p in ((a.get("surName") or "").strip(), a_suf)
                if p
            )
            ap = [
                p
                for p in (
                    (a.get("givenName") or "").strip(),
                    (a.get("middleName") or "").strip(),
                    a_last,
                )
                if p
            ]
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

        # Registry jurisdiction (who hosts the flyer) beats residential address
        # state — out-of-state GA registrants living in FL must stay GA, not FL.
        jur_id = normalize_jurisdiction_code(
            obj.get("jurisdictionId"),
            loc.get("state"),
        ) or (obj.get("jurisdictionId") or "").strip().upper()
        jur = normalize_jurisdiction_code(
            obj.get("jurisdictionId"),
            loc.get("state"),
        )

        return NSOPWOffender(
            first_name=given,
            middle_name=middle,
            last_name=last,
            full_name=full,
            gender=(obj.get("gender") or "").strip(),
            date_of_birth=dob,
            age=age,
            # Prefer registry jurisdictionId; never store NSOPW junk like "YY"
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


