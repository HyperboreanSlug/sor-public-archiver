"""Shared detail drawer (photo + fields + export card)."""
from __future__ import annotations

from .build import DetailBuildMixin
from .fill import DetailFillMixin
from .helpers import DetailHelpersMixin


class DetailDrawerMixin(
    DetailBuildMixin,
    DetailHelpersMixin,
    DetailFillMixin,
):
    """Right-side record detail used by Search / Misclassify / etc."""


__all__ = ["DetailDrawerMixin"]
