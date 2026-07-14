"""DfrPhotoPathMixin."""
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


class DfrPhotoPathMixin:
    @staticmethod
    def _dfr_resolve_photo_path(raw: Optional[str]) -> Optional[Path]:
        """Resolve relative mugshot paths against project ROOT and cwd."""
        s = (raw or "").strip()
        if not s:
            return None
        candidates = [
            Path(s),
            Path(s.replace("/", "\\")),
            Path(s.replace("\\", "/")),
            ROOT / s,
            ROOT / s.replace("\\", "/"),
            Path.cwd() / s,
            Path.cwd() / s.replace("\\", "/"),
        ]
        # Also try under data/ if path is just a filename
        name = Path(s).name
        if name and name != s:
            candidates.append(ROOT / "data" / "report_pages" / name)
        for p in candidates:
            try:
                if p.is_file() and p.stat().st_size > 0:
                    return p.resolve()
            except OSError:
                continue
        return None


    def _dfr_set_photo_placeholder(self, text: str = "Select a hit") -> None:
        try:
            self._dfr_photo_tk = None
            cv = getattr(self, "dfr_photo_canvas", None)
            if cv is None:
                return
            cv.delete("all")
            cv.create_text(
                int(cv.cget("width") or 360) // 2,
                int(cv.cget("height") or 300) // 2,
                text=text,
                fill=C["dim"],
                font=("Segoe UI", 11),
                tags=("placeholder",),
                width=int(cv.cget("width") or 360) - 20,
                justify="center",
            )
        except Exception:
            pass


    def _dfr_set_photo_image(self, path: Path) -> tuple[bool, str]:
        """Paint mugshot onto the review Canvas. Returns (ok, message)."""
        try:
            from PIL import Image, ImageTk
        except Exception as e:
            return False, f"PIL missing: {e}"

        cv = getattr(self, "dfr_photo_canvas", None)
        if cv is None:
            return False, "photo canvas missing"

        try:
            with Image.open(path) as raw:
                img = raw.convert("RGB")
            max_w = int(getattr(self, "_DFR_PHOTO_W", 360) or 360)
            max_h = int(getattr(self, "_DFR_PHOTO_H", 300) or 300)
            img.thumbnail((max_w - 8, max_h - 8))
            w, h = img.size
            if w < 140 or h < 140:
                scale = max(140 / max(w, 1), 140 / max(h, 1))
                w = min(max_w - 8, max(1, int(w * scale)))
                h = min(max_h - 8, max(1, int(h * scale)))
                try:
                    resample = Image.Resampling.BILINEAR
                except AttributeError:
                    resample = Image.BILINEAR  # type: ignore[attr-defined]
                img = img.resize((w, h), resample)
            img = img.copy()

            # master must be the live Tk root (CTk window)
            try:
                master = cv.winfo_toplevel()
            except Exception:
                master = cv
            photo = ImageTk.PhotoImage(img, master=master)
            # Strong refs — Tk drops the bitmap if PhotoImage is GC'd
            self._dfr_photo_tk = photo
            if not hasattr(self, "_dfr_image_refs") or self._dfr_image_refs is None:
                self._dfr_image_refs = []
            self._dfr_image_refs.append(photo)

            cv.delete("all")
            cv.create_image(
                max_w // 2,
                max_h // 2,
                image=photo,
                anchor="center",
                tags=("mugshot",),
            )
            # Keep a ref on the canvas too (Tk idiom)
            cv.image = photo  # type: ignore[attr-defined]
            try:
                cv.update_idletasks()
            except Exception:
                pass
            return True, f"{path.name} ({w}x{h})"
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"


    def _dfr_clear_review(self) -> None:
        try:
            self._dfr_set_photo_placeholder("Select a hit")
            self.dfr_name.configure(text="—")
            self._dfr_set_meta_text("")
            self.dfr_verdict_lbl.configure(text="", text_color=C["dim"])
            for b in (
                self.dfr_btn_bad,
                self.dfr_btn_ok,
                self.dfr_btn_skip,
                getattr(self, "dfr_btn_html", None),
                getattr(self, "dfr_btn_url", None),
                getattr(self, "dfr_btn_photo", None),
                getattr(self, "dfr_btn_copy", None),
            ):
                if b is not None:
                    b.configure(state="disabled")
            self._dfr_html_path = None
            self._dfr_source_url = ""
            self._dfr_photo_open_path = None
            if hasattr(self, "dfr_eth_combo"):
                self.dfr_eth_combo.configure(state="disabled")
            if hasattr(self, "dfr_eth_var"):
                self.dfr_eth_var.set("Unknown")
        except Exception:
            pass


    def _dfr_set_meta_text(self, text: str) -> None:
        """Write selectable detail text into the review textbox."""
        self._dfr_meta_text = text or ""
        body = getattr(self, "dfr_meta", None)
        if body is None:
            return
        try:
            body.configure(state="normal")
            body.delete("1.0", "end")
            if text:
                body.insert("1.0", text)
            if hasattr(self, "_detail_hide_unneeded_scrollbars"):
                self.after(
                    30, lambda b=body: self._detail_hide_unneeded_scrollbars(b)
                )
        except Exception:
            pass


    @staticmethod
    def _dfr_resolve_existing_path(raw: Optional[str]) -> Optional[Path]:
        """Resolve relative archived HTML/file paths against ROOT and cwd."""
        s = (raw or "").strip()
        if not s:
            return None
        candidates = [
            Path(s),
            Path(s.replace("/", "\\")),
            Path(s.replace("\\", "/")),
            ROOT / s,
            ROOT / s.replace("\\", "/"),
            Path.cwd() / s,
            Path.cwd() / s.replace("\\", "/"),
        ]
        for p in candidates:
            try:
                if p.is_file() and p.stat().st_size > 0:
                    return p.resolve()
            except OSError:
                continue
        return None


