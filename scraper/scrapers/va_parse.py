"""Virginia vspsor.com parse helpers (list + detail)."""
from __future__ import annotations

from .va_parse_detail import (
    merge_detail_into_record,
    names_compatible,
    parse_detail_html,
)
from .va_parse_list import list_row_to_record

__all__ = [
    "list_row_to_record",
    "parse_detail_html",
    "merge_detail_into_record",
    "names_compatible",
]
