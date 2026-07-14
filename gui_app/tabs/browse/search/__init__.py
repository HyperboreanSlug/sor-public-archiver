"""Browse → Search package."""
from __future__ import annotations

from .build import SearchBuildMixin
from .run_query import SearchQueryMixin
from .run_tree import SearchTreeMixin
from .select import SearchSelectMixin


class SearchTabMixin(
    SearchBuildMixin,
    SearchQueryMixin,
    SearchTreeMixin,
    SearchSelectMixin,
):
    """Local DB search UI."""


__all__ = ["SearchTabMixin"]
