"""DfrGridMixin."""
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


class DfrGridMixin:
    def _dfr_view_as_grid(self) -> None:
        """Open Browse → Reports in Grid layout with DeepFace hits enabled."""
        hits = list(getattr(self, "_dfr_hits", None) or [])
        if not hits and not getattr(self, "_dfr_all_hits", None):
            messagebox.showinfo(
                "View as grid",
                "No DeepFace hits loaded yet.\nRefresh hits first, or run DeepFace → Scan.",
            )
            return

        # Ensure Reports tab widgets exist (lazy)
        if hasattr(self, "_browse_lazy"):
            try:
                self._browse_lazy.ensure("Reports")
            except Exception as e:
                messagebox.showerror("View as grid", f"Could not open Reports:\n{e}")
                return

        try:
            if hasattr(self, "report_include_deepface"):
                self.report_include_deepface.set(True)
            if hasattr(self, "report_photos_only"):
                self.report_photos_only.set(True)
            if hasattr(self, "report_listed_filter"):
                # DeepFace hits span all registry races — don't keep White-only default
                self.report_listed_filter.set("All")
            if hasattr(self, "report_actual_filter"):
                self.report_actual_filter.set("All")
            if hasattr(self, "report_layout_mode"):
                self.report_layout_mode.set("Grid")
            if hasattr(self, "report_grid_view"):
                self.report_grid_view.set(True)
            if hasattr(self, "report_layout_seg"):
                try:
                    self.report_layout_seg.set("Grid")
                except Exception:
                    pass

            # Mirror DeepFace Show filter into Reports when possible
            vmap = {
                "unreviewed": "Unconfirmed",
                "confirmed": "Confirmed incorrect",
                "correct": "Confirmed correct",
                "skip": "All",
                "all": "All",
            }
            show = vmap.get(self._dfr_show_filter_key(), "Unconfirmed")
            if hasattr(self, "report_verdict_filter"):
                self.report_verdict_filter.set(show)

            if hasattr(self, "browse_tabs"):
                self.browse_tabs.set("Reports")
        except Exception as e:
            messagebox.showerror("View as grid", str(e))
            return

        def _rebuild():
            try:
                # Seed Reports with the *currently filtered* DeepFace hit list so
                # face/state/min-conf/verdict filters are not discarded.
                seed = list(getattr(self, "_dfr_hits", None) or [])
                self._report_page = 0
                if seed:
                    self._report_pool = seed
                    if hasattr(self, "_reports_rebuild_cards"):
                        self._reports_rebuild_cards(refilter=False)
                    if hasattr(self, "_reports_update_metrics"):
                        try:
                            self._reports_update_metrics()
                        except Exception:
                            pass
                elif hasattr(self, "_reports_on_filter_change"):
                    self._reports_on_filter_change(show_value=show)
                elif hasattr(self, "_reports_rebuild_cards"):
                    self._reports_rebuild_cards(refilter=True)
                if hasattr(self, "report_status"):
                    n = len(getattr(self, "_report_pool", None) or [])
                    self.report_status.configure(
                        text=f"DeepFace filtered hits · Grid · {n:,} people"
                    )
                if hasattr(self, "dfr_status"):
                    self.dfr_status.configure(
                        text="Opened Browse → Reports (Grid · current DeepFace filter)"
                    )
            except Exception as e:
                messagebox.showerror("View as grid", str(e))

        self.after(60, _rebuild)


