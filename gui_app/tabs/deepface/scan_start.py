"""Start"""
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


class DeepfaceScanStartMixin:
    def _deepface_scan_start(self) -> None:
        if getattr(self, "_df_scan_running", False):
            self._deepface_scan_log_msg("Scan already running")
            return
        self._deepface_scan_save_options()
        opts = self._deepface_scan_collect_options()
        if not opts["recorded_races"]:
            self._deepface_scan_log_msg("Select at least one recorded race filter")
            return
        if not opts["face_labels"]:
            self._deepface_scan_log_msg("Select at least one face label to flag")
            return
        self._df_scan_cancel = False
        self._df_scan_hits = []
        self._df_scan_hit_ids = set()
        self._df_scan_hits_by_iid = {}
        self._df_scan_selected_iid = None
        self._df_scan_image_refs = []
        self._df_scan_live_preview = True
        self._df_scan_live_seq = int(getattr(self, "_df_scan_live_seq", 0) or 0) + 1
        live_gen = self._df_scan_live_seq
        try:
            self.df_scan_tree.delete(*self.df_scan_tree.get_children())
            self.df_scan_progress.set(0)
            self._deepface_scan_clear_review()
            self.df_scan_review_meta.configure(
                text="Starting scan — mugshots will appear here as they are scored."
            )
        except Exception:
            pass
        self._deepface_scan_set_busy(True)
        self._deepface_scan_log_msg(
            f"Starting scan: state={opts['state'] or 'ALL'} "
            f"min_conf={opts['min_confidence']} limit={opts['limit'] or '∞'} "
            f"recorded={opts['recorded_races']} faces={opts['face_labels']}"
            f"{' · FORCE RESCAN' if opts.get('force_rescan') else ' · skip already scanned'}"
        )
        try:
            self.df_scan_status.configure(
                text="Starting…", text_color=C["accent"]
            )
        except Exception:
            pass

        db_path = str(getattr(self, "db_path", None) or "data/offenders.db")
        detector = "retinaface"
        try:
            from scraper.app_settings import load_settings

            detector = str(
                (getattr(self, "app_settings", None) or load_settings()).get(
                    "deepface_detector"
                )
                or "retinaface"
            )
        except Exception:
            pass

        def progress(done: int, total: int) -> None:
            def ui():
                try:
                    frac = (done / total) if total else 0.0
                    self.df_scan_progress.set(min(1.0, max(0.0, frac)))
                    n = len(getattr(self, "_df_scan_hits", []) or [])
                    self.df_scan_status.configure(
                        text=f"Scoring {done:,} / {total:,}  ·  hits {n:,}",
                        text_color=C["text"],
                    )
                except Exception:
                    pass

            try:
                self.after(0, ui)
            except Exception:
                pass

        def on_photo(rec, done: int, total: int) -> None:
            # Coalesce: only apply if this is still the active scan generation
            def ui(r=rec, d=done, t=total, gen=live_gen):
                if gen != getattr(self, "_df_scan_live_seq", 0):
                    return
                try:
                    self._deepface_scan_show_live(r, d, t, phase="scoring")
                except Exception:
                    pass

            try:
                self.after(0, ui)
            except Exception:
                pass

        def on_scored(rec, face, is_hit: bool, done: int, total: int) -> None:
            def ui(r=rec, f=face, h=is_hit, d=done, t=total, gen=live_gen):
                if gen != getattr(self, "_df_scan_live_seq", 0):
                    return
                if not getattr(self, "_df_scan_live_preview", True):
                    return
                try:
                    self._deepface_scan_show_live(
                        r, d, t, face=f, is_hit=h, phase="scored"
                    )
                except Exception:
                    pass

            try:
                self.after(0, ui)
            except Exception:
                pass

        def on_hit(hit) -> None:
            try:
                self.after(0, lambda h=hit: self._deepface_scan_append_hit(h))
            except Exception:
                pass

        def worker() -> None:
            hits = []
            err = None
            try:
                from scraper.mugshot_ethnicity.setup import configure_tf_keras_env
                from scraper.mugshot_ethnicity.scorer import (
                    BackendUnavailableError,
                    MugshotEthnicityScorer,
                )
                from scraper.mugshot_ethnicity.scanner import scan_gross_misclassifications

                # Legacy TF env only needed if auto falls back to DeepFace.
                configure_tf_keras_env()
                # Default: FairFace (face-race) → DeepFace → CLIP
                try:
                    scorer = MugshotEthnicityScorer(
                        backend="auto",
                        auto_install=True,
                        log=self._deepface_scan_log_msg,
                    )
                except BackendUnavailableError as e:
                    raise RuntimeError(str(e)) from e

                self._deepface_scan_log_msg(
                    f"Using backend: {scorer.backend_name}"
                )
                hits = scan_gross_misclassifications(
                    db_path=db_path,
                    scorer=scorer,
                    recorded_races=opts["recorded_races"],
                    face_labels=opts["face_labels"],
                    min_confidence=opts["min_confidence"],
                    limit=opts["limit"],
                    state=opts["state"],
                    progress=progress,
                    log=self._deepface_scan_log_msg,
                    cancel=lambda: bool(getattr(self, "_df_scan_cancel", False)),
                    skip_scanned=not bool(opts.get("force_rescan")),
                    force_rescan=bool(opts.get("force_rescan")),
                    persist=True,
                    detector=detector,
                    on_hit=on_hit,
                    on_photo=on_photo,
                    on_scored=on_scored,
                )
            except Exception as e:
                err = e
                self._deepface_scan_log_msg(f"ERROR: {e}")

            def done():
                self._deepface_scan_set_busy(False)
                # Prefer live list; fall back to final return value
                if hits and not getattr(self, "_df_scan_hits", None):
                    self._df_scan_hits = list(hits)
                elif hits:
                    # Ensure export list is complete (deduped final set)
                    self._df_scan_hits = list(hits)
                n = len(getattr(self, "_df_scan_hits", []) or [])
                try:
                    if err:
                        self.df_scan_status.configure(
                            text=f"Failed: {err}",
                            text_color=C["danger"],
                        )
                        self.df_scan_progress.set(0)
                    elif getattr(self, "_df_scan_cancel", False):
                        self.df_scan_status.configure(
                            text=f"Stopped — {n:,} hits",
                            text_color=C["accent"],
                        )
                    else:
                        self.df_scan_progress.set(1.0)
                        self.df_scan_status.configure(
                            text=f"Done — {n:,} hits",
                            text_color=C["success"],
                        )
                except Exception:
                    pass
                self._deepface_scan_log_msg(
                    f"Scan finished: {n} hits"
                    + (f" (error: {err})" if err else "")
                    + " — results stored; skipped photos stay skipped next run"
                )
                try:
                    self._deepface_scan_refresh_db_stats()
                except Exception:
                    pass
                # After scan: open first unreviewed hit for review
                try:
                    if n and getattr(self, "_df_scan_live_preview", True):
                        self.after(80, self._deepface_scan_next_unreviewed)
                except Exception:
                    pass

            try:
                self.after(0, done)
            except Exception:
                pass

        threading.Thread(target=worker, name="deepface-scan", daemon=True).start()


