"""IntegrityEnrichRefreshMixin."""
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


class IntegrityEnrichRefreshMixin:
    def _enrich_refresh_misclass_rows(self, enriched_recs: list) -> None:
        """Pull fresh DB rows for enriched IDs back into Analyze / tree."""
        ids = []
        for rec in enriched_recs or []:
            try:
                ids.append(int(rec.get("id")))
            except (TypeError, ValueError):
                continue
        if not ids or not getattr(self, "_misclass_results", None):
            return
        try:
            from scraper.database import Database

            db = Database(self.db_path)
            try:
                by_id = {}
                for oid in ids:
                    full = db.get_offender_by_id(oid)
                    if full:
                        by_id[oid] = full
            finally:
                db.close()
        except Exception:
            return
        if not by_id:
            return
        updated = 0
        for mc in self._misclass_results:
            rec = mc.record or {}
            try:
                oid = int(rec.get("id"))
            except (TypeError, ValueError):
                continue
            full = by_id.get(oid)
            if not full:
                continue
            # Prefer fresh DB row; drop stale analytic overlays that can
            # contradict updated photo/race after enrich.
            merged = dict(full)
            for k, v in rec.items():
                if not str(k).startswith("_"):
                    continue
                if k in ("_deepface", "_deepface_is_hit", "_source"):
                    continue
                merged[k] = v
            mc.record = merged
            # Keep Misclassification display fields in sync with DB race
            try:
                from scraper.searcher import format_race_label

                race_disp = format_race_label(full.get("race") or "") or (
                    full.get("race") or mc.expected_race
                )
                if race_disp:
                    mc.expected_race = str(race_disp)
            except Exception:
                if full.get("race"):
                    mc.expected_race = str(full.get("race"))
            eth = (full.get("likely_ethnicity") or "").strip()
            if eth:
                mc.likely_ethnicity = eth
            updated += 1
        if updated and hasattr(self, "_populate_misclass_tree"):
            try:
                shown = (
                    self._results_excluding_correct(self._misclass_results)
                    if hasattr(self, "_results_excluding_correct")
                    else self._misclass_results
                )
                self._populate_misclass_tree(shown)
            except Exception:
                pass


