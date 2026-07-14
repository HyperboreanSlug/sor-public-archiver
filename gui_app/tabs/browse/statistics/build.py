"""StatisticsBuildMixin."""
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


class StatisticsBuildMixin:
    def _build_misclass_statistics(self, tab):
        """Statistics: fixed toolbar + metrics; scroll only for charts/tables."""
        tab.configure(fg_color=C["surface"])
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        # Fixed top — always visible, no wasted scroll gap above content
        top = ctk.CTkFrame(tab, fg_color=C["surface"])
        top.grid(row=0, column=0, sticky="ew", padx=0, pady=0)

        bar = self._misclass_controls_bar(top)
        bar.pack(fill="x", padx=8, pady=(6, 2))

        # Metrics as a single compact row (no nested "Run summary" card header)
        sum_row = ctk.CTkFrame(top, fg_color="transparent")
        sum_row.pack(fill="x", padx=8, pady=(0, 4))

        def _metric_chip(parent, key: str) -> ctk.CTkLabel:
            chip = ctk.CTkFrame(
                parent, fg_color=C["elevated"], corner_radius=6,
                border_width=1, border_color=C["border"],
            )
            chip.pack(side="left", padx=3, pady=1, fill="x", expand=True)
            lb = ctk.CTkLabel(
                chip, text="—", font=FONT_SM, text_color=C["text"], anchor="center",
            )
            lb.pack(padx=8, pady=5)
            setattr(self, key, lb)
            return lb

        _metric_chip(sum_row, "mcstat_db")
        _metric_chip(sum_row, "mcstat_eth_n")  # selected ethnicity population
        _metric_chip(sum_row, "mcstat_n")      # misclassified count
        _metric_chip(sum_row, "mcstat_rate")   # % of selected ethnicity
        _metric_chip(sum_row, "mcstat_conf")
        self.mcstat_filter = ctk.CTkLabel(
            top, text="Run Analyze to fill charts and tables.",
            font=FONT_SM, text_color=C["dim"], anchor="w",
        )
        self.mcstat_filter.pack(fill="x", padx=10, pady=(0, 4))

        # Scroll only the heavy content
        scroll = ctk.CTkScrollableFrame(
            tab, fg_color=C["surface"], corner_radius=0, border_width=0,
        )
        scroll.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        scroll.grid_columnconfigure(0, weight=1)
        self._mcstat_scroll = scroll
        self.after(30, lambda: _wire_wide_scroll(tab, scroll))

        # Three pie charts side by side — first content in the scroll area
        charts = ctk.CTkFrame(scroll, fg_color="transparent")
        charts.pack(fill="x", padx=4, pady=(2, 6))
        self._mcstat_charts_host = charts
        charts.grid_columnconfigure((0, 1, 2), weight=1, uniform="pies")
        self._mcstat_chart_refs: List[Any] = []
        self.mcstat_chart_labels: List[ctk.CTkLabel] = []
        self._mcstat_chart_cells: List[ctk.CTkFrame] = []
        for i, placeholder in enumerate(
            (
                "By surname ethnicity\n(run Analyze)",
                "Misclassified as\n(run Analyze)",
                "Confidence bands\n(run Analyze)",
            )
        ):
            cell = ctk.CTkFrame(
                charts,
                fg_color=C["tree_bg"],
                corner_radius=8,
                border_width=1,
                border_color=C["border"],
                height=300,
            )
            cell.grid(row=0, column=i, sticky="nsew", padx=3, pady=0)
            cell.grid_propagate(False)
            lab = ctk.CTkLabel(
                cell, text=placeholder, font=FONT_SM, text_color=C["dim"],
            )
            lab.pack(expand=True, fill="both", padx=2, pady=2)
            self.mcstat_chart_labels.append(lab)
            self._mcstat_chart_cells.append(cell)

        # Transition table — full width, stretch columns
        trans = _card(scroll)
        trans.pack(fill="x", padx=6, pady=(0, 6))
        ctk.CTkLabel(
            trans,
            text="Transitions · surname ethnicity → recorded race",
            font=FONT_BOLD, text_color=C["muted"], anchor="w",
        ).pack(anchor="w", padx=10, pady=(8, 4))
        tw, self.mcstat_transition_tree = _tree_frame(trans)
        tw.pack(fill="x", padx=8, pady=(0, 8))
        tw.configure(height=220)
        tw.pack_propagate(False)
        tcols = ["surname_ethnicity", "misclassified_as", "count", "pct", "avg_conf", "example"]
        self.mcstat_transition_tree.configure(columns=tcols, show="headings", height=12)
        _stretch_columns(
            self.mcstat_transition_tree, tcols, [200, 180, 80, 70, 90, 260]
        )
        _enable_tree_column_sort(
            self.mcstat_transition_tree,
            tcols,
            labels={
                "surname_ethnicity": "SURNAME ETHNICITY",
                "misclassified_as": "MISCLASSIFIED AS",
                "count": "COUNT",
                "pct": "PERCENT",
                "avg_conf": "AVG CONF",
                "example": "EXAMPLE NAME",
            },
        )
        _bind_tree_scroll_isolation(self.mcstat_transition_tree, tw)

        # Breakdown tables side by side under transition table
        tables = ctk.CTkFrame(scroll, fg_color="transparent")
        tables.pack(fill="x", padx=4, pady=(0, 8))
        tables.grid_columnconfigure((0, 1, 2), weight=1, uniform="bkt")

        def _col_table(parent, col: int, title: str, cols: List[str], labels: Dict[str, str], widths: List[int]):
            cell = _card(parent)
            cell.grid(row=0, column=col, sticky="nsew", padx=3, pady=0)
            ctk.CTkLabel(
                cell, text=title, font=FONT_BOLD, text_color=C["muted"], anchor="w",
            ).pack(fill="x", padx=8, pady=(6, 2))
            w, tree = _tree_frame(cell)
            w.pack(fill="both", expand=True, padx=6, pady=(0, 6))
            w.configure(height=140)
            w.pack_propagate(False)
            tree.configure(columns=cols, show="headings", height=5)
            _stretch_columns(tree, cols, widths)
            _enable_tree_column_sort(tree, cols, labels=labels)
            _bind_tree_scroll_isolation(tree, w)
            return tree

        self.mcstat_eth_tree = _col_table(
            tables, 0, "By surname ethnicity",
            ["ethnicity", "count", "pct"],
            {"ethnicity": "ETHNICITY", "count": "COUNT", "pct": "%"},
            [160, 60, 50],
        )
        self.mcstat_race_tree = _col_table(
            tables, 1, "By recorded race",
            ["race", "count", "pct"],
            {"race": "RECORDED AS", "count": "COUNT", "pct": "%"},
            [160, 60, 50],
        )
        self.mcstat_conf_tree = _col_table(
            tables, 2, "Confidence bands",
            ["band", "count", "pct"],
            {"band": "BAND", "count": "COUNT", "pct": "%"},
            [160, 60, 50],
        )

        self.mcstat_status = ctk.CTkLabel(
            scroll,
            text="Statistics update when you run Analyze (from this tab or Misclassify).",
            font=FONT_SM, text_color=C["muted"],
        )
        self.mcstat_status.pack(anchor="w", padx=8, pady=(0, 8))


