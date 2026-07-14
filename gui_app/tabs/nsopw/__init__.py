"""NSOPW harvest tab package (composed mixins)."""
from __future__ import annotations

from .build import NsopwBuildMixin
from .options_ethnicity import NsopwEthnicityMixin
from .options_runtime import NsopwRuntimeMixin
from .progress_eta import NsopwEtaMixin
from .progress_ui import NsopwProgressUiMixin
from .run_cancel import NsopwCancelMixin
from .run_start import NsopwStartMixin
from .tree_open import NsopwTreeOpenMixin
from .tree_rows import NsopwTreeRowsMixin


class NsopwTabMixin(
    NsopwBuildMixin,
    NsopwEthnicityMixin,
    NsopwRuntimeMixin,
    NsopwEtaMixin,
    NsopwProgressUiMixin,
    NsopwTreeRowsMixin,
    NsopwTreeOpenMixin,
    NsopwCancelMixin,
    NsopwStartMixin,
):
    """NSOPW ethnic-surname harvest UI."""


__all__ = ["NsopwTabMixin"]
