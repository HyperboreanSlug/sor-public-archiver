"""Summarize long SOR offense / crime strings for report cards.

Registry pages often dump multi-statute boilerplate (FL “Commission of OR
Attempt…”, chapter cites, F.S. sections, case numbers, dates). Reports show a
short human summary; Misclassify / detail drawers keep the full text.
"""
from __future__ import annotations

import re
from typing import List, Optional

from scraper.crime_summary_clause import (
    CITY_STATE,
    COUNTY_LOC,
    extract_from_clause,
    norm,
    strip_dates,
    strip_location_junk,
)
from scraper.crime_summary_junk import (
    clean_label,
    is_junk_label,
    strip_parentheses,
    strip_statute_cites,
)


def _dedupe_preserve(items: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for it in items:
        key = it.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def summarize_crime(text: Optional[str], *, max_len: int = 140) -> str:
    """
    Return a short multi-offense summary for report cards.

    Example::

        Commission of OR Attempt...; Chapter 794; Sexual Battery *Excluding...;
        s. 800.04(4)(b); Lewd/lascivious ... under 12 ... force...;

        → Sexual battery
    """
    raw = norm(text or "")
    if not raw:
        return ""

    raw = re.sub(
        r"(?i)^scars,?\s*marks\s+and\s+tattoos\s*[—\-:]+\s*",
        "",
        raw,
    )
    raw = re.sub(r"(?i)no\s+photograph\s+available[^.]*\.", " ", raw)

    labels: List[str] = []
    for p in re.split(r"\s*;\s*", raw):
        lab = extract_from_clause(p)
        if lab:
            labels.append(lab)

    if not labels:
        cleaned = strip_location_junk(strip_statute_cites(strip_dates(raw)))
        cleaned = re.sub(
            r"(?i)commission of or attempt, solicit, or conspire to commit",
            "",
            cleaned,
        )
        cleaned = clean_label(strip_location_junk(norm(cleaned))) or ""
        if cleaned and is_junk_label(cleaned):
            cleaned = ""
        cleaned = strip_parentheses(cleaned).replace("(", "").replace(")", "")
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ·;,")
        if cleaned and len(cleaned) <= max_len:
            return cleaned
        if cleaned:
            cut = cleaned[: max_len - 1]
            if " " in cut:
                cut = cut.rsplit(" ", 1)[0]
            return cut.rstrip(" ,;:") + "…"
        return ""

    labels = _dedupe_preserve(labels)

    cleaned_labels: List[str] = []
    for x in labels:
        if re.search(r"(?i)\blewd\b|\blascivious\b", x):
            continue
        if CITY_STATE.fullmatch(x) or COUNTY_LOC.fullmatch(x):
            continue
        polished = clean_label(strip_location_junk(x))
        if polished and len(polished) >= 3 and not is_junk_label(polished):
            cleaned_labels.append(polished)
    labels = _dedupe_preserve(cleaned_labels)

    has_sb_qual = any(
        x.casefold().startswith("sexual battery —")
        or x.casefold().startswith("sexual battery -")
        for x in labels
    )
    if has_sb_qual:
        labels = [x for x in labels if x.casefold() != "sexual battery"]

    summary = " · ".join(labels)
    # Final guard: never ship parentheses in report/export crime text
    summary = summary.replace("(", "").replace(")", "")
    summary = re.sub(r"\s{2,}", " ", summary).strip(" ·;,")
    if len(summary) <= max_len:
        return summary

    while len(labels) > 1 and len(" · ".join(labels)) > max_len:
        labels.pop()
    summary = " · ".join(labels)
    summary = summary.replace("(", "").replace(")", "")
    summary = re.sub(r"\s{2,}", " ", summary).strip(" ·;,")
    if len(summary) <= max_len:
        return summary
    cut = summary[: max_len - 1]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ·,;:") + "…"
