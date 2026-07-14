"""NSOPW live runtime option capture."""
from __future__ import annotations

import csv
import json
import os
import queue
import re
import subprocess
import sys
import threading
import traceback
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from gui_app.paths import ROOT
from gui_app.theme import (
    C,
    FONT_BOLD,
    FONT_MONO,
    FONT_SECTION,
    FONT_SM,
    FONT_TITLE,
    FONT_UI,
)
from gui_app.widgets import (
    _bind_tree_scroll_isolation,
    _card,
    _enable_tree_column_sort,
    _format_race_display,
    _format_state_display,
    _hpaned,
    _misclass_race_bucket,
    _muted,
    _render_bar_chart,
    _render_pie_chart,
    _section_label,
    _stretch_columns,
    _tree_frame,
    _vpaned,
    _wire_wide_scroll,
)


class NsopwRuntimeMixin:
    def _nsopw_parse_optional_limit(self, raw: Any) -> Optional[int]:
        """Blank / 0 / non-numeric → None (unlimited)."""
        text = (str(raw) if raw is not None else "").strip()
        if not text:
            return None
        try:
            n = int(text)
        except (TypeError, ValueError):
            return None
        return None if n <= 0 else n


    def _nsopw_capture_runtime_options(self) -> Dict[str, Any]:
        """Read current NSOPW operational knobs from the UI (main thread)."""
        try:
            search_delay = max(2.0, float(self.nsopw_search_delay.get()))
        except (TypeError, ValueError):
            search_delay = 3.0
        try:
            report_delay = max(0.25, float(self.nsopw_report_delay.get()))
        except (TypeError, ValueError):
            report_delay = 0.75
        repeat_old = bool(self.nsopw_repeat_searches.get())
        return {
            "max_searches": self._nsopw_parse_optional_limit(self.nsopw_max_searches.get()),
            "max_names": self._nsopw_parse_optional_limit(self.nsopw_max_reports.get()),
            "search_delay": search_delay,
            "report_delay": report_delay,
            "enrich_reports": bool(self.nsopw_enrich.get()),
            "enrich_scope": (self.nsopw_enrich_scope.get() or "all").strip().lower(),
            "save_html": bool(self.nsopw_save_html.get()),
            "skip_existing_urls": bool(self.nsopw_skip_existing.get()),
            "skip_completed_searches": not repeat_old,
            "new_files_only": bool(self.nsopw_new_files_only.get()),
        }


    def _nsopw_sync_runtime_options(self, *_args: Any) -> None:
        """Main-thread: snapshot UI options for the worker."""
        try:
            snap = self._nsopw_capture_runtime_options()
        except Exception:
            return
        with self._nsopw_runtime_lock:
            self._nsopw_runtime = snap


    def _nsopw_live_options(self) -> Dict[str, Any]:
        """Worker-thread: copy of latest operational knobs."""
        with self._nsopw_runtime_lock:
            return dict(self._nsopw_runtime)


    def _nsopw_bind_live_option_traces(self) -> None:
        """Re-sync runtime snapshot whenever the user edits live knobs."""
        if getattr(self, "_nsopw_live_traces_bound", False):
            return
        self._nsopw_live_traces_bound = True
        vars_ = [
            self.nsopw_max_searches,
            self.nsopw_max_reports,
            self.nsopw_search_delay,
            self.nsopw_report_delay,
            self.nsopw_enrich,
            self.nsopw_enrich_scope,
            self.nsopw_save_html,
            self.nsopw_repeat_searches,
            self.nsopw_skip_existing,
            self.nsopw_new_files_only,
        ]
        for v in vars_:
            try:
                v.trace_add("write", self._nsopw_sync_runtime_options)
            except Exception:
                try:
                    v.trace("w", self._nsopw_sync_runtime_options)  # type: ignore[attr-defined]
                except Exception:
                    pass


    def _nsopw_clear_tree(self):
        self.nsopw_tree.delete(*self.nsopw_tree.get_children())
        if getattr(self, "nsopw_tree_other", None) is not None:
            self.nsopw_tree_other.delete(*self.nsopw_tree_other.get_children())
        self._nsopw_insert_count = 0
        self._nsopw_other_count = 0
        self._nsopw_photo_by_iid = {}
        self._nsopw_records_by_iid = {}
        if getattr(self, "nsopw_detail", None) is not None:
            self._fill_detail_drawer(self.nsopw_detail, None)


