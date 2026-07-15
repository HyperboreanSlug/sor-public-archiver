"""Browse → Misclassify package."""
from __future__ import annotations

from .build import MisclassifyBuildMixin
from .filters import MisclassifyFiltersMixin
from .run import MisclassifyRunMixin
from .run_apply import MisclassifyApplyMixin
from .sidebar_actions import MisclassifySidebarActionsMixin


class MisclassifyTabMixin(
    MisclassifyBuildMixin,
    MisclassifyFiltersMixin,
    MisclassifyRunMixin,
    MisclassifySidebarActionsMixin,
    MisclassifyApplyMixin,
):
    """Surname vs race mismatch analysis UI."""


__all__ = ["MisclassifyTabMixin"]
