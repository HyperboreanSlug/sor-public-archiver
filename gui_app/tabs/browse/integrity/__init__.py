"""Browse → Integrity package."""
from __future__ import annotations

from .build import IntegrityBuildMixin
from .enrich_refresh import IntegrityEnrichRefreshMixin
from .enrich_start import IntegrityEnrichStartMixin
from .refresh import IntegrityRefreshMixin
from .requeue import IntegrityRequeueMixin


class IntegrityTabMixin(
    IntegrityBuildMixin,
    IntegrityRefreshMixin,
    IntegrityEnrichStartMixin,
    IntegrityEnrichRefreshMixin,
    IntegrityRequeueMixin,
):
    """Coverage, enrich, requeue incomplete reports."""


__all__ = ["IntegrityTabMixin"]
