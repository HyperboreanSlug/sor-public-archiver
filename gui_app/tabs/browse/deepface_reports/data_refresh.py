"""DfrRefreshMixin."""
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


class DfrRefreshMixin:
    def _dfr_refresh(self) -> None:
        """Reload hits from DB using the same criteria as DeepFace → Scan."""
        try:
            min_c = 0.0
            try:
                min_c = float((self.dfr_min_conf.get() or "0").strip() or "0")
            except ValueError:
                min_c = 0.0
            state = ""
            try:
                state = (self.dfr_state.get() or "").strip() or None
            except Exception:
                state = None

            # Prefer live Scan-tab options when that UI exists; else app_settings
            recorded = None
            faces = None
            criteria_note = ""
            if hasattr(self, "_deepface_scan_collect_options"):
                try:
                    opts = self._deepface_scan_collect_options()
                    recorded = list(opts.get("recorded_races") or [])
                    faces = list(opts.get("face_labels") or [])
                    if not (self.dfr_min_conf.get() or "").strip():
                        min_c = float(opts.get("min_confidence") or min_c)
                    if not state and opts.get("state"):
                        state = opts.get("state")
                except Exception:
                    recorded = None
                    faces = None
            if recorded is None or faces is None:
                try:
                    from scraper.app_settings import load_settings

                    sett = load_settings()
                except Exception:
                    sett = getattr(self, "app_settings", None) or {}
                if recorded is None:
                    raw_r = str(sett.get("deepface_scan_recorded") or "WHITE")
                    recorded = [
                        p.strip().upper()
                        for p in raw_r.replace(";", ",").split(",")
                        if p.strip()
                    ] or ["WHITE"]
                if faces is None:
                    raw_f = str(
                        sett.get("deepface_scan_faces") or "black,indian,asian"
                    )
                    faces = [
                        p.strip().lower()
                        for p in raw_f.replace(";", ",").split(",")
                        if p.strip()
                    ] or ["black", "indian", "asian"]

            criteria_note = (
                f"recorded∈{','.join(recorded) or '—'} · "
                f"face∈{','.join(faces) or '—'}"
            )

            from scraper.mugshot_ethnicity.scanner import load_deepface_hits_as_misclass
            from scraper.database import Database

            db_path = str(getattr(self, "db_path", None) or "data/offenders.db")
            hits = load_deepface_hits_as_misclass(
                db_path=db_path,
                min_confidence=min_c,
                state=state,
                recorded_races=recorded,
                face_labels=faces,
                revalidate=True,
            )
            # Also show scan stats
            try:
                db = Database(db_path)
                try:
                    st = db.count_deepface_scans()
                finally:
                    db.close()
            except Exception:
                st = {"total": 0, "hits": len(hits)}

            self._dfr_all_hits = list(hits)
            self._dfr_apply_filters()
            if hasattr(self, "dfr_status"):
                self.dfr_status.configure(
                    text=(
                        f"Loaded {len(hits):,} DeepFace hits · "
                        f"DB scanned {st.get('total', 0):,} · {criteria_note}"
                    )
                )
        except Exception as e:
            if hasattr(self, "dfr_status"):
                self.dfr_status.configure(text=f"Load error: {e}")
            messagebox.showerror("DeepFace reports", str(e))


