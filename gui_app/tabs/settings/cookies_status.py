"""CookieStatus"""
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


class SettingsCookieStatusMixin:
    def _settings_set_cookie_pull_status(self, text: str, *, color: Optional[str] = None) -> None:
        if not hasattr(self, "settings_cookie_pull_status"):
            return
        try:
            self.settings_cookie_pull_status.configure(
                text=text,
                text_color=color or C["dim"],
            )
        except Exception:
            pass


    def _settings_import_cookies(self) -> None:
        try:
            from scraper.cookie_jar import CookieJarStore

            raw = self.settings_cookie_text.get("1.0", "end")
            domain = (self.settings_cookie_domain.get() or "").strip()
            n = CookieJarStore().import_cookies(raw, default_domain=domain)
            self.settings_cookie_status.configure(
                text=f"Imported {n} cookie(s). Requeue incomplete reports to retry."
            )
            self._settings_refresh_captcha_queue()
            if n == 0:
                messagebox.showwarning(
                    "No cookies imported",
                    "Paste JSON cookies, Netscape cookies.txt lines, or a Cookie: header.\n"
                    "Set default domain if the paste has no domain field.",
                )
        except Exception as e:
            messagebox.showerror("Import cookies", str(e))


    def _settings_load_cookie_file(self) -> None:
        from tkinter import filedialog

        path = filedialog.askopenfilename(
            title="Cookie file",
            filetypes=[
                ("Cookie / JSON / text", "*.txt *.json *.cookies"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
            self.settings_cookie_text.delete("1.0", "end")
            self.settings_cookie_text.insert("1.0", text)
            self._settings_import_cookies()
        except Exception as e:
            messagebox.showerror("Load cookies", str(e))


    def _settings_clear_cookies(self) -> None:
        try:
            from scraper.cookie_jar import CookieJarStore

            CookieJarStore().clear()
            self.settings_cookie_status.configure(text="Saved cookies cleared.")
            self._settings_refresh_captcha_queue()
        except Exception as e:
            messagebox.showerror("Clear cookies", str(e))


