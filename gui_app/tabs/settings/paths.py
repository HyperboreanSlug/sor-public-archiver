"""Paths"""
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


class SettingsPathsMixin:
    def _settings_browse_db(self) -> None:
        from tkinter import filedialog

        path = filedialog.asksaveasfilename(
            title="Database file",
            defaultextension=".db",
            filetypes=[("SQLite database", "*.db"), ("All files", "*.*")],
            initialfile=Path(self.settings_db_path.get() or "offenders.db").name,
        )
        if path:
            # Store project-relative when under install root (portable across machines).
            try:
                from scraper.paths import portable_path_str

                self.settings_db_path.set(portable_path_str(path))
            except Exception:
                self.settings_db_path.set(path)


    def _settings_browse_backup_dir(self) -> None:
        from tkinter import filedialog

        path = filedialog.askdirectory(
            title="Backup folder",
            initialdir=self.settings_backup_dir.get() or "data",
        )
        if path:
            try:
                from scraper.paths import portable_path_str

                self.settings_backup_dir.set(
                    portable_path_str(path, default="data/backups")
                )
            except Exception:
                self.settings_backup_dir.set(path)


    def _settings_open_backup_dir(self) -> None:
        path = Path(self.settings_backup_dir.get() or "data/backups")
        path.mkdir(parents=True, exist_ok=True)
        self._open_path(path)


    def _settings_on_compact_toggle(self) -> None:
        if hasattr(self, "_nsopw_update_surname_count"):
            try:
                self._nsopw_update_surname_count()
            except Exception:
                pass


    def _settings_refresh_status(self) -> None:
        bdir = Path(self.settings_backup_dir.get() or "data/backups")
        n = 0
        latest = "—"
        if bdir.is_dir():
            files = sorted(bdir.glob("offenders_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
            n = len(files)
            if files:
                latest = files[0].name
        try:
            from scraper.paths import resolve_under_root

            dbp = resolve_under_root(self.settings_db_path.get() or self.db_path)
        except Exception:
            dbp = Path(self.settings_db_path.get() or self.db_path)
        db_info = (
            f"{dbp} ({dbp.stat().st_size // 1024} KB)"
            if dbp.is_file()
            else f"{dbp} (not created yet)"
        )
        if hasattr(self, "settings_backup_status"):
            self.settings_backup_status.configure(
                text=f"DB: {db_info}  ·  {n} backup(s)  ·  latest: {latest}"
            )


    def _settings_backup_now(self) -> None:
        """Manual backup using current Settings fields (does not require Save first)."""
        try:
            dest, note = self._run_db_backup(
                db_path=self.settings_db_path.get() or self.db_path,
                backup_dir=self.settings_backup_dir.get() or "data/backups",
                max_backups=self.settings_max_backups.get(),
            )
            msg = f"Backed up → {dest}"
            if note:
                msg += f" ({note})"
            self.settings_backup_status.configure(text=msg)
            self.settings_status.configure(text=msg)
            self.log_queue.put(msg)
        except Exception as e:
            self.settings_backup_status.configure(text=f"Backup failed: {e}")
            messagebox.showerror("Backup failed", str(e))


    def _run_db_backup(
        self,
        db_path: Optional[str] = None,
        backup_dir: Optional[str] = None,
        max_backups: Any = None,
    ):
        from scraper.database import backup_database_file

        try:
            from scraper.paths import resolve_under_root

            src = resolve_under_root(db_path or self.db_path)
            bdir = resolve_under_root(
                backup_dir or self.app_settings.get("backup_dir") or "data/backups",
                default="data/backups",
            )
        except Exception:
            src = Path(db_path or self.db_path)
            bdir = Path(
                backup_dir or self.app_settings.get("backup_dir") or "data/backups"
            )
        if not src.exists():
            raise FileNotFoundError(f"Database not found: {src}")
        try:
            keep = int(
                max_backups
                if max_backups is not None
                else self.app_settings.get("max_backups", 10)
            )
        except (TypeError, ValueError):
            keep = 10

        # backup_database_file opens its own connection + verifies integrity
        return backup_database_file(
            src, bdir, keep=keep, prefix="offenders", verify=True
        )


