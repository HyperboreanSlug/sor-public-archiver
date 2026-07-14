"""MisclassifyBuildMixin."""
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


class MisclassifyBuildMixin:
    def _ensure_misclass_filter_vars(self) -> None:
        """Create Analyze filter vars even if Misclassify tab was never opened.

        Reports → Analyze & build and CSV export call into this path while the
        Misclassify UI (which used to create the vars) may still be lazy-unbuilt.
        """
        if not hasattr(self, "misclass_ethnicity_var"):
            self.misclass_ethnicity_var = ctk.StringVar(value="all")
        if not hasattr(self, "misclass_conf_var"):
            self.misclass_conf_var = ctk.DoubleVar(value=0.5)
        if not hasattr(self, "misclass_limit_var"):
            # 0 = scan entire DB; when capped, Analyze walks newest ids first
            self.misclass_limit_var = ctk.IntVar(value=0)
        if not hasattr(self, "enrich_limit_var"):
            self.enrich_limit_var = ctk.IntVar(value=25)
        if not hasattr(self, "enrich_external_only_var"):
            self.enrich_external_only_var = ctk.BooleanVar(value=False)
        if not hasattr(self, "_misclass_results"):
            self._misclass_results = []
        if not hasattr(self, "_misclass_meta"):
            self._misclass_meta = {}


    def _misclass_controls_bar(self, parent) -> ctk.CTkFrame:
        """Shared Analyze filters (used by Misclassify + Statistics)."""
        bar = ctk.CTkFrame(parent, fg_color="transparent")
        self._ensure_misclass_filter_vars()

        ctk.CTkComboBox(
            bar, variable=self.misclass_ethnicity_var, width=160,
            values=[
                "all", "hispanic", "asian", "indian", "indian_high_confidence",
                "african_american",
            ],
            fg_color=C["bg"], border_color=C["border"], button_color=C["elevated"],
            text_color=C["text"], dropdown_fg_color=C["panel"],
        ).pack(side="left", padx=(0, 8))

        ctk.CTkLabel(bar, text="Min conf.", font=FONT_SM, text_color=C["muted"]).pack(
            side="left", padx=(8, 4)
        )
        ctk.CTkEntry(
            bar, textvariable=self.misclass_conf_var, width=60,
            fg_color=C["bg"], border_color=C["border"], text_color=C["text"],
        ).pack(side="left")

        ctk.CTkLabel(bar, text="Scan cap (0=all)", font=FONT_SM, text_color=C["muted"]).pack(
            side="left", padx=(12, 4)
        )
        ctk.CTkEntry(
            bar, textvariable=self.misclass_limit_var, width=80,
            fg_color=C["bg"], border_color=C["border"], text_color=C["text"],
        ).pack(side="left")

        ctk.CTkButton(
            bar, text="Analyze", width=100, command=self._run_misclassification,
            fg_color=C["accent"], hover_color=C["accent_hover"], text_color=C["bg"],
        ).pack(side="left", padx=12)
        ctk.CTkButton(
            bar, text="Export CSV", width=100, command=self._export_misclass,
            fg_color=C["elevated"], hover_color=C["border"], text_color=C["text"],
            border_width=1, border_color=C["border"],
        ).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(bar, text="Enrich lim", font=FONT_SM, text_color=C["muted"]).pack(
            side="left", padx=(8, 4)
        )
        ctk.CTkEntry(
            bar, textvariable=self.enrich_limit_var, width=52,
            fg_color=C["bg"], border_color=C["border"], text_color=C["text"],
        ).pack(side="left", padx=(0, 4))
        ctk.CTkCheckBox(
            bar, text="External imports only", variable=self.enrich_external_only_var,
            font=FONT_SM, text_color=C["text"],
            fg_color=C["accent"], hover_color=C["accent_hover"],
            checkmark_color=C["bg"], border_color=C["border"],
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            bar, text="NSOPW enrich", width=120, command=self._start_enrich_misclassified,
            fg_color=C["elevated"], hover_color=C["border"], text_color=C["text"],
            border_width=1, border_color=C["border"],
        ).pack(side="left")
        return bar


    def _build_misclass(self, tab):
        tab.configure(fg_color=C["surface"])
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        bar = self._misclass_controls_bar(tab)
        bar.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))

        # Table | detail drawer (photo + fields) — same pattern as Search
        mid = _hpaned(tab)
        mid.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 4))
        left = ctk.CTkFrame(mid, fg_color="transparent")
        mid.add(left, minsize=360, stretch="always")
        self.misclass_detail = self._make_detail_drawer(mid)
        mid.add(self.misclass_detail, minsize=220, stretch="never")
        self.after(160, lambda: self._set_sash(mid, 0, 0.72))

        results_card = _card(left)
        results_card.pack(fill="both", expand=True)
        _section_label(results_card, "Potential mismatches").pack(
            anchor="w", padx=14, pady=(12, 4)
        )
        _muted(
            results_card,
            "Surname ethnicity does not match recorded race. "
            "Select a row for photo · Statistics for charts · Reports for photo review.",
        ).pack(anchor="w", padx=14, pady=(0, 6))

        wrap, self.misclass_tree = _tree_frame(results_card)
        wrap.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        cols = ["name", "recorded_race", "likely_ethnicity", "confidence", "matching_names"]
        self.misclass_tree.configure(columns=cols, show="headings")
        _stretch_columns(self.misclass_tree, cols, [160, 110, 130, 90, 200])
        _enable_tree_column_sort(
            self.misclass_tree,
            cols,
            labels={c: c.replace("_", " ").upper() for c in cols},
        )
        _bind_tree_scroll_isolation(self.misclass_tree, wrap)
        self.misclass_tree.bind("<<TreeviewSelect>>", self._misclass_on_select)
        self._misclass_records_by_iid: Dict[str, Dict[str, Any]] = {}

        self.misclass_status = ctk.CTkLabel(
            tab,
            text="Compare recorded race to surname ethnicity lists · click a name for photo",
            font=FONT_SM, text_color=C["muted"],
        )
        self.misclass_status.grid(row=2, column=0, sticky="w", padx=14, pady=(0, 10))


