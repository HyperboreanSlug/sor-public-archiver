"""NSOPW ethnicity/subcategory controls."""
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


class NsopwEthnicityMixin:
    def _nsopw_on_ethnicity_change(self, _choice=None):
        self._nsopw_refresh_subcategories()
        self._nsopw_update_surname_count()


    def _nsopw_on_subcategory_change(self, _choice=None):
        self._nsopw_update_surname_count()


    def _nsopw_refresh_subcategories(self):
        """Reload subcategory dropdown for the current ethnicity."""
        from scraper.ethnic_names import get_ethnic_database

        eth = (self.nsopw_ethnicity.get() or "hispanic").strip().lower()
        db = get_ethnic_database()
        subs = db.subcategories(eth)
        if not subs:
            subs = ["all"]
        self.nsopw_sub_combo.configure(values=subs)
        # Default to all when list changes
        self.nsopw_subcategory.set("all" if "all" in subs else subs[0])
        # Enable only when real subgroups exist
        if db.has_subcategories(eth):
            self.nsopw_sub_combo.configure(state="normal")
        else:
            self.nsopw_sub_combo.configure(state="disabled")


    def _nsopw_toggle_surname_cap(self):
        """Enable max-surnames entry only when the limit toggle is on."""
        if self.nsopw_limit_surnames.get():
            self.nsopw_surnames_entry.configure(state="normal")
        else:
            self.nsopw_surnames_entry.configure(state="disabled")
        self._nsopw_update_surname_count()


    def _nsopw_surname_selection_params(self) -> tuple:
        """Return (ethnicity, subcategory, all_surnames, surnames_limit)."""
        eth = (self.nsopw_ethnicity.get() or "hispanic").strip().lower()
        sub = (self.nsopw_subcategory.get() or "all").strip().lower()
        limit_on = bool(self.nsopw_limit_surnames.get())
        all_surnames = not limit_on
        try:
            surnames_limit = int(self.nsopw_surnames_limit.get()) if limit_on else 0
        except (TypeError, ValueError):
            surnames_limit = 15 if limit_on else 0
        return eth, sub, all_surnames, surnames_limit


    def _nsopw_update_surname_count(self):
        """Show how many unique surnames the current filters select."""
        try:
            from scraper.ethnic_names import get_ethnic_database
            from scraper.nsopw_builder import (
                FIRST_INITIALS,
                NSOPWEthnicDatabaseBuilder,
                describe_first_mode,
                estimate_compact_query_count,
                first_initials_for_mode,
            )

            eth, sub, all_surnames, surnames_limit = self._nsopw_surname_selection_params()
            first_mode = (
                (self.nsopw_first_mode_var.get() or "initials").strip().lower()
                if hasattr(self, "nsopw_first_mode_var")
                else "initials"
            )
            firsts = first_initials_for_mode(first_mode)
            # Avoid full builder init (HTTP clients) — only need ethnic_db for selection
            light = object.__new__(NSOPWEthnicDatabaseBuilder)
            light.ethnic_db = get_ethnic_database()
            pairs = NSOPWEthnicDatabaseBuilder.surnames_for_ethnicity(
                light,
                eth,
                limit_per_group=surnames_limit,
                all_surnames=all_surnames,
                subcategory=sub,
            )
            n = len(pairs)
            naive = n * len(firsts)
            az_naive = n * len(FIRST_INITIALS)
            use_compact = bool(self.app_settings.get("nsopw_compact_prefixes", True))
            if hasattr(self, "settings_compact_prefixes"):
                use_compact = bool(self.settings_compact_prefixes.get())
            try:
                mcl = int(self.app_settings.get("nsopw_min_combined_len", 3))
                if hasattr(self, "settings_min_combined"):
                    mcl = int(str(self.settings_min_combined.get()).strip() or "3")
            except (TypeError, ValueError):
                mcl = 3
            mcl = max(3, min(mcl, 10))
            from scraper.nsopw_builder import (
                is_abbreviated_first_mode,
                last_prefix_whitelist_for,
            )
            last_allow = last_prefix_whitelist_for(
                eth,
                pairs,
                abbreviated=is_abbreviated_first_mode(first_mode),
                mode=first_mode,
            )
            if use_compact:
                est = estimate_compact_query_count(
                    pairs, firsts, min_combined=mcl, allowed_last_prefixes=last_allow
                )
                est_az = estimate_compact_query_count(
                    pairs, FIRST_INITIALS, min_combined=mcl
                )
                mode_txt = (
                    f"Est. queries: {est:,}  ·  {describe_first_mode(first_mode)}"
                )
                if first_mode not in ("initials", "all", "") and est_az != est:
                    mode_txt += f"  (A–Z would be {est_az:,})"
            else:
                est = naive
                mode_txt = (
                    f"Est. queries: {est:,} full surnames × {len(firsts)} firsts"
                )
                if first_mode not in ("initials", "all", "") and az_naive != est:
                    mode_txt += f"  (A–Z would be {az_naive:,})"
            scope = f"{eth}" + (f" / {sub}" if sub and sub != "all" else " / all groups")
            self.nsopw_surname_count_label.configure(
                text=f"Surnames in list: {n:,}  ({scope})  ·  {mode_txt}"
            )
        except Exception as e:
            self.nsopw_surname_count_label.configure(
                text=f"Surnames to search: (error computing count: {e})"
            )


