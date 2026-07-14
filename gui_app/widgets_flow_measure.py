"""Size helpers for FlowRow reflow (keep labels/menus fully visible)."""
from __future__ import annotations

from typing import Any, Tuple


def cfg_int(widget: Any, key: str) -> int:
    try:
        val = widget.cget(key)
        if val in (None, "", 0, "0"):
            return 0
        return int(float(val))
    except Exception:
        return 0


def req_size(widget: Any) -> Tuple[int, int]:
    try:
        widget.update_idletasks()
    except Exception:
        pass
    try:
        rw = int(widget.winfo_reqwidth() or 0)
        rh = int(widget.winfo_reqheight() or 0)
    except Exception:
        rw, rh = 0, 0
    return rw, rh


def text_px(text: str, *, per_char: float = 7.2, pad: int = 12, cap: int = 360) -> int:
    if not text:
        return 0
    return min(pad + int(len(text) * per_char), cap)


def longest_value_px(widget: Any) -> int:
    try:
        values = list(widget.cget("values") or [])
    except Exception:
        return 0
    if not values:
        return 0
    longest = max((str(v) for v in values), key=len, default="")
    return text_px(longest, per_char=7.4, pad=36, cap=280)


def is_flow_chip(widget: Any) -> bool:
    if getattr(widget, "_flow_chip", False):
        return True
    try:
        name = widget.__class__.__name__
    except Exception:
        name = ""
    if name not in ("CTkFrame", "Frame", "CTkScrollableFrame"):
        return False
    try:
        return bool(list(widget.winfo_children()))
    except Exception:
        return False


def leaf_size(widget: Any) -> Tuple[int, int]:
    """Pixel size for a button/entry/combo/label — honor DPI via reqwidth."""
    explicit_w = cfg_int(widget, "width")
    explicit_h = cfg_int(widget, "height")
    rw, rh = req_size(widget)

    if rw <= 0 and explicit_w > 0:
        rw = explicit_w
    elif explicit_w > 0 and rw > 0:
        # Prefer real pixels (CTk scaling) but cap inflation
        rw = max(explicit_w, min(rw, max(explicit_w + 48, int(explicit_w * 1.45))))
    elif rw <= 0:
        try:
            txt = str(widget.cget("text") or "")
        except Exception:
            txt = ""
        rw = max(text_px(txt), longest_value_px(widget), 28)

    need = longest_value_px(widget)
    if need > 0:
        rw = max(rw, need)

    try:
        txt = str(widget.cget("text") or "")
        if txt and explicit_w <= 0:
            rw = max(rw, text_px(txt))
    except Exception:
        pass

    if explicit_h > 0 and explicit_h <= 52:
        rh = max(explicit_h, min(rh, explicit_h + 12) if 0 < rh <= 52 else explicit_h)
    elif 0 < rh <= 52:
        rh = max(rh, 26)
    else:
        rh = 30

    return max(rw, 24), max(rh, 26)


def chip_size(widget: Any) -> Tuple[int, int]:
    """Size a label+control chip without trusting CTkFrame's default 200×200."""
    rw, rh = req_size(widget)
    if 40 <= rw <= 900 and 20 <= rh <= 48:
        return rw, max(rh, 28)

    try:
        kids = list(widget.winfo_children())
    except Exception:
        kids = []
    sum_w = 0
    max_h = 0
    for ch in kids:
        cw, ch_h = leaf_size(ch)
        sum_w += cw + 6
        max_h = max(max_h, ch_h)
    if sum_w > 0:
        return max(sum_w + 4, 40), max(max_h + 4, 28)
    if rw >= 40 and rw != 200:
        return rw, 32
    return 120, 32


def measure_widget(widget: Any, padx: int) -> Tuple[int, int]:
    """Natural size for reflow — full text visible, one control-row height."""
    if is_flow_chip(widget):
        rw, rh = chip_size(widget)
        return rw + padx, rh
    rw, rh = leaf_size(widget)
    return rw + padx, rh
