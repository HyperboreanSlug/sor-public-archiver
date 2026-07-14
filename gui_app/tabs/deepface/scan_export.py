"""Export"""
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


class DeepfaceScanExportMixin:
    def _deepface_scan_export(self) -> None:
        hits = list(getattr(self, "_df_scan_hits", []) or [])
        if not hits:
            self._deepface_scan_log_msg("No hits to export")
            return
        path = filedialog.asksaveasfilename(
            title="Export DeepFace scan hits",
            defaultextension=".csv",
            filetypes=[
                ("CSV", "*.csv"),
                ("JSON", "*.json"),
                ("All", "*.*"),
            ],
            initialfile=f"deepface_scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        )
        if not path:
            return
        try:
            p = Path(path)
            if p.suffix.lower() == ".json":
                import json

                p.write_text(
                    json.dumps([h.to_dict() for h in hits], indent=2),
                    encoding="utf-8",
                )
            else:
                with open(p, "w", newline="", encoding="utf-8") as f:
                    w = csv.writer(f)
                    w.writerow([
                        "id", "name", "state", "recorded_race", "predicted_label",
                        "confidence", "severity", "reason", "photo_path",
                    ])
                    for h in hits:
                        rec = h.record or {}
                        w.writerow([
                            rec.get("id"),
                            f"{rec.get('first_name') or ''} {rec.get('last_name') or ''}".strip(),
                            rec.get("state"),
                            h.recorded_race,
                            h.predicted_label,
                            f"{h.confidence:.4f}",
                            h.severity,
                            h.reason,
                            getattr(h.face, "photo_path", None),
                        ])
            self._deepface_scan_log_msg(f"Exported {len(hits)} hits → {p}")
        except Exception as e:
            self._deepface_scan_log_msg(f"Export failed: {e}")


