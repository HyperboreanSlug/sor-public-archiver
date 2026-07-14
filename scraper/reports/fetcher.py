"""Jurisdiction report fetcher (composed mixins)."""
from __future__ import annotations

from scraper.reports.fetcher_attrs import FetcherAttrsMixin
from scraper.reports.fetcher_session import FetcherSessionMixin
from scraper.reports.fetcher_fetch import FetcherFetchMixin
from scraper.reports.fetcher_disclaimer import FetcherDisclaimerMixin
from scraper.reports.fetcher_photo import FetcherPhotoMixin
from scraper.reports.fetcher_html import FetcherHtmlMixin
from scraper.reports.fetcher_parse import FetcherParseMixin


class ReportFetcher(
    FetcherAttrsMixin,
    FetcherSessionMixin,
    FetcherFetchMixin,
    FetcherDisclaimerMixin,
    FetcherPhotoMixin,
    FetcherHtmlMixin,
    FetcherParseMixin,
):
    """Fetch/parse jurisdiction report HTML and photos."""


__all__ = ["ReportFetcher"]
