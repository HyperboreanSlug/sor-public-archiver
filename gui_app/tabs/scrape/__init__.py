"""Scrape tab package."""
from __future__ import annotations

from .build import ScrapeBuildMixin
from .dedupe import ScrapeDedupeMixin
from .import_csv import ScrapeImportMixin
from .run import ScrapeRunMixin
from .select import ScrapeSelectMixin


class ScrapeTabMixin(
    ScrapeBuildMixin,
    ScrapeSelectMixin,
    ScrapeRunMixin,
    ScrapeImportMixin,
    ScrapeDedupeMixin,
):
    """State bulk scrape + CSV import + dedupe."""


__all__ = ["ScrapeTabMixin"]
