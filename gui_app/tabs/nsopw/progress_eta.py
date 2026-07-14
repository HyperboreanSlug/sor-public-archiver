"""NSOPW ETA helpers."""
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


class NsopwEtaMixin:
    @staticmethod
    def _format_eta(seconds: Optional[float]) -> str:
        """Human ETA string from seconds remaining (None → still calculating)."""
        if seconds is None:
            return "ETA …"
        try:
            s = max(0, int(round(float(seconds))))
        except (TypeError, ValueError):
            return "ETA …"
        if s < 5:
            return "ETA <5s"
        if s < 60:
            return f"ETA ~{s}s"
        mins, sec = divmod(s, 60)
        if mins < 60:
            return f"ETA ~{mins}m {sec:02d}s" if sec else f"ETA ~{mins}m"
        hours, mins = divmod(mins, 60)
        if hours < 48:
            return f"ETA ~{hours}h {mins:02d}m"
        days, hours = divmod(hours, 24)
        return f"ETA ~{days}d {hours}h"


    def _nsopw_estimate_eta_seconds(self, info: Dict[str, Any]) -> Optional[float]:
        """
        Estimate remaining runtime from observed pace.

        Prefers new-search throughput when max_searches is set; otherwise plan
        steps. Blends wall-clock rate with configured search_delay as a floor.
        """
        import time as _time

        t0 = getattr(self, "_nsopw_run_t0", None)
        if t0 is None:
            return None
        now = _time.monotonic()
        elapsed = now - t0
        if elapsed < 1.0:
            return None

        searches = int(info.get("searches") or 0)
        plan_i = int(info.get("plan_i") or 0)
        plan_total = int(info.get("plan_total") or 0)
        search_cap = info.get("search_cap")
        try:
            search_delay = float(info.get("search_delay") or self.nsopw_search_delay.get() or 3.0)
        except (TypeError, ValueError):
            search_delay = 3.0
        search_delay = max(2.0, search_delay)

        # Work unit: new searches under a cap, else plan cursor
        remaining: Optional[float] = None
        rate: Optional[float] = None  # units per second

        if search_cap is not None:
            try:
                cap = int(search_cap)
            except (TypeError, ValueError):
                cap = 0
            if cap > 0:
                remaining = max(0.0, float(cap - searches))
                if searches >= 1:
                    rate = searches / elapsed
        if remaining is None and plan_total > 0:
            remaining = max(0.0, float(plan_total - plan_i))
            if plan_i >= 1:
                rate = plan_i / elapsed

        if remaining is not None and remaining <= 0:
            return 0.0
        if remaining is None:
            return None

        # Pace from recent samples (smoother than whole-run average)
        samples = getattr(self, "_nsopw_eta_samples", None)
        if samples is None:
            self._nsopw_eta_samples = []
            samples = self._nsopw_eta_samples
        work_done = float(searches if search_cap is not None else plan_i)
        samples.append((now, work_done))
        # Keep ~2 minutes of samples
        cutoff = now - 120.0
        self._nsopw_eta_samples = [(t, w) for t, w in samples if t >= cutoff]
        samples = self._nsopw_eta_samples
        if len(samples) >= 2:
            t_a, w_a = samples[0]
            t_b, w_b = samples[-1]
            dt = t_b - t_a
            dw = w_b - w_a
            if dt >= 3.0 and dw > 0:
                recent_rate = dw / dt
                rate = recent_rate if rate is None else (0.4 * rate + 0.6 * recent_rate)

        if rate is None or rate <= 0:
            # Before first completed unit: lower-bound from configured delay
            if search_cap is not None and remaining is not None:
                return remaining * search_delay
            return None

        eta = remaining / rate
        # Don't estimate faster than delay allows for remaining *new* searches
        if search_cap is not None:
            eta = max(eta, remaining * search_delay * 0.85)
        # Cap absurd estimates
        if eta > 7 * 24 * 3600:
            eta = 7 * 24 * 3600
        return eta


    def _nsopw_reset_progress_ui(self) -> None:
        """Zero the progress bar and statistic chips."""
        try:
            self.nsopw_progress.set(0)
            if hasattr(self, "nsopw_progress_label"):
                self.nsopw_progress_label.configure(text="0%")
            if hasattr(self, "nsopw_eta_label"):
                self.nsopw_eta_label.configure(text="ETA —")
            if hasattr(self, "nsopw_current_search_label"):
                self.nsopw_current_search_label.configure(text="—")
            self._nsopw_last_search_terms = ""
            self._nsopw_eta_samples = []
            for key, lbl in getattr(self, "_nsopw_stat_vars", {}).items():
                lbl.configure(text="0" if key != "plan" else "—")
        except Exception:
            pass


