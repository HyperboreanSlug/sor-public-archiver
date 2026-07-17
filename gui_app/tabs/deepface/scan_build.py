"""ScanBuild"""
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


class DeepfaceScanBuildMixin:
    def _build_deepface_scan(self, tab) -> None:
        """Scan options, start/stop, progress, and results monitor."""
        tab.configure(fg_color=C["surface"])
        sett = getattr(self, "app_settings", {}) or {}

        # Fixed top: options + controls; bottom expands for results
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        top = ctk.CTkFrame(tab, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 4))
        top.grid_columnconfigure(0, weight=1)

        opt = _card(top)
        opt.pack(fill="x", padx=2, pady=2)
        _section_label(opt, "Mugshot gross-misclass scan").pack(
            anchor="w", padx=14, pady=(12, 4)
        )
        _muted(
            opt,
            "Score mugshots with FairFace by default (DeepFace only if FairFace is "
            "unavailable). Flags high-confidence face ethnicity that contradicts the "
            "registry race (default: face Black/Indian/Asian while race is White). "
            "Does not use surnames. Setup still manages DeepFace weights as fallback.",
        ).pack(anchor="w", padx=14, pady=(0, 8))

        grid = ctk.CTkFrame(opt, fg_color="transparent")
        grid.pack(fill="x", padx=14, pady=(0, 8))
        for c in range(4):
            grid.grid_columnconfigure(c, weight=1)

        # Row 0: state, min conf, limit, backend note
        ctk.CTkLabel(grid, text="State filter", font=FONT_SM, text_color=C["muted"]).grid(
            row=0, column=0, sticky="w", padx=(0, 8), pady=2
        )
        self.df_scan_state = ctk.CTkEntry(
            grid, width=80, placeholder_text="All",
            fg_color=C["bg"], border_color=C["border"], text_color=C["text"],
        )
        self.df_scan_state.grid(row=1, column=0, sticky="ew", padx=(0, 12), pady=(0, 6))
        st0 = str(sett.get("deepface_scan_state") or "").strip()
        if st0:
            self.df_scan_state.insert(0, st0)

        ctk.CTkLabel(grid, text="Min face confidence", font=FONT_SM, text_color=C["muted"]).grid(
            row=0, column=1, sticky="w", padx=(0, 8), pady=2
        )
        self.df_scan_min_conf = ctk.CTkEntry(
            grid, width=80, placeholder_text="0.85",
            fg_color=C["bg"], border_color=C["border"], text_color=C["text"],
        )
        self.df_scan_min_conf.grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=(0, 6))
        self.df_scan_min_conf.insert(0, str(sett.get("deepface_scan_min_conf") or "0.85"))

        ctk.CTkLabel(grid, text="Max candidates (0=all)", font=FONT_SM, text_color=C["muted"]).grid(
            row=0, column=2, sticky="w", padx=(0, 8), pady=2
        )
        self.df_scan_limit = ctk.CTkEntry(
            grid, width=80, placeholder_text="0",
            fg_color=C["bg"], border_color=C["border"], text_color=C["text"],
        )
        self.df_scan_limit.grid(row=1, column=2, sticky="ew", padx=(0, 12), pady=(0, 6))
        self.df_scan_limit.insert(0, str(sett.get("deepface_scan_limit") or "0"))

        # --- Selectable recorded-race filter ---
        ctk.CTkLabel(
            opt, text="Recorded race filter (scan records listed as…)",
            font=FONT_SM, text_color=C["muted"], anchor="w",
        ).pack(fill="x", padx=14, pady=(4, 2))
        race_row = ctk.CTkFrame(opt, fg_color="transparent")
        race_row.pack(fill="x", padx=14, pady=(0, 6))
        # Canonical keys used by scanner._race_is_target / _canonical_race_key
        self._DF_SCAN_RACE_OPTS = [
            ("WHITE", "White"),
            ("BLACK", "Black"),
            ("ASIAN", "Asian"),
            ("HISPANIC", "Hispanic"),
            ("INDIAN", "Indian"),
            ("OTHER", "Other"),
        ]
        saved_races = {
            p.strip().upper()
            for p in str(sett.get("deepface_scan_recorded") or "WHITE").replace(";", ",").split(",")
            if p.strip()
        }
        if not saved_races:
            saved_races = {"WHITE"}
        self._df_scan_race_vars: Dict[str, ctk.BooleanVar] = {}
        for i, (key, label) in enumerate(self._DF_SCAN_RACE_OPTS):
            var = ctk.BooleanVar(value=(key in saved_races))
            self._df_scan_race_vars[key] = var
            ctk.CTkCheckBox(
                race_row,
                text=label,
                variable=var,
                font=FONT_SM,
                text_color=C["text"],
                fg_color=C["accent"],
                hover_color=C["accent_hover"],
                border_color=C["border"],
                checkmark_color=C["bg"],
                width=90,
            ).pack(side="left", padx=(0, 10))

        # --- Selectable face labels to flag ---
        ctk.CTkLabel(
            opt, text="Face labels to flag (DeepFace prediction…)",
            font=FONT_SM, text_color=C["muted"], anchor="w",
        ).pack(fill="x", padx=14, pady=(4, 2))
        face_row = ctk.CTkFrame(opt, fg_color="transparent")
        face_row.pack(fill="x", padx=14, pady=(0, 6))
        self._DF_SCAN_FACE_OPTS = [
            ("black", "Black"),
            ("indian", "Indian"),
            ("asian", "Asian"),
            ("hispanic", "Hispanic"),
            ("middle_eastern", "Mid. Eastern"),
            ("white", "White"),
        ]
        saved_faces = {
            p.strip().lower()
            for p in str(
                sett.get("deepface_scan_faces") or "black,indian,asian"
            ).replace(";", ",").split(",")
            if p.strip()
        }
        if not saved_faces:
            saved_faces = {"black", "indian", "asian"}
        self._df_scan_face_vars: Dict[str, ctk.BooleanVar] = {}
        for key, label in self._DF_SCAN_FACE_OPTS:
            var = ctk.BooleanVar(value=(key in saved_faces))
            self._df_scan_face_vars[key] = var
            ctk.CTkCheckBox(
                face_row,
                text=label,
                variable=var,
                font=FONT_SM,
                text_color=C["text"],
                fg_color=C["accent"],
                hover_color=C["accent_hover"],
                border_color=C["border"],
                checkmark_color=C["bg"],
                width=100,
            ).pack(side="left", padx=(0, 10))

        skip_row = ctk.CTkFrame(opt, fg_color="transparent")
        skip_row.pack(fill="x", padx=14, pady=(0, 4))
        self.df_scan_rescan = ctk.BooleanVar(
            value=bool(sett.get("deepface_scan_force_rescan", False))
        )
        ctk.CTkCheckBox(
            skip_row,
            text="Rescan already-scored mugshots (ignore stored DeepFace results)",
            variable=self.df_scan_rescan,
            font=FONT_SM,
            text_color=C["text"],
            fg_color=C["accent"],
            hover_color=C["accent_hover"],
            border_color=C["border"],
            checkmark_color=C["bg"],
        ).pack(side="left")
        self.df_scan_db_stats = ctk.CTkLabel(
            skip_row, text="", font=FONT_SM, text_color=C["dim"], anchor="e",
        )
        self.df_scan_db_stats.pack(side="right")
        self.after(80, self._deepface_scan_refresh_db_stats)

        # Controls
        ctrl = ctk.CTkFrame(opt, fg_color="transparent")
        ctrl.pack(fill="x", padx=14, pady=(4, 8))
        self.df_scan_start_btn = ctk.CTkButton(
            ctrl, text="Start scan", width=120,
            command=self._deepface_scan_start,
            fg_color=C["accent"], hover_color=C["accent_hover"], text_color=C["bg"],
        )
        self.df_scan_start_btn.pack(side="left", padx=(0, 8))
        self.df_scan_stop_btn = ctk.CTkButton(
            ctrl, text="Stop", width=90,
            command=self._deepface_scan_stop,
            fg_color=C["elevated"], hover_color=C["border"], text_color=C["text"],
            border_width=1, border_color=C["border"], state="disabled",
        )
        self.df_scan_stop_btn.pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            ctrl, text="Export hits…", width=110,
            command=self._deepface_scan_export,
            fg_color=C["elevated"], hover_color=C["border"], text_color=C["text"],
            border_width=1, border_color=C["border"],
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            ctrl, text="Clear results", width=100,
            command=self._deepface_scan_clear,
            fg_color=C["elevated"], hover_color=C["border"], text_color=C["text"],
            border_width=1, border_color=C["border"],
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            ctrl, text="Open Setup →", width=110,
            command=self._deepface_goto_setup,
            fg_color=C["elevated"], hover_color=C["border"], text_color=C["text"],
            border_width=1, border_color=C["border"],
        ).pack(side="right")

        self.df_scan_progress = ctk.CTkProgressBar(
            opt, height=8, progress_color=C["accent"], fg_color=C["elevated"],
        )
        self.df_scan_progress.pack(fill="x", padx=14, pady=(0, 4))
        self.df_scan_progress.set(0)
        self.df_scan_status = ctk.CTkLabel(
            opt, text="Ready — configure options and click Start scan",
            font=FONT_SM, text_color=C["dim"], anchor="w",
        )
        self.df_scan_status.pack(fill="x", padx=14, pady=(0, 12))

        # Bottom: hits list | mugshot review + confirm | activity
        bottom = ctk.CTkFrame(tab, fg_color="transparent")
        bottom.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
        bottom.grid_columnconfigure(0, weight=3)
        bottom.grid_columnconfigure(1, weight=3)
        bottom.grid_columnconfigure(2, weight=2)
        bottom.grid_rowconfigure(0, weight=1)

        res_card = _card(bottom)
        res_card.grid(row=0, column=0, sticky="nsew", padx=(2, 4), pady=2)
        res_card.grid_columnconfigure(0, weight=1)
        res_card.grid_rowconfigure(1, weight=1)
        _section_label(res_card, "Hits (select to review)").pack(
            anchor="w", padx=14, pady=(12, 4)
        )
        wrap, tree = _tree_frame(res_card)
        wrap.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        cols = ("name", "state", "race", "face", "conf", "verdict", "id")
        tree["columns"] = cols
        tree["show"] = "headings"
        widths = [140, 45, 80, 70, 50, 90, 50]
        labels = {
            "name": "NAME",
            "state": "ST",
            "race": "LISTED",
            "face": "FACE",
            "conf": "CONF",
            "verdict": "VERDICT",
            "id": "ID",
        }
        for c, w in zip(cols, widths):
            tree.heading(c, text=labels.get(c, c.upper()))
            tree.column(c, width=w, minwidth=36, stretch=(c == "name"))
        _stretch_columns(tree, cols, widths)
        self.df_scan_tree = tree
        self._df_scan_hits_by_iid: Dict[str, Any] = {}
        self._df_scan_image_refs: list = []
        tree.bind("<<TreeviewSelect>>", self._deepface_scan_on_select)
        _bind_tree_scroll_isolation(tree, wrap)

        # Review panel: live scan mugshot + hit confirm/reject
        rev_card = _card(bottom)
        rev_card.grid(row=0, column=1, sticky="nsew", padx=4, pady=2)
        _section_label(rev_card, "Review / live scan").pack(
            anchor="w", padx=14, pady=(12, 4)
        )
        _muted(
            rev_card,
            "While scanning, shows the mugshot currently being scored. "
            "Click a hit in the list to pin it for confirm/skip. "
            "Verdicts sync to Browse → Reports.",
        ).pack(anchor="w", padx=14, pady=(0, 6))
        self._df_scan_live_preview = True
        self._df_scan_live_seq = 0

        rev_body = ctk.CTkFrame(rev_card, fg_color="transparent")
        rev_body.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        rev_body.grid_columnconfigure(1, weight=1)
        rev_body.grid_rowconfigure(1, weight=1)

        photo_wrap = ctk.CTkFrame(
            rev_body, fg_color=C["tree_bg"], corner_radius=10, width=160, height=200,
        )
        photo_wrap.grid(row=0, column=0, rowspan=2, sticky="nw", padx=(0, 12), pady=4)
        photo_wrap.grid_propagate(False)
        self.df_scan_photo_lbl = ctk.CTkLabel(
            photo_wrap, text="Start a scan\nto preview", font=FONT_SM, text_color=C["dim"],
        )
        self.df_scan_photo_lbl.place(relx=0.5, rely=0.5, anchor="center")

        self.df_scan_review_name = ctk.CTkLabel(
            rev_body, text="—", font=FONT_TITLE, text_color=C["text"], anchor="w",
        )
        self.df_scan_review_name.grid(row=0, column=1, sticky="ew", pady=(4, 2))

        self.df_scan_review_meta = ctk.CTkLabel(
            rev_body,
            text="Scan to live-preview each mugshot, or select a hit to review.",
            font=FONT_SM,
            text_color=C["muted"],
            anchor="nw",
            justify="left",
            wraplength=320,
        )
        self.df_scan_review_meta.grid(row=1, column=1, sticky="new", pady=(0, 6))

        self.df_scan_review_verdict = ctk.CTkLabel(
            rev_body, text="", font=FONT_BOLD, text_color=C["dim"], anchor="w",
        )
        self.df_scan_review_verdict.grid(row=2, column=1, sticky="ew", pady=(0, 6))

        btn_row = ctk.CTkFrame(rev_card, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=(0, 12))
        self.df_scan_btn_confirm = ctk.CTkButton(
            btn_row, text="Confirmed incorrect", width=150,
            command=lambda: self._deepface_scan_set_verdict("confirmed"),
            fg_color="#5c3030", hover_color="#7a4040", text_color=C["text"],
            state="disabled",
        )
        self.df_scan_btn_confirm.pack(side="left", padx=(0, 6))
        self.df_scan_btn_correct = ctk.CTkButton(
            btn_row, text="Confirmed correct", width=140,
            command=lambda: self._deepface_scan_set_verdict("correct"),
            fg_color="#2a4a38", hover_color="#356348", text_color=C["text"],
            state="disabled",
        )
        self.df_scan_btn_correct.pack(side="left", padx=(0, 6))
        self.df_scan_btn_skip = ctk.CTkButton(
            btn_row, text="Skip", width=70,
            command=lambda: self._deepface_scan_set_verdict("skip"),
            fg_color=C["elevated"], hover_color=C["border"], text_color=C["muted"],
            border_width=1, border_color=C["border"],
            state="disabled",
        )
        self.df_scan_btn_skip.pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            btn_row, text="Next unreviewed", width=120,
            command=self._deepface_scan_next_unreviewed,
            fg_color=C["elevated"], hover_color=C["border"], text_color=C["text"],
            border_width=1, border_color=C["border"],
        ).pack(side="right")

        log_card = _card(bottom)
        log_card.grid(row=0, column=2, sticky="nsew", padx=(4, 2), pady=2)
        _section_label(log_card, "Scan activity").pack(
            anchor="w", padx=14, pady=(12, 4)
        )
        self.df_scan_log = ctk.CTkTextbox(
            log_card,
            font=FONT_MONO,
            fg_color=C["bg"],
            text_color=C["muted"],
            border_color=C["border"],
            border_width=1,
            corner_radius=8,
        )
        self.df_scan_log.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.df_scan_log.configure(state="disabled")
        self._df_scan_log_queue: queue.Queue = queue.Queue()
        self._df_scan_selected_iid: Optional[str] = None
        # Share report verdict store if Browse already loaded it
        if not hasattr(self, "_report_verdicts") or self._report_verdicts is None:
            self._report_verdicts = {}
        if hasattr(self, "_load_report_verdicts"):
            try:
                self._load_report_verdicts()
            except Exception:
                pass
        self.after(120, self._deepface_poll_scan_log)


