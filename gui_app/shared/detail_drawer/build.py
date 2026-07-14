"""DetailBuildMixin."""
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


class DetailBuildMixin:
    def _make_detail_drawer(self, parent) -> ctk.CTkFrame:
        """Right-side detail card used by Search and (optionally) other tables."""
        card = _card(parent)
        _section_label(card, "Detail").pack(anchor="w", padx=12, pady=(12, 4))
        photo = ctk.CTkLabel(
            card,
            text="Select a row",
            font=FONT_SM,
            text_color=C["dim"],
            width=180,
            height=180,
            fg_color=C["tree_bg"],
            corner_radius=8,
        )
        photo.pack(padx=12, pady=(0, 6))
        # Stable host: empty label (no scrollbar) OR textbox when a row is selected
        content = ctk.CTkFrame(card, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        empty = ctk.CTkLabel(
            content,
            text="Select a result to view photo, crime, race, and links.",
            font=FONT_SM,
            text_color=C["dim"],
            anchor="nw",
            justify="left",
            wraplength=220,
        )
        empty.pack(fill="x", anchor="nw")
        body = ctk.CTkTextbox(
            content,
            height=200,
            font=FONT_SM,
            fg_color=C["bg"],
            text_color=C["text"],
            border_color=C["border"],
            border_width=1,
            corner_radius=8,
            activate_scrollbars=True,
            wrap="word",
        )
        # Not packed until a row is selected (avoids empty scrollbar chrome)
        btns = ctk.CTkFrame(card, fg_color="transparent")
        btns.pack(fill="x", padx=12, pady=(0, 12))
        open_html = ctk.CTkButton(
            btns, text="Open HTML", width=90, state="disabled",
            fg_color=C["elevated"], hover_color=C["border"], text_color=C["text"],
            border_width=1, border_color=C["border"],
        )
        open_html.pack(side="left", padx=(0, 6))
        open_url = ctk.CTkButton(
            btns, text="Open URL", width=90, state="disabled",
            fg_color=C["elevated"], hover_color=C["border"], text_color=C["text"],
            border_width=1, border_color=C["border"],
        )
        open_url.pack(side="left", padx=(0, 6))
        open_photo = ctk.CTkButton(
            btns, text="Open photo", width=90, state="disabled",
            fg_color=C["elevated"], hover_color=C["border"], text_color=C["text"],
            border_width=1, border_color=C["border"],
        )
        open_photo.pack(side="left", padx=(0, 6))
        copy_btn = ctk.CTkButton(
            btns, text="Copy text", width=90, state="disabled",
            fg_color=C["elevated"], hover_color=C["border"], text_color=C["text"],
            border_width=1, border_color=C["border"],
        )
        copy_btn.pack(side="left", padx=(0, 6))
        export_btn = ctk.CTkButton(
            btns, text="Export card", width=100, state="disabled",
            fg_color=C["accent"], hover_color=C["accent_hover"], text_color=C["bg"],
            command=lambda: self._detail_export_card(card),
        )
        export_btn.pack(side="left")
        self._make_textbox_selectable(body)
        card._detail_photo = photo  # type: ignore[attr-defined]
        card._detail_content = content  # type: ignore[attr-defined]
        card._detail_empty = empty  # type: ignore[attr-defined]
        card._detail_body = body  # type: ignore[attr-defined]
        card._detail_open_html = open_html  # type: ignore[attr-defined]
        card._detail_open_url = open_url  # type: ignore[attr-defined]
        card._detail_open_photo = open_photo  # type: ignore[attr-defined]
        card._detail_copy = copy_btn  # type: ignore[attr-defined]
        card._detail_export = export_btn  # type: ignore[attr-defined]
        card._detail_image_ref = None  # type: ignore[attr-defined]
        card._detail_record = None  # type: ignore[attr-defined]
        card._detail_body_packed = False  # type: ignore[attr-defined]
        return card


    def _detail_export_card(self, drawer: ctk.CTkFrame) -> None:
        """Render a shareable mugshot card to the Desktop (mapa-style)."""
        rec = getattr(drawer, "_detail_record", None)
        if not isinstance(rec, dict) or not rec:
            return
        btn = getattr(drawer, "_detail_export", None)
        if btn is not None:
            try:
                btn.configure(state="disabled", text="…")
            except Exception:
                pass
        record = dict(rec)

        def work() -> None:
            err = None
            path = None
            try:
                from gui_app.shared.export_card import export_record_card_to_desktop

                path = export_record_card_to_desktop(record)
            except Exception as exc:
                err = exc

            def done() -> None:
                if btn is not None:
                    try:
                        btn.configure(state="normal", text="Export card")
                    except Exception:
                        pass
                if err is not None:
                    try:
                        messagebox.showerror("Export card", str(err))
                    except Exception:
                        pass
                    return
                try:
                    if hasattr(self, "stats_label") and path is not None:
                        self.stats_label.configure(text=f"Card → {path.name}")
                except Exception:
                    pass

            try:
                self.after(0, done)
            except Exception:
                pass

        threading.Thread(target=work, name="export-card", daemon=True).start()


    @staticmethod
    def _detail_set_body_visible(drawer: ctk.CTkFrame, show_body: bool) -> None:
        """Show textbox (with content) or empty label (no scrollbar)."""
        empty = getattr(drawer, "_detail_empty", None)
        body = getattr(drawer, "_detail_body", None)
        if empty is None or body is None:
            return
        packed = bool(getattr(drawer, "_detail_body_packed", False))
        if show_body and not packed:
            try:
                empty.pack_forget()
            except Exception:
                pass
            body.pack(fill="both", expand=True)
            drawer._detail_body_packed = True  # type: ignore[attr-defined]
        elif not show_body and packed:
            try:
                body.pack_forget()
            except Exception:
                pass
            empty.pack(fill="x", anchor="nw")
            drawer._detail_body_packed = False  # type: ignore[attr-defined]
        elif not show_body and not packed:
            try:
                empty.pack(fill="x", anchor="nw")
            except Exception:
                pass


    @staticmethod
    def _detail_hide_unneeded_scrollbars(body: ctk.CTkTextbox) -> None:
        """Force-hide CTkTextbox scrollbars when content fully fits."""
        try:
            body.update_idletasks()
            tb = getattr(body, "_textbox", None)
            if tb is None:
                return
            y0, y1 = tb.yview()
            x0, x1 = tb.xview()
            hide_y = (y1 - y0) >= 0.999 or (y0, y1) == (0.0, 1.0)
            hide_x = (x1 - x0) >= 0.999 or (x0, x1) == (0.0, 1.0)
            body._hide_y_scrollbar = hide_y  # type: ignore[attr-defined]
            body._hide_x_scrollbar = hide_x  # type: ignore[attr-defined]
            body._create_grid_for_text_and_scrollbars(  # type: ignore[attr-defined]
                re_grid_x_scrollbar=True, re_grid_y_scrollbar=True
            )
        except Exception:
            pass


