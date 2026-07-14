"""Flowing toolbar: wrap option-bar controls so nothing is clipped or hidden."""
from __future__ import annotations

from typing import Any, List, Tuple

import customtkinter as ctk


def _cfg_int(widget: Any, key: str) -> int:
    try:
        val = widget.cget(key)
        if val in (None, "", 0, "0"):
            return 0
        return int(float(val))
    except Exception:
        return 0


def _measure_widget(widget: Any, padx: int) -> Tuple[int, int]:
    """Natural size so labels/menus are not clipped by reflow."""
    try:
        widget.update_idletasks()
    except Exception:
        pass
    rw = rh = 0
    try:
        rw = int(widget.winfo_reqwidth() or 0)
        rh = int(widget.winfo_reqheight() or 0)
    except Exception:
        pass
    rw = max(rw, _cfg_int(widget, "width"))
    rh = max(rh, _cfg_int(widget, "height"))
    try:
        kids = list(widget.winfo_children())
    except Exception:
        kids = []
    if kids:
        sum_w = max_h = 0
        for ch in kids:
            try:
                ch.update_idletasks()
            except Exception:
                pass
            cw = max(int(getattr(ch, "winfo_reqwidth", lambda: 0)() or 0), _cfg_int(ch, "width"))
            ch_h = max(int(getattr(ch, "winfo_reqheight", lambda: 0)() or 0), _cfg_int(ch, "height"))
            try:
                txt = str(ch.cget("text") or "")
                if txt:
                    cw = max(cw, 12 + int(len(txt) * 7))
            except Exception:
                pass
            sum_w += max(cw, 16) + 4
            max_h = max(max_h, ch_h, 22)
        rw = max(rw, sum_w + 4)
        rh = max(rh, max_h + 4)
    try:
        values = list(widget.cget("values") or [])
        if values:
            longest = max((str(v) for v in values), key=len, default="")
            rw = max(rw, min(28 + int(len(longest) * 7.2), 320))
    except Exception:
        pass
    return max(rw, 28) + padx, max(rh, 26)


class FlowRow:
    """Left-to-right toolbar that wraps; host height grows so rows stay visible."""

    def __init__(self, parent: Any, *, padx: int = 4, pady: int = 4, pack: bool = True):
        self.padx = int(padx)
        self.pady = int(pady)
        self.host = ctk.CTkFrame(parent, fg_color="transparent")
        if pack:
            self.host.pack(fill="x", expand=False, padx=0, pady=0)
        self._items: List[Any] = []
        self._last_w = 0
        self._busy = False
        self._laid_out = False
        try:
            self.host.pack_propagate(False)
        except Exception:
            pass
        self.host.bind("<Configure>", self._on_configure, add="+")
        try:
            self.host.bind("<Map>", self._on_map, add="+")
        except Exception:
            pass

    def add(self, widget: Any) -> Any:
        self._items.append(widget)
        try:
            widget.place(x=0, y=0)
        except Exception:
            pass
        try:
            self.host.after_idle(self.reflow)
        except Exception:
            pass
        return widget

    def chip(self) -> ctk.CTkFrame:
        fr = ctk.CTkFrame(self.host, fg_color="transparent")
        try:
            fr.pack_propagate(True)
        except Exception:
            pass
        return fr

    def reflow(self) -> None:
        try:
            w = int(self.host.winfo_width() or 0)
        except Exception:
            w = 0
        if w < 40:
            try:
                w = int(self.host.master.winfo_width() or 0) - 8
            except Exception:
                w = 0
        self._layout(max(w, 200))

    def _on_map(self, _event=None) -> None:
        for ms in (30, 120, 400):
            try:
                self.host.after(ms, self.reflow)
            except Exception:
                pass

    def _on_configure(self, event) -> None:
        w = int(getattr(event, "width", 0) or 0)
        if w < 40:
            return
        if self._laid_out and abs(w - self._last_w) < 4:
            return
        self._last_w = w
        self._layout(w)

    def _layout(self, width: int) -> None:
        if self._busy or not self._items:
            return
        self._busy = True
        try:
            max_w = max(120, int(width) - 4)
            x, y, row_h = self.padx, self.pady, 0
            for w in self._items:
                req_w, req_h = _measure_widget(w, self.padx)
                if x > self.padx and (x + req_w) > max_w:
                    x = self.padx
                    y += row_h + self.pady
                    row_h = 0
                try:
                    w.place(x=x, y=y)
                    w.lift()
                except Exception:
                    pass
                x += req_w
                row_h = max(row_h, req_h)
            try:
                self.host.configure(height=max(int(y + row_h + self.pady + 2), 30))
            except Exception:
                pass
            self._laid_out = True
        finally:
            self._busy = False


def after_idle_reflow(widget: Any, flow: FlowRow, *, delay_ms: int = 50) -> None:
    """Schedule reflows until the host has a real width."""

    def _go() -> None:
        try:
            flow.reflow()
        except Exception:
            pass

    try:
        base = int(delay_ms)
        for extra in (0, 150, 400, 900):
            widget.after(base + extra, _go)
    except Exception:
        pass
