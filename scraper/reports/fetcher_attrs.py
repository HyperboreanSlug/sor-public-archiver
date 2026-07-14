"""Class-level constants for ReportFetcher."""
from __future__ import annotations


class FetcherAttrsMixin:
    """Photo size thresholds shared by download/embed paths."""

    MIN_PHOTO_BYTES = 80
    MIN_PRIMARY_PHOTO_BYTES = 2000
