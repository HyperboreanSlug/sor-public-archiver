"""ScanOpts"""
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


class DeepfaceScanOptsMixin:
    def _deepface_scan_log_msg(self, msg: str) -> None:
        try:
            self._df_scan_log_queue.put(str(msg))
        except Exception:
            pass


    def _deepface_poll_scan_log(self) -> None:
        if not hasattr(self, "df_scan_log"):
            return
        try:
            while True:
                msg = self._df_scan_log_queue.get_nowait()
                self.df_scan_log.configure(state="normal")
                ts = datetime.now().strftime("%H:%M:%S")
                self.df_scan_log.insert("end", f"[{ts}] {msg}\n")
                self.df_scan_log.see("end")
                self.df_scan_log.configure(state="disabled")
        except queue.Empty:
            pass
        except Exception:
            pass
        try:
            self.after(200, self._deepface_poll_scan_log)
        except Exception:
            pass


    def _deepface_scan_collect_options(self) -> Dict[str, Any]:
        def _f(entry, default=""):
            try:
                return (entry.get() or "").strip() or default
            except Exception:
                return default

        try:
            min_conf = float(_f(self.df_scan_min_conf, "0.85") or "0.85")
        except ValueError:
            min_conf = 0.85
        try:
            limit = int(float(_f(self.df_scan_limit, "0") or "0"))
        except ValueError:
            limit = 0
        recorded = []
        for key, var in getattr(self, "_df_scan_race_vars", {}).items():
            try:
                if bool(var.get()):
                    recorded.append(key)
            except Exception:
                pass
        if not recorded:
            recorded = ["WHITE"]
        faces = []
        for key, var in getattr(self, "_df_scan_face_vars", {}).items():
            try:
                if bool(var.get()):
                    faces.append(key)
            except Exception:
                pass
        if not faces:
            faces = ["black", "indian", "asian"]
        state = _f(self.df_scan_state, "") or None
        force = False
        try:
            force = bool(self.df_scan_rescan.get())
        except Exception:
            force = False
        return {
            "min_confidence": min_conf,
            "limit": max(0, limit),
            "recorded_races": recorded,
            "face_labels": faces,
            "state": state,
            "force_rescan": force,
        }


