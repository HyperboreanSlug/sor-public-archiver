"""StatisticsUpdateMixin."""
from __future__ import annotations

import csv
import json
import os
import queue
import re
import subprocess
import sys
import threading
import traceback
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from gui_app.paths import ROOT
from gui_app.theme import (
    C,
    FONT_BOLD,
    FONT_MONO,
    FONT_SECTION,
    FONT_SM,
    FONT_TITLE,
    FONT_UI,
)
from gui_app.widgets import (
    _bind_tree_scroll_isolation,
    _card,
    _enable_tree_column_sort,
    _format_race_display,
    _format_state_display,
    _hpaned,
    _misclass_race_bucket,
    _muted,
    _render_bar_chart,
    _render_pie_chart,
    _section_label,
    _stretch_columns,
    _tree_frame,
    _vpaned,
    _wire_wide_scroll,
)


class StatisticsUpdateMixin:
    def _update_misclass_stats(
        self,
        results: list,
        *,
        db_total: int,
        scanned_cap: int,
        min_conf: float,
        eth_filter: str,
        eth_base_count: Optional[int] = None,
    ) -> None:
        """Refresh Statistics tab from analysis results.

        *eth_base_count*: how many scanned offenders matched the selected
        surname ethnicity (at min conf). Misclassification rate is
        mismatches / eth_base_count when a specific ethnicity is selected.
        """
        from collections import Counter, defaultdict

        n = len(results)
        eth_label = (eth_filter or "all").strip() or "all"
        # Rate among selected ethnicity when we know the base population
        if eth_base_count is not None and eth_label != "all":
            denom = max(1, int(eth_base_count))
            rate = (n / denom * 100.0) if denom else 0.0
            rate_txt = f"Misclass: {rate:.1f}% of {eth_label}"
            eth_n_txt = f"{eth_label}: {int(eth_base_count):,}"
        else:
            denom = max(1, min(db_total, scanned_cap) if db_total else scanned_cap)
            rate = (n / denom * 100.0) if denom else 0.0
            rate_txt = f"Rate: {rate:.2f}% of scanned"
            eth_n_txt = f"Ethnicity base: — (filter=all)"

        if hasattr(self, "mcstat_db"):
            self.mcstat_db.configure(text=f"DB: {db_total:,}")
            if hasattr(self, "mcstat_eth_n"):
                self.mcstat_eth_n.configure(text=eth_n_txt)
            self.mcstat_n.configure(text=f"Misclassified: {n:,}")
            self.mcstat_rate.configure(text=rate_txt)
            if results:
                confs = [float(mc.confidence) for mc in results]
                self.mcstat_conf.configure(
                    text=f"Conf avg {sum(confs)/len(confs):.3f}  "
                    f"({min(confs):.2f}–{max(confs):.2f})"
                )
            else:
                self.mcstat_conf.configure(text="Conf: —")
            if eth_base_count is not None and eth_label != "all":
                ok_n = max(0, int(eth_base_count) - n)
                self.mcstat_filter.configure(
                    text=(
                        f"Selected ethnicity: {eth_label} · "
                        f"{int(eth_base_count):,} name matches (min conf {min_conf:.2f}) · "
                        f"{n:,} misclassified ({rate:.1f}%) · "
                        f"{ok_n:,} race-compatible · "
                        f"scan cap {scanned_cap:,}"
                    )
                )
            else:
                self.mcstat_filter.configure(
                    text=(
                        f"Filter: {eth_label} · min conf. {min_conf:.2f} · "
                        f"scanned cap {scanned_cap:,} · "
                        f"{'no mismatches' if n == 0 else f'{n:,} rows in transition table'}"
                    )
                )

        # Transitions: surname ethnicity → recorded race
        pair_counts: Counter = Counter()
        pair_conf: Dict[tuple, list] = defaultdict(list)
        pair_example: Dict[tuple, str] = {}
        for mc in results:
            eth = (mc.likely_ethnicity or "—").strip() or "—"
            race = (mc.expected_race or "—").strip() or "—"
            key = (eth, race)
            pair_counts[key] += 1
            pair_conf[key].append(float(mc.confidence))
            if key not in pair_example:
                rec = mc.record or {}
                name = (
                    " ".join(
                        p for p in (
                            rec.get("first_name") or "",
                            rec.get("middle_name") or "",
                            rec.get("last_name") or "",
                        ) if str(p).strip()
                    )
                    or (rec.get("full_name") or "—")
                )
                pair_example[key] = name

        if hasattr(self, "mcstat_transition_tree"):
            self.mcstat_transition_tree.delete(*self.mcstat_transition_tree.get_children())
            for (eth, race), cnt in pair_counts.most_common():
                confs = pair_conf[(eth, race)]
                avg = sum(confs) / len(confs) if confs else 0.0
                pct = (cnt / n * 100.0) if n else 0.0
                self.mcstat_transition_tree.insert(
                    "",
                    "end",
                    values=(
                        eth,  # full ethnicity label
                        race,  # full race label
                        str(cnt),
                        f"{pct:.1f}%",
                        f"{avg:.3f}",
                        pair_example.get((eth, race), "—"),
                    ),
                )

        by_eth = Counter((mc.likely_ethnicity or "—") for mc in results)
        # "Misclassified as (race)" pie: Black / White / Other (residual bucket).
        by_race: Counter = Counter(
            _misclass_race_bucket(mc.expected_race) for mc in results
        )
        race_n = sum(by_race.values())

        def _fill(tree, counter: Counter, total: Optional[int] = None):
            if tree is None:
                return
            denom = n if total is None else total
            tree.delete(*tree.get_children())
            for label, cnt in counter.most_common():
                pct = (cnt / denom * 100.0) if denom else 0.0
                tree.insert("", "end", values=(str(label), str(cnt), f"{pct:.1f}%"))

        _fill(getattr(self, "mcstat_eth_tree", None), by_eth)
        _fill(getattr(self, "mcstat_race_tree", None), by_race, total=race_n)

        # Confidence bands (high → low)
        bands = Counter()
        for mc in results:
            c = float(mc.confidence)
            if c >= 0.9:
                bands["0.90 – 1.00 (high)"] += 1
            elif c >= 0.75:
                bands["0.75 – 0.89"] += 1
            elif c >= 0.6:
                bands["0.60 – 0.74"] += 1
            else:
                bands["below 0.60"] += 1

        band_order = [
            "0.90 – 1.00 (high)",
            "0.75 – 0.89",
            "0.60 – 0.74",
            "below 0.60",
        ]
        if hasattr(self, "mcstat_conf_tree"):
            self.mcstat_conf_tree.delete(*self.mcstat_conf_tree.get_children())
            for band in band_order:
                cnt = bands.get(band, 0)
                if cnt == 0 and n > 0:
                    continue
                if n == 0 and band != band_order[0]:
                    continue
                pct = (cnt / n * 100.0) if n else 0.0
                self.mcstat_conf_tree.insert(
                    "", "end", values=(band, str(cnt), f"{pct:.1f}")
                )

        # Side-by-side pie charts (each ~1/3 width)
        if getattr(self, "mcstat_chart_labels", None):
            try:
                host = getattr(self, "_mcstat_charts_host", None)
                if host is not None:
                    host.update_idletasks()
                    host_w = max(720, host.winfo_width())
                else:
                    host_w = 960
            except Exception:
                host_w = 960
            # 3 columns with small gaps
            pie_w = max(220, (host_w - 24) // 3)
            pie_h = 300
            eth_items = by_eth.most_common(8)
            race_items = by_race.most_common(8)
            conf_items = [(b, bands[b]) for b in band_order if bands.get(b, 0) > 0]
            charts_data = [
                (eth_items, "By surname ethnicity"),
                (race_items, "Misclassified as (race)"),
                (conf_items, "Confidence bands"),
            ]
            refs: List[Any] = []
            for i, (items, title) in enumerate(charts_data):
                try:
                    img = _render_pie_chart(
                        items,
                        title=title,
                        width=pie_w,
                        height=pie_h,
                        max_slices=8,
                        bg=C["tree_bg"],
                        fg=C["text"],
                        muted=C["muted"],
                        accent=C["accent"],
                        legend_below=True,
                    )
                    refs.append(img)
                    self.mcstat_chart_labels[i].configure(image=img, text="")
                    if getattr(self, "_mcstat_chart_cells", None) and i < len(self._mcstat_chart_cells):
                        self._mcstat_chart_cells[i].configure(height=pie_h + 8)
                except Exception:
                    self.mcstat_chart_labels[i].configure(
                        image=None, text=f"{title} (chart error)"
                    )
            self._mcstat_chart_refs = refs

        if hasattr(self, "mcstat_status"):
            if n:
                top = pair_counts.most_common(1)
                if top:
                    (eth, race), cnt = top[0]
                    self.mcstat_status.configure(
                        text=(
                            f"Top transition: {eth} → recorded as {race}  ({cnt:,} · "
                            f"{cnt/n*100:.1f}% of mismatches)"
                        )
                    )
                else:
                    self.mcstat_status.configure(text=f"{n:,} mismatches")
            else:
                self.mcstat_status.configure(
                    text="No mismatches for this filter — try lower min conf. or another ethnicity."
                )


