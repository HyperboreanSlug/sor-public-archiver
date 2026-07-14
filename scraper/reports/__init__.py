"""Jurisdiction report fetch / parse / photo package."""
from __future__ import annotations

from typing import Any

from scraper.reports.util import (
    photo_state_from_url,
    photo_url_variants,
    extract_dedicated_photo_urls,
    _normalize_url,
)

__all__ = [
    "ReportFetcher",
    "photo_state_from_url",
    "photo_url_variants",
    "extract_dedicated_photo_urls",
]


def __getattr__(name: str) -> Any:
    if name == "ReportFetcher":
        from scraper.reports.fetcher import ReportFetcher

        return ReportFetcher
    raise AttributeError(name)
