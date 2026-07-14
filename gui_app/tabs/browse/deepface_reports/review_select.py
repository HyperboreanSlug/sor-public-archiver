"""DfrSelectMixin."""
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


class DfrSelectMixin:
    def _dfr_on_select(self, _event=None) -> None:
        try:
            sel = self.dfr_tree.selection()
            if not sel:
                return
            iid = sel[0]
            mc = self._dfr_hits_by_iid.get(iid)
            if mc is None:
                return
            self._dfr_show(iid, mc)
        except Exception:
            pass


    def _dfr_select_initial(self) -> None:
        """Pick first unreviewed hit, else first row — always show a photo if possible."""
        if not hasattr(self, "dfr_tree"):
            return
        kids = list(self.dfr_tree.get_children() or [])
        if not kids:
            self._dfr_clear_review()
            return
        pick = None
        for iid in kids:
            mc = self._dfr_hits_by_iid.get(iid)
            if mc is not None and self._dfr_get_verdict(mc) == "unreviewed":
                pick = iid
                break
        if pick is None:
            pick = kids[0]
        try:
            self.dfr_tree.selection_set(pick)
            self.dfr_tree.focus(pick)
            self.dfr_tree.see(pick)
        except Exception:
            pass
        mc = self._dfr_hits_by_iid.get(pick)
        if mc is not None:
            self._dfr_show(pick, mc)


    def _dfr_set_verdict(self, verdict: str) -> None:
        iid = getattr(self, "_dfr_selected_iid", None)
        mc = self._dfr_hits_by_iid.get(iid) if iid else None
        if mc is None:
            try:
                sel = self.dfr_tree.selection()
                if sel:
                    iid = sel[0]
                    mc = self._dfr_hits_by_iid.get(iid)
            except Exception:
                pass
        if mc is None:
            return

        if hasattr(self, "_set_verdict_for_mc"):
            try:
                self._set_verdict_for_mc(mc, verdict, save=True)
            except Exception:
                self._dfr_save_verdict_fallback(mc, verdict)
        else:
            self._dfr_save_verdict_fallback(mc, verdict)

        # Update tree cell
        if iid and hasattr(self, "dfr_tree"):
            try:
                vals = list(self.dfr_tree.item(iid, "values") or [])
                # name state listed face conf severity verdict id
                if len(vals) >= 7:
                    vals[6] = self._dfr_verdict_label(verdict)
                    self.dfr_tree.item(iid, values=vals)
            except Exception:
                pass
        self._dfr_show(iid, mc)
        self._dfr_update_metrics()
        self.after(40, self._dfr_next_unreviewed)


    def _dfr_save_verdict_fallback(self, mc, verdict: str) -> None:
        if not hasattr(self, "_report_verdicts") or self._report_verdicts is None:
            self._report_verdicts = {}
        key = self._dfr_verdict_key_for_mc(mc)
        keys = [key]
        rid = (mc.record or {}).get("id")
        if rid is not None:
            keys.append(f"id:{rid}")
        if verdict == "unreviewed":
            for k in keys:
                self._report_verdicts.pop(k, None)
        else:
            for k in keys:
                self._report_verdicts[k] = verdict
        if hasattr(self, "_save_report_verdicts"):
            try:
                self._save_report_verdicts()
                return
            except Exception:
                pass
        path = ROOT / "data" / "report_verdicts.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self._report_verdicts, indent=2, sort_keys=True),
            encoding="utf-8",
        )


    def _dfr_next_unreviewed(self) -> None:
        if not hasattr(self, "dfr_tree"):
            return
        kids = list(self.dfr_tree.get_children() or [])
        if not kids:
            return
        start = 0
        sel = self.dfr_tree.selection()
        if sel:
            try:
                start = kids.index(sel[0]) + 1
            except ValueError:
                start = 0
        order = kids[start:] + kids[:start]
        for iid in order:
            mc = self._dfr_hits_by_iid.get(iid)
            if mc is None:
                continue
            if self._dfr_get_verdict(mc) == "unreviewed":
                self.dfr_tree.selection_set(iid)
                self.dfr_tree.focus(iid)
                self.dfr_tree.see(iid)
                self._dfr_show(iid, mc)
                return
        if hasattr(self, "dfr_status"):
            self.dfr_status.configure(text="No unreviewed hits in current filter")


