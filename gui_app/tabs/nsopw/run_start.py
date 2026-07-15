"""NSOPW start harvest worker."""
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


class NsopwStartMixin:
    def _start_nsopw(self):
        if self.is_running:
            return

        db_path = self.nsopw_db_path
        html_dir = self.nsopw_html_dir
        # Snapshot plan + initial knobs (plan is fixed; knobs stay live via callback)
        self._nsopw_sync_runtime_options()
        live0 = self._nsopw_live_options()
        search_delay = float(live0.get("search_delay") or 3.0)
        report_delay = float(live0.get("report_delay") or 0.75)
        eth, sub, all_surnames, surnames_limit = self._nsopw_surname_selection_params()
        # Settings tab: compact 3-letter partials (default on)
        use_compact = bool(self.app_settings.get("nsopw_compact_prefixes", True))
        if hasattr(self, "settings_compact_prefixes"):
            use_compact = bool(self.settings_compact_prefixes.get())
        try:
            min_combined = int(self.app_settings.get("nsopw_min_combined_len", 3))
            if hasattr(self, "settings_min_combined"):
                min_combined = int(str(self.settings_min_combined.get()).strip() or "3")
        except (TypeError, ValueError):
            min_combined = 3
        min_combined = max(3, min(min_combined, 10))
        try:
            report_threads = max(1, min(int(self.nsopw_report_threads.get()), 16))
        except (TypeError, ValueError):
            report_threads = 1

        self._nsopw_cancel = False
        self._nsopw_insert_count = 0
        self._nsopw_other_count = 0
        self._set_running(True)
        self.nsopw_start_btn.configure(state="disabled")
        self.nsopw_cancel_btn.configure(state="normal")
        self._nsopw_reset_progress_ui()
        import time as _time

        self._nsopw_run_t0 = _time.monotonic()
        self._nsopw_eta_samples = []
        if hasattr(self, "nsopw_eta_label"):
            self.nsopw_eta_label.configure(text="ETA …")
        jurs_preview = (
            self._nsopw_selected_jurisdictions()
            if hasattr(self, "_nsopw_selected_jurisdictions")
            else None
        )
        jurs_txt = (
            ", ".join(jurs_preview)
            if jurs_preview
            else "all states"
        )
        self.nsopw_status.configure(
            text=f"Running NSOPW ({jurs_txt})… (edit delays/caps/checkboxes anytime)"
        )
        self.nsopw_tree.delete(*self.nsopw_tree.get_children())
        if getattr(self, "nsopw_tree_other", None) is not None:
            self.nsopw_tree_other.delete(*self.nsopw_tree_other.get_children())
        self._nsopw_photo_by_iid = {}
        self._nsopw_records_by_iid = {}
        if getattr(self, "nsopw_detail", None) is not None:
            self._fill_detail_drawer(self.nsopw_detail, None)

        def log(msg):
            self.log_queue.put(msg)

        def on_insert(record: Dict[str, Any]) -> None:
            # Marshal to UI thread
            self.after(0, lambda r=dict(record): self._nsopw_append_row(r))

        def on_progress(info: Dict[str, Any]) -> None:
            self.after(0, lambda d=dict(info): self._nsopw_update_progress(d))

        def worker():
            from scraper.nsopw_builder import NSOPWEthnicDatabaseBuilder

            builder = NSOPWEthnicDatabaseBuilder(
                db_path=db_path,
                delay=search_delay,
                report_delay=report_delay,
                html_dir=html_dir,
                cancel_check=lambda: self._nsopw_cancel,
                report_threads=report_threads,
            )
            try:
                stats = builder.build(
                    ethnicity=eth,
                    surnames_limit=surnames_limit,
                    all_surnames=all_surnames,
                    subcategory=sub,
                    first_names=None,
                    first_mode=(
                        (self.nsopw_first_mode_var.get() or "initials").strip().lower()
                        if hasattr(self, "nsopw_first_mode_var")
                        else "initials"
                    ),
                    jurisdictions=(
                        self._nsopw_selected_jurisdictions()
                        if hasattr(self, "_nsopw_selected_jurisdictions")
                        else None
                    ),
                    max_searches=live0.get("max_searches"),
                    max_names=live0.get("max_names"),
                    skip_existing_urls=bool(live0.get("skip_existing_urls", True)),
                    skip_completed_searches=bool(live0.get("skip_completed_searches", True)),
                    new_files_only=bool(live0.get("new_files_only", True)),
                    enrich_reports=bool(live0.get("enrich_reports", True)),
                    enrich_scope=str(live0.get("enrich_scope") or "all"),
                    save_html=bool(live0.get("save_html", True)),
                    use_compact_prefixes=use_compact,
                    min_combined_len=min_combined,
                    log=log,
                    on_insert=on_insert,
                    on_progress=on_progress,
                    live_options=self._nsopw_live_options,
                )

                def done():
                    self._set_running(False)
                    self.nsopw_start_btn.configure(state="normal")
                    self.nsopw_cancel_btn.configure(state="disabled")
                    # Final bar + chips from completed stats
                    self._nsopw_update_progress({
                        "plan_i": getattr(stats, "searches", 0) + getattr(stats, "searches_skipped", 0),
                        "plan_total": max(
                            getattr(stats, "searches", 0) + getattr(stats, "searches_skipped", 0),
                            1,
                        ),
                        "done": 1,
                        "total": 1,
                        "searches": stats.searches,
                        "searches_skipped": stats.searches_skipped,
                        "search_hits": stats.search_hits,
                        "inserted_matched": getattr(stats, "inserted_matched", stats.inserted),
                        "inserted_other": getattr(stats, "inserted_other", 0),
                        "html_saved": stats.html_saved,
                        "photos_saved": getattr(stats, "photos_saved", 0),
                        "reports_with_race": stats.reports_with_race,
                        "current": "complete",
                        "phase": "done",
                    })
                    self.nsopw_progress.set(1.0)
                    if hasattr(self, "nsopw_progress_label"):
                        self.nsopw_progress_label.configure(text="100%")
                    if hasattr(self, "nsopw_eta_label"):
                        self.nsopw_eta_label.configure(text="ETA done")
                    matched_n = getattr(stats, "inserted_matched", stats.inserted)
                    other_n = getattr(stats, "inserted_other", 0)
                    self.nsopw_status.configure(
                        text=(
                            f"Done · matched {matched_n} · other {other_n} · "
                            f"{stats.reports_with_race} with race · "
                            f"{stats.html_saved} HTML · "
                            f"{getattr(stats, 'photos_saved', 0)} photos · "
                            f"{stats.searches} new searches · "
                            f"{stats.searches_skipped} skipped (already done)"
                        )
                    )
                    self.db_path = db_path
                    # Top-bar record count + integrity after inserts
                    try:
                        if hasattr(self, "_after_db_data_changed"):
                            self._after_db_data_changed()
                        elif hasattr(self, "schedule_header_refresh"):
                            self.schedule_header_refresh(0)
                        else:
                            self._refresh_header_db_path()
                    except Exception:
                        pass
                    messagebox.showinfo(
                        "NSOPW complete",
                        (
                            f"Inserted {stats.inserted} "
                            f"(ethnicity match {matched_n}, other surnames {other_n})\n"
                            f"New searches: {stats.searches}\n"
                            f"Skipped completed searches: {stats.searches_skipped}\n"
                            f"Reports with race: {stats.reports_with_race}\n"
                            f"HTML saved: {stats.html_saved}\n"
                            f"Photos saved: {getattr(stats, 'photos_saved', 0)}\n"
                            f"HTML skipped (cached): {stats.reports_skipped_existing_file}\n"
                            f"{db_path}"
                        ),
                    )

                self.after(0, done)
            except Exception as e:
                log(f"NSOPW ERROR: {e}")

                def fail():
                    self._set_running(False)
                    self.nsopw_start_btn.configure(state="normal")
                    self.nsopw_cancel_btn.configure(state="disabled")
                    self.nsopw_status.configure(text=f"Error: {e}")
                    messagebox.showerror("NSOPW error", str(e))

                self.after(0, fail)
            finally:
                builder.close()

        threading.Thread(target=worker, daemon=True).start()


