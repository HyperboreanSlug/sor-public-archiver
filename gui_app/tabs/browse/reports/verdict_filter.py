"""VFilter"""
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


class ReportsVerdictFilterMixin:
    # Show dropdown labels (lowercased) → internal verdict filter keys
    _REPORT_SHOW_TO_VERDICT = {
        "unconfirmed": "unreviewed",
        "confirmed incorrect": "confirmed",
        "confirmed correct": "correct",
        "skip": "skip",
        "all": "all",
        # Internal keys pass through if already stored that way
        "unreviewed": "unreviewed",
        "confirmed": "confirmed",
        "correct": "correct",
    }

    def _reports_verdict_filter_key(self, show_value: Optional[str] = None) -> str:
        """Normalize Show dropdown → unreviewed|confirmed|correct|skip|all."""
        try:
            default = (
                self.report_verdict_filter.get()
                if hasattr(self, "report_verdict_filter")
                else "Unconfirmed"
            )
        except Exception:
            default = "Unconfirmed"
        raw = show_value if show_value is not None else default
        raw = str(raw or "Unconfirmed").strip().lower()
        # Tolerate partial / truncated combo text
        mapping = getattr(self, "_REPORT_SHOW_TO_VERDICT", {}) or {}
        if raw in mapping:
            return mapping[raw]
        if "unconfirm" in raw or raw == "pending":
            return "unreviewed"
        if "incorrect" in raw or raw == "misclass":
            return "confirmed"
        if "correct" in raw:
            return "correct"
        if "skip" in raw:
            return "skip"
        if raw == "all" or raw.startswith("all "):
            return "all"
        return "unreviewed"


    @staticmethod
    def _reports_verdict_passes_filter(verdict: str, vfilter: str) -> bool:
        """Strict Show filter: Unconfirmed never includes confirmed/correct/skip."""
        v = (verdict or "unreviewed").strip() or "unreviewed"
        f = (vfilter or "unreviewed").strip() or "unreviewed"
        if f == "all":
            return True
        if f == "unreviewed":
            # Only never-reviewed cards — not confirmed incorrect/correct/skip
            return v == "unreviewed"
        return v == f


