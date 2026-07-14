"""DfrBuildMixin."""
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


class DfrBuildMixin:
    def _build_deepface_reports(self, tab) -> None:
        tab.configure(fg_color=C["surface"])
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        self._dfr_hits: List[Any] = []
        self._dfr_hits_by_iid: Dict[str, Any] = {}
        self._dfr_selected_iid: Optional[str] = None
        self._dfr_image_refs: list = []

        # Ensure shared verdict store
        if not hasattr(self, "_report_verdicts") or self._report_verdicts is None:
            self._report_verdicts = {}
        if hasattr(self, "_load_report_verdicts"):
            try:
                self._load_report_verdicts()
            except Exception:
                pass

        # ---- Toolbar ----
        top = ctk.CTkFrame(tab, fg_color=C["surface"])
        top.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))

        bar = ctk.CTkFrame(top, fg_color="transparent")
        bar.pack(fill="x", padx=4, pady=(0, 4))

        ctk.CTkButton(
            bar, text="Refresh hits", width=110,
            command=self._dfr_refresh,
            fg_color=C["accent"], hover_color=C["accent_hover"], text_color=C["bg"],
        ).pack(side="left", padx=(0, 8))

        ctk.CTkLabel(bar, text="Show", font=FONT_SM, text_color=C["muted"]).pack(
            side="left", padx=(4, 4)
        )
        self.dfr_verdict_filter = ctk.StringVar(value="All")
        ctk.CTkComboBox(
            bar, variable=self.dfr_verdict_filter, width=150,
            values=["Unconfirmed", "Confirmed incorrect", "Confirmed correct", "Skip", "All"],
            fg_color=C["bg"], border_color=C["border"], button_color=C["elevated"],
            text_color=C["text"], dropdown_fg_color=C["panel"],
            command=lambda _v: self._dfr_apply_filters(),
        ).pack(side="left", padx=(0, 8))

        ctk.CTkLabel(bar, text="Face", font=FONT_SM, text_color=C["muted"]).pack(
            side="left", padx=(4, 4)
        )
        self.dfr_face_filter = ctk.StringVar(value="All")
        ctk.CTkComboBox(
            bar, variable=self.dfr_face_filter, width=120,
            values=["All", "black", "indian", "asian", "hispanic", "middle_eastern", "white"],
            fg_color=C["bg"], border_color=C["border"], button_color=C["elevated"],
            text_color=C["text"], dropdown_fg_color=C["panel"],
            command=lambda _v: self._dfr_apply_filters(),
        ).pack(side="left", padx=(0, 8))

        ctk.CTkLabel(bar, text="State", font=FONT_SM, text_color=C["muted"]).pack(
            side="left", padx=(4, 4)
        )
        self.dfr_state = ctk.CTkEntry(
            bar, width=56, placeholder_text="All",
            fg_color=C["bg"], border_color=C["border"], text_color=C["text"],
        )
        self.dfr_state.pack(side="left", padx=(0, 8))
        self.dfr_state.bind("<Return>", lambda _e: self._dfr_apply_filters())

        ctk.CTkLabel(bar, text="Min conf", font=FONT_SM, text_color=C["muted"]).pack(
            side="left", padx=(4, 4)
        )
        self.dfr_min_conf = ctk.CTkEntry(
            bar, width=56, placeholder_text="0.85",
            fg_color=C["bg"], border_color=C["border"], text_color=C["text"],
        )
        # Match DeepFace → Scan default (and last saved scan settings)
        _min_default = "0.85"
        try:
            sett = getattr(self, "app_settings", None) or {}
            if not sett:
                from scraper.app_settings import load_settings

                sett = load_settings()
            _min_default = str(sett.get("deepface_scan_min_conf") or "0.85")
        except Exception:
            pass
        self.dfr_min_conf.insert(0, _min_default)
        self.dfr_min_conf.pack(side="left", padx=(0, 8))
        self.dfr_min_conf.bind("<Return>", lambda _e: self._dfr_apply_filters())

        ctk.CTkButton(
            bar, text="Apply", width=70,
            command=self._dfr_apply_filters,
            fg_color=C["elevated"], hover_color=C["border"], text_color=C["text"],
            border_width=1, border_color=C["border"],
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            bar, text="Next unreviewed", width=120,
            command=self._dfr_next_unreviewed,
            fg_color=C["elevated"], hover_color=C["border"], text_color=C["text"],
            border_width=1, border_color=C["border"],
        ).pack(side="right", padx=(6, 0))
        ctk.CTkButton(
            bar, text="View as grid", width=110,
            command=self._dfr_view_as_grid,
            fg_color=C["elevated"], hover_color=C["border"], text_color=C["text"],
            border_width=1, border_color=C["border"],
        ).pack(side="right")

        # Metrics
        metrics = ctk.CTkFrame(top, fg_color="transparent")
        metrics.pack(fill="x", padx=4, pady=(0, 4))
        self.dfr_m_total = ctk.CTkLabel(
            metrics, text="Hits: —", font=FONT_SM, text_color=C["text"]
        )
        self.dfr_m_total.pack(side="left", padx=(0, 12))
        self.dfr_m_open = ctk.CTkLabel(
            metrics, text="Open: —", font=FONT_SM, text_color=C["muted"]
        )
        self.dfr_m_open.pack(side="left", padx=(0, 12))
        self.dfr_m_bad = ctk.CTkLabel(
            metrics, text="Incorrect: —", font=FONT_SM, text_color=C["danger"]
        )
        self.dfr_m_bad.pack(side="left", padx=(0, 12))
        self.dfr_m_ok = ctk.CTkLabel(
            metrics, text="Correct: —", font=FONT_SM, text_color=C["success"]
        )
        self.dfr_m_ok.pack(side="left", padx=(0, 12))
        self.dfr_status = ctk.CTkLabel(
            metrics, text="Stored DeepFace scan hits (from DeepFace → Scan).",
            font=FONT_SM, text_color=C["dim"],
        )
        self.dfr_status.pack(side="left", fill="x", expand=True)

        # ---- Body: list | review ----
        body = ctk.CTkFrame(tab, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        list_card = _card(body)
        list_card.grid(row=0, column=0, sticky="nsew", padx=(2, 4), pady=2)
        _section_label(list_card, "DeepFace hits").pack(
            anchor="w", padx=14, pady=(12, 4)
        )
        wrap, tree = _tree_frame(list_card)
        wrap.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        cols = ("name", "state", "listed", "face", "conf", "severity", "verdict", "id")
        tree["columns"] = cols
        tree["show"] = "headings"
        widths = [150, 44, 80, 80, 50, 60, 80, 50]
        labels = {
            "name": "NAME",
            "state": "ST",
            "listed": "LISTED",
            "face": "FACE",
            "conf": "CONF",
            "severity": "SEV",
            "verdict": "VERDICT",
            "id": "ID",
        }
        for c, w in zip(cols, widths):
            tree.heading(c, text=labels.get(c, c.upper()))
            tree.column(c, width=w, minwidth=36, stretch=(c == "name"))
        _stretch_columns(tree, cols, widths)
        self.dfr_tree = tree
        tree.bind("<<TreeviewSelect>>", self._dfr_on_select)
        _bind_tree_scroll_isolation(tree, wrap)

        # Review pane
        rev = _card(body)
        rev.grid(row=0, column=1, sticky="nsew", padx=(4, 2), pady=2)
        _section_label(rev, "Review").pack(anchor="w", padx=14, pady=(12, 4))
        _muted(
            rev,
            "Confirm incorrect = real face/race mismatch. "
            "Confirm correct = not a misclass. Verdicts sync with Browse → Reports. "
            "Hit list uses the same recorded-race / face-label rules as DeepFace → Scan. "
            "Open HTML / URL for the source page · View as grid opens Reports.",
        ).pack(anchor="w", padx=14, pady=(0, 6))

        rev_body = ctk.CTkFrame(rev, fg_color="transparent")
        rev_body.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        rev_body.grid_columnconfigure(0, weight=1)

        # Photo host: fixed-size tk.Canvas (most reliable image surface under CTk)
        self._DFR_PHOTO_W = 360
        self._DFR_PHOTO_H = 300
        photo_wrap = ctk.CTkFrame(
            rev_body,
            fg_color=C["tree_bg"],
            corner_radius=10,
            width=self._DFR_PHOTO_W + 16,
            height=self._DFR_PHOTO_H + 16,
            border_width=1,
            border_color=C["border"],
        )
        photo_wrap.pack(fill="x", pady=(0, 8))
        photo_wrap.pack_propagate(False)
        self.dfr_photo_wrap = photo_wrap
        # Canvas is a real Tk drawing surface — CTkLabel/CTkImage stays blank here
        self.dfr_photo_canvas = tk.Canvas(
            photo_wrap,
            width=self._DFR_PHOTO_W,
            height=self._DFR_PHOTO_H,
            bg=C["tree_bg"],
            highlightthickness=0,
            bd=0,
        )
        self.dfr_photo_canvas.place(relx=0.5, rely=0.5, anchor="center")
        self.dfr_photo_canvas.create_text(
            self._DFR_PHOTO_W // 2,
            self._DFR_PHOTO_H // 2,
            text="Select a hit",
            fill=C["dim"],
            font=("Segoe UI", 11),
            tags=("placeholder",),
        )
        self._dfr_photo_tk = None
        # Keep alias so older clear code doesn't break
        self.dfr_photo = self.dfr_photo_canvas

        self.dfr_name = ctk.CTkLabel(
            rev_body, text="—", font=FONT_TITLE, text_color=C["text"], anchor="w",
        )
        self.dfr_name.pack(fill="x")
        # Selectable / copyable detail text (Ctrl+C, right-click, or Copy button)
        self.dfr_meta = ctk.CTkTextbox(
            rev_body,
            height=140,
            font=FONT_SM,
            fg_color=C["bg"],
            text_color=C["text"],
            border_color=C["border"],
            border_width=1,
            corner_radius=8,
            activate_scrollbars=True,
            wrap="word",
        )
        self.dfr_meta.pack(fill="x", pady=(4, 6))
        if hasattr(self, "_make_textbox_selectable"):
            self._make_textbox_selectable(self.dfr_meta)
        self._dfr_meta_text = ""
        self._dfr_html_path: Optional[Path] = None
        self._dfr_source_url = ""
        self._dfr_photo_open_path: Optional[Path] = None

        self.dfr_verdict_lbl = ctk.CTkLabel(
            rev_body, text="", font=FONT_BOLD, text_color=C["dim"], anchor="w",
        )
        self.dfr_verdict_lbl.pack(fill="x", pady=(0, 8))

        # Open archived HTML / live registry / mugshot + copy detail blob
        link_row = ctk.CTkFrame(rev, fg_color="transparent")
        link_row.pack(fill="x", padx=12, pady=(0, 6))
        self.dfr_btn_html = ctk.CTkButton(
            link_row, text="Open HTML", width=90, state="disabled",
            command=self._dfr_open_html,
            fg_color=C["elevated"], hover_color=C["border"], text_color=C["text"],
            border_width=1, border_color=C["border"],
        )
        self.dfr_btn_html.pack(side="left", padx=(0, 6))
        self.dfr_btn_url = ctk.CTkButton(
            link_row, text="Open URL", width=90, state="disabled",
            command=self._dfr_open_url,
            fg_color=C["elevated"], hover_color=C["border"], text_color=C["text"],
            border_width=1, border_color=C["border"],
        )
        self.dfr_btn_url.pack(side="left", padx=(0, 6))
        self.dfr_btn_photo = ctk.CTkButton(
            link_row, text="Open photo", width=90, state="disabled",
            command=self._dfr_open_photo,
            fg_color=C["elevated"], hover_color=C["border"], text_color=C["text"],
            border_width=1, border_color=C["border"],
        )
        self.dfr_btn_photo.pack(side="left", padx=(0, 6))
        self.dfr_btn_copy = ctk.CTkButton(
            link_row, text="Copy", width=70, state="disabled",
            command=self._dfr_copy_detail,
            fg_color=C["elevated"], hover_color=C["border"], text_color=C["text"],
            border_width=1, border_color=C["border"],
        )
        self.dfr_btn_copy.pack(side="left")

        btns = ctk.CTkFrame(rev, fg_color="transparent")
        btns.pack(fill="x", padx=12, pady=(0, 12))
        self.dfr_btn_bad = ctk.CTkButton(
            btns, text="Confirmed incorrect", width=150,
            command=lambda: self._dfr_set_verdict("confirmed"),
            fg_color="#5c3030", hover_color="#7a4040", text_color=C["text"],
            state="disabled",
        )
        self.dfr_btn_bad.pack(side="left", padx=(0, 6))
        self.dfr_btn_ok = ctk.CTkButton(
            btns, text="Confirmed correct", width=140,
            command=lambda: self._dfr_set_verdict("correct"),
            fg_color="#2a4a38", hover_color="#356348", text_color=C["text"],
            state="disabled",
        )
        self.dfr_btn_ok.pack(side="left", padx=(0, 6))
        self.dfr_btn_skip = ctk.CTkButton(
            btns, text="Skip", width=70,
            command=lambda: self._dfr_set_verdict("skip"),
            fg_color=C["elevated"], hover_color=C["border"], text_color=C["muted"],
            border_width=1, border_color=C["border"],
            state="disabled",
        )
        self.dfr_btn_skip.pack(side="left")

        # Ethnicity override (persists to offender.likely_ethnicity + Reports Actual)
        eth_row = ctk.CTkFrame(rev, fg_color="transparent")
        eth_row.pack(fill="x", padx=12, pady=(0, 12))
        ctk.CTkLabel(
            eth_row, text="Ethnicity", font=FONT_SM, text_color=C["muted"],
        ).pack(side="left", padx=(0, 6))
        self.dfr_eth_var = ctk.StringVar(value="Unknown")
        eth_opts = list(
            getattr(self, "_ETHNICITY_OPTIONS", None) or self._DFR_ETHNICITY_OPTIONS
        )
        self.dfr_eth_combo = ctk.CTkComboBox(
            eth_row,
            variable=self.dfr_eth_var,
            values=eth_opts,
            width=200,
            height=30,
            fg_color=C["bg"],
            border_color=C["border"],
            button_color=C["elevated"],
            text_color=C["text"],
            dropdown_fg_color=C["panel"],
            state="disabled",
            font=FONT_SM,
            command=self._dfr_on_ethnicity_change,
        )
        self.dfr_eth_combo.pack(side="left")
        ctk.CTkLabel(
            eth_row,
            text="Saved on the person · used by Reports Actual filter",
            font=FONT_SM,
            text_color=C["dim"],
        ).pack(side="left", padx=(10, 0))

        self.after(80, self._dfr_refresh)


