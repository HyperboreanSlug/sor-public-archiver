"""NSOPW tree append/select."""
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


class NsopwTreeRowsMixin:
    def _nsopw_append_row(self, record: Dict[str, Any]) -> None:
        """UI-thread: route insert into ethnicity-match or other-surnames table."""
        name = (
            (record.get("full_name") or "").strip()
            or f"{record.get('first_name') or ''} {record.get('last_name') or ''}".strip()
        )
        race = (record.get("race") or "").strip()
        eth = (record.get("ethnicity") or "").strip()
        race_disp = race
        if eth and eth.lower() != race.lower():
            race_disp = f"{race} / {eth}" if race else eth
        if not race_disp:
            race_disp = "—"
        photo_path = (record.get("photo_path") or "").strip()
        photo_mark = "yes" if photo_path and Path(photo_path).is_file() else (
            "url" if (record.get("photo_url") or "").strip() else "—"
        )
        crime = (
            (record.get("crime") or record.get("offense_description") or record.get("offense_type") or "")
            .strip()
            or "—"
        )
        vals = (
            name,
            record.get("state") or record.get("source_state") or "",
            race_disp,
            crime,
            photo_mark,
            record.get("source_url") or "",
            record.get("report_html_path") or "",
        )

        bucket = (record.get("nsopw_result_bucket") or "").strip().lower()
        if not bucket:
            # Fallback from flags JSON if builder field missing
            try:
                flags = record.get("flags")
                fl = json.loads(flags) if isinstance(flags, str) else (flags or [])
                if "other_surname" in fl:
                    bucket = "other"
                else:
                    bucket = "matched"
            except Exception:
                bucket = "matched"
        is_other = bucket == "other"
        tree = self.nsopw_tree_other if is_other else self.nsopw_tree

        sort_state = getattr(tree, "_sort_state", None) or {}
        if sort_state.get("col"):
            iid = tree.insert("", "end", values=vals)
        else:
            iid = tree.insert("", 0, values=vals)
        self._nsopw_records_by_iid[iid] = dict(record)
        if photo_path:
            self._nsopw_photo_by_iid[iid] = photo_path
        # Cap live table size
        kids = tree.get_children()
        if len(kids) > 200:
            for drop in kids[200:]:
                self._nsopw_photo_by_iid.pop(drop, None)
                self._nsopw_records_by_iid.pop(drop, None)
                tree.delete(drop)
        reapply = getattr(tree, "_reapply_sort", None)
        if callable(reapply) and sort_state.get("col"):
            reapply()

        if is_other:
            self._nsopw_other_count += 1
        else:
            self._nsopw_insert_count += 1
        # Keep chip stats in sync with live inserts (progress callback may lag)
        if hasattr(self, "_nsopw_stat_vars"):
            try:
                self._nsopw_stat_vars["matched"].configure(text=str(self._nsopw_insert_count))
                self._nsopw_stat_vars["other"].configure(text=str(self._nsopw_other_count))
            except Exception:
                pass
        # Do not wipe the current-search line — keep last query terms visible
        terms = getattr(self, "_nsopw_last_search_terms", "") or ""
        if terms:
            self.nsopw_status.configure(
                text=(
                    f"Running… {terms} · matched {self._nsopw_insert_count} · "
                    f"other {self._nsopw_other_count} (live)"
                )
            )
        else:
            self.nsopw_status.configure(
                text=(
                    f"Running… matched {self._nsopw_insert_count} · "
                    f"other surnames {self._nsopw_other_count} (live)"
                )
            )


    def _nsopw_on_tree_select(self, event=None):
        tree = event.widget if event is not None else self.nsopw_tree
        sel = tree.selection() if isinstance(tree, ttk.Treeview) else ()
        if not sel:
            return
        iid = sel[0]
        rec = self._nsopw_records_by_iid.get(iid)
        if rec is None:
            rec = {}
        # Attach photo from map / HTML assets if missing
        path = self._nsopw_photo_by_iid.get(iid) or (rec.get("photo_path") or "").strip()
        if not path or not Path(path).is_file():
            vals = tree.item(iid, "values")
            html_path = vals[-1] if len(vals) >= 5 else ""
            if html_path and html_path != "—":
                hp = Path(str(html_path))
                assets = hp.parent / f"{hp.stem}_assets"
                if assets.is_dir():
                    for cand in sorted(assets.iterdir()):
                        if cand.suffix.lower() in (
                            ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"
                        ) and cand.stat().st_size > 80:
                            path = str(cand)
                            self._nsopw_photo_by_iid[iid] = path
                            rec = dict(rec)
                            rec["photo_path"] = path
                            self._nsopw_records_by_iid[iid] = rec
                            break
        elif path and not rec.get("photo_path"):
            rec = dict(rec)
            rec["photo_path"] = path
            self._nsopw_records_by_iid[iid] = rec
        if getattr(self, "nsopw_detail", None) is not None:
            self._fill_detail_drawer(self.nsopw_detail, rec or None)


