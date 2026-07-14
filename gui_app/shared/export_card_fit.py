"""Text fitting helpers for export cards (crime block stays inside the frame)."""
from __future__ import annotations

from typing import List

from gui_app.shared.export_card_fields import _MUTED, _TEXT, load_font
from gui_app.shared.export_card_photo import wrap_text


def draw_labeled_block(
    draw,
    label: str,
    value: str,
    top: int,
    margin: int,
    max_text_w: int,
    label_font,
    value_font,
    *,
    max_lines: int = 3,
) -> int:
    draw.text((margin, top), label.upper(), font=label_font, fill=_MUTED)
    top += 34
    all_lines = wrap_text(draw, value, value_font, max_text_w)
    lines = all_lines[:max_lines]
    if len(all_lines) > max_lines and lines:
        lines[-1] = ellipsize(draw, " ".join(all_lines[max_lines - 1 :]), value_font, max_text_w)
    for line in lines:
        draw.text((margin, top), line, font=value_font, fill=_TEXT)
        top += 42
    return top + 10


def draw_crime_block(
    draw,
    cr: str,
    top: int,
    *,
    margin: int,
    max_text_w: int,
    bottom_limit: int,
    label_font,
) -> int:
    """Draw CRIME, shrinking type so it never spills past *bottom_limit*."""
    label_h = 34
    avail = bottom_limit - top - label_h - 8
    if avail < 36:
        return top
    draw.text((margin, top), "CRIME", font=label_font, fill=_MUTED)
    body_top = top + label_h
    for size in (34, 30, 26, 22, 18):
        font = load_font(size, bold=True)
        line_h = max(28, size + 8)
        max_lines = max(1, avail // line_h)
        lines = fit_lines(draw, cr, font, max_text_w, max_lines)
        if len(lines) * line_h <= avail:
            y = body_top
            for line in lines:
                draw.text((margin, y), line, font=font, fill=_TEXT)
                y += line_h
            return y + 6
    font = load_font(18, bold=True)
    draw.text(
        (margin, body_top),
        ellipsize(draw, cr, font, max_text_w),
        font=font,
        fill=_TEXT,
    )
    return body_top + 28


def fit_lines(draw, text: str, font, max_width: int, max_lines: int) -> List[str]:
    lines = wrap_text(draw, text, font, max_width)
    if len(lines) <= max_lines:
        return lines
    kept = lines[:max_lines]
    kept[-1] = ellipsize(draw, " ".join(lines[max_lines - 1 :]), font, max_width)
    return kept


def ellipsize(draw, text: str, font, max_width: int) -> str:
    text = " ".join((text or "").split())
    if not text:
        return ""
    if draw.textlength(text, font=font) <= max_width:
        return text
    ell = "…"
    lo, hi = 0, len(text)
    best = ell
    while lo <= hi:
        mid = (lo + hi) // 2
        cand = text[:mid].rstrip() + ell
        if draw.textlength(cand, font=font) <= max_width:
            best = cand
            lo = mid + 1
        else:
            hi = mid - 1
    return best
