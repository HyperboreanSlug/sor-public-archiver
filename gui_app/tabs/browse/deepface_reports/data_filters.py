"""DfrFiltersMixin."""
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


class DfrFiltersMixin:
    def _dfr_verdict_key_for_mc(self, mc) -> str:
        rec = mc.record or {}
        rid = rec.get("id")
        if rid is not None and str(rid).strip() != "":
            return f"id:{rid}"
        name = (
            f"{rec.get('first_name') or ''} {rec.get('last_name') or ''}"
        ).strip()
        return f"df:{name}|{mc.likely_ethnicity}"


    def _dfr_get_verdict(self, mc) -> str:
        if hasattr(self, "_verdict_for_mc"):
            try:
                return self._verdict_for_mc(mc)
            except Exception:
                pass
        if not hasattr(self, "_report_verdicts") or self._report_verdicts is None:
            self._report_verdicts = {}
        key = self._dfr_verdict_key_for_mc(mc)
        v = (self._report_verdicts.get(key) or "").strip()
        return v if v in ("confirmed", "correct", "skip") else "unreviewed"


    def _dfr_verdict_label(self, v: str) -> str:
        return {
            "confirmed": "Incorrect",
            "correct": "Correct",
            "skip": "Skip",
            "unreviewed": "—",
        }.get(v or "unreviewed", "—")


    def _dfr_show_filter_key(self) -> str:
        raw = (self.dfr_verdict_filter.get() or "Unconfirmed").strip().lower()
        if "incorrect" in raw:
            return "confirmed"
        if "correct" in raw:
            return "correct"
        if raw.startswith("skip"):
            return "skip"
        if raw == "all":
            return "all"
        return "unreviewed"


    def _dfr_apply_filters(self) -> None:
        all_hits = list(getattr(self, "_dfr_all_hits", None) or [])
        vfilter = self._dfr_show_filter_key()
        face_f = (self.dfr_face_filter.get() or "All").strip().lower()
        try:
            min_c = float((self.dfr_min_conf.get() or "0").strip() or "0")
        except ValueError:
            min_c = 0.0

        filtered = []
        for mc in all_hits:
            if float(mc.confidence or 0) < min_c:
                continue
            v = self._dfr_get_verdict(mc)
            if vfilter != "all" and v != vfilter:
                continue
            if face_f and face_f != "all":
                df = (mc.record or {}).get("_deepface") or {}
                lab = (
                    df.get("predicted_label")
                    or df.get("top_label")
                    or (mc.likely_ethnicity or "")
                ).lower()
                lab = lab.replace(" ", "_").replace("(south_asian)", "").replace("indian_(south_asian)", "indian")
                if "indian" in lab:
                    lab = "indian"
                if face_f not in lab and lab != face_f:
                    # also match face:black@ style in matching_names
                    names = " ".join(mc.matching_names or []).lower()
                    if face_f not in names:
                        continue
            filtered.append(mc)

        filtered.sort(key=lambda m: float(m.confidence or 0), reverse=True)
        self._dfr_hits = filtered
        self._dfr_populate_tree()
        self._dfr_update_metrics()


    def _dfr_populate_tree(self) -> None:
        if not hasattr(self, "dfr_tree"):
            return
        self.dfr_tree.delete(*self.dfr_tree.get_children())
        self._dfr_hits_by_iid = {}
        self._dfr_selected_iid = None
        self._dfr_clear_review()
        for mc in self._dfr_hits:
            rec = mc.record or {}
            name = (
                f"{rec.get('first_name') or ''} {rec.get('last_name') or ''}"
            ).strip() or (rec.get("full_name") or "—")
            df = rec.get("_deepface") or {}
            face = df.get("predicted_label") or df.get("top_label") or "—"
            sev = df.get("severity") or ""
            race = _format_race_display(mc.expected_race) or (mc.expected_race or "—")
            v = self._dfr_get_verdict(mc)
            iid = self.dfr_tree.insert(
                "",
                "end",
                values=(
                    name,
                    _format_state_display(rec),
                    str(race)[:18],
                    face,
                    f"{float(mc.confidence or 0):.2f}",
                    sev,
                    self._dfr_verdict_label(v),
                    rec.get("id") or "",
                ),
            )
            self._dfr_hits_by_iid[iid] = mc
        # Always show something: first unreviewed, else first row
        self.after(40, self._dfr_select_initial)


    def _dfr_update_metrics(self) -> None:
        all_hits = list(getattr(self, "_dfr_all_hits", None) or [])
        n_open = n_bad = n_ok = 0
        for mc in all_hits:
            v = self._dfr_get_verdict(mc)
            if v == "unreviewed":
                n_open += 1
            elif v == "confirmed":
                n_bad += 1
            elif v == "correct":
                n_ok += 1
        shown = len(getattr(self, "_dfr_hits", []) or [])
        try:
            self.dfr_m_total.configure(
                text=f"Hits: {len(all_hits):,} · showing {shown:,}"
            )
            self.dfr_m_open.configure(text=f"Open: {n_open:,}")
            self.dfr_m_bad.configure(text=f"Incorrect: {n_bad:,}")
            self.dfr_m_ok.configure(text=f"Correct: {n_ok:,}")
        except Exception:
            pass


