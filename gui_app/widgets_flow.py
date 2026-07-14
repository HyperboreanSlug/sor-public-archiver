"""Flowing toolbar: wrap top controls so they stay visible when narrow."""
from __future__ import annotations

from typing import Any, List, Optional

import customtkinter as ctk


class FlowRow:
    """Place child widgets left-to-right, wrapping to new lines on resize."""

    def __init__(
        self,
        parent: Any,
        *,
        padx: int = 4,
        pady: int = 4,
        pack: bool = True,
    ):
        self.padx = padx
        self.pady = pady
        self.host = ctk.CTkFrame(parent, fg_color="transparent")
        if pack:
            self.host.pack(fill="x", padx=0, pady=0)
        self._items: List[Any] = []
        self.host.bind("<Configure>", self._on_configure, add="+")
        self._last_w = 0
        self._busy = False

    def add(self, widget: Any) -> Any:
        """Track *widget* (must be a child of ``self.host``) for reflow."""
        self._items.append(widget)
        try:
            widget.place(x=0, y=0)
        except Exception:
            pass
        return widget

    def chip(self) -> ctk.CTkFrame:
        """Transparent frame for a label+control group (one flow unit)."""
        return ctk.CTkFrame(self.host, fg_color="transparent")

    def reflow(self) -> None:
        self._layout(self.host.winfo_width())

    def _on_configure(self, event) -> None:
        w = int(getattr(event, "width", 0) or 0)
        if w < 40 or abs(w - self._last_w) < 6:
            return
        self._last_w = w
        self._layout(w)

    def _layout(self, width: int) -> None:
        if self._busy or not self._items:
            return
        self._busy = True
        try:
            max_w = max(80, width - 8)
            x = self.padx
            y = self.pady
            row_h = 0
            for w in self._items:
                try:
                    w.update_idletasks()
                    req_w = max(int(w.winfo_reqwidth()), 24) + self.padx
                    req_h = max(int(w.winfo_reqheight()), 20)
                except Exception:
                    req_w, req_h = 80, 28
                if x > self.padx and x + req_w > max_w:
                    x = self.padx
                    y += row_h + self.pady
                    row_h = 0
                try:
                    w.place(x=x, y=y)
                except Exception:
                    pass
                x += req_w
                row_h = max(row_h, req_h)
            total_h = y + row_h + self.pady
            try:
                self.host.configure(height=max(int(total_h), 28))
            except Exception:
                pass
        finally:
            self._busy = False


def after_idle_reflow(widget: Any, flow: FlowRow, *, delay_ms: int = 80) -> None:
    """Schedule a reflow once the host has a real width."""

    def _go() -> None:
        try:
            flow.reflow()
        except Exception:
            pass

    try:
        widget.after(int(delay_ms), _go)
        widget.after(int(delay_ms) + 200, _go)
    except Exception:
        pass
