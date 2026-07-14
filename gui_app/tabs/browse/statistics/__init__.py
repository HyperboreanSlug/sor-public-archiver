"""Browse → Statistics package."""
from __future__ import annotations

from .build import StatisticsBuildMixin
from .update import StatisticsUpdateMixin


class StatisticsTabMixin(
    StatisticsBuildMixin,
    StatisticsUpdateMixin,
):
    """Misclassification charts and distributions."""


__all__ = ["StatisticsTabMixin"]
