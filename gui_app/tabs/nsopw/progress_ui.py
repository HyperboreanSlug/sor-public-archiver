"""NSOPW progress bar updates."""
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


class NsopwProgressUiMixin:
    def _nsopw_update_progress(self, info: Dict[str, Any]) -> None:
        """UI-thread: update determinate progress bar + stat chips + ETA."""
        try:
            # Throttle top-bar record count while inserts land
            import time as _time

            now = _time.monotonic()
            last = float(getattr(self, "_nsopw_header_refresh_ts", 0) or 0)
            if now - last >= 2.0:
                self._nsopw_header_refresh_ts = now
                try:
                    if hasattr(self, "schedule_header_refresh"):
                        self.schedule_header_refresh(0)
                    else:
                        self._refresh_header_db_path()
                except Exception:
                    pass

            done = float(info.get("done") or info.get("plan_i") or 0)
            total = float(info.get("total") or info.get("plan_total") or 0)
            # Prefer search-cap progress when available (matches live max searches)
            sc = info.get("search_cap")
            searches = int(info.get("searches") or 0)
            if sc is not None:
                try:
                    sc_n = float(sc)
                    if sc_n > 0:
                        total = sc_n
                        done = float(searches)
                except (TypeError, ValueError):
                    pass
            if total <= 0:
                frac = 0.0
            else:
                frac = min(1.0, max(0.0, done / total))
            self.nsopw_progress.set(frac)
            if hasattr(self, "nsopw_progress_label"):
                self.nsopw_progress_label.configure(text=f"{int(round(frac * 100))}%")

            eta_sec = self._nsopw_estimate_eta_seconds(info)
            eta_txt = self._format_eta(eta_sec)
            if hasattr(self, "nsopw_eta_label"):
                phase0 = (info.get("phase") or "").strip()
                if phase0 == "done":
                    self.nsopw_eta_label.configure(text="ETA done")
                elif phase0 == "cancelled":
                    self.nsopw_eta_label.configure(text="ETA —")
                else:
                    self.nsopw_eta_label.configure(text=eta_txt)

            plan_i = int(info.get("plan_i") or 0)
            plan_total = int(info.get("plan_total") or 0)
            skipped = int(info.get("searches_skipped") or 0)
            matched = int(info.get("inserted_matched") or self._nsopw_insert_count or 0)
            other = int(info.get("inserted_other") or self._nsopw_other_count or 0)
            hits = int(info.get("search_hits") or 0)
            html = int(info.get("html_saved") or 0)
            photos = int(info.get("photos_saved") or 0)
            race = int(info.get("reports_with_race") or 0)

            vars_ = getattr(self, "_nsopw_stat_vars", {})
            if "plan" in vars_:
                vars_["plan"].configure(
                    text=f"{plan_i}/{plan_total}" if plan_total else str(plan_i)
                )
            if "searches" in vars_:
                cap = info.get("search_cap")
                cap_s = f"/{cap}" if cap is not None else ""
                vars_["searches"].configure(
                    text=f"{searches}{cap_s}" + (f" (+{skipped} skip)" if skipped else "")
                )
            if "matched" in vars_:
                vars_["matched"].configure(text=str(matched))
            if "other" in vars_:
                vars_["other"].configure(text=str(other))
            if "hits" in vars_:
                vars_["hits"].configure(text=str(hits))
            if "html" in vars_:
                vars_["html"].configure(text=str(html))
            if "photos" in vars_:
                vars_["photos"].configure(text=str(photos))
            if "race" in vars_:
                vars_["race"].configure(text=str(race))

            phase = (info.get("phase") or "").strip()
            current = (info.get("current") or "").strip()
            # Structured search terms (preferred) or free-text current
            sf = (info.get("search_first") or "").strip()
            sl = (info.get("search_last") or "").strip()
            covers = (info.get("search_covers") or "").strip()
            lab = (info.get("search_label") or "").strip()
            if sf or sl:
                terms = f"first='{sf}' last='{sl}'"
                if covers:
                    terms += f" · covers {covers}"
                if lab:
                    terms += f" · {lab}"
            else:
                terms = current
            if terms and phase not in ("done", "cancelled", "start"):
                self._nsopw_last_search_terms = terms
            if hasattr(self, "nsopw_current_search_label"):
                if phase == "done":
                    self.nsopw_current_search_label.configure(text="complete")
                elif phase == "cancelled":
                    self.nsopw_current_search_label.configure(text="cancelled")
                elif phase == "start" or not terms:
                    self.nsopw_current_search_label.configure(text="starting…")
                elif phase == "resume_skip":
                    self.nsopw_current_search_label.configure(
                        text=f"skip {terms}" if terms else "skip…"
                    )
                else:
                    self.nsopw_current_search_label.configure(text=terms or "—")

            if phase == "done":
                pass  # status set by completion handler
            elif phase == "cancelled":
                self.nsopw_status.configure(text="Cancelled")
            elif terms or current:
                display = terms or current
                self.nsopw_status.configure(
                    text=(
                        f"Running… search {display} · {eta_txt} · "
                        f"matched {matched} · other {other} · "
                        f"plan {plan_i}/{plan_total or '—'}"
                    )
                )
        except Exception:
            pass


