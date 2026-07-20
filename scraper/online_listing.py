"""Detect when a registry listing is not available online (dead / 404 URL)."""
from __future__ import annotations

import json
import re
from typing import Any, List, Mapping, Optional

# Shown on Reports cards when the live person listing is gone.
UNAVAILABLE_ONLINE_LABEL = "NOT AVAILABLE ONLINE"

_ERROR404_RE = re.compile(r"(?i)error404|/error/error|error\.jsf")


def _flags_list(record: Optional[Mapping[str, Any]]) -> List[str]:
    if not record:
        return []
    raw = record.get("flags")
    if isinstance(raw, list):
        return [str(t) for t in raw]
    if isinstance(raw, dict):
        tags = raw.get("tags")
        if isinstance(tags, list):
            return [str(t) for t in tags]
        return []
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except Exception:
            return [raw] if "blocked:" in raw.lower() else []
        if isinstance(parsed, list):
            return [str(t) for t in parsed]
        if isinstance(parsed, dict):
            tags = parsed.get("tags")
            if isinstance(tags, list):
                return [str(t) for t in tags]
            return []
    return []


def _sources_list(record: Optional[Mapping[str, Any]]) -> List[dict]:
    if not record:
        return []
    raw = record.get("sources_json")
    if not raw:
        return []
    try:
        srcs = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return []
    if not isinstance(srcs, list):
        return []
    return [s for s in srcs if isinstance(s, dict)]


def _url_is_error_page(url: str) -> bool:
    return bool(url and _ERROR404_RE.search(url))


def _has_dead_listing_evidence(record: Mapping[str, Any]) -> bool:
    """Prior scrape / stored URL proves a listing was removed (404/410/error page)."""
    for t in _flags_list(record):
        tl = t.lower()
        if "blocked:http_404" in tl or tl in ("http_404", "blocked:404"):
            return True
        if "blocked:http_410" in tl or tl == "gone":
            return True
    raw_url = str(record.get("source_url") or "")
    if _url_is_error_page(raw_url):
        return True
    for s in _sources_list(record):
        st = str(s.get("html_status") or "").lower()
        if "http_404" in st or st.endswith(":404") or "http_410" in st:
            return True
        if _url_is_error_page(str(s.get("source_url") or "")):
            return True
    return False


_SEARCH_HOMES_CACHE: Optional[set] = None


def _search_homes() -> set:
    global _SEARCH_HOMES_CACHE
    if _SEARCH_HOMES_CACHE is not None:
        return _SEARCH_HOMES_CACHE
    try:
        from scraper.public_links import (
            CO_SOR_SEARCH_HOME,
            FL_FDLE_HOME,
            FL_FDLE_SEARCH_HOME,
            MI_MSPSOR_SEARCH_HOME,
            TX_SOR_SEARCH_HOME,
        )

        _SEARCH_HOMES_CACHE = {
            FL_FDLE_SEARCH_HOME.rstrip("/").lower(),
            FL_FDLE_HOME.rstrip("/").lower(),
            CO_SOR_SEARCH_HOME.rstrip("/").lower(),
            MI_MSPSOR_SEARCH_HOME.rstrip("/").lower(),
            TX_SOR_SEARCH_HOME.rstrip("/").lower(),
        }
    except Exception:
        _SEARCH_HOMES_CACHE = set()
    return _SEARCH_HOMES_CACHE


def _is_generic_search_home(url: str) -> bool:
    """True for jurisdiction search landings (not a person-specific listing)."""
    if not url:
        return True
    low = url.rstrip("/").lower()
    # Person rapsheets share a /PublicSite/Search/ prefix with the TX home —
    # never treat those as generic search.
    if "rapsheet" in low or "offenderdetails" in low or "flyer.jsf" in low:
        return False
    if "/details/" in low or "personid=" in low:
        return False
    homes = _search_homes()
    if homes and low in homes:
        return True
    # Exact-ish path ends (avoid substring hits on /Search/Rapsheet)
    if low.endswith("/sops/search.jsf") or low.endswith("/sops/home.jsf"):
        return True
    if low.endswith("/publicsite/search") or low.endswith("/home/search"):
        return True
    return False


def _source_url_pieces(record: Mapping[str, Any]) -> List[str]:
    """All candidate listing URLs on the record (multi-jurisdiction aware)."""
    pieces: List[str] = []
    try:
        from scraper.public_links import split_source_urls
    except Exception:
        split_source_urls = None  # type: ignore

    raw = str(record.get("source_url") or "").strip()
    if raw:
        if split_source_urls is not None:
            pieces.extend(split_source_urls(raw))
        else:
            pieces.append(raw)
    for s in _sources_list(record):
        su = str(s.get("source_url") or "").strip()
        if not su:
            continue
        if split_source_urls is not None:
            pieces.extend(split_source_urls(su))
        else:
            pieces.append(su)
    seen = set()
    out: List[str] = []
    for u in pieces:
        key = u.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(u.strip())
    return out


def _resolve_piece(url: str, state: Optional[str]) -> str:
    try:
        from scraper.public_links import resolve_public_source_url

        # Do not skip FDLE flyers for this check — sticky 404 flags are too noisy.
        return (
            resolve_public_source_url(url, state=state, skip_fdle_flyers=False) or ""
        ).strip()
    except Exception:
        return (url or "").strip()


def _has_person_listing_url(record: Mapping[str, Any]) -> bool:
    """True if any stored URL looks like a person-specific listing page.

    Ignores past HTML-fetch ``blocked:http_404`` / sources_json status. Those
    flags are sticky and often wrong for bots (403/captcha/disclaimer), while
    photos are commonly archived from NSOPW ``photo_url`` or FDLE CallImage
    independently of the HTML page. Multi-jurisdiction rows may also keep a
    live IL/AK detail next to a dead FDLE error page.

    Only error404 landings and bare search homes are treated as non-person URLs.
    """
    state = record.get("source_state") or record.get("state")
    state_s = str(state).split("|")[0].strip() if state else None

    pieces = _source_url_pieces(record)
    if not pieces:
        try:
            from scraper.public_links import openable_url_for_record

            ou = (openable_url_for_record(dict(record)) or "").strip()
        except Exception:
            ou = ""
        return bool(
            ou and not _url_is_error_page(ou) and not _is_generic_search_home(ou)
        )

    for piece in pieces:
        if _url_is_error_page(piece) or _is_generic_search_home(piece):
            continue
        resolved = _resolve_piece(piece, state_s)
        if not resolved or _url_is_error_page(resolved) or _is_generic_search_home(resolved):
            continue
        return True
    return False


def listing_unavailable_online(record: Optional[Mapping[str, Any]]) -> bool:
    """True when there is no person-specific listing URL left to open.

    **NOT AVAILABLE ONLINE** means the stored links are only error pages /
    search homes (or empty) *and* we have dead-listing evidence. It does **not**
    mean "HTML enrich once returned 404" — that would wrongly banner thousands
    of rows that still have detail URLs and archived mugshots.
    """
    if not record:
        return False

    if _has_person_listing_url(record):
        return False

    return _has_dead_listing_evidence(record)


def online_status_label(record: Optional[Mapping[str, Any]]) -> str:
    """Banner text for Reports, or empty when a person listing URL may exist."""
    if listing_unavailable_online(record):
        return UNAVAILABLE_ONLINE_LABEL
    return ""
