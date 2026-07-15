"""Inline record preview sidebar (photo + key fields)."""
from __future__ import annotations

import queue
from typing import Any, Callable, Dict, Optional

from gui_app.shared.record_sidebar_actions import RecordSidebarActionsMixin
from gui_app.shared.record_sidebar_flags import (
    merge_ethnicity_review_flags,
    merge_race_manual_flags,
    race_manual_override,
)
from gui_app.shared.record_sidebar_show import RecordSidebarShowMixin
from gui_app.shared.record_sidebar_ui import (
    ACTUAL_RACE_OPTIONS,
    _DETAIL_KEYS,
    build_sidebar_widgets,
    first_field,
)

# Back-compat alias used internally by older helpers.
_first = first_field


class RecordSidebar(RecordSidebarActionsMixin, RecordSidebarShowMixin):
    """Right-hand photo + details pane bound to a tree selection."""

    def __init__(self, parent: Any, *, photo_size: tuple[int, int] = (320, 320)) -> None:
        self.photo_size = photo_size
        build_sidebar_widgets(self, parent, photo_size)

        self._image_ref: Any = None
        self._pil_source: Any = None  # full-res RGB for dynamic re-fit
        self._load_token = 0
        self._after: Optional[Callable[..., Any]] = None
        self._record: Optional[Dict[str, Any]] = None
        self._on_verdict: Optional[Callable[[Dict[str, Any], str], None]] = None
        self._on_actual_race: Optional[Callable[[Dict[str, Any], str], None]] = None
        self._ui_q: queue.Queue[Callable[[], None]] = queue.Queue()
        self._pumping = False
        self._syncing_actual = False
        self._resize_after: Any = None
        self.frame.bind("<Configure>", self._on_sidebar_configure)
        try:
            self.photo.bind("<Configure>", self._on_sidebar_configure)
        except Exception:
            pass


__all__ = [
    "ACTUAL_RACE_OPTIONS",
    "RecordSidebar",
    "merge_ethnicity_review_flags",
    "merge_race_manual_flags",
    "race_manual_override",
    "_DETAIL_KEYS",
    "_first",
]
