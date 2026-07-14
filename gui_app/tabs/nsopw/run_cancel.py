"""NSOPW cancel."""
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


class NsopwCancelMixin:
    def _cancel_nsopw(self):
        self._nsopw_cancel = True
        self.log_queue.put("NSOPW cancel requested… (stops within ~50ms of delay)")
        try:
            self.nsopw_status.configure(text="Cancelling… stopping ASAP")
            if hasattr(self, "nsopw_current_search_label"):
                self.nsopw_current_search_label.configure(text="cancelling…")
            if hasattr(self, "nsopw_eta_label"):
                self.nsopw_eta_label.configure(text="ETA —")
        except Exception:
            pass


