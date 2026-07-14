"""Verdict"""
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


class DeepfaceScanVerdictMixin:
    def _deepface_scan_verdict_key(self, hit) -> str:
        rec = getattr(hit, "record", None) or {}
        rid = rec.get("id")
        if rid is not None and str(rid).strip() != "":
            return f"id:{rid}"
        name = (
            f"{rec.get('first_name') or ''} {rec.get('last_name') or ''}"
        ).strip()
        return f"df:{name}|{getattr(hit, 'predicted_label', '')}"


    def _deepface_scan_get_verdict(self, hit) -> str:
        if not hasattr(self, "_report_verdicts") or self._report_verdicts is None:
            self._report_verdicts = {}
            if hasattr(self, "_load_report_verdicts"):
                try:
                    self._load_report_verdicts()
                except Exception:
                    pass
        key = self._deepface_scan_verdict_key(hit)
        v = (self._report_verdicts.get(key) or "").strip()
        if v in ("confirmed", "correct", "skip"):
            return v
        # also try bare id
        rec = getattr(hit, "record", None) or {}
        rid = rec.get("id")
        if rid is not None:
            v2 = (self._report_verdicts.get(f"id:{rid}") or "").strip()
            if v2 in ("confirmed", "correct", "skip"):
                return v2
        return "unreviewed"


    def _deepface_scan_verdict_label(self, verdict: str) -> str:
        return {
            "confirmed": "Incorrect",
            "correct": "Correct",
            "skip": "Skip",
            "unreviewed": "—",
        }.get(verdict or "unreviewed", "—")


    def _deepface_scan_clear_review(self) -> None:
        try:
            self.df_scan_photo_lbl.configure(image=None, text="Start a scan\nto preview")
            self.df_scan_review_name.configure(text="—")
            self.df_scan_review_meta.configure(
                text="Scan to live-preview each mugshot, or select a hit to review."
            )
            self.df_scan_review_verdict.configure(text="", text_color=C["dim"])
            for name in (
                "df_scan_btn_confirm",
                "df_scan_btn_correct",
                "df_scan_btn_skip",
            ):
                w = getattr(self, name, None)
                if w is not None:
                    w.configure(state="disabled")
        except Exception:
            pass
        self._df_scan_selected_iid = None


    def _deepface_scan_set_verdict(self, verdict: str) -> None:
        """Confirm incorrect / correct / skip for the selected hit (→ Reports)."""
        iid = getattr(self, "_df_scan_selected_iid", None)
        hit = (getattr(self, "_df_scan_hits_by_iid", {}) or {}).get(iid) if iid else None
        if hit is None:
            # try current tree selection
            try:
                sel = self.df_scan_tree.selection()
                if sel:
                    iid = sel[0]
                    hit = self._df_scan_hits_by_iid.get(iid)
            except Exception:
                pass
        if hit is None:
            self._deepface_scan_log_msg("Select a hit first")
            return
        if not hasattr(self, "_report_verdicts") or self._report_verdicts is None:
            self._report_verdicts = {}
        key = self._deepface_scan_verdict_key(hit)
        keys = [key]
        rec = hit.record or {}
        rid = rec.get("id")
        if rid is not None:
            keys.append(f"id:{rid}")
        verdict = (verdict or "").strip()
        if verdict == "unreviewed":
            for k in keys:
                self._report_verdicts.pop(k, None)
        else:
            for k in keys:
                self._report_verdicts[k] = verdict
        if hasattr(self, "_save_report_verdicts"):
            try:
                self._save_report_verdicts()
            except Exception:
                # fallback write
                try:
                    path = ROOT / "data" / "report_verdicts.json"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(
                        json.dumps(self._report_verdicts, indent=2, sort_keys=True),
                        encoding="utf-8",
                    )
                except Exception as e:
                    self._deepface_scan_log_msg(f"Could not save verdict: {e}")
                    return
        # Update tree row
        if iid and hasattr(self, "df_scan_tree"):
            try:
                vals = list(self.df_scan_tree.item(iid, "values") or [])
                # columns: name state race face conf verdict id
                if len(vals) >= 6:
                    vals[5] = self._deepface_scan_verdict_label(verdict)
                    self.df_scan_tree.item(iid, values=vals)
            except Exception:
                pass
        self._deepface_scan_show_hit(iid, hit)
        self._deepface_scan_log_msg(
            f"Verdict {verdict} → {key} "
            f"({(rec.get('first_name') or '')} {(rec.get('last_name') or '')})".strip()
        )
        # Auto-advance to next unreviewed hit
        self.after(50, self._deepface_scan_next_unreviewed)


    def _deepface_scan_next_unreviewed(self) -> None:
        if not hasattr(self, "df_scan_tree"):
            return
        try:
            kids = list(self.df_scan_tree.get_children() or [])
            if not kids:
                return
            # Start after current selection
            start = 0
            sel = self.df_scan_tree.selection()
            if sel:
                try:
                    start = kids.index(sel[0]) + 1
                except ValueError:
                    start = 0
            order = kids[start:] + kids[:start]
            for iid in order:
                hit = (self._df_scan_hits_by_iid or {}).get(iid)
                if hit is None:
                    continue
                if self._deepface_scan_get_verdict(hit) == "unreviewed":
                    self.df_scan_tree.selection_set(iid)
                    self.df_scan_tree.focus(iid)
                    self.df_scan_tree.see(iid)
                    self._deepface_scan_show_hit(iid, hit)
                    return
            self._deepface_scan_log_msg("No unreviewed hits left")
        except Exception:
            pass


