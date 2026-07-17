"""Texas DPS SOR URL canonicalization (publicsite → sor.dps.texas.gov)."""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import parse_qs, urlparse

# Live public site (publicsite.dps.texas.gov redirects / 503s for rapsheets)
TX_SOR_HOST = "sor.dps.texas.gov"
TX_SOR_SEARCH_HOME = "https://sor.dps.texas.gov/PublicSite/Search"
TX_SOR_RAPSHEET_BASE = "https://sor.dps.texas.gov/PublicSite/Search/Rapsheet"
TX_SOR_XML_BASE = (
    "https://sor.dps.texas.gov/PublicSite/Search/Rapsheet/GetRapsheetXml"
)

_TX_HOST_MARKERS = (
    "publicsite.dps.texas.gov",
    "sor.dps.texas.gov",
    "securesite.dps.texas.gov",
)
# SID is typically 7–8 digits (zero-padded)
_SID_RE = re.compile(r"(?i)(?:[?&]sid=|/sid/|sid[=:])(\d{5,12})\b")
_SID_PATH_RE = re.compile(r"(?i)rapsheet[^0-9]*(\d{5,12})\b")


def is_tx_dps_url(url: str) -> bool:
    low = (url or "").lower()
    return any(h in low for h in _TX_HOST_MARKERS) or (
        "dps.texas.gov" in low and "sexoffender" in low.replace("_", "")
    )


def extract_tx_sid(url: str) -> Optional[str]:
    """Return DPS SID digits from a Texas rapsheet / registry URL."""
    u = (url or "").strip()
    if not u:
        return None
    m = _SID_RE.search(u)
    if m:
        return m.group(1)
    try:
        qs = parse_qs(urlparse(u).query or "", keep_blank_values=False)
    except Exception:
        qs = {}
    for key in ("sid", "Sid", "SID", "dps_nbr", "DPS_NBR"):
        if key in qs and qs[key]:
            cand = re.sub(r"\D", "", qs[key][0] or "")
            if len(cand) >= 5:
                return cand
    m2 = _SID_PATH_RE.search(u)
    if m2:
        return m2.group(1)
    return None


def tx_rapsheet_url(sid: str) -> str:
    s = re.sub(r"\D", "", str(sid or ""))
    if not s:
        return TX_SOR_SEARCH_HOME
    return f"{TX_SOR_RAPSHEET_BASE}?sid={s}"


def tx_rapsheet_xml_url(sid: str) -> str:
    s = re.sub(r"\D", "", str(sid or ""))
    if not s:
        return ""
    return f"{TX_SOR_XML_BASE}?sid={s}"


def normalize_tx_dps_url(url: str) -> str:
    """
    Canonical openable Texas rapsheet link.

    Old: ``https://publicsite.dps.texas.gov/.../Rapsheet?sid=…`` (often 503)
    New: ``https://sor.dps.texas.gov/PublicSite/Search/Rapsheet?sid=…``
    Bare rapsheet without sid → public search home.
    """
    u = (url or "").strip()
    if not u:
        return u
    if not is_tx_dps_url(u) and "sid=" not in u.lower():
        return u
    sid = extract_tx_sid(u)
    if sid:
        return tx_rapsheet_url(sid)
    # Texas host but no SID — send to search (never leave dead publicsite rapsheet)
    if is_tx_dps_url(u):
        return TX_SOR_SEARCH_HOME
    return u
