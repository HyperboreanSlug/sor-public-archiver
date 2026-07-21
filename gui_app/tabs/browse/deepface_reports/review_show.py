"""DfrShowMixin."""
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


class DfrShowMixin:
    def _dfr_show(self, iid: str, mc, *, preserve_eth: bool = False) -> None:
        self._dfr_selected_iid = iid
        rec = dict(mc.record or {})
        name = (
            f"{rec.get('first_name') or ''} {rec.get('middle_name') or ''} "
            f"{rec.get('last_name') or ''}"
        ).strip() or (rec.get("full_name") or "—")
        name = " ".join(name.split())
        state = _format_state_display(rec)
        race = _format_race_display(mc.expected_race) or (mc.expected_race or "—")
        df = rec.get("_deepface") or {}
        face = df.get("predicted_label") or df.get("top_label") or "—"
        conf = float(mc.confidence or 0)
        sev = df.get("severity") or ""
        reason = df.get("reason") or ""
        eth_cur = self._dfr_current_ethnicity(mc)
        crime = ""
        for key in ("crime", "offense_description", "offense_type"):
            if rec.get(key):
                crime = str(rec.get(key)).strip()
                break

        photo_raw = (rec.get("photo_path") or "").strip()
        photo_path = self._dfr_resolve_photo_path(photo_raw)
        html_raw = (rec.get("report_html_path") or "").strip()
        html_path = self._dfr_resolve_existing_path(html_raw)
        raw_url = (rec.get("source_url") or "").strip()
        try:
            from scraper.public_links import openable_url_for_record

            url = openable_url_for_record(rec) or raw_url
        except Exception:
            url = raw_url

        lines = [
            f"LISTED AS: {race}",
            f"Face: {face} @ {conf:.0%}{(' · ' + sev) if sev else ''}",
            f"Ethnicity: {eth_cur}",
            f"State: {state}  ·  ID: {rec.get('id') or '—'}",
        ]
        if df.get("scanned_at"):
            lines.append(f"Scanned: {df.get('scanned_at')}")
        if crime:
            lines.append(f"Crime: {crime[:200]}")
        if reason:
            lines.append(str(reason)[:220])
        if html_path:
            lines.append(f"HTML: {html_path}")
        elif html_raw:
            lines.append(f"HTML missing: {html_raw}")
        else:
            lines.append("HTML: —")
        lines.append(f"URL: {url or '—'}")
        if photo_path:
            lines.append(f"Photo: {photo_path}")
        elif photo_raw:
            lines.append(f"Photo missing: {photo_raw}")
        else:
            lines.append("Photo: (no path on record)")

        self._dfr_html_path = html_path
        self._dfr_source_url = url or ""
        self._dfr_photo_open_path = photo_path
        self._dfr_current_record = rec

        try:
            self.dfr_name.configure(text=name)
            self._dfr_set_meta_text("\n".join(lines))
        except Exception:
            pass

        # Link / copy actions
        try:
            if hasattr(self, "dfr_btn_html"):
                self.dfr_btn_html.configure(
                    state="normal" if html_path is not None else "disabled"
                )
            if hasattr(self, "dfr_btn_url"):
                self.dfr_btn_url.configure(
                    state="normal" if url else "disabled"
                )
            if hasattr(self, "dfr_btn_photo"):
                self.dfr_btn_photo.configure(
                    state="normal" if photo_path is not None else "disabled"
                )
            if hasattr(self, "dfr_btn_copy"):
                self.dfr_btn_copy.configure(state="normal")
            if hasattr(self, "dfr_btn_export"):
                self.dfr_btn_export.configure(state="normal")
        except Exception:
            pass

        if photo_path is not None:
            stub_reason = None
            try:
                from scraper.mugshot_ethnicity.photo_quality import placeholder_reason

                stub_reason = placeholder_reason(photo_path)
            except Exception:
                stub_reason = None
            if stub_reason:
                # Still paint the silhouette so user sees what was stored, but flag it
                ok, msg = self._dfr_set_photo_image(photo_path)
                lines.append(f"⚠ PLACEHOLDER: {stub_reason}")
                lines.append(
                    "Not a real mugshot — registry white/outline stub. "
                    "Do not treat as a face hit."
                )
                if ok:
                    lines.append(f"Image OK (stub): {msg}")
                self._dfr_set_meta_text("\n".join(lines))
            else:
                ok, msg = self._dfr_set_photo_image(photo_path)
                if ok:
                    lines.append(f"Image OK: {msg}")
                    self._dfr_set_meta_text("\n".join(lines))
                else:
                    self._dfr_set_photo_placeholder(f"Photo error\n{msg[:100]}")
                    self._dfr_set_meta_text(
                        "\n".join(lines + [f"Image FAIL: {msg}"])
                    )
        else:
            self._dfr_set_photo_placeholder(
                "No photo on disk" + (f"\n{photo_raw[:60]}" if photo_raw else "")
            )

        v = self._dfr_get_verdict(mc)
        vtxt = {
            "confirmed": "● Confirmed incorrect",
            "correct": "● Confirmed correct",
            "skip": "● Skipped",
            "unreviewed": "○ Unconfirmed — choose below",
        }.get(v, "○ Unconfirmed")
        vcol = {
            "confirmed": C["danger"],
            "correct": C["success"],
            "skip": C["dim"],
            "unreviewed": C["muted"],
        }.get(v, C["muted"])
        try:
            self.dfr_verdict_lbl.configure(text=vtxt, text_color=vcol)
            for b in (self.dfr_btn_bad, self.dfr_btn_ok, self.dfr_btn_skip):
                b.configure(state="normal")
        except Exception:
            pass

        # Ethnicity combo (skip re-set when user just changed it to avoid loops)
        if not preserve_eth and hasattr(self, "dfr_eth_combo"):
            try:
                eth_opts = list(
                    getattr(self, "_ETHNICITY_OPTIONS", None)
                    or self._DFR_ETHNICITY_OPTIONS
                )
                if eth_cur not in eth_opts:
                    eth_opts = [eth_cur] + eth_opts
                self._dfr_eth_updating = True
                try:
                    self.dfr_eth_combo.configure(values=eth_opts, state="normal")
                    self.dfr_eth_var.set(eth_cur)
                finally:
                    self._dfr_eth_updating = False
            except Exception:
                self._dfr_eth_updating = False


