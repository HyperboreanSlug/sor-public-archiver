"""IntegrityRefreshMixin."""
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


class IntegrityRefreshMixin:
    def _refresh_integrity(self):
        from scraper.database import Database

        try:
            db = Database(self.db_path)
            try:
                # One-shot fix for NSOPW junk location.state codes (e.g. YY → FL)
                try:
                    fixed_yy = db.repair_bogus_states()
                    if fixed_yy:
                        self.log_queue.put(
                            f"Repaired {fixed_yy:,} rows with bogus state codes (YY/XX/…)"
                        )
                except Exception:
                    pass
                # Pull middle names from full_name / multi-token first / raw JSON
                try:
                    mid = db.backfill_middle_names()
                    if mid.get("updated"):
                        self.log_queue.put(
                            f"Backfilled middle_name on {mid['updated']:,} rows "
                            f"(scanned {mid['scanned']:,})"
                        )
                except Exception:
                    pass
                report = db.get_integrity_report()
                incomplete = db.find_incomplete_reports(
                    need_race=True, need_crime=True, need_photo=True, need_html=False,
                    limit=5000,
                )
                try:
                    from scraper.database import DEFAULT_DEDUPE_STRATEGIES

                    dup_summary = db.count_duplicates(list(DEFAULT_DEDUPE_STRATEGIES))
                except Exception:
                    dup_summary = None
            finally:
                db.close()
        except Exception as e:
            self.integrity_summary.configure(text=f"Error: {e}")
            return

        o = report["overall"]
        complete = int(o.get("with_everything") or 0)
        total = int(o.get("total") or 0)
        dup_line = ""
        if dup_summary and isinstance(dup_summary.get("by_strategy"), dict):
            parts = []
            for s, info in dup_summary["by_strategy"].items():
                safe_e = int(info.get("safe_extra_rows") or 0)
                unsafe_g = int(info.get("unsafe_groups") or 0)
                if safe_e or unsafe_g or info.get("extra_rows"):
                    bit = f"{s}: {safe_e:,} safe"
                    if unsafe_g:
                        bit += f" (+{unsafe_g} portal/CAPTCHA clusters skipped)"
                    parts.append(bit)
            if parts:
                dup_line = "\nDuplicates: " + " · ".join(parts)
            else:
                dup_line = "\nDuplicates: none found (URL / external id / name+DOB / multi-state)"
        self.integrity_summary.configure(
            text=(
                f"Total records: {total:,}  ·  "
                f"Complete (race+crime+photo+HTML): {complete:,} "
                f"({o.get('pct_everything', 0)}%)\n"
                f"Race: {o['with_race']:,} ({o.get('pct_race', 0)}%)  ·  "
                f"Crime: {o['with_crime']:,} ({o.get('pct_crime', 0)}%)  ·  "
                f"Photo: {o['with_photo']:,} ({o.get('pct_photo', 0)}%)  ·  "
                f"HTML: {o['with_html']:,} ({o.get('pct_html', 0)}%)"
                f"{dup_line}"
            )
        )
        self.requeue_incomplete_label.configure(
            text=f"Incomplete with URL (race/crime/photo): {len(incomplete):,}"
        )
        self.integrity_tree.delete(*self.integrity_tree.get_children())
        for st in report["by_state"]:
            self.integrity_tree.insert(
                "",
                "end",
                values=(
                    st["state"],
                    st["total"],
                    f"{st['pct_race']:.0f}%",
                    f"{st['pct_crime']:.0f}%",
                    f"{st['pct_photo']:.0f}%",
                    f"{st['pct_html']:.0f}%",
                    st["with_race"],
                    st["with_crime"],
                    st["with_photo"],
                    st["with_html"],
                ),
            )
        n_states = max(8, len(report["by_state"]))
        self.integrity_tree.configure(height=min(24, max(12, n_states + 2)))

        self.integrity_status.configure(
            text=f"Updated · {len(report['by_state'])} states/territories in DB"
        )
        self._last_integrity_report = report


    def _export_integrity_csv(self):
        report = getattr(self, "_last_integrity_report", None)
        if not report:
            self._refresh_integrity()
            report = getattr(self, "_last_integrity_report", None)
        if not report:
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(
                    f,
                    fieldnames=[
                        "state", "total", "with_race", "pct_race", "with_crime", "pct_crime",
                        "with_photo", "pct_photo", "with_html", "pct_html", "with_url",
                    ],
                )
                w.writeheader()
                for row in report["by_state"]:
                    w.writerow(row)
            messagebox.showinfo("Exported", path)
        except Exception as e:
            messagebox.showerror("Export failed", str(e))


    def _open_data_folder_header(self):
        path = Path("data")
        path.mkdir(parents=True, exist_ok=True)
        # Prefer folder containing the DB
        try:
            dbp = Path(self.db_path)
            if dbp.parent.is_dir():
                path = dbp.parent
        except Exception:
            pass
        self._open_path(path)


