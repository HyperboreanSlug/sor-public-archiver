"""Browse → Misclassify package."""
from __future__ import annotations

from .build import MisclassifyBuildMixin
from .run import MisclassifyRunMixin


class MisclassifyTabMixin(
    MisclassifyBuildMixin,
    MisclassifyRunMixin,
):
    """Surname vs race mismatch analysis UI."""


__all__ = ["MisclassifyTabMixin"]
