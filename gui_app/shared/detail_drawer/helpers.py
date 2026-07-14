"""DetailHelpersMixin."""
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


class DetailHelpersMixin:
    @staticmethod
    def _clear_label_image(photo_lbl, drawer: Optional[ctk.CTkFrame] = None) -> None:
        """Detach a CTk/Tk image from a label without leaving a dangling image name.

        CustomTkinter + Tk can raise ``TclError: image "pyimageN" doesn't exist``
        on a later configure() if the PhotoImage is GC'd while the label still
        references it. Clear the image *before* dropping the Python ref.
        """
        # Keep local ref so GC cannot race mid-clear
        old_ref = None
        if drawer is not None:
            old_ref = getattr(drawer, "_detail_image_ref", None)
        try:
            # Empty string is the reliable Tk way to clear -image
            photo_lbl.configure(image="")
        except Exception:
            try:
                inner = getattr(photo_lbl, "_label", None)
                if inner is not None:
                    inner.configure(image="")
            except Exception:
                pass
        if drawer is not None:
            try:
                drawer._detail_image_ref = None  # type: ignore[attr-defined]
            except Exception:
                pass
        # Drop after Tk no longer names it
        del old_ref


    def _make_textbox_selectable(self, body: ctk.CTkTextbox) -> None:
        """Allow select + copy (Ctrl+C / right-click) without editing content."""
        try:
            tb = getattr(body, "_textbox", None) or body
        except Exception:
            return

        def _block_edit(event):
            if event.state & 0x4:  # Control
                if event.keysym.lower() in ("c", "a", "insert"):
                    return None
            if event.keysym in (
                "Left", "Right", "Up", "Down", "Home", "End",
                "Prior", "Next", "Shift_L", "Shift_R", "Control_L", "Control_R",
            ):
                return None
            return "break"

        def _copy_sel(_event=None):
            try:
                if tb.tag_ranges("sel"):
                    text = tb.get("sel.first", "sel.last")
                else:
                    text = tb.get("1.0", "end-1c")
                if text:
                    self.clipboard_clear()
                    self.clipboard_append(text)
            except Exception:
                pass
            return "break"

        def _select_all(_event=None):
            try:
                tb.tag_add("sel", "1.0", "end-1c")
                tb.mark_set("insert", "1.0")
            except Exception:
                pass
            return "break"

        try:
            tb.bind("<Key>", _block_edit, add="+")
            tb.bind("<Control-c>", _copy_sel, add="+")
            tb.bind("<Control-C>", _copy_sel, add="+")
            tb.bind("<Control-a>", _select_all, add="+")
            tb.bind("<Control-A>", _select_all, add="+")
            # Right-click copies selection or full text
            tb.bind("<Button-3>", lambda _e: _copy_sel(), add="+")
        except Exception:
            pass


    def _copy_to_clipboard(self, text: str, *, toast: Optional[str] = None) -> None:
        try:
            self.clipboard_clear()
            self.clipboard_append(text or "")
            if toast:
                if hasattr(self, "report_status"):
                    self.report_status.configure(text=toast)
                elif hasattr(self, "misclass_status"):
                    self.misclass_status.configure(text=toast)
        except Exception as e:
            messagebox.showerror("Copy", str(e))


    def _bind_global_copy_shortcuts(self) -> None:
        """Ctrl+C on treeviews copies selected row values as TSV."""
        def _tree_copy(event):
            w = event.widget
            try:
                if not isinstance(w, ttk.Treeview):
                    return
                sel = w.selection()
                if not sel:
                    return
                lines = []
                for iid in sel:
                    vals = w.item(iid, "values") or ()
                    lines.append("\t".join(str(v) for v in vals))
                if lines:
                    self._copy_to_clipboard("\n".join(lines))
                return "break"
            except Exception:
                return

        try:
            self.bind_all("<Control-c>", _tree_copy, add="+")
            self.bind_all("<Control-C>", _tree_copy, add="+")
        except Exception:
            pass


