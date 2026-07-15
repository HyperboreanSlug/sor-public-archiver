"""DfrEthnicityMixin."""
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


class DfrEthnicityMixin:
    def _dfr_current_ethnicity(self, mc) -> str:
        """Best ethnicity label for the combo (saved, then face, then Unknown)."""
        rec = getattr(mc, "record", None) or {}
        eth = (getattr(mc, "likely_ethnicity", None) or "").strip()
        if not eth or eth in ("—", "-"):
            eth = (rec.get("likely_ethnicity") or "").strip()
        if eth and eth not in ("—", "-", "unknown"):
            return eth
        df = rec.get("_deepface") or {}
        face = (df.get("predicted_label") or df.get("top_label") or "").strip()
        if face:
            face_l = face.lower().replace("_", " ")
            # Map face labels to display options
            if "black" in face_l or "african" in face_l:
                return "African American"
            if "indian" in face_l or "middle" in face_l or "arab" in face_l:
                return "Indian/MENA"
            if "asian" in face_l:
                return "Asian"
            if "hispanic" in face_l or "latino" in face_l:
                return "Hispanic"
            if "white" in face_l:
                return "European"
            return face.replace("_", " ").title()
        return "Unknown"


    def _dfr_on_ethnicity_change(self, choice: str = "") -> None:
        """Persist ethnicity for the selected DeepFace hit."""
        if getattr(self, "_dfr_eth_updating", False):
            return
        iid = getattr(self, "_dfr_selected_iid", None)
        mc = (getattr(self, "_dfr_hits_by_iid", {}) or {}).get(iid) if iid else None
        if mc is None:
            return
        eth = (choice or "").strip()
        if not eth and hasattr(self, "dfr_eth_var"):
            eth = (self.dfr_eth_var.get() or "").strip()
        eth = eth or "Unknown"

        if hasattr(self, "_set_ethnicity_for_mc"):
            try:
                self._set_ethnicity_for_mc(mc, eth)
            except Exception:
                self._dfr_set_ethnicity_fallback(mc, eth)
        else:
            self._dfr_set_ethnicity_fallback(mc, eth)

        # Refresh meta so "Ethnicity:" line updates without losing selection
        try:
            self._dfr_show(iid, mc, preserve_eth=True)
        except Exception:
            pass


    def _dfr_set_ethnicity_fallback(self, mc, ethnicity: str) -> None:
        """Write likely_ethnicity when Reports mixin method is unavailable."""
        eth = (ethnicity or "").strip() or "Unknown"
        mc.likely_ethnicity = eth
        rec = mc.record if isinstance(mc.record, dict) else {}
        rec = dict(rec)
        rec["likely_ethnicity"] = eth
        mc.record = rec
        rid = rec.get("id")
        if rid is None:
            return
        try:
            from scraper.database import Database

            db = Database(str(getattr(self, "db_path", None) or "data/offenders.db"))
            try:
                db.update_offender(int(rid), {"likely_ethnicity": eth})
            finally:
                db.close()
        except Exception:
            pass


