"""IntegrityEnrichStartMixin."""
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


class IntegrityEnrichStartMixin:
    def _start_enrich_misclassified(self):
        """NSOPW search + report fetch for current misclassification candidates."""
        if self.is_running:
            messagebox.showwarning("Busy", "Wait for the current job to finish.")
            return

        from scraper.nsopw_builder import NSOPWEthnicDatabaseBuilder
        from scraper.database.enrich_scope import filter_records_for_enrich

        # Prefer last Analyze results (what Misclassify shows). Never use the
        # Reports *page slice* alone — that ignored fresh Analyze and capped
        # enrich to one page of stale cards.
        results = list(self._misclass_results or [])
        pool = list(getattr(self, "_report_pool", None) or [])
        if results:
            mcs = (
                self._results_excluding_correct(results)
                if hasattr(self, "_results_excluding_correct")
                else results
            )
            records = []
            for mc in mcs:
                rec = dict(mc.record or {})
                if rec.get("id") is not None:
                    records.append(rec)
            source_label = "last Analyze results (excl. Correct)"
        elif pool:
            records = []
            for mc in pool:
                if hasattr(self, "_verdict_for_mc") and self._verdict_for_mc(mc) == "correct":
                    continue
                rec = dict(mc.record or {})
                if rec.get("id") is not None:
                    records.append(rec)
            source_label = "Reports pool (excl. Correct)"
        else:
            items = list(self._report_items or [])
            records = []
            for mc in items:
                if hasattr(self, "_verdict_for_mc") and self._verdict_for_mc(mc) == "correct":
                    continue
                rec = dict(mc.record or {})
                if rec.get("id") is not None:
                    records.append(rec)
            source_label = "Reports page (excl. Correct)"

        if not records:
            messagebox.showinfo(
                "NSOPW enrich",
                "No misclassified people to enrich.\n\n"
                "Run Analyze (or Reports → Analyze & build) first.",
            )
            return

        # Only rows still missing photo / race / crime / URL
        incomplete = [
            r for r in records
            if NSOPWEthnicDatabaseBuilder.record_needs_enrichment(r)
        ]
        n_complete = len(records) - len(incomplete)
        if not incomplete:
            messagebox.showinfo(
                "NSOPW enrich",
                f"All {len(records):,} candidates already have photo + race + crime + URL.\n"
                "Nothing to look up.",
            )
            return

        try:
            enrich_lim = int(self.enrich_limit_var.get()) if hasattr(self, "enrich_limit_var") else 25
        except (TypeError, ValueError):
            enrich_lim = 25
        if enrich_lim <= 0:
            # 0 = no cap (still hard-cap to avoid runaway API use)
            enrich_lim = min(len(incomplete), 500)
        else:
            enrich_lim = max(1, min(enrich_lim, 500))

        self._ensure_misclass_filter_vars()
        enrich_external = bool(self.enrich_external_only_var.get())
        source_scope = "external_imports" if enrich_external else "all"
        ethnicity_filter = (self.misclass_ethnicity_var.get() or "all").strip().lower()
        try:
            min_conf = float(self.misclass_conf_var.get())
        except (TypeError, ValueError):
            min_conf = 0.5

        # Apply scope filters BEFORE confirm so the dialog shows the real queue
        ethnic_db = None
        try:
            if hasattr(self, "searcher") and getattr(self.searcher, "ethnic_db", None):
                ethnic_db = self.searcher.ethnic_db
        except Exception:
            ethnic_db = None
        if ethnic_db is None and ethnicity_filter and ethnicity_filter != "all":
            try:
                from scraper.ethnic_names import get_ethnic_database

                ethnic_db = get_ethnic_database()
            except Exception as e:
                messagebox.showerror(
                    "NSOPW enrich",
                    f"Ethnicity filter “{ethnicity_filter}” requires the name "
                    f"classifier, which failed to load:\n{e}\n\n"
                    "Set ethnicity to “all” or fix ethnic_names data, then retry.",
                )
                return
            if ethnic_db is None:
                messagebox.showerror(
                    "NSOPW enrich",
                    "Ethnicity filter is set but the name classifier is unavailable.",
                )
                return

        scoped, skipped_scope = filter_records_for_enrich(
            incomplete,
            source_scope=source_scope,
            ethnicity_filter=ethnicity_filter,
            min_confidence=min_conf,
            ethnic_db=ethnic_db,
        )
        if not scoped:
            messagebox.showinfo(
                "NSOPW enrich",
                (
                    f"Source: {source_label}\n"
                    f"Incomplete candidates: {len(incomplete):,}\n"
                    f"Skipped by scope filter: {skipped_scope:,}\n\n"
                    f"Scope={source_scope}, ethnicity={ethnicity_filter}.\n"
                    "Nothing left to look up — uncheck “External imports only” "
                    "or set ethnicity to “all”, then try again."
                ),
            )
            return

        will_run = min(len(scoped), enrich_lim)
        ok = messagebox.askyesno(
            "NSOPW enrich misclassified?",
            (
                f"Source: {source_label}\n"
                f"Candidates: {len(records):,} · incomplete: {len(incomplete):,}\n"
                f"Already complete (skipped): {n_complete:,}\n"
                f"Skipped by scope filter: {skipped_scope:,}\n"
                f"Queue after filters: {len(scoped):,} · will process: {will_run:,}\n"
                f"Lookup limit: {enrich_lim}\n"
                f"Source scope: {source_scope}\n"
                f"Ethnicity filter: {ethnicity_filter} (min conf {min_conf:.2f})\n\n"
                "Only people missing photo, race, crime, or source URL are processed.\n"
                "Prefer missing photos first.\n\n"
                "For each incomplete person:\n"
                "  • If they have a report URL → re-fetch photo/race/crime\n"
                "  • On fetch failure / no URL → NSOPW first+last search\n\n"
                "Existing DB rows are updated (no new duplicates).\n"
                "Progress shows on this status line and Integrity.\n\n"
                "Continue?"
            ),
        )
        if not ok:
            return

        self._enrich_cancel = False
        self._requeue_cancel = False
        self._set_running(True)
        if hasattr(self, "requeue_btn"):
            self.requeue_btn.configure(state="disabled")
        if hasattr(self, "requeue_cancel_btn"):
            self.requeue_cancel_btn.configure(state="normal")
        status_msg = f"NSOPW enrich running… 0/{will_run}"
        for attr in ("requeue_status", "misclass_status", "report_status"):
            lbl = getattr(self, attr, None)
            if lbl is not None:
                try:
                    lbl.configure(text=status_msg)
                except Exception:
                    pass
        if hasattr(self, "requeue_progress"):
            self.requeue_progress.set(0)

        def log(msg):
            self.log_queue.put(msg)

        def on_progress(done: int, total: int):
            frac = (done / total) if total else 0.0

            def _ui(d=done, t=total, f=frac):
                text = f"NSOPW enrich {d}/{t}…"
                if hasattr(self, "requeue_progress"):
                    self.requeue_progress.set(min(1.0, max(0.0, f)))
                for attr in ("requeue_status", "misclass_status", "report_status"):
                    lbl = getattr(self, attr, None)
                    if lbl is not None:
                        try:
                            lbl.configure(text=text)
                        except Exception:
                            pass

            self.after(0, _ui)

        def worker():
            from scraper.nsopw_builder import NSOPWEthnicDatabaseBuilder

            builder = NSOPWEthnicDatabaseBuilder(
                db_path=self.db_path,
                delay=2.0,
                report_delay=0.75,
                html_dir="data/report_pages",
                cancel_check=lambda: getattr(self, "_enrich_cancel", False)
                or getattr(self, "_requeue_cancel", False),
            )
            try:
                # Scope already applied; pass all + filters that no-op
                summary = builder.enrich_misclassified(
                    scoped,
                    limit=enrich_lim,
                    prefer_missing_photo=True,
                    only_missing_data=True,
                    enrich_reports=True,
                    source_scope="all",
                    ethnicity_filter="all",
                    min_confidence=min_conf,
                    save_html=True,
                    log=log,
                    on_progress=on_progress,
                )

                def done():
                    self._set_running(False)
                    if hasattr(self, "requeue_btn"):
                        self.requeue_btn.configure(state="normal")
                    if hasattr(self, "requeue_cancel_btn"):
                        self.requeue_cancel_btn.configure(state="disabled")
                    msg = (
                        f"NSOPW enrich: updated {summary.get('updated', 0)}/"
                        f"{summary.get('attempted', 0)} "
                        f"· matched {summary.get('nsopw_matched', 0)} "
                        f"· photos {summary.get('with_photo', 0)} "
                        f"· skipped complete {summary.get('skipped_complete', 0)} "
                        f"· skipped scope {summary.get('skipped_scope', 0)} "
                        f"· errors {summary.get('errors', 0)}"
                    )
                    for attr in ("requeue_status", "misclass_status", "report_status"):
                        lbl = getattr(self, attr, None)
                        if lbl is not None:
                            try:
                                lbl.configure(
                                    text=msg
                                    + (
                                        " · re-run Analyze"
                                        if attr != "requeue_status"
                                        else ""
                                    )
                                )
                            except Exception:
                                pass
                    if hasattr(self, "requeue_progress"):
                        self.requeue_progress.set(1.0)
                    self.log_queue.put(msg)
                    try:
                        self._after_db_data_changed()
                    except Exception:
                        pass
                    # Refresh Analyze rows from DB so table reflects new photos/URLs
                    try:
                        self._enrich_refresh_misclass_rows(scoped)
                    except Exception:
                        pass
                    messagebox.showinfo("NSOPW enrich", msg)

                self.after(0, done)
            except Exception as e:
                err = str(e)

                def fail():
                    self._set_running(False)
                    if hasattr(self, "requeue_btn"):
                        self.requeue_btn.configure(state="normal")
                    if hasattr(self, "requeue_cancel_btn"):
                        self.requeue_cancel_btn.configure(state="disabled")
                    if hasattr(self, "misclass_status"):
                        try:
                            self.misclass_status.configure(text=f"NSOPW enrich failed: {err}")
                        except Exception:
                            pass
                    messagebox.showerror("NSOPW enrich failed", err)

                self.after(0, fail)
            finally:
                try:
                    builder.close()
                except Exception:
                    pass

        threading.Thread(target=worker, daemon=True).start()


