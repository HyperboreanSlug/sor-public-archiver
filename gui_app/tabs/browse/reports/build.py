"""Build"""
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


class ReportsBuildMixin:
    def _build_reports(self, tab):
        """Scrollable photo gallery for verifying mismatches and exporting."""
        tab.configure(fg_color=C["surface"])
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(2, weight=1)

        # ---- Toolbar ----
        top = ctk.CTkFrame(tab, fg_color=C["surface"])
        top.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 2))

        bar = ctk.CTkFrame(top, fg_color="transparent")
        bar.pack(fill="x", padx=4, pady=(0, 4))

        ctk.CTkButton(
            bar, text="Analyze & build", width=130,
            command=self._reports_build_list,
            fg_color=C["accent"], hover_color=C["accent_hover"], text_color=C["bg"],
        ).pack(side="left", padx=(0, 6))

        self.report_photos_only = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            bar, text="Photos only", variable=self.report_photos_only,
            font=FONT_SM, text_color=C["text"],
            fg_color=C["accent"], hover_color=C["accent_hover"],
            border_color=C["border"], checkmark_color=C["bg"],
            command=lambda: self._reports_on_filter_change(),
        ).pack(side="left", padx=(0, 8))

        # Include stored DeepFace mugshot hits (from DeepFace → Scan) — off by default
        self.report_include_deepface = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            bar, text="DeepFace hits", variable=self.report_include_deepface,
            font=FONT_SM, text_color=C["text"],
            fg_color=C["accent"], hover_color=C["accent_hover"],
            border_color=C["border"], checkmark_color=C["bg"],
            command=lambda: self._reports_on_filter_change(),
        ).pack(side="left", padx=(0, 8))

        # Layout: list rows vs multi-column mugshot grid (also used by Open HTML)
        self.report_grid_view = ctk.BooleanVar(value=True)
        self.report_layout_mode = ctk.StringVar(value="Grid")
        ctk.CTkLabel(bar, text="Layout", font=FONT_SM, text_color=C["muted"]).pack(
            side="left", padx=(4, 4)
        )
        self.report_layout_seg = ctk.CTkSegmentedButton(
            bar,
            values=["Grid", "List"],
            variable=self.report_layout_mode,
            command=self._reports_on_layout_change,
            font=FONT_SM,
            fg_color=C["elevated"],
            selected_color=C["accent_dim"],
            selected_hover_color=C["select"],
            unselected_color=C["elevated"],
            unselected_hover_color=C["panel"],
            text_color=C["text"],
            height=28,
        )
        self.report_layout_seg.pack(side="left", padx=(0, 10))
        try:
            self.report_layout_seg.set("Grid")
        except Exception:
            pass

        # Listed-as (registry race) + actual (surname / face) — dropdowns
        ctk.CTkLabel(bar, text="Listed as", font=FONT_SM, text_color=C["muted"]).pack(
            side="left", padx=(4, 4)
        )
        self.report_listed_filter = ctk.StringVar(value="White")
        ctk.CTkComboBox(
            bar,
            variable=self.report_listed_filter,
            width=100,
            values=["All", "White", "Black", "Other"],
            fg_color=C["bg"],
            border_color=C["border"],
            button_color=C["elevated"],
            text_color=C["text"],
            dropdown_fg_color=C["panel"],
            command=lambda _v: self._reports_on_filter_change(),
        ).pack(side="left", padx=(0, 8))

        ctk.CTkLabel(bar, text="Actual", font=FONT_SM, text_color=C["muted"]).pack(
            side="left", padx=(4, 4)
        )
        self.report_actual_filter = ctk.StringVar(value="All")
        ctk.CTkComboBox(
            bar,
            variable=self.report_actual_filter,
            width=150,
            values=[
                "All",
                "Hispanic",
                "Indian",
                "Asian",
                "African American",
                "Arabic",
                "European",
                "Jewish",
                "Portuguese",
                "Native American",
                "Other",
            ],
            fg_color=C["bg"],
            border_color=C["border"],
            button_color=C["elevated"],
            text_color=C["text"],
            dropdown_fg_color=C["panel"],
            command=lambda _v: self._reports_on_filter_change(),
        ).pack(side="left", padx=(0, 8))

        # Legacy BooleanVars kept in sync for any old callers
        self.report_race_white = ctk.BooleanVar(value=True)
        self.report_race_black = ctk.BooleanVar(value=False)
        self.report_race_other = ctk.BooleanVar(value=False)

        ctk.CTkLabel(bar, text="Page size", font=FONT_SM, text_color=C["muted"]).pack(
            side="left", padx=(8, 4)
        )
        self.report_max_var = ctk.IntVar(value=48)
        page_size_entry = ctk.CTkEntry(
            bar, textvariable=self.report_max_var, width=48,
            fg_color=C["bg"], border_color=C["border"], text_color=C["text"],
        )
        page_size_entry.pack(side="left", padx=(0, 8))
        # Enter reapplies page size (Prev/Next also re-read it each click)
        page_size_entry.bind(
            "<Return>", lambda _e: self._reports_on_filter_change()
        )

        ctk.CTkLabel(bar, text="Show", font=FONT_SM, text_color=C["muted"]).pack(
            side="left", padx=(4, 4)
        )
        # Work queue default: unconfirmed only
        self.report_verdict_filter = ctk.StringVar(value="Unconfirmed")
        ctk.CTkComboBox(
            bar, variable=self.report_verdict_filter, width=170,
            values=[
                "Unconfirmed",
                "Confirmed incorrect",
                "Confirmed correct",
                "All",
            ],
            fg_color=C["bg"], border_color=C["border"], button_color=C["elevated"],
            text_color=C["text"], dropdown_fg_color=C["panel"],
            # Pass selection explicitly — StringVar can lag one tick behind command
            command=lambda v: self._reports_on_filter_change(show_value=v),
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            bar, text="Confirm unchecked", width=130,
            command=self._reports_confirm_unchecked,
            fg_color="#5c3030", hover_color="#7a4040", text_color=C["text"],
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            bar, text="Open HTML", width=100,
            command=self._reports_open_html,
            fg_color=C["elevated"], hover_color=C["border"], text_color=C["text"],
            border_width=1, border_color=C["border"],
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            bar, text="Export CSV", width=90,
            command=self._reports_export_csv,
            fg_color=C["elevated"], hover_color=C["border"], text_color=C["text"],
            border_width=1, border_color=C["border"],
        ).pack(side="left", padx=(0, 8))

        # Checkbox export → watermarked mapa-style card grids
        ctk.CTkLabel(
            bar, text="Grid export", font=FONT_SM, text_color=C["muted"],
        ).pack(side="left", padx=(4, 4))
        ctk.CTkButton(
            bar, text="1×2", width=48,
            command=lambda: self._reports_export_grid("1x2"),
            fg_color=C["elevated"], hover_color=C["border"], text_color=C["text"],
            border_width=1, border_color=C["border"],
        ).pack(side="left", padx=(0, 4))
        ctk.CTkButton(
            bar, text="2×2", width=48,
            command=lambda: self._reports_export_grid("2x2"),
            fg_color=C["elevated"], hover_color=C["border"], text_color=C["text"],
            border_width=1, border_color=C["border"],
        ).pack(side="left", padx=(0, 4))
        ctk.CTkButton(
            bar, text="Clear sel", width=70,
            command=self._reports_clear_export_selection,
            fg_color=C["elevated"], hover_color=C["border"], text_color=C["muted"],
            border_width=1, border_color=C["border"],
        ).pack(side="left", padx=(0, 6))
        self.report_export_sel_label = ctk.CTkLabel(
            bar, text="Selected for grid: 0", font=FONT_SM, text_color=C["dim"],
        )
        self.report_export_sel_label.pack(side="left", padx=(0, 4))
        if hasattr(self, "_reports_export_selected_init"):
            self._reports_export_selected_init()

        # Pagination row
        page_row = ctk.CTkFrame(top, fg_color="transparent")
        page_row.pack(fill="x", padx=4, pady=(0, 2))
        self._report_page = 0
        self._report_pool: list = []  # full filtered list
        ctk.CTkButton(
            page_row, text="◀ Prev", width=80,
            command=self._reports_prev_page,
            fg_color=C["elevated"], hover_color=C["border"], text_color=C["text"],
            border_width=1, border_color=C["border"],
        ).pack(side="left", padx=(0, 6))
        self.report_page_label = ctk.CTkLabel(
            page_row, text="Page —", font=FONT_SM, text_color=C["muted"],
        )
        self.report_page_label.pack(side="left", padx=6)
        ctk.CTkButton(
            page_row, text="Next ▶", width=90,
            command=self._reports_next_page,
            fg_color=C["elevated"], hover_color=C["border"], text_color=C["text"],
            border_width=1, border_color=C["border"],
        ).pack(side="left", padx=(6, 0))
        self.report_layout_hint = ctk.CTkLabel(
            page_row,
            text="Check cards → 1×2 / 2×2 watermarked export  ·  Open HTML uses layout",
            font=FONT_SM,
            text_color=C["dim"],
        )
        self.report_layout_hint.pack(side="left", padx=(14, 0))

        # ---- Summary metrics ----
        sum_row = ctk.CTkFrame(top, fg_color="transparent")
        sum_row.pack(fill="x", padx=4, pady=(0, 4))

        def _chip(key: str) -> ctk.CTkLabel:
            chip = ctk.CTkFrame(
                sum_row, fg_color=C["elevated"], corner_radius=6,
                border_width=1, border_color=C["border"],
            )
            chip.pack(side="left", padx=3, pady=1, fill="x", expand=True)
            lb = ctk.CTkLabel(
                chip, text="—", font=FONT_SM, text_color=C["text"], anchor="center",
            )
            lb.pack(padx=8, pady=5)
            setattr(self, key, lb)
            return lb

        _chip("report_m_total")
        _chip("report_m_photo")
        _chip("report_m_confirmed")
        _chip("report_m_correct")
        _chip("report_m_unreviewed")

        self.report_status = ctk.CTkLabel(
            top,
            text=(
                "Click Analyze & build (uses Misclassify ethnicity / min conf). "
                "Show: Unconfirmed (default) · Confirmed correct drops off this sheet."
            ),
            font=FONT_SM, text_color=C["dim"], anchor="w",
        )
        self.report_status.pack(fill="x", padx=8, pady=(0, 4))

        # ---- Scrollable card list (fast wheel binding after paint) ----
        scroll = ctk.CTkScrollableFrame(
            tab, fg_color=C["surface"], corner_radius=0, border_width=0,
        )
        scroll.grid(row=2, column=0, sticky="nsew", padx=4, pady=(0, 6))
        scroll.grid_columnconfigure(0, weight=1)
        self._report_scroll = scroll
        self._report_tab = tab
        self.after(30, lambda: _wire_wide_scroll(tab, scroll))
        self.after(80, lambda: self._reports_bind_fast_scroll(tab, scroll))

        # Empty-state placeholder
        self._report_empty = ctk.CTkLabel(
            scroll,
            text=(
                "No report list yet.\n\n"
                "1. Set ethnicity / min conf (shared with Misclassify)\n"
                "2. Click Analyze & build\n"
                "3. Review Unconfirmed — mark Confirmed incorrect or Confirmed correct\n"
                "4. Confirmed cards leave Unconfirmed (use Show → Confirmed / All)\n"
                "5. Show: Unconfirmed · Confirmed incorrect · Confirmed correct · All"
            ),
            font=FONT_SM, text_color=C["dim"], justify="left",
        )
        self._report_empty.pack(anchor="w", padx=16, pady=24)


