"""NSOPW open paths/rows."""
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


class NsopwTreeOpenMixin:
    def _nsopw_open_data_folder(self):
        path = Path("data")
        path.mkdir(parents=True, exist_ok=True)
        self._open_path(path)


    def _open_path(self, path: Path):
        try:
            if os.name == "nt":
                os.startfile(str(path))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as e:
            messagebox.showerror("Cannot open", str(e))


    def _nsopw_open_selected(self, event=None):
        tree = event.widget if event is not None else self.nsopw_tree
        if not isinstance(tree, ttk.Treeview):
            tree = self.nsopw_tree
        sel = tree.selection()
        if not sel and getattr(self, "nsopw_tree_other", None) is not None:
            # Fallback: selection on the other tab
            for t in (self.nsopw_tree, self.nsopw_tree_other):
                if t.selection():
                    tree = t
                    sel = t.selection()
                    break
        if not sel:
            return
        iid = sel[0]
        vals = tree.item(iid, "values")
        # columns: name, state, race, crime, photo, url, html  (legacy layouts supported)
        if len(vals) >= 7:
            url, html_path = vals[5], vals[6]
        elif len(vals) >= 6:
            url, html_path = vals[4], vals[5]
        elif len(vals) >= 5:
            url, html_path = vals[3], vals[4]
        elif len(vals) >= 4:
            url, html_path = vals[2], vals[3]
        else:
            return

        photo_path = self._nsopw_photo_by_iid.get(iid)
        # Prefer opening HTML (includes embedded photos offline), then photo, then URL
        if html_path and html_path != "—":
            p = Path(html_path)
            if p.exists():
                self._open_path(p)
                return
        if photo_path and Path(photo_path).is_file():
            self._open_path(Path(photo_path))
            return
        if url:
            try:
                from scraper.public_links import resolve_public_source_url

                # Tree may only have the raw URL; prefer FL personId fix / search home
                target = resolve_public_source_url(url) or url
                webbrowser.open(target)
            except Exception as e:
                messagebox.showerror("Open link", str(e))


