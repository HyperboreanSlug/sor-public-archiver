"""NSOPW HTTP client (composed)."""
from __future__ import annotations

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
    _is_cloudflare_block,
    _make_http_session,
    _stable_external_id,
    _stable_source_url,
    normalize_jurisdiction_code,
    offender_matches_name_prefixes,
)
from scraper.nsopw.client_session import NSOPWClientSessionMixin
from scraper.nsopw.client_search_run import NSOPWClientSearchRunMixin
from scraper.nsopw.client_parse import NSOPWClientParseMixin


class NSOPWClient(
    NSOPWClientSessionMixin,
    NSOPWClientSearchRunMixin,
    NSOPWClientParseMixin,
):
    """NSOPW search client."""


__all__ = [
    "NSOPWClient",
    "NSOPWOffender",
    "DEFAULT_JURISDICTIONS",
    "BROWSER_UA",
    "NSOPW_SEARCH_URL",
    "NSOPW_OFFLINE_URL",
    "NSOPW_SEARCH_PAGE",
    "NSOPW_ORIGIN",
    "normalize_jurisdiction_code",
    "offender_matches_name_prefixes",
    "_stable_source_url",
    "_stable_external_id",
    "_is_cloudflare_block",
    "_make_http_session",
]
