"""Treeview helpers, scroll isolation, and row↔record mapping."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import tkinter as tk
from tkinter import ttk

import customtkinter as ctk

from gui_app.theme import C, FONT_SECTION, FONT_SM


def card(parent, **kwargs) -> ctk.CTkFrame:
    return ctk.CTkFrame(
        parent, fg_color=C["panel"], border_color=C["border"],
        border_width=1, corner_radius=12, **kwargs,
    )


def section_label(parent, text: str) -> ctk.CTkLabel:
    return ctk.CTkLabel(
        parent, text=text, font=FONT_SECTION, text_color=C["text"], anchor="w",
    )


def muted(parent, text: str) -> ctk.CTkLabel:
    return ctk.CTkLabel(
        parent, text=text, font=FONT_SM, text_color=C["muted"],
        anchor="w", wraplength=900, justify="left",
    )


def tree_frame(parent) -> tuple[ctk.CTkFrame, ttk.Treeview]:
    wrap = ctk.CTkFrame(
        parent, fg_color=C["tree_bg"], corner_radius=10, border_width=1, border_color=C["border"]
    )
    tree = ttk.Treeview(wrap, style="Dark.Treeview", show="headings")
    vsb = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview, style="Dark.Vertical.TScrollbar")
    hsb = ttk.Scrollbar(wrap, orient="horizontal", command=tree.xview, style="Dark.Horizontal.TScrollbar")
    tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
    vsb.pack(side="right", fill="y", padx=(0, 4), pady=4)
    hsb.pack(side="bottom", fill="x", padx=4, pady=(0, 4))
    tree.pack(side="left", fill="both", expand=True, padx=4, pady=4)
    wrap._tree_vsb = vsb  # type: ignore[attr-defined]
    wrap._tree_hsb = hsb  # type: ignore[attr-defined]
    return wrap, tree


def vpaned(parent) -> tk.PanedWindow:
    return tk.PanedWindow(
        parent, orient=tk.VERTICAL, sashwidth=6, sashrelief=tk.FLAT,
        bg=C["border"], bd=0, opaqueresize=False,
    )


def hpaned(parent) -> tk.PanedWindow:
    return tk.PanedWindow(
        parent, orient=tk.HORIZONTAL, sashwidth=6, sashrelief=tk.FLAT,
        bg=C["border"], bd=0, opaqueresize=False,
    )


def stretch_columns(tree: ttk.Treeview, columns: List[str], widths: Optional[List[int]] = None) -> None:
    for i, c in enumerate(columns):
        w = widths[i] if widths and i < len(widths) else 120
        tree.column(c, width=w, minwidth=40, stretch=True)


def format_state_display(record: Optional[Dict[str, Any]]) -> str:
    if not record:
        return "—"
    try:
        from scraper.nsopw_client import normalize_jurisdiction_code

        code = normalize_jurisdiction_code(record.get("state"), record.get("source_state"))
        if code:
            return code
    except Exception:
        pass
    for key in ("state", "source_state"):
        raw = (record.get(key) or "").strip().upper()
        if raw and raw not in ("YY", "XX", "ZZ", "NA", "N/A", "UN", "UK", "US"):
            return raw
    return "—"


def format_race_display(race: Optional[str]) -> str:
    raw = (race or "").strip()
    if not raw or raw == "—":
        return "—"
    try:
        from scraper.searcher import format_race_label
        return format_race_label(raw)
    except Exception:
        return raw.title()


def wire_wide_scroll(tab, scroll_frame) -> None:
    try:
        canvas = scroll_frame._parent_canvas  # type: ignore[attr-defined]
        parent_frame = scroll_frame._parent_frame  # type: ignore[attr-defined]
        scrollbar = scroll_frame._scrollbar  # type: ignore[attr-defined]
    except Exception:
        return

    def _wheel(event):
        delta = getattr(event, "delta", 0) or 0
        if delta:
            steps = int(-1 * (delta / 120)) if abs(delta) >= 120 else int(-1 * delta)
            if steps == 0:
                steps = -1 if delta > 0 else 1
            canvas.yview_scroll(steps, "units")
        else:
            num = getattr(event, "num", 0)
            if num == 4:
                canvas.yview_scroll(-3, "units")
            elif num == 5:
                canvas.yview_scroll(3, "units")
        return "break"

    for w in (tab, parent_frame, canvas, scroll_frame):
        try:
            w.bind("<MouseWheel>", _wheel, add="+")
            w.bind("<Button-4>", _wheel, add="+")
            w.bind("<Button-5>", _wheel, add="+")
        except Exception:
            pass
    try:
        canvas.grid_configure(padx=(0, 0), pady=0)
        scrollbar.grid_configure(padx=(2, 0), pady=0, sticky="ns")
        parent_frame.grid_columnconfigure(0, weight=1)
        parent_frame.grid_columnconfigure(1, weight=0, minsize=14)
    except Exception:
        pass


def bind_tree_scroll_isolation(tree: ttk.Treeview, wrap: ctk.CTkFrame) -> None:
    def _on_wheel(event):
        delta = getattr(event, "delta", 0) or 0
        if delta:
            steps = int(-1 * (delta / 120)) if abs(delta) >= 120 else int(-1 * delta)
            if steps == 0:
                steps = -1 if delta > 0 else 1
            tree.yview_scroll(steps, "units")
        else:
            num = getattr(event, "num", 0)
            if num == 4:
                tree.yview_scroll(-3, "units")
            elif num == 5:
                tree.yview_scroll(3, "units")
        return "break"

    targets = [tree, wrap]
    vsb = getattr(wrap, "_tree_vsb", None)
    hsb = getattr(wrap, "_tree_hsb", None)
    if vsb is not None:
        targets.append(vsb)
    if hsb is not None:
        targets.append(hsb)
    for w in targets:
        w.bind("<MouseWheel>", _on_wheel)
        w.bind("<Button-4>", _on_wheel)
        w.bind("<Button-5>", _on_wheel)


def misclass_race_bucket(recorded_race: Optional[str]) -> str:
    try:
        from scraper.searcher import _canonical_race_key

        key = _canonical_race_key(recorded_race or "")
    except Exception:
        key = (recorded_race or "").strip().upper()
    if key == "WHITE":
        return "White"
    if key == "BLACK":
        return "Black"
    return "Other"


def tree_cell_sort_key(val: Any):
    s = str(val if val is not None else "").strip()
    if not s or s in ("—", "–", "-", "N/A", "n/a", "None"):
        return (2, 0.0, "")
    cleaned = s.replace(",", "").replace("\u00a0", " ").strip()
    if cleaned.endswith("%"):
        cleaned = cleaned[:-1].strip()
    try:
        return (0, float(cleaned), "")
    except ValueError:
        pass
    m = re.match(r"^([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)", cleaned)
    if m:
        try:
            return (0, float(m.group(1)), s.casefold())
        except ValueError:
            pass
    return (1, 0.0, s.casefold())
