"""Photo"""
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


class DeepfaceScanPhotoMixin:
    @staticmethod
    def _deepface_scan_resolve_photo(raw: Optional[str]) -> Optional[Path]:
        """Resolve mugshot path against cwd and project ROOT."""
        s = (raw or "").strip()
        if not s:
            return None
        candidates = [
            Path(s),
            ROOT / s,
            ROOT / s.replace("\\", "/"),
            Path.cwd() / s,
        ]
        for p in candidates:
            try:
                if p.is_file() and p.stat().st_size > 0:
                    return p.resolve()
            except OSError:
                continue
        return None


    def _deepface_scan_set_photo(self, photo_path: Optional[Path]) -> bool:
        """Paint mugshot into the scan review label. Returns True if shown."""
        if photo_path is None:
            try:
                self.df_scan_photo_lbl.configure(image=None, text="No photo\non disk")
            except Exception:
                pass
            return False
        try:
            from PIL import Image

            with Image.open(photo_path) as raw:
                img = raw.convert("RGB")
            img.thumbnail((152, 192))
            img = img.copy()
            ctk_img = ctk.CTkImage(
                light_image=img, dark_image=img, size=img.size
            )
            if not hasattr(self, "_df_scan_image_refs") or self._df_scan_image_refs is None:
                self._df_scan_image_refs = []
            self._df_scan_image_refs.append(ctk_img)
            if len(self._df_scan_image_refs) > 40:
                self._df_scan_image_refs = self._df_scan_image_refs[-20:]
            self.df_scan_photo_lbl.configure(image=ctk_img, text="")
            return True
        except Exception:
            try:
                self.df_scan_photo_lbl.configure(image=None, text="Photo\nerror")
            except Exception:
                pass
            return False


    def _deepface_scan_show_live(
        self,
        rec: dict,
        done: int,
        total: int,
        *,
        face=None,
        is_hit: Optional[bool] = None,
        phase: str = "scoring",
    ) -> None:
        """Update review pane with the mugshot currently being scored (live)."""
        if not getattr(self, "_df_scan_live_preview", True):
            return
        if not hasattr(self, "df_scan_photo_lbl"):
            return
        rec = rec or {}
        name = (
            f"{rec.get('first_name') or ''} {rec.get('last_name') or ''}"
        ).strip() or (rec.get("full_name") or "—")
        state = rec.get("state") or rec.get("source_state") or "—"
        race = rec.get("race") or "—"
        photo_raw = (rec.get("photo_path") or "").strip()
        photo_path = self._deepface_scan_resolve_photo(photo_raw)

        meta_lines = [
            f"● LIVE  {done:,} / {total:,}",
            f"LISTED AS: {race}",
            f"State: {state}  ·  ID: {rec.get('id') or '—'}",
        ]
        if phase == "scoring":
            meta_lines.append("Scoring face…")
        elif face is not None:
            lab = getattr(face, "top_label", None) or "—"
            conf = float(getattr(face, "top_confidence", 0) or 0)
            err = getattr(face, "error", None)
            if err:
                meta_lines.append(f"Result: skip — {str(err)[:120]}")
            elif getattr(face, "ok", False):
                tag = "HIT" if is_hit else "ok"
                meta_lines.append(f"Face: {lab} @ {conf:.0%}  ({tag})")
            else:
                meta_lines.append("Result: no face / unknown")
        try:
            from scraper.mugshot_ethnicity.photo_quality import placeholder_reason

            if photo_path:
                stub = placeholder_reason(photo_path)
                if stub:
                    meta_lines.append(f"⚠ PLACEHOLDER: {stub}")
        except Exception:
            pass

        try:
            self.df_scan_review_name.configure(text=name)
            self.df_scan_review_meta.configure(text="\n".join(meta_lines))
            self.df_scan_review_verdict.configure(
                text="○ Live scan — click a hit to pin for review",
                text_color=C["accent"] if is_hit else C["dim"],
            )
            for bname in (
                "df_scan_btn_confirm",
                "df_scan_btn_correct",
                "df_scan_btn_skip",
            ):
                w = getattr(self, bname, None)
                if w is not None:
                    w.configure(state="disabled")
        except Exception:
            pass
        self._deepface_scan_set_photo(photo_path)
        self._df_scan_selected_iid = None


    def _deepface_scan_show_hit(self, iid: str, hit) -> None:
        """Populate review pane for one hit (mugshot + actions). Pins away from live."""
        self._df_scan_live_preview = False
        self._df_scan_selected_iid = iid
        rec = getattr(hit, "record", None) or {}
        name = (
            f"{rec.get('first_name') or ''} {rec.get('last_name') or ''}"
        ).strip() or (rec.get("full_name") or "—")
        state = rec.get("state") or rec.get("source_state") or "—"
        race = getattr(hit, "recorded_race", None) or rec.get("race") or "—"
        face = getattr(hit, "predicted_label", None) or "—"
        conf = float(getattr(hit, "confidence", 0) or 0)
        sev = getattr(hit, "severity", None) or ""
        reason = getattr(hit, "reason", None) or ""
        crime = ""
        for key in ("crime", "offense_description", "offense_type"):
            if rec.get(key):
                crime = str(rec.get(key)).strip()
                break
        meta_lines = [
            f"LISTED AS: {race}",
            f"Face: {face} @ {conf:.0%}{(' · ' + sev) if sev else ''}",
            f"State: {state}  ·  ID: {rec.get('id') or '—'}",
        ]
        if crime:
            meta_lines.append(f"Crime: {crime[:180]}")
        if reason:
            meta_lines.append(reason[:200])
        try:
            self.df_scan_review_name.configure(text=name)
            self.df_scan_review_meta.configure(text="\n".join(meta_lines))
        except Exception:
            pass

        # Mugshot
        photo_path_raw = (rec.get("photo_path") or "").strip()
        if not photo_path_raw and getattr(hit, "face", None) is not None:
            photo_path_raw = (getattr(hit.face, "photo_path", None) or "").strip()
        photo_path = self._deepface_scan_resolve_photo(photo_path_raw)
        stub_reason = None
        if photo_path is not None:
            try:
                from scraper.mugshot_ethnicity.photo_quality import placeholder_reason

                stub_reason = placeholder_reason(photo_path)
            except Exception:
                stub_reason = None
        shown = self._deepface_scan_set_photo(photo_path)
        if stub_reason:
            meta_lines.append(f"⚠ PLACEHOLDER: {stub_reason}")
            meta_lines.append("Not a real mugshot — skip / do not confirm as a hit.")
            try:
                self.df_scan_review_meta.configure(text="\n".join(meta_lines))
            except Exception:
                pass
        if not shown and photo_path is None:
            try:
                self.df_scan_photo_lbl.configure(image=None, text="No photo\non disk")
            except Exception:
                pass

        verdict = self._deepface_scan_get_verdict(hit)
        vcolor = {
            "confirmed": C["danger"],
            "correct": C["success"],
            "skip": C["dim"],
            "unreviewed": C["muted"],
        }.get(verdict, C["muted"])
        vtxt = {
            "confirmed": "● Confirmed incorrect",
            "correct": "● Confirmed correct",
            "skip": "● Skipped",
            "unreviewed": "○ Unconfirmed — choose below",
        }.get(verdict, "○ Unconfirmed")
        try:
            self.df_scan_review_verdict.configure(text=vtxt, text_color=vcolor)
            for bname in (
                "df_scan_btn_confirm",
                "df_scan_btn_correct",
                "df_scan_btn_skip",
            ):
                w = getattr(self, bname, None)
                if w is not None:
                    w.configure(state="normal")
        except Exception:
            pass


    def _deepface_scan_on_select(self, _event=None) -> None:
        if not hasattr(self, "df_scan_tree"):
            return
        try:
            sel = self.df_scan_tree.selection()
            if not sel:
                return
            iid = sel[0]
            hit = (getattr(self, "_df_scan_hits_by_iid", {}) or {}).get(iid)
            if hit is None:
                return
            # Pin this hit — stop overwriting with live scan previews
            self._df_scan_live_preview = False
            self._deepface_scan_show_hit(iid, hit)
        except Exception:
            pass


    def _deepface_scan_append_hit(self, hit) -> None:
        """Insert one hit into the results tree (main thread; live updates)."""
        if not hasattr(self, "df_scan_tree"):
            return
        try:
            rec = hit.record or {}
            try:
                oid = int(rec["id"]) if rec.get("id") is not None else None
            except (TypeError, ValueError):
                oid = None
            seen = getattr(self, "_df_scan_hit_ids", None)
            if seen is None:
                self._df_scan_hit_ids = set()
                seen = self._df_scan_hit_ids
            if oid is not None and oid in seen:
                return
            if oid is not None:
                seen.add(oid)
            name = (
                f"{rec.get('first_name') or ''} {rec.get('last_name') or ''}"
            ).strip()
            verdict = self._deepface_scan_get_verdict(hit)
            iid = self.df_scan_tree.insert(
                "",
                "end",
                values=(
                    name,
                    rec.get("state") or "—",
                    (hit.recorded_race or "—")[:20],
                    hit.predicted_label,
                    f"{float(hit.confidence or 0):.2f}",
                    self._deepface_scan_verdict_label(verdict),
                    rec.get("id") or "",
                ),
            )
            if not hasattr(self, "_df_scan_hits_by_iid"):
                self._df_scan_hits_by_iid = {}
            self._df_scan_hits_by_iid[iid] = hit
            # Keep newest hits visible
            try:
                self.df_scan_tree.see(iid)
            except Exception:
                pass
            if not hasattr(self, "_df_scan_hits") or self._df_scan_hits is None:
                self._df_scan_hits = []
            self._df_scan_hits.append(hit)
            n = len(self._df_scan_hits)
            try:
                self.df_scan_status.configure(
                    text=f"Live · {n:,} hits",
                    text_color=C["text"],
                )
            except Exception:
                pass
            # Keep live mugshot preview during scan; don't steal the panel for hits.
            # When scan finishes (or user clicks a row), review mode takes over.
        except Exception:
            pass


