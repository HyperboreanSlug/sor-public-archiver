"""Compose 1×2 / 2×2 grids of watermarked export cards."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, List, Mapping, Sequence

from PIL import Image

from gui_app.shared.export_card_fields import (
    _BG,
    _CARD_H,
    _CARD_W,
    desktop_dir,
    person_name,
    safe_filename,
)
from gui_app.shared.export_card_render import render_export_card

_GAP = 28
_LAYOUTS = {
    "1x2": (1, 2),  # rows, cols
    "2x2": (2, 2),
}


def normalize_layout(layout: str) -> str:
    key = (layout or "2x2").strip().lower().replace("×", "x").replace(" ", "")
    if key in ("1x2", "2x1"):
        return "1x2"
    return "2x2"


def layout_capacity(layout: str) -> int:
    rows, cols = _LAYOUTS[normalize_layout(layout)]
    return rows * cols


def render_export_grid(
    records: Sequence[Mapping[str, Any]],
    layout: str = "2x2",
    *,
    assign_number: bool = False,
) -> Image.Image:
    """Build a grid of mapa-style watermarked cards.

    Each cell is a full ``render_export_card`` (seal + @DoDeportations).
    Empty slots (fewer selections than capacity) are solid dark panels.
    ``assign_number`` only for deliberate grid export to Desktop.
    """
    layout = normalize_layout(layout)
    rows, cols = _LAYOUTS[layout]
    cap = rows * cols
    recs = list(records)[:cap]

    # Render watermarked cards first so empty panels match card size
    cards: List[Image.Image] = []
    for rec in recs:
        img = render_export_card(rec, assign_number=assign_number).convert("RGBA")
        cards.append(img)
    cw, ch = (_CARD_W, _CARD_H)
    if cards:
        cw, ch = cards[0].size
    while len(cards) < cap:
        blank = Image.new("RGBA", (cw, ch), _BG)
        cards.append(blank)

    out_w = cols * cw + (cols + 1) * _GAP
    out_h = rows * ch + (rows + 1) * _GAP
    canvas = Image.new("RGBA", (out_w, out_h), _BG)

    for i, card in enumerate(cards):
        r, c = divmod(i, cols)
        if layout == "1x2":
            r, c = 0, i
        x = _GAP + c * (cw + _GAP)
        y = _GAP + r * (ch + _GAP)
        if card.size != (cw, ch):
            card = card.resize((cw, ch), Image.Resampling.LANCZOS)
        canvas.alpha_composite(card, (x, y))
    return canvas


def export_grid_to_desktop(
    records: Sequence[Mapping[str, Any]],
    layout: str = "2x2",
) -> Path:
    """Render grid PNG to Desktop; return path.

    Deliberate export: assigns (or reuses) export numbers for each person.
    """
    layout = normalize_layout(layout)
    img = render_export_grid(records, layout=layout, assign_number=True)
    desktop = desktop_dir()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    names = [safe_filename(person_name(r)) for r in list(records)[:4]]
    stem = "_".join(n for n in names if n)[:60] or "grid"
    out = desktop / f"{stem}_{layout}_{stamp}.png"
    n = 1
    while out.exists():
        out = desktop / f"{stem}_{layout}_{stamp}_{n}.png"
        n += 1
    img.convert("RGB").save(out, format="PNG", optimize=True)
    return out
