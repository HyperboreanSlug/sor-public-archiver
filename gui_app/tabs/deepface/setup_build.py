"""SetupBuild"""
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


class DeepfaceSetupBuildMixin:
    def _build_deepface_setup(self, tab) -> None:
        """Build scrollable status / options / weights UI (lazy, no TF import)."""
        if getattr(self, "_df_setup_built", False):
            return
        self._df_setup_built = True
        # Keep _df_built alias for shell refresh guards
        self._df_built = True
        self._df_tab = tab

        # Scrollable host fills the tab; mouse-wheel works over full area
        root = ctk.CTkScrollableFrame(
            tab,
            fg_color=C["surface"],
            corner_radius=0,
            border_width=0,
        )
        root.pack(fill="both", expand=True, padx=8, pady=8)
        _wire_wide_scroll(tab, root)
        self._df_scroll = root

        # --- Status (top, full width) ---
        status_card = _card(root)
        status_card.pack(fill="x", padx=4, pady=(4, 8))
        _section_label(status_card, "DeepFace status").pack(
            anchor="w", padx=14, pady=(12, 4)
        )
        _muted(
            status_card,
            "Local open-source face race model (no cloud). Scan defaults to FairFace; "
            "DeepFace is legacy fallback. Used by mugshot verify/scan.",
        ).pack(anchor="w", padx=14, pady=(0, 8))

        self.df_status_installed = ctk.CTkLabel(
            status_card, text="Installed: —", font=FONT_SM, text_color=C["text"], anchor="w",
        )
        self.df_status_installed.pack(fill="x", padx=14, pady=2)
        self.df_status_backend = ctk.CTkLabel(
            status_card, text="Backend: —", font=FONT_SM, text_color=C["text"], anchor="w",
        )
        self.df_status_backend.pack(fill="x", padx=14, pady=2)
        self.df_status_backends = ctk.CTkLabel(
            status_card, text="Available: —", font=FONT_SM, text_color=C["muted"], anchor="w",
        )
        self.df_status_backends.pack(fill="x", padx=14, pady=2)
        self.df_status_python = ctk.CTkLabel(
            status_card,
            text=f"Interpreter: {sys.executable}",
            font=FONT_MONO,
            text_color=C["dim"],
            anchor="w",
            wraplength=900,
            justify="left",
        )
        self.df_status_python.pack(fill="x", padx=14, pady=(2, 4))
        self.df_status_weights = ctk.CTkLabel(
            status_card, text="Weights cache: —", font=FONT_SM, text_color=C["muted"], anchor="w",
        )
        self.df_status_weights.pack(fill="x", padx=14, pady=(0, 10))

        btn_row = ctk.CTkFrame(status_card, fg_color="transparent")
        btn_row.pack(fill="x", padx=14, pady=(0, 12))
        ctk.CTkButton(
            btn_row, text="Refresh status", width=120,
            command=self._deepface_refresh_status,
            fg_color=C["elevated"], hover_color=C["border"], text_color=C["text"],
            border_width=1, border_color=C["border"],
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            btn_row, text="Open setup log", width=120,
            command=self._deepface_open_log,
            fg_color=C["elevated"], hover_color=C["border"], text_color=C["text"],
            border_width=1, border_color=C["border"],
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            btn_row, text="Open weights folder", width=140,
            command=self._deepface_open_weights_dir,
            fg_color=C["elevated"], hover_color=C["border"], text_color=C["text"],
            border_width=1, border_color=C["border"],
        ).pack(side="left")

        # --- Options (full width) ---
        opt_card = _card(root)
        opt_card.pack(fill="x", padx=4, pady=(0, 8))
        _section_label(opt_card, "Setup options").pack(
            anchor="w", padx=14, pady=(12, 4)
        )
        _muted(
            opt_card,
            "Controls automatic install when the app starts and when mugshot tools run. "
            "Does not block the VBS launcher.",
        ).pack(anchor="w", padx=14, pady=(0, 8))

        sett = getattr(self, "app_settings", {}) or {}
        self.df_auto_setup = ctk.BooleanVar(
            value=bool(sett.get("deepface_auto_setup", True))
        )
        self.df_auto_warm = ctk.BooleanVar(
            value=bool(sett.get("deepface_auto_warm", True))
        )
        ctk.CTkCheckBox(
            opt_card,
            text="Auto-install DeepFace on app start (background)",
            variable=self.df_auto_setup,
            font=FONT_SM,
            text_color=C["text"],
            fg_color=C["accent"],
            hover_color=C["accent_hover"],
            border_color=C["border"],
            checkmark_color=C["bg"],
            command=self._deepface_save_options,
        ).pack(anchor="w", padx=14, pady=4)
        ctk.CTkCheckBox(
            opt_card,
            text="Warm selected weights after install (download once to ~/.deepface/weights)",
            variable=self.df_auto_warm,
            font=FONT_SM,
            text_color=C["text"],
            fg_color=C["accent"],
            hover_color=C["accent_hover"],
            border_color=C["border"],
            checkmark_color=C["bg"],
            command=self._deepface_save_options,
        ).pack(anchor="w", padx=14, pady=(0, 10))

        act = ctk.CTkFrame(opt_card, fg_color="transparent")
        act.pack(fill="x", padx=14, pady=(0, 8))
        self.df_install_btn = ctk.CTkButton(
            act, text="Install / repair packages", width=160,
            command=lambda: self._deepface_run_setup(warm=True),
            fg_color=C["accent"], hover_color=C["accent_hover"], text_color=C["bg"],
        )
        self.df_install_btn.pack(side="left", padx=(0, 8))
        self.df_warm_btn = ctk.CTkButton(
            act, text="Download selected weights", width=170,
            command=self._deepface_download_selected_weights,
            fg_color=C["elevated"], hover_color=C["border"], text_color=C["text"],
            border_width=1, border_color=C["border"],
        )
        self.df_warm_btn.pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            act, text="Packages only (no weights)", width=160,
            command=lambda: self._deepface_run_setup(warm=False),
            fg_color=C["elevated"], hover_color=C["border"], text_color=C["text"],
            border_width=1, border_color=C["border"],
        ).pack(side="left")

        self.df_job_status = ctk.CTkLabel(
            opt_card, text="", font=FONT_SM, text_color=C["dim"], anchor="w",
        )
        self.df_job_status.pack(fill="x", padx=14, pady=(0, 12))

        # --- Weights / detector selection ---
        w_card = _card(root)
        w_card.pack(fill="x", padx=4, pady=(0, 8))
        _section_label(w_card, "Weights & face detector").pack(
            anchor="w", padx=14, pady=(12, 4)
        )
        from scraper.mugshot_ethnicity.weights_catalog import (
            DETECTOR_OPTIONS,
            DOWNLOAD_GUIDANCE,
            WEIGHT_MODELS,
            detector_dropdown_label,
            detector_local_status,
            explain_detector,
            explain_weight,
            weight_local_status,
        )

        guide = ctk.CTkLabel(
            w_card,
            text=DOWNLOAD_GUIDANCE,
            font=FONT_SM,
            text_color=C["muted"],
            anchor="w",
            justify="left",
            wraplength=920,
        )
        guide.pack(fill="x", padx=14, pady=(0, 10))

        det_default = str(sett.get("deepface_detector") or "retinaface")
        # Dropdown shows name + VRAM + local download status
        det_labels = [detector_dropdown_label(d) for d in DETECTOR_OPTIONS]
        det_id_by_label = {
            detector_dropdown_label(d): d["id"] for d in DETECTOR_OPTIONS
        }
        label_by_det_id = {
            d["id"]: detector_dropdown_label(d) for d in DETECTOR_OPTIONS
        }
        self._df_det_id_by_label = det_id_by_label
        self._df_label_by_det_id = label_by_det_id
        self._df_detector_options = DETECTOR_OPTIONS

        det_row = ctk.CTkFrame(w_card, fg_color="transparent")
        det_row.pack(fill="x", padx=14, pady=(0, 6))
        ctk.CTkLabel(
            det_row,
            text="Face detector (one only · VRAM · download status)",
            font=FONT_SM,
            text_color=C["muted"],
        ).pack(side="left", padx=(0, 8))
        self.df_detector_var = ctk.StringVar(
            value=label_by_det_id.get(det_default, det_labels[0])
        )
        self.df_detector_combo = ctk.CTkComboBox(
            det_row,
            variable=self.df_detector_var,
            values=det_labels,
            width=480,
            fg_color=C["bg"],
            border_color=C["border"],
            button_color=C["elevated"],
            text_color=C["text"],
            dropdown_fg_color=C["panel"],
            command=self._deepface_on_detector_change,
        )
        self.df_detector_combo.pack(side="left")

        det_st = detector_local_status(det_default)
        self.df_detector_status = ctk.CTkLabel(
            det_row,
            text=det_st.get("label") or "",
            font=FONT_SM,
            text_color=C["success"] if det_st.get("downloaded") else C["danger"],
            anchor="w",
        )
        self.df_detector_status.pack(side="left", padx=(12, 0))

        self.df_detector_help = ctk.CTkLabel(
            w_card,
            text=explain_detector(det_default),
            font=FONT_SM,
            text_color=C["dim"],
            anchor="w",
            justify="left",
            wraplength=920,
        )
        self.df_detector_help.pack(fill="x", padx=14, pady=(0, 10))

        ctk.CTkLabel(
            w_card,
            text=(
                "Model weights (check boxes, then Download selected weights). "
                "Green “Downloaded” = file present under ~/.deepface/weights. "
                "Race alone is enough for ethnicity tools."
            ),
            font=FONT_SM,
            text_color=C["muted"],
            anchor="w",
            wraplength=920,
            justify="left",
        ).pack(fill="x", padx=14, pady=(4, 4))

        saved_models = {
            p.strip()
            for p in str(sett.get("deepface_weight_models") or "Race").split(",")
            if p.strip()
        }
        if "Race" not in saved_models:
            saved_models.add("Race")

        self._df_weight_vars: Dict[str, ctk.BooleanVar] = {}
        self._df_weight_status_labels: Dict[str, ctk.CTkLabel] = {}
        self._df_weight_summary_labels: Dict[str, ctk.CTkLabel] = {}
        weights_frame = ctk.CTkFrame(w_card, fg_color="transparent")
        weights_frame.pack(fill="x", padx=10, pady=(0, 6))

        # Two columns of checkboxes
        left_col = ctk.CTkFrame(weights_frame, fg_color="transparent")
        right_col = ctk.CTkFrame(weights_frame, fg_color="transparent")
        left_col.pack(side="left", fill="both", expand=True, padx=(4, 8))
        right_col.pack(side="left", fill="both", expand=True, padx=(8, 4))

        for i, m in enumerate(WEIGHT_MODELS):
            parent = left_col if i % 2 == 0 else right_col
            mid = m["id"]
            var = ctk.BooleanVar(value=(mid in saved_models) or bool(m.get("required")))
            self._df_weight_vars[mid] = var
            row = ctk.CTkFrame(parent, fg_color=C["elevated"], corner_radius=8)
            row.pack(fill="x", pady=3)
            vram = m.get("vram_short") or m.get("vram") or ""
            size = m.get("size") or ""
            st = weight_local_status(mid)
            st_label = st.get("label") or "Not downloaded"
            st_ok = bool(st.get("downloaded"))

            head = ctk.CTkFrame(row, fg_color="transparent")
            head.pack(fill="x", padx=10, pady=(8, 2))
            cb = ctk.CTkCheckBox(
                head,
                text=f"{m['label']}  ·  {size}" + (f"  ·  {vram}" if vram else ""),
                variable=var,
                font=FONT_SM,
                text_color=C["text"],
                fg_color=C["accent"],
                hover_color=C["accent_hover"],
                border_color=C["border"],
                checkmark_color=C["bg"],
                command=lambda mid=mid: self._deepface_on_weight_toggle(mid),
            )
            cb.pack(side="left", anchor="w")
            if m.get("required"):
                try:
                    cb.configure(state="disabled")
                except Exception:
                    pass
            badge = ctk.CTkLabel(
                head,
                text=("✓ " + st_label) if st_ok else st_label,
                font=FONT_SM,
                text_color=C["success"] if st_ok else C["danger"],
                anchor="e",
            )
            badge.pack(side="right", padx=(8, 0))
            self._df_weight_status_labels[mid] = badge

            cat = m.get("category") or ""
            cat_note = {
                "attribute": "Attribute model",
                "recognition": "Identity model (not race)",
            }.get(cat, cat)
            sum_lbl = ctk.CTkLabel(
                row,
                text=f"{m['summary']}\n{cat_note} · disk {size} · load {vram}",
                font=FONT_SM,
                text_color=C["dim"],
                anchor="w",
                wraplength=420,
                justify="left",
            )
            sum_lbl.pack(fill="x", padx=14, pady=(0, 8))
            self._df_weight_summary_labels[mid] = sum_lbl

        self.df_weight_help = ctk.CTkLabel(
            w_card,
            text=explain_weight("Race"),
            font=FONT_SM,
            text_color=C["muted"],
            anchor="nw",
            justify="left",
            wraplength=920,
        )
        self.df_weight_help.pack(fill="x", padx=14, pady=(4, 12))

        # --- Activity log (scrolls with page; tall enough to read) ---
        log_card = _card(root)
        log_card.pack(fill="x", padx=4, pady=(0, 8))
        _section_label(log_card, "Setup activity").pack(
            anchor="w", padx=14, pady=(12, 4)
        )
        self.df_log = ctk.CTkTextbox(
            log_card,
            height=220,
            font=FONT_MONO,
            fg_color=C["bg"],
            text_color=C["muted"],
            border_color=C["border"],
            border_width=1,
            corner_radius=8,
        )
        self.df_log.pack(fill="x", expand=False, padx=12, pady=(0, 12))
        self.df_log.configure(state="disabled")
        self._df_log_queue: queue.Queue = queue.Queue()
        self._df_setup_running = False

        self.after(50, self._deepface_refresh_status)
        self.after(100, self._deepface_poll_log)
        # Re-bind wheel after children exist (wheel is delivered to widget under cursor)
        self.after(150, lambda: self._deepface_bind_scroll_children(tab, root))


