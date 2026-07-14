"""ScrapeRunMixin."""
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


class ScrapeRunMixin:
    def _start_scrape(self):
        if self.is_running:
            return
        from scraper.config import REGISTRIES, get_registry_by_abbr
        from scraper.scrapers.base import ScraperFactory

        states = list(self.selected_states)
        delay = float(self.scrape_delay_var.get())
        direct_only = bool(self.scrape_direct_only.get())

        if states:
            registries = [get_registry_by_abbr(s) for s in states]
            registries = [r for r in registries if r]
            if direct_only:
                registries = [r for r in registries if r.direct_downloads]
        elif direct_only:
            registries = [r for r in REGISTRIES if r.abbr != "US" and r.direct_downloads]
        else:
            messagebox.showwarning(
                "No selection",
                "Select jurisdictions or enable Direct / bulk only.",
            )
            return
        if not registries:
            messagebox.showwarning("No targets", "No matching registries.")
            return

        output_dir = Path(self.scrape_output_var.get())
        output_dir.mkdir(parents=True, exist_ok=True)
        auto_import = bool(self.scrape_auto_import.get()) if hasattr(self, "scrape_auto_import") else True
        skip_urls = bool(self.scrape_import_skip.get()) if hasattr(self, "scrape_import_skip") else True
        db_path = self.db_path
        self._set_running(True)
        self.scrape_progress.set(0)
        total = len(registries)

        def log(msg):
            self.log_queue.put(msg)

        def worker():
            from scraper.database import Database

            try:
                total_records = 0
                total_imported = 0
                total_skipped = 0
                for i, reg in enumerate(registries):
                    log(f"[{reg.abbr}] Scraping {reg.name}…")
                    scraper = ScraperFactory.create(reg.abbr, delay=delay)
                    try:
                        records = scraper.scrape()
                    finally:
                        scraper.close()
                    if records:
                        csv_path = output_dir / f"{reg.abbr.lower()}_offenders.csv"
                        fields: List[str] = []
                        seen = set()
                        for rec in records:
                            for k in rec:
                                if k not in seen:
                                    seen.add(k)
                                    fields.append(k)
                        with open(csv_path, "w", newline="", encoding="utf-8") as f:
                            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
                            w.writeheader()
                            w.writerows(records)
                        log(f"  Saved {len(records)} → {csv_path}")
                        total_records += len(records)
                        if auto_import:
                            try:
                                db = Database(db_path)
                                try:
                                    imp = db.import_records(
                                        records,
                                        state=reg.abbr,
                                        skip_existing_urls=skip_urls,
                                    )
                                finally:
                                    db.close()
                                total_imported += int(imp.get("imported") or 0)
                                total_skipped += int(imp.get("skipped") or 0)
                                log(
                                    f"  DB import: +{imp.get('imported', 0)} "
                                    f"(skipped {imp.get('skipped', 0)})"
                                )
                            except Exception as ie:
                                log(f"  DB import error: {ie}")
                    else:
                        log("  No records")
                    pct = (i + 1) / max(total, 1)
                    self.after(0, lambda p=pct: self.scrape_progress.set(p))
                log(
                    f"Done. Scraped {total_records}"
                    + (
                        f" · DB imported {total_imported} (skipped {total_skipped})"
                        if auto_import
                        else " · (DB auto-import off — use Import for Misclassify)"
                    )
                )
                if auto_import and total_imported:
                    self.after(0, self._after_db_data_changed)
            except Exception as e:
                log(f"ERROR: {e}")
            finally:
                self.after(0, lambda: self._set_running(False))

        threading.Thread(target=worker, daemon=True).start()


