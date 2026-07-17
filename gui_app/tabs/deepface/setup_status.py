"""SetupStatus"""
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


class DeepfaceSetupStatusMixin:
    def _deepface_refresh_status(self) -> None:
        """Update status labels. Keras/TF probe runs off the UI thread."""
        if not hasattr(self, "df_status_installed"):
            return
        if getattr(self, "_df_status_busy", False):
            return
        self._df_status_busy = True

        # Fast UI-thread updates only (no heavy imports)
        try:
            import importlib.util

            pkg_df = importlib.util.find_spec("deepface") is not None
            pkg_ff = importlib.util.find_spec("face_race") is not None
        except Exception:
            pkg_df = False
            pkg_ff = False
        pkg = pkg_ff or pkg_df

        try:
            self.df_status_installed.configure(
                text=(
                    "Installed: package found — checking runtime…"
                    if pkg
                    else "Installed: No (need face-race and/or DeepFace)"
                ),
                text_color=C["accent"] if pkg else C["danger"],
            )
            self.df_status_backend.configure(
                text="Preferred backend: checking…",
                text_color=C["dim"],
            )
            self.df_status_backends.configure(text="Available: …")
        except Exception:
            pass

        ff_home = Path.home() / ".face_race" / "weights"
        df_home = Path.home() / ".deepface" / "weights"

        def _cache_line(label: str, home: Path) -> str:
            try:
                if home.is_dir():
                    files = [f for f in home.glob("*") if f.is_file()]
                    n = len(files)
                    size = sum(f.stat().st_size for f in files)
                    mb = size / (1024 * 1024)
                    return f"{label}: {home}  ·  {n} files  ·  {mb:.1f} MB"
                return f"{label}: not created yet ({home})"
            except Exception:
                return f"{label}: {home}"

        try:
            self.df_status_weights.configure(
                text=(
                    _cache_line("FairFace weights", ff_home)
                    + "  |  "
                    + _cache_line("DeepFace cache", df_home)
                )
            )
        except Exception:
            pass

        skip = os.environ.get("SOR_SKIP_DEEPFACE_INSTALL", "").strip().lower() in (
            "1", "true", "yes",
        )
        if skip and hasattr(self, "df_job_status"):
            try:
                self.df_job_status.configure(
                    text="Note: SOR_SKIP_DEEPFACE_INSTALL is set — auto-install disabled in env"
                )
            except Exception:
                pass

        def worker() -> None:
            df_runtime_ok = False
            df_runtime_detail = "check failed"
            backends: Dict[str, bool] = {}
            err: Optional[str] = None
            try:
                # Import setup directly — avoid package side effects
                from scraper.mugshot_ethnicity.setup import deepface_runtime_ok
                from scraper.mugshot_ethnicity.scorer import get_available_backends

                df_runtime_ok, df_runtime_detail = deepface_runtime_ok()
                backends = get_available_backends()
            except Exception as e:
                err = str(e)

            def apply() -> None:
                self._df_status_busy = False
                if not hasattr(self, "df_status_installed"):
                    return
                try:
                    if err:
                        self.df_status_installed.configure(
                            text=f"Installed: error ({err})",
                            text_color=C["danger"],
                        )
                        return
                    ff_ok = bool(backends.get("fairface"))
                    df_ok = bool(df_runtime_ok and backends.get("deepface"))
                    if ff_ok:
                        inst_txt = "Installed: FairFace ready (primary)"
                        if df_ok:
                            inst_txt += " · DeepFace fallback OK"
                        inst_col = C["success"]
                    elif df_ok:
                        inst_txt = "Installed: DeepFace ready (FairFace missing)"
                        inst_col = C["accent"]
                    elif pkg:
                        inst_txt = (
                            f"Installed: package present but broken — {df_runtime_detail}"
                        )
                        inst_col = C["danger"]
                    else:
                        inst_txt = "Installed: No"
                        inst_col = C["danger"]
                    self.df_status_installed.configure(
                        text=inst_txt, text_color=inst_col
                    )
                    # Scan default is auto: FairFace → DeepFace → CLIP
                    if ff_ok:
                        be = "fairface (default)"
                        col = C["success"]
                    elif df_ok:
                        be = "deepface (fallback — install face-race for FairFace)"
                        col = C["accent"]
                    elif backends.get("clip"):
                        be = "clip (last resort)"
                        col = C["accent"]
                    else:
                        be = "none — install face-race (FairFace) or DeepFace"
                        col = C["danger"]
                    self.df_status_backend.configure(
                        text=f"Preferred backend: {be}", text_color=col
                    )
                    parts = [
                        f"{k}={'yes' if v else 'no'}"
                        for k, v in sorted(backends.items())
                    ]
                    self.df_status_backends.configure(
                        text="Available: " + ", ".join(parts)
                    )
                    try:
                        self._deepface_refresh_download_badges()
                    except Exception:
                        pass
                except Exception:
                    pass

            try:
                self.after(0, apply)
            except Exception:
                self._df_status_busy = False

        threading.Thread(
            target=worker, name="deepface-status", daemon=True
        ).start()


    def _deepface_selected_weight_ids(self) -> List[str]:
        ids = ["Race"]
        for mid, var in getattr(self, "_df_weight_vars", {}).items():
            try:
                if bool(var.get()) and mid not in ids:
                    ids.append(mid)
            except Exception:
                pass
        return ids


    def _deepface_selected_detector_id(self) -> str:
        label = ""
        try:
            label = (self.df_detector_var.get() or "").strip()
        except Exception:
            pass
        return (getattr(self, "_df_det_id_by_label", {}) or {}).get(label, "retinaface")


    def _deepface_on_detector_change(self, _choice: str = "") -> None:
        from scraper.mugshot_ethnicity.weights_catalog import (
            detector_local_status,
            explain_detector,
        )

        det = self._deepface_selected_detector_id()
        try:
            self.df_detector_help.configure(text=explain_detector(det))
        except Exception:
            pass
        try:
            st = detector_local_status(det)
            if hasattr(self, "df_detector_status"):
                self.df_detector_status.configure(
                    text=st.get("label") or "",
                    text_color=C["success"] if st.get("downloaded") else C["danger"],
                )
        except Exception:
            pass
        self._deepface_save_options()


    def _deepface_refresh_download_badges(self) -> None:
        """Update per-weight / detector “Downloaded” badges from the local cache."""
        try:
            from scraper.mugshot_ethnicity.weights_catalog import (
                DETECTOR_OPTIONS,
                detector_dropdown_label,
                detector_local_status,
                weight_local_status,
            )
        except Exception:
            return

        # Weight cards
        for mid, lbl in list(getattr(self, "_df_weight_status_labels", {}).items()):
            try:
                st = weight_local_status(mid)
                ok = bool(st.get("downloaded"))
                text = st.get("label") or ("Downloaded" if ok else "Not downloaded")
                lbl.configure(
                    text=("✓ " + text) if ok else text,
                    text_color=C["success"] if ok else C["danger"],
                )
            except Exception:
                pass

        # Detector dropdown values + badge (preserve selected id)
        det = self._deepface_selected_detector_id()
        try:
            det_labels = [detector_dropdown_label(d) for d in DETECTOR_OPTIONS]
            det_id_by_label = {
                detector_dropdown_label(d): d["id"] for d in DETECTOR_OPTIONS
            }
            label_by_det_id = {
                d["id"]: detector_dropdown_label(d) for d in DETECTOR_OPTIONS
            }
            self._df_det_id_by_label = det_id_by_label
            self._df_label_by_det_id = label_by_det_id
            new_label = label_by_det_id.get(det, det_labels[0] if det_labels else "")
            if hasattr(self, "df_detector_combo"):
                self.df_detector_combo.configure(values=det_labels)
            if hasattr(self, "df_detector_var") and new_label:
                self.df_detector_var.set(new_label)
            st = detector_local_status(det)
            if hasattr(self, "df_detector_status"):
                self.df_detector_status.configure(
                    text=st.get("label") or "",
                    text_color=C["success"] if st.get("downloaded") else C["danger"],
                )
        except Exception:
            pass


    def _deepface_on_weight_toggle(self, model_id: str = "") -> None:
        from scraper.mugshot_ethnicity.weights_catalog import explain_weight

        mid = model_id or "Race"
        # Race always on
        if mid == "Race" and mid in getattr(self, "_df_weight_vars", {}):
            try:
                self._df_weight_vars["Race"].set(True)
            except Exception:
                pass
        try:
            self.df_weight_help.configure(text=explain_weight(mid))
        except Exception:
            pass
        self._deepface_save_options()


