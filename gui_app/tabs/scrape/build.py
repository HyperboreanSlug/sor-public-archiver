"""ScrapeBuildMixin."""
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


class ScrapeBuildMixin:
    def _build_scrape(self, tab):
        tab.configure(fg_color=C["surface"])
        top = ctk.CTkFrame(tab, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(12, 6))

        self.scrape_direct_only = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            top,
            text="Direct / bulk only",
            variable=self.scrape_direct_only,
            font=FONT_SM,
            text_color=C["text"],
            fg_color=C["accent"],
            hover_color=C["accent_hover"],
            checkmark_color=C["bg"],
            border_color=C["border"],
        ).pack(side="left", padx=(0, 12))

        ctk.CTkButton(
            top, text="Select all", width=100, command=self._scrape_select_all,
            fg_color=C["elevated"], hover_color=C["border"], text_color=C["text"],
            border_width=1, border_color=C["border"],
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            top, text="Clear", width=80, command=self._scrape_clear_selection,
            fg_color=C["elevated"], hover_color=C["border"], text_color=C["text"],
            border_width=1, border_color=C["border"],
        ).pack(side="left", padx=4)

        mid_split = _hpaned(tab)
        mid_split.pack(fill="both", expand=True, padx=12, pady=6)
        self._scrape_split = mid_split

        left = _card(mid_split)
        right = _card(mid_split)
        mid_split.add(left, minsize=320, stretch="always")
        mid_split.add(right, minsize=220, stretch="never")
        self.after(150, lambda: self._set_sash(mid_split, 0, 0.72))

        _section_label(left, "Jurisdictions").pack(anchor="w", padx=14, pady=(12, 4))
        _muted(
            left,
            "INTERACTIVE: the site only offers a web search form (often disclaimer, CAPTCHA, "
            "or session). There is no public bulk download, so automated scrape returns no "
            "records — look up offenders in a browser. Prefer Direct / bulk only for "
            "jurisdictions that publish downloadable data (DIRECT, ARCGIS, etc.).",
        ).pack(anchor="w", padx=14, pady=(0, 8))

        tree_wrap, self.scrape_tree = _tree_frame(left)
        tree_wrap.pack(fill="both", expand=True, padx=10, pady=(0, 12))
        self.scrape_tree.configure(columns=("abbr", "method", "notes"), show="tree headings", selectmode="extended")
        self.scrape_tree.heading("#0", text="Jurisdiction")
        self.scrape_tree.heading("abbr", text="Code")
        self.scrape_tree.heading("method", text="Method")
        self.scrape_tree.heading("notes", text="Notes")
        self.scrape_tree.column("#0", width=220, minwidth=80, stretch=True)
        self.scrape_tree.column("abbr", width=50, anchor="center", minwidth=40, stretch=False)
        self.scrape_tree.column("method", width=90, anchor="center", minwidth=60, stretch=False)
        self.scrape_tree.column("notes", width=280, minwidth=80, stretch=True)
        self.scrape_tree.bind("<<TreeviewSelect>>", self._scrape_on_select)
        self.scrape_tree.tag_configure("direct", background="#1a241c")
        _bind_tree_scroll_isolation(self.scrape_tree, tree_wrap)

        _section_label(right, "Options").pack(anchor="w", padx=14, pady=(12, 8))

        ctk.CTkLabel(right, text="Output folder", font=FONT_SM, text_color=C["muted"]).pack(
            anchor="w", padx=14
        )
        out_row = ctk.CTkFrame(right, fg_color="transparent")
        out_row.pack(fill="x", padx=14, pady=4)
        self.scrape_output_var = ctk.StringVar(value=str(Path("data/downloads")))
        ctk.CTkEntry(
            out_row, textvariable=self.scrape_output_var, fg_color=C["bg"],
            border_color=C["border"], text_color=C["text"],
        ).pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            out_row, text="…", width=36, command=self._scrape_browse_output,
            fg_color=C["elevated"], hover_color=C["border"],
        ).pack(side="left", padx=(6, 0))

        ctk.CTkLabel(right, text="Delay (seconds)", font=FONT_SM, text_color=C["muted"]).pack(
            anchor="w", padx=14, pady=(12, 0)
        )
        self.scrape_delay_var = ctk.DoubleVar(value=2.0)
        ctk.CTkSlider(
            right, from_=0.5, to=10.0, variable=self.scrape_delay_var,
            progress_color=C["accent"], button_color=C["accent"],
            button_hover_color=C["accent_hover"], fg_color=C["elevated"],
        ).pack(fill="x", padx=14, pady=8)

        self.scrape_btn = ctk.CTkButton(
            right,
            text="Start scraping",
            font=FONT_BOLD,
            height=42,
            fg_color=C["accent"],
            hover_color=C["accent_hover"],
            text_color=C["bg"],
            command=self._start_scrape,
        )
        self.scrape_btn.pack(fill="x", padx=14, pady=(16, 6))

        ctk.CTkButton(
            right, text="Open output folder", height=36,
            fg_color=C["elevated"], hover_color=C["border"], text_color=C["text"],
            border_width=1, border_color=C["border"],
            command=self._open_output_folder,
        ).pack(fill="x", padx=14, pady=4)

        ctk.CTkLabel(
            right, text="Import to database", font=FONT_BOLD, text_color=C["muted"],
        ).pack(anchor="w", padx=14, pady=(12, 4))
        _muted(
            right,
            "Scraped rows must be in the SQLite DB for Search, Integrity, and Misclassify. "
            "Auto-import after scrape is on by default; you can also load CSVs manually.",
        ).pack(anchor="w", padx=14, pady=(0, 6))
        self.scrape_auto_import = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            right, text="Import scrape results into DB (for Misclassify)",
            variable=self.scrape_auto_import, font=FONT_SM, text_color=C["text"],
            fg_color=C["accent"], hover_color=C["accent_hover"],
            checkmark_color=C["bg"], border_color=C["border"],
        ).pack(anchor="w", padx=14, pady=2)
        self.scrape_import_skip = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            right, text="Skip existing source URLs",
            variable=self.scrape_import_skip, font=FONT_SM, text_color=C["text"],
            fg_color=C["accent"], hover_color=C["accent_hover"],
            checkmark_color=C["bg"], border_color=C["border"],
        ).pack(anchor="w", padx=14, pady=2)
        ctk.CTkButton(
            right, text="Import folder → DB", height=36,
            command=self._import_downloads_folder,
            fg_color=C["accent"], hover_color=C["accent_hover"], text_color=C["bg"],
        ).pack(fill="x", padx=14, pady=(8, 4))
        ctk.CTkButton(
            right, text="Import CSV file…", height=32,
            command=self._import_csv_file,
            fg_color=C["elevated"], hover_color=C["border"], text_color=C["text"],
            border_width=1, border_color=C["border"],
        ).pack(fill="x", padx=14, pady=4)
        self.scrape_import_status = ctk.CTkLabel(
            right, text="", font=FONT_SM, text_color=C["muted"], anchor="w",
        )
        self.scrape_import_status.pack(fill="x", padx=14, pady=(4, 8))

        self.scrape_progress = ctk.CTkProgressBar(
            right, progress_color=C["accent"], fg_color=C["elevated"], height=8
        )
        self.scrape_progress.pack(fill="x", padx=14, pady=(8, 16))
        self.scrape_progress.set(0)

        # Sources may have been loaded before this tab was lazy-built
        self._populate_scrape_tree()


