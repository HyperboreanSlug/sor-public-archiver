"""Flowing toolbar: wrap option-bar controls so nothing is clipped or hidden."""
from __future__ import annotations

from typing import Any, List

import customtkinter as ctk

from gui_app.widgets_flow_measure import measure_widget


class FlowRow:
    """Left-to-right toolbar that wraps; host height matches content only."""

    def __init__(self, parent: Any, *, padx: int = 4, pady: int = 4, pack: bool = True):
        self.padx = int(padx)
        self.pady = int(pady)
        # width/height 1: avoid CTkFrame default 200×200 reserving empty space
        self.host = ctk.CTkFrame(parent, fg_color="transparent", width=1, height=1)
        if pack:
            self.host.pack(fill="x", expand=False, padx=0, pady=0)
        self._items: List[Any] = []
        self._last_w = 0
        self._busy = False
        self._laid_out = False
        try:
            self.host.pack_propagate(True)
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
        # width/height 1 + pack_propagate: size from children, not CTk 200×200 default
        fr = ctk.CTkFrame(self.host, fg_color="transparent", width=1, height=1)
        fr._flow_chip = True  # type: ignore[attr-defined]
        try:
            fr.pack_propagate(True)
        except Exception:
            pass
        return fr

    def reflow(self) -> None:
        w = self._usable_width()
        if w < 80:
            return  # wait for real width — fake narrow layouts create huge stacks
        self._layout(w)

    def _usable_width(self) -> int:
        try:
            w = int(self.host.winfo_width() or 0)
        except Exception:
            w = 0
        if w >= 80:
            return w
        parent = self.host.master
        for _ in range(4):
            if parent is None:
                break
            try:
                pw = int(parent.winfo_width() or 0)
            except Exception:
                pw = 0
            if pw >= 80:
                return max(pw - 16, 80)
            try:
                parent = parent.master
            except Exception:
                break
        return 0

    def _on_map(self, _event=None) -> None:
        for ms in (20, 80, 200, 450):
            try:
                self.host.after(ms, self.reflow)
            except Exception:
                pass

    def _on_configure(self, event) -> None:
        w = int(getattr(event, "width", 0) or 0)
        if w < 80:
            return
        if self._laid_out and abs(w - self._last_w) < 6:
            return
        self._last_w = w
        self._layout(w)

    def _layout(self, width: int) -> None:
        if self._busy or not self._items:
            return
        self._busy = True
        try:
            max_w = max(160, int(width) - 4)
            x, y, row_h = self.padx, self.pady, 0
            for w in self._items:
                req_w, req_h = measure_widget(w, self.padx)
                req_w = min(req_w, max_w)
                req_h = min(max(req_h, 26), 48)
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
            total_h = max(int(y + row_h + self.pady + 4), 30)
            try:
                self.host.pack_propagate(False)
                self.host.configure(height=total_h)
            except Exception:
                pass
            try:
                master = self.host.master
                if master is not None:
                    master.update_idletasks()
            except Exception:
                pass
            self._laid_out = True
        finally:
            self._busy = False


def after_idle_reflow(widget: Any, flow: FlowRow, *, delay_ms: int = 40) -> None:
    """Schedule reflows once the host has a real width."""

    def _go() -> None:
        try:
            flow.reflow()
        except Exception:
            pass

    try:
        base = int(delay_ms)
        for extra in (0, 100, 250, 500):
            widget.after(base + extra, _go)
    except Exception:
        pass
