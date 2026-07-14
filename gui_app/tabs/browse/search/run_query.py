"""SearchQueryMixin."""
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


class SearchQueryMixin:
    def _do_search(
        self, name=None, state=None, race=None, ethnicity=None, *_args, **_kwargs
    ):
        from scraper.searcher import SexOffenderSearcher

        # Always re-read widgets unless explicit override (avoids stale second-run
        # blanks from leftover kwargs / partial clear).
        try:
            name_ui = (self.search_name_var.get() or "").strip()
            state_ui = (self.search_state_var.get() or "").strip().upper()
            race_ui = (self.search_race_var.get() or "").strip()
            eth_ui = (
                (self.search_ethnicity_var.get() or "").strip()
                if hasattr(self, "search_ethnicity_var")
                else ""
            )
        except Exception:
            name_ui, state_ui, race_ui, eth_ui = "", "", "", ""

        name = name_ui if name is None else (name or "").strip()
        state = state_ui if state is None else (state or "").strip().upper()
        race = race_ui if race is None else (race or "").strip()
        eth = eth_ui if ethnicity is None else (ethnicity or "").strip()
        # Treat blank / ALL as no filter
        state_f = state if state and state != "ALL" else None
        race_f = race or None
        eth_f = eth or None

        searcher = SexOffenderSearcher(db_path=self.db_path)
        try:
            try:
                if name:
                    results = searcher.search_by_name(
                        name=name,
                        state=state_f,
                        race=race_f if race_f and race_f.upper() != "INDIAN" else None,
                        limit=500,
                    )
                    records = list(results.records)
                    # Optional post-filters for Indian race + surname ethnicity
                    if race_f and race_f.upper() == "INDIAN":
                        records = [
                            r for r in records
                            if "indian" in (r.get("race") or "").lower()
                            or "indian" in (r.get("ethnicity") or "").lower()
                            or "indian" in (r.get("likely_ethnicity") or "").lower()
                            or "south asian" in (r.get("race") or "").lower()
                        ]
                    if eth_f:
                        eth_res = searcher.search_by_surname_ethnicity(
                            eth_f, state=state_f, limit=5000
                        )
                        allowed = {
                            (
                                (r.get("last_name") or "").strip().lower(),
                                (r.get("full_name") or "").strip().lower(),
                            )
                            for r in eth_res.records
                        }
                        records = [
                            r for r in records
                            if (
                                (r.get("last_name") or "").strip().lower(),
                                (r.get("full_name") or "").strip().lower(),
                            ) in allowed
                            or (r.get("last_name") or "").strip().lower()
                            in {a[0] for a in allowed if a[0]}
                        ]
                    self._populate_search_tree(records)
                    filt = []
                    if state_f:
                        filt.append(state_f)
                    if race_f:
                        filt.append(race_f)
                    if eth_f:
                        filt.append(eth_f)
                    extra = f" · {', '.join(filt)}" if filt else ""
                    self.search_status.configure(
                        text=(
                            f"{len(records)} name matches{extra} · "
                            f"{results.query_time_ms:.0f} ms"
                        )
                    )
                elif eth_f:
                    results = searcher.search_by_surname_ethnicity(
                        eth_f, state=state_f, limit=500
                    )
                    records = list(results.records)
                    if race_f:
                        if race_f.upper() == "INDIAN":
                            records = [
                                r for r in records
                                if "indian" in (r.get("race") or "").lower()
                                or "indian" in (r.get("ethnicity") or "").lower()
                                or "indian" in (r.get("likely_ethnicity") or "").lower()
                                or "south asian" in (r.get("race") or "").lower()
                                or not (r.get("race") or "").strip()
                            ]
                        else:
                            records = [
                                r for r in records
                                if (r.get("race") or "").strip().upper() == race_f.upper()
                            ]
                    self._populate_search_tree(records)
                    where = f" · {state_f}" if state_f else ""
                    self.search_status.configure(
                        text=(
                            f"{len(records)} with surname ethnicity {eth_f}{where}"
                            + (f" · race {race_f}" if race_f else "")
                            + f" · {results.query_time_ms:.0f} ms"
                        )
                    )
                elif race_f:
                    results = searcher.search_by_race(
                        race=race_f,
                        state=state_f,
                        limit=500,
                    )
                    self._populate_search_tree(results.records)
                    where = f" · {state_f}" if state_f else ""
                    self.search_status.configure(
                        text=f"{len(results.records)} with race {race_f}{where}"
                    )
                elif state_f:
                    results = searcher.search_by_state(state=state_f, limit=500)
                    self._populate_search_tree(results.records)
                    self.search_status.configure(
                        text=f"{len(results.records)} in {state_f}"
                    )
                else:
                    # Default / Show all: list of offenders by name, not race stats
                    results = searcher.search_by_state(state="ALL", limit=500)
                    self._populate_search_tree(results.records)
                    total = searcher.get_total_count()
                    shown = len(results.records)
                    self.search_status.configure(
                        text=(
                            f"{shown} names"
                            + (
                                f" (of {total:,} total)"
                                if total > shown
                                else f" · {total:,} total"
                            )
                            + " · select a row for detail"
                        )
                    )
            except Exception as e:
                try:
                    self._populate_search_tree([])
                except Exception:
                    pass
                try:
                    self.search_status.configure(text=f"Search error: {e}")
                except Exception:
                    pass
                try:
                    self.log_queue.put(f"Search error: {e}")
                except Exception:
                    pass
        finally:
            searcher.close()


