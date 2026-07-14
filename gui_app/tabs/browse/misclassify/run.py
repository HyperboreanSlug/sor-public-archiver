"""MisclassifyRunMixin."""
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


class MisclassifyRunMixin:
    def _misclass_on_select(self, _event=None):
        """Show photo + detail for the selected mismatch row."""
        sel = self.misclass_tree.selection()
        if not sel:
            return
        rec = self._misclass_records_by_iid.get(sel[0])
        if not rec:
            return
        # Prefer full DB row so photo_path / HTML paths are current
        if rec.get("id"):
            try:
                from scraper.database import Database

                db = Database(self.db_path)
                try:
                    full = db.get_offender_by_id(int(rec["id"]))
                    if full:
                        # Keep analysis labels on the record for display context
                        full = dict(full)
                        for k in ("_misclass_expected_race", "_misclass_likely", "_misclass_conf"):
                            if k in rec:
                                full[k] = rec[k]
                        rec = full
                        self._misclass_records_by_iid[sel[0]] = rec
                finally:
                    db.close()
            except Exception:
                pass
        if getattr(self, "misclass_detail", None) is not None:
            self._fill_detail_drawer(self.misclass_detail, rec)


    def _run_misclassification(self):
        from scraper.searcher import SexOffenderSearcher

        self._ensure_misclass_filter_vars()
        searcher = SexOffenderSearcher(db_path=self.db_path)
        eth = (self.misclass_ethnicity_var.get() or "all").strip()
        try:
            min_conf = float(self.misclass_conf_var.get())
            limit = int(self.misclass_limit_var.get())
            db_total = searcher.get_total_count()
            eth_filter = None if eth == "all" else eth
            # Always get base_count so Statistics can show % of selected ethnicity
            results, eth_base = searcher.analyze_ethnicities(
                min_confidence=min_conf,
                limit=limit,
                ethnicity_filter=eth_filter,
                return_base_count=True,
            )
        finally:
            searcher.close()

        self._misclass_results = results
        self._misclass_meta = {
            "db_total": db_total,
            "scanned_cap": limit,
            "min_conf": min_conf,
            "eth_filter": eth,
            "eth_base_count": eth_base,
        }

        # Exclude manually Correct-labeled rows from table + Statistics
        stats_results = self._results_excluding_correct(results)
        n_correct = len(results) - len(stats_results)

        if getattr(self, "misclass_detail", None) is not None:
            try:
                self._fill_detail_drawer(self.misclass_detail, None)
            except Exception:
                pass
        self._populate_misclass_tree(stats_results)
        shown = min(500, len(stats_results))
        if hasattr(self, "misclass_status"):
            if eth != "all" and eth_base is not None:
                rate = (len(stats_results) / eth_base * 100.0) if eth_base else 0.0
                self.misclass_status.configure(
                    text=(
                        f"{eth}: {eth_base:,} name matches · "
                        f"{len(stats_results):,} misclassified ({rate:.1f}%)"
                        + (f" · {n_correct} marked correct (excluded)" if n_correct else "")
                        + (f" · showing first {shown}" if len(stats_results) > shown else "")
                        + " · select a row for photo · Ctrl+C copies row"
                    )
                )
            else:
                self.misclass_status.configure(
                    text=f"{len(stats_results)} potential mismatches"
                    + (f" · {n_correct} correct excluded" if n_correct else "")
                    + (f" · showing first {shown}" if len(stats_results) > shown else "")
                    + " · select a row for photo · Statistics for transitions"
                )

        self._update_misclass_stats(
            stats_results,
            db_total=db_total,
            scanned_cap=limit,
            min_conf=min_conf,
            eth_filter=eth,
            eth_base_count=eth_base,
        )
        self.log_queue.put(
            f"Misclassification: {len(stats_results)} mismatches"
            + (f" ({n_correct} correct excluded)" if n_correct else "")
            + (f" / {eth_base} {eth}" if eth != "all" else "")
        )
        if hasattr(self, "report_status"):
            self.report_status.configure(
                text=(
                    f"Analyze ready · {len(stats_results):,} mismatches"
                    + (f" · {n_correct} correct excluded" if n_correct else "")
                    + " · Reports → Analyze & build for photo review"
                )
            )


    def _export_misclass(self):
        from scraper.searcher import SexOffenderSearcher

        self._ensure_misclass_filter_vars()
        path = filedialog.asksaveasfilename(defaultextension=".csv")
        if not path:
            return
        searcher = SexOffenderSearcher(db_path=self.db_path)
        eth = (self.misclass_ethnicity_var.get() or "all").strip()
        try:
            n = searcher.export_misclassifications(
                path,
                min_confidence=float(self.misclass_conf_var.get()),
                ethnicity_filter=None if eth == "all" else eth,
            )
        finally:
            searcher.close()
        messagebox.showinfo("Exported", f"{n} rows → {path}")


