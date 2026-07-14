"""ScrapeSelectMixin."""
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


class ScrapeSelectMixin:
    def _scrape_select_all(self):
        for item in self.scrape_tree.get_children():
            if self.scrape_direct_only.get():
                if "direct" not in self.scrape_tree.item(item, "tags"):
                    continue
            self.scrape_tree.selection_add(item)
        self._update_scrape_selection()


    def _scrape_clear_selection(self):
        self.scrape_tree.selection_remove(*self.scrape_tree.selection())
        self._update_scrape_selection()


    def _scrape_on_select(self, _event=None):
        self._update_scrape_selection()


    def _update_scrape_selection(self):
        self.selected_states.clear()
        for item in self.scrape_tree.selection():
            vals = self.scrape_tree.item(item, "values")
            if vals:
                self.selected_states.add(vals[0])
        self.stats_label.configure(text=f"{len(self.selected_states)} selected")


    def _scrape_browse_output(self):
        folder = filedialog.askdirectory(initialdir=self.scrape_output_var.get())
        if folder:
            self.scrape_output_var.set(folder)


