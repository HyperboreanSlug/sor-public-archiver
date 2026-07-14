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
    """Natural size for reflow — prefer explicit widths; never invent tall stacks."""
    try:
        widget.update_idletasks()
    except Exception:
        pass

    explicit_w = _cfg_int(widget, "width")
    explicit_h = _cfg_int(widget, "height")
    try:
        rw = int(widget.winfo_reqwidth() or 0)
        rh = int(widget.winfo_reqheight() or 0)
    except Exception:
        rw, rh = 0, 0

    # Fixed-size CTk controls (button/entry/combo): trust explicit width.
    # Do NOT walk internal CTk children — they inflate size and force wrap spam.
    if explicit_w > 0:
        rw = explicit_w
        rh = explicit_h if explicit_h > 0 else (min(rh, 40) if rh > 0 else 28)
        return rw + padx, max(rh, 26)

    # Chip frames: sum only direct kids' explicit/req sizes (labels + one control)
    try:
        kids = list(widget.winfo_children())
    except Exception:
        kids = []
    if kids:
        sum_w = 0
        max_h = 0
        for ch in kids:
            cw = _cfg_int(ch, "width")
            ch_h = _cfg_int(ch, "height")
            if cw <= 0:
                try:
                    ch.update_idletasks()
                    cw = int(ch.winfo_reqwidth() or 0)
                except Exception:
                    cw = 0
                # Labels without fixed width
                try:
                    txt = str(ch.cget("text") or "")
                    if txt and not _cfg_int(ch, "width"):
                        cw = max(cw, min(10 + len(txt) * 7, 200))
                except Exception:
                    pass
            if ch_h <= 0:
                try:
                    ch_h = min(int(ch.winfo_reqheight() or 0), 40)
                except Exception:
                    ch_h = 28
            # Combo with values but no width: room for longest option
            if cw < 80:
                try:
                    values = list(ch.cget("values") or [])
                    if values:
                        longest = max((str(v) for v in values), key=len, default="")
                        cw = max(cw, min(28 + int(len(longest) * 7), 220))
                except Exception:
                    pass
            sum_w += max(cw, 20) + 6
            max_h = max(max_h, ch_h if ch_h > 0 else 28, 26)
        rw = max(sum_w + 2, 40)
        rh = max(max_h + 2, 28)
        return rw + padx, rh

    # Bare label
    try:
        txt = str(widget.cget("text") or "")
        if txt:
            rw = max(rw, min(10 + len(txt) * 7, 360))
    except Exception:
        pass
    if rh <= 0 or rh > 48:
        rh = 28
    return max(rw, 28) + padx, max(rh, 26)


class FlowRow:
    """Left-to-right toolbar that wraps; host height matches content only."""

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
        # Start with propagate on so we don't reserve a tall empty strip before layout
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
        fr = ctk.CTkFrame(self.host, fg_color="transparent")
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
        try:
            w = int(self.host.master.winfo_width() or 0) - 12
        except Exception:
            w = 0
        return w if w >= 80 else 0

    def _on_map(self, _event=None) -> None:
        for ms in (20, 80, 200):
            try:
                self.host.after(ms, self.reflow)
            except Exception:
                pass

    def _on_configure(self, event) -> None:
        w = int(getattr(event, "width", 0) or 0)
        if w < 80:
            return
        if self._laid_out and abs(w - self._last_w) < 8:
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
                req_w, req_h = _measure_widget(w, self.padx)
                # Cap absurd measurements so one bad widget cannot force full-column wrap
                req_w = min(req_w, max_w)
                req_h = min(req_h, 48)
                if x > self.padx and (x + req_w) > max_w:
                    x = self.padx
                    y += row_h + self.pady
                    row_h = 0
                try:
                    w.place(x=x, y=y)
                except Exception:
                    pass
                x += req_w
                row_h = max(row_h, req_h)
            total_h = max(int(y + row_h + self.pady + 2), 28)
            try:
                self.host.pack_propagate(False)
                self.host.configure(height=total_h)
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
        for extra in (0, 100, 250):
            widget.after(base + extra, _go)
    except Exception:
        pass
