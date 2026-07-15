"""Text fitting helpers for export cards (crime block stays inside the frame)."""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

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
    bottom_limit: Optional[int] = None,
) -> int:
    """Draw labeled value. Stops early if *bottom_limit* would be exceeded."""
    need = 34 + 42  # label + one value line
    if bottom_limit is not None and top + need > bottom_limit:
        return top
    draw.text((margin, top), label.upper(), font=label_font, fill=_MUTED)
    top += 34
    all_lines = wrap_text(draw, value, value_font, max_text_w)
    lines = all_lines[:max_lines]
    if len(all_lines) > max_lines and lines:
        lines[-1] = ellipsize(
            draw, " ".join(all_lines[max_lines - 1 :]), value_font, max_text_w
        )
    for line in lines:
        if bottom_limit is not None and top + 42 > bottom_limit:
            break
        draw.text((margin, top), line, font=value_font, fill=_TEXT)
        top += 42
    return top + 10


def wrap_crime_text(draw, text: str, font, max_width: int) -> List[str]:
    """Wrap crime summaries at `` · `` between offenses (not mid-phrase).

    Multi-part summaries break so later offenses start on a new line even when
    the full string would still fit on one line — e.g. CHRISTOPHER SINGH::

        Sexual battery · Victim under 12/force · Unclothed genitals
        → Sexual battery · Victim under 12/force
          Unclothed genitals
    """
    text = " ".join((text or "").split())
    if not text:
        return [""]
    if not re.search(r"\s[·•]\s", text):
        return wrap_text(draw, text, font, max_width)

    parts = [p.strip() for p in re.split(r"\s*[·•]\s*", text) if p.strip()]
    if len(parts) < 2:
        return wrap_text(draw, text, font, max_width)

    # 3+ clauses: keep leading clauses together when they fit; last clause
    # always starts its own line (readable card layout).
    if len(parts) >= 3:
        head = " · ".join(parts[:-1])
        tail = parts[-1]
        lines: List[str] = []
        if draw.textlength(head, font=font) <= max_width:
            lines.append(head)
        else:
            # Pack leading clauses left-to-right with width wrap
            lines.extend(_pack_crime_parts(draw, parts[:-1], font, max_width))
        for seg in wrap_text(draw, tail, font, max_width):
            if seg:
                lines.append(seg)
        return lines or [""]

    # Exactly two clauses: one per line when each fits alone
    a, b = parts[0], parts[1]
    joined = f"{a} · {b}"
    if draw.textlength(joined, font=font) <= max_width:
        # Still prefer two lines when both phrases are substantial
        if len(a) >= 8 and len(b) >= 8:
            return [a, b]
        return [joined]
    return _pack_crime_parts(draw, parts, font, max_width)


def _pack_crime_parts(draw, parts: List[str], font, max_width: int) -> List[str]:
    """Left-pack offense phrases with middots; wrap when width exceeded."""
    lines: List[str] = []
    current = ""
    for part in parts:
        for seg in wrap_text(draw, part, font, max_width):
            if not seg:
                continue
            trial = f"{current} · {seg}" if current else seg
            if current and draw.textlength(trial, font=font) > max_width:
                lines.append(current)
                current = seg
            else:
                current = trial
    if current:
        lines.append(current)
    return lines or [""]


def plan_crime_block(
    draw,
    cr: str,
    *,
    max_text_w: int,
    max_height: int,
) -> Optional[Tuple]:
    """Return (font, line_h, lines, total_h) that fits in *max_height*."""
    label_h = 34
    body_avail = max_height - label_h - 8
    if body_avail < 22:
        return None
    # Prefer wrapping to 2–3 lines over one ellipsized mega-line
    for size in (34, 30, 26, 22, 18):
        font = load_font(size, bold=True)
        line_h = max(28, size + 10)
        max_lines = max(1, body_avail // line_h)
        lines = fit_crime_lines(draw, cr, font, max_text_w, max_lines)
        body_h = len(lines) * line_h
        if body_h <= body_avail and lines:
            return font, line_h, lines, label_h + body_h + 6
    font = load_font(18, bold=True)
    line_h = 28
    max_lines = max(1, body_avail // line_h)
    lines = fit_crime_lines(draw, cr, font, max_text_w, max_lines)
    if not lines:
        lines = [ellipsize(draw, cr, font, max_text_w)]
    body_h = len(lines) * line_h
    total = label_h + body_h + 6
    if total > max_height:
        lines = [ellipsize(draw, cr, font, max_text_w)]
        total = label_h + line_h + 6
        if total > max_height:
            return None
    return font, line_h, lines, total


def draw_crime_block(
    draw,
    cr: str,
    top: int,
    *,
    margin: int,
    max_text_w: int,
    bottom_limit: int,
    label_font,
    anchor_bottom: bool = False,
    min_height: int = 90,
) -> int:
    """Draw CRIME with multi-line wrap (middot-aware)."""
    cr = " ".join((cr or "").split())
    if not cr:
        return top

    if anchor_bottom:
        # Room for 2–3 wrapped crime lines
        band = max(min_height, min(240, bottom_limit - max(0, top)))
        if band < 50:
            band = min_height
        max_height = band
    else:
        max_height = bottom_limit - top
        if max_height < 40:
            return top

    plan = plan_crime_block(
        draw, cr, max_text_w=max_text_w, max_height=max_height
    )
    if plan is None:
        font = load_font(18, bold=True)
        line_h = 28
        lines = wrap_crime_text(draw, cr, font, max_text_w)[:3]
        if not lines:
            lines = [ellipsize(draw, cr, font, max_text_w)]
        total_h = 34 + len(lines) * line_h + 6
        label_h = 34
    else:
        font, line_h, lines, total_h = plan
        label_h = 34

    if anchor_bottom:
        top = bottom_limit - total_h
    draw.text((margin, top), "CRIME", font=label_font, fill=_MUTED)
    y = top + label_h
    for line in lines:
        draw.text((margin, y), line, font=font, fill=_TEXT)
        y += line_h
    return y + 6


def fit_crime_lines(
    draw, text: str, font, max_width: int, max_lines: int
) -> List[str]:
    """Wrap crime text; only ellipsize when still over *max_lines*."""
    lines = wrap_crime_text(draw, text, font, max_width)
    if len(lines) <= max_lines:
        return lines
    if max_lines <= 1:
        return [ellipsize(draw, text, font, max_width)]
    # Keep early lines intact; squeeze the remainder onto the last line
    kept = list(lines[: max_lines - 1])
    rest = " · ".join(lines[max_lines - 1 :])
    # If rest was middot-joined, re-wrap once more into one ellipsized line
    kept.append(ellipsize(draw, rest, font, max_width))
    return kept


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
