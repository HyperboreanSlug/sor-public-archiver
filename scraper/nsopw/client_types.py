"""NSOPW HTTP client (package path scraper.nsopw.client).


NSOPW (Dru Sjodin National Sex Offender Public Website) search client.

Uses the same HTTPS JSON endpoint the official nsopw.gov SPA calls after
the user accepts Conditions of Use. The API accepts a same-day token header
(MM/DD/YYYY), first + last name, and a jurisdiction list.

The API sits behind Cloudflare. Plain Python TLS fingerprints and bursty
traffic often get 403/429 challenge pages ("Just a moment..."). This client:
  - prefers curl_cffi Chrome impersonation when installed
  - sends browser-like Origin/Referer headers
  - warms the session against nsopw.gov
  - retries Cloudflare blocks with backoff

Polite rate limiting is enforced. Respect NSOPW Conditions of Use.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from html import unescape
from typing import Any, Dict, List, Optional, Sequence, Tuple

import requests

from scraper.config import DEFAULT_DELAY, REQUEST_TIMEOUT

NSOPW_SEARCH_URL = "https://nsopw-api.ojp.gov/nsopw/v1/v1.0/search"
NSOPW_OFFLINE_URL = "https://nsopw-api.ojp.gov/nsopw/v1/v1.0/jurisdictions/offline"
NSOPW_SEARCH_PAGE = "https://www.nsopw.gov/search-public-sex-offender-registries"
NSOPW_ORIGIN = "https://www.nsopw.gov"

# Match a current desktop Chrome — bot scoring is less harsh than custom UAs.
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# Cloudflare cool-down after a challenge (seconds), per attempt after the first.
_CF_BACKOFF_SECONDS = (0, 12, 28, 50)


def _stable_source_url(uri: Optional[str]) -> str:
    """Strip session uid/tokens from offender page URLs (for dedupe)."""
    if not uri:
        return ""
    try:
        from scraper.database import Database

        return Database.normalize_identity_url(uri) or (uri or "").strip()
    except Exception:
        return (uri or "").strip()


def _stable_external_id(uri: Optional[str], jurisdiction: Optional[str] = None) -> str:
    """Prefer stable registry Id over full session URL."""
    if not uri:
        return ""
    try:
        from scraper.database import Database

        key = Database.stable_external_key(
            {"source_url": uri, "external_id": uri, "state": jurisdiction or ""},
            state_hint=jurisdiction,
        )
        # key looks like "ga|reg:50604" — store reg id when available
        if "|reg:" in key:
            return key.split("|reg:", 1)[1]
        return Database.normalize_identity_url(uri) or (uri or "").strip()
    except Exception:
        return (uri or "").strip()

# Core state/territory codes accepted by NSOPW (excludes "All")
DEFAULT_JURISDICTIONS = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI",
    "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN",
    "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH",
    "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA",
    "WV", "WI", "WY", "GU", "PR", "USVI", "AMERICANSAMOA", "CNMI",
]

# NSOPW sometimes returns bogus location.state codes (esp. "YY" for FL rows).
# Prefer jurisdictionId when location.state is not a real US/territory code.
_VALID_JURISDICTION_CODES = frozenset(j.upper() for j in DEFAULT_JURISDICTIONS) | {
    "AS",  # American Samoa short form
    "VI",  # Virgin Islands short form
    "MP",  # CNMI short form
}
_BOGUS_STATE_CODES = frozenset({
    "YY", "XX", "ZZ", "NA", "N/A", "UN", "UK", "00", "??", "NONE", "NULL",
})


def normalize_jurisdiction_code(
    *candidates: Optional[str],
    default: str = "",
) -> str:
    """
    Return the first candidate that looks like a real jurisdiction code.

    Filters NSOPW junk such as location.state == \"YY\" (seen on many FL hits
    where jurisdictionId correctly reports FL).
    """
    for raw in candidates:
        code = (raw or "").strip().upper()
        if not code:
            continue
        if code in _BOGUS_STATE_CODES:
            continue
        if code in _VALID_JURISDICTION_CODES:
            return code
        # 2-letter alpha codes that are not in the list still beat YY
        if len(code) == 2 and code.isalpha() and code not in _BOGUS_STATE_CODES:
            return code
    return (default or "").strip().upper()


def _token_starts_with(value: str, prefix: str) -> bool:
    """True if value starts with prefix (case-insensitive)."""
    v = (value or "").strip().upper()
    p = (prefix or "").strip().upper()
    return bool(v) and bool(p) and v.startswith(p)


def _last_starts_with_prefix(surname: str, prefix: str) -> bool:
    """Primary last or any space/hyphen token starts with prefix."""
    s = (surname or "").strip().upper()
    p = (prefix or "").strip().upper()
    if not s or not p:
        return False
    if s.startswith(p):
        return True
    for tok in re.split(r"[\s\-]+", s):
        if tok and tok.startswith(p):
            return True
    return False


def offender_matches_name_prefixes(
    first_q: str,
    last_q: str,
    *,
    first_name: str = "",
    middle_name: str = "",
    last_name: str = "",
    alias_dicts: Optional[Sequence[Dict[str, Any]]] = None,
    aliases: Optional[Sequence[str]] = None,
    allow_aliases: bool = False,
) -> bool:
    """
    True if this offender is a *real* starts-with match for first_q + last_q.

    NSOPW's national API often returns rows that only match via **aliases** or
    loose server scoring (looks like "any letters appear somewhere"). By default
    we require the **primary** record name to satisfy:

      first_name.startswith(first_q) AND last_name.startswith(last_q)

    (case-insensitive; multi-word / hyphenated names match on any token).
    Middle name may stand in for first (common on registry records).

    Set ``allow_aliases=True`` to also accept alias pairs (including swapped
    first/last order used by some jurisdictions).
    """
    fq = (first_q or "").strip()
    lq = (last_q or "").strip()
    if not fq or not lq:
        return False

    def _pair(giv: str, sur: str) -> bool:
        return _token_starts_with(giv, fq) and _last_starts_with_prefix(sur, lq)

    # --- Primary record only (default) ---
    if _pair(first_name, last_name):
        return True
    if middle_name and _pair(middle_name, last_name):
        return True
    # Hyphenated / multi first names: "XANDON-ANTHONY"
    for part in re.split(r"[\s\-]+", (first_name or "").strip()):
        if part and _pair(part, last_name):
            return True

    if not allow_aliases:
        return False

    for a in alias_dicts or []:
        if not isinstance(a, dict):
            continue
        ag = str(a.get("givenName") or "")
        am = str(a.get("middleName") or "")
        as_ = str(a.get("surName") or "")
        if _pair(ag, as_):
            return True
        if am and _pair(am, as_):
            return True
        # Registries often reverse first/last on aliases
        if _pair(as_, ag):
            return True

    for a in aliases or []:
        parts = [p for p in re.split(r"[\s,]+", str(a).strip()) if p]
        if len(parts) >= 2:
            if _pair(parts[0], parts[-1]):
                return True
            if _pair(parts[-1], parts[0]):
                return True
    return False


@dataclass
class NSOPWOffender:
    """One hit from an NSOPW search."""

    first_name: str = ""
    middle_name: str = ""
    last_name: str = ""
    full_name: str = ""
    gender: str = ""
    date_of_birth: str = ""
    age: Optional[int] = None
    state: str = ""
    city: str = ""
    address: str = ""
    zip_code: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    jurisdiction_id: str = ""
    offender_uri: str = ""
    image_uri: str = ""
    absconder: bool = False
    aliases: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> Dict[str, Any]:
        """Map to database/offender dict."""
        import json

        # Registry jurisdictionId beats residential address state (out-of-state
        # registrants living in FL must not be labeled FL when flyer is GA/etc.).
        st = normalize_jurisdiction_code(self.jurisdiction_id, self.state)
        src_st = normalize_jurisdiction_code(self.jurisdiction_id, self.state) or st or "US"
        return {
            "first_name": self.first_name or None,
            "middle_name": self.middle_name or None,
            "last_name": self.last_name or None,
            "full_name": self.full_name or None,
            "gender": self.gender or None,
            "date_of_birth": self.date_of_birth or None,
            "age": self.age,
            "state": st or None,
            "city": self.city or None,
            "address": self.address or None,
            "zip_code": self.zip_code or None,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "source_state": src_st,
            # Normalize: NSOPW state links often append volatile uid= session tokens
            "source_url": _stable_source_url(self.offender_uri) or None,
            "external_id": _stable_external_id(self.offender_uri, self.jurisdiction_id)
            or None,
            "photo_url": self.image_uri or None,
            "raw_data_json": json.dumps(self.raw, ensure_ascii=False)[:50000],
            "flags": "nsopw",
        }


def _make_http_session() -> Tuple[Any, str]:
    """
    Prefer curl_cffi Chrome impersonation (Cloudflare-friendly TLS).
    Fall back to requests with a browser User-Agent.
    """
    try:
        from curl_cffi import requests as creq  # type: ignore

        session = creq.Session(impersonate="chrome")
        backend = "curl_cffi"
    except Exception:
        session = requests.Session()
        session.headers["User-Agent"] = BROWSER_UA
        backend = "requests"

    session.headers.update(
        {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": NSOPW_ORIGIN,
            "Referer": NSOPW_SEARCH_PAGE,
            "Content-Type": "application/json;charset=UTF-8",
        }
    )
    return session, backend


def _is_cloudflare_block(resp: Any) -> bool:
    """True when the response is a CF challenge / rate-limit page, not API JSON."""
    code = getattr(resp, "status_code", 0) or 0
    if code not in (403, 429, 503):
        return False
    ct = (getattr(resp, "headers", {}) or {}).get("Content-Type") or ""
    if "application/json" in ct.lower():
        return False
    body = (getattr(resp, "text", None) or "")[:1200].lower()
    markers = (
        "just a moment",
        "cloudflare",
        "attention required",
        "cf-ray",
        "enable javascript",
        "checking your browser",
    )
    if any(m in body for m in markers):
        return True
    # 429 from this host is almost always edge rate limiting
    return code == 429


