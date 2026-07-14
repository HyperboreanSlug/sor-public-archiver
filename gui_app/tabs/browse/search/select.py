"""SearchSelectMixin."""
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


class SearchSelectMixin:
    def _search_on_select(self, _event=None):
        sel = self.search_tree.selection()
        if not sel:
            return
        rec = self._search_records_by_iid.get(sel[0])
        if rec and rec.get("id") and not rec.get("photo_path"):
            # Refresh full row from DB for photo/html
            try:
                from scraper.database import Database

                db = Database(self.db_path)
                try:
                    full = db.get_offender_by_id(int(rec["id"]))
                    if full:
                        rec = full
                        self._search_records_by_iid[sel[0]] = full
                finally:
                    db.close()
            except Exception:
                pass
        self._fill_detail_drawer(self.search_detail, rec)


    def _show_race_distribution(self, dist):
        self.search_tree.delete(*self.search_tree.get_children())
        self._search_records_by_iid = {}
        self._fill_detail_drawer(self.search_detail, None)
        total = sum(d.get("count", 0) for d in dist) or 1
        for d in dist:
            race = d.get("race") or "—"
            count = d.get("count", 0)
            pct = count / total * 100
            bar = "▮" * max(1, int(pct / 4))
            self.search_tree.insert(
                "", "end", values=(race, str(count), f"{pct:.1f}%", bar, "", "", "")
            )


