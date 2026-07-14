"""SetupLog"""
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


class DeepfaceSetupLogMixin:
    def _deepface_bind_scroll_children(self, tab, scroll_frame) -> None:
        """Fast mouse-wheel scrolling over the full DeepFace tab content."""
        try:
            canvas = scroll_frame._parent_canvas  # type: ignore[attr-defined]
        except Exception:
            return

        # Fraction of the visible page to move per wheel notch (~18% feels snappy)
        PAGE_FRAC = 0.18

        def _scroll_by_notches(notches: int) -> None:
            if notches == 0:
                return
            try:
                first, last = canvas.yview()
            except Exception:
                canvas.yview_scroll(notches * 12, "units")
                return
            page = max(last - first, 0.05)
            # Move ~PAGE_FRAC of the visible page per notch (not tiny Tk "units")
            step = notches * max(PAGE_FRAC * page, 0.08)
            try:
                canvas.yview_moveto(max(0.0, min(1.0, first + step)))
            except Exception:
                canvas.yview_scroll(notches * 12, "units")

        def _wheel(event):
            delta = getattr(event, "delta", 0) or 0
            if delta:
                # Windows: multiples of 120; high-res trackpads may send smaller values
                if abs(delta) >= 120:
                    notches = int(-delta / 120)
                else:
                    notches = -1 if delta > 0 else 1
                if notches == 0:
                    notches = -1 if delta > 0 else 1
                _scroll_by_notches(notches)
            else:
                num = getattr(event, "num", 0)
                if num == 4:
                    _scroll_by_notches(-1)
                elif num == 5:
                    _scroll_by_notches(1)
            return "break"

        def _walk(w):
            try:
                # Don't steal wheel from the activity textbox (it scrolls itself)
                if w is getattr(self, "df_log", None):
                    return
            except Exception:
                pass
            try:
                # Replace prior bindings so we don't stack slow + fast handlers
                w.bind("<MouseWheel>", _wheel)
                w.bind("<Button-4>", _wheel)
                w.bind("<Button-5>", _wheel)
            except Exception:
                pass
            try:
                for child in w.winfo_children():
                    _walk(child)
            except Exception:
                pass

        try:
            _walk(tab)
            _walk(scroll_frame)
            # Also re-wire the scroll frame's own canvas/parent (wire_wide_scroll is slow)
            for w in (
                tab,
                getattr(scroll_frame, "_parent_frame", None),
                canvas,
                scroll_frame,
            ):
                if w is None:
                    continue
                try:
                    w.bind("<MouseWheel>", _wheel)
                    w.bind("<Button-4>", _wheel)
                    w.bind("<Button-5>", _wheel)
                except Exception:
                    pass
        except Exception:
            pass


    def _deepface_append_log(self, msg: str) -> None:
        try:
            self._df_log_queue.put(str(msg))
        except Exception:
            pass


    def _deepface_poll_log(self) -> None:
        if not hasattr(self, "df_log"):
            return
        try:
            while True:
                msg = self._df_log_queue.get_nowait()
                self.df_log.configure(state="normal")
                ts = datetime.now().strftime("%H:%M:%S")
                self.df_log.insert("end", f"[{ts}] {msg}\n")
                self.df_log.see("end")
                self.df_log.configure(state="disabled")
        except queue.Empty:
            pass
        except Exception:
            pass
        try:
            self.after(200, self._deepface_poll_log)
        except Exception:
            pass


    def _deepface_open_log(self) -> None:
        path = ROOT / "deepface_setup.log"
        if not path.is_file():
            try:
                path.write_text("# DeepFace setup log\n", encoding="utf-8")
            except OSError:
                pass
        if hasattr(self, "_open_path"):
            self._open_path(path)
        else:
            try:
                os.startfile(str(path))  # type: ignore[attr-defined]
            except Exception:
                pass


    def _deepface_open_weights_dir(self) -> None:
        path = Path.home() / ".deepface" / "weights"
        path.mkdir(parents=True, exist_ok=True)
        if hasattr(self, "_open_path"):
            self._open_path(path)
        else:
            try:
                os.startfile(str(path))  # type: ignore[attr-defined]
            except Exception:
                pass


