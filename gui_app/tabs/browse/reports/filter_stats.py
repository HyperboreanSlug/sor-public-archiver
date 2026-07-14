"""FStats"""
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


class ReportsFilterStatsMixin:
    def _results_excluding_correct(self, results: Optional[list] = None) -> list:
        """Misclass results with Correct-label verdicts removed (for Statistics)."""
        src = list(results if results is not None else (self._misclass_results or []))
        out = []
        for mc in src:
            if self._verdict_for_mc(mc) == "correct":
                continue
            out.append(mc)
        return out


    def _refresh_stats_from_verdicts(self) -> None:
        """Recompute Statistics after Correct labels change."""
        meta = getattr(self, "_misclass_meta", None) or {}
        if not meta and not self._misclass_results:
            return
        filtered = self._results_excluding_correct()
        # Correct rows no longer count as mismatches; eth_base unchanged
        try:
            self._update_misclass_stats(
                filtered,
                db_total=int(meta.get("db_total") or 0),
                scanned_cap=int(meta.get("scanned_cap") or 0),
                min_conf=float(meta.get("min_conf") or 0.5),
                eth_filter=str(meta.get("eth_filter") or "all"),
                eth_base_count=meta.get("eth_base_count"),
            )
        except Exception:
            pass
        # Rebuild misclass tree without correct rows
        if hasattr(self, "misclass_tree"):
            try:
                self._populate_misclass_tree(filtered)
            except Exception:
                pass


    def _populate_misclass_tree(self, results: list) -> None:
        if not hasattr(self, "misclass_tree"):
            return
        self.misclass_tree.delete(*self.misclass_tree.get_children())
        self._misclass_records_by_iid = {}
        for mc in results[:500]:
            rec = dict(mc.record or {})
            name = (
                " ".join(
                    p for p in (
                        rec.get("first_name") or "",
                        rec.get("middle_name") or "",
                        rec.get("last_name") or "",
                    ) if str(p).strip()
                )
                or (rec.get("full_name") or "—")
            )
            rec["_misclass_expected_race"] = mc.expected_race
            rec["_misclass_likely"] = mc.likely_ethnicity
            rec["_misclass_conf"] = mc.confidence
            iid = self.misclass_tree.insert(
                "",
                "end",
                values=(
                    name,
                    (mc.expected_race or "—")[:14],
                    (mc.likely_ethnicity or "")[:18],
                    f"{mc.confidence:.3f}",
                    "; ".join(mc.matching_names[:3]),
                ),
            )
            self._misclass_records_by_iid[iid] = rec


