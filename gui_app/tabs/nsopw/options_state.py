"""NSOPW state filter dropdown UI."""
from __future__ import annotations

from typing import Dict, List, Optional

import customtkinter as ctk

from gui_app.theme import C, FONT_SM
from gui_app.tabs.nsopw.state_stats import build_state_dropdown_values


class NsopwStateMixin:
    """State filter UI + jurisdiction selection for NSOPW Start."""

    def _nsopw_ensure_state_var(self) -> None:
        if not hasattr(self, "nsopw_state_var"):
            self.nsopw_state_var = ctk.StringVar(value="")
        if not hasattr(self, "_nsopw_state_map"):
            self._nsopw_state_map: Dict[str, Optional[List[str]]] = {}

    def _nsopw_refresh_state_dropdown(self) -> None:
        """Rebuild state combo labels from DB counts + scrape accessibility."""
        self._nsopw_ensure_state_var()
        db_path = str(
            getattr(self, "nsopw_db_path", None)
            or getattr(self, "db_path", None)
            or "data/offenders.db"
        )
        values, mapping = build_state_dropdown_values(db_path)
        self._nsopw_state_map = mapping
        prev = (self.nsopw_state_var.get() or "").strip()
        keep = values[0]
        if prev:
            prev_code = prev.split("·", 1)[0].strip().upper()
            for v in values:
                if v.split("·", 1)[0].strip().upper() == prev_code:
                    keep = v
                    break
            if prev in mapping:
                keep = prev if prev in values else keep
        if hasattr(self, "nsopw_state_combo"):
            self.nsopw_state_combo.configure(values=values)
        self.nsopw_state_var.set(keep)

    def _nsopw_selected_jurisdictions(self) -> Optional[List[str]]:
        """None = all jurisdictions; else one-element list of state code."""
        self._nsopw_ensure_state_var()
        label = (self.nsopw_state_var.get() or "").strip()
        if not label:
            return None
        mapping = getattr(self, "_nsopw_state_map", {}) or {}
        if label in mapping:
            return mapping[label]
        code = label.split("·", 1)[0].strip().upper()
        if code in ("ALL", "ALL STATES", ""):
            return None
        if len(code) >= 2:
            return [code]
        return None

    def _nsopw_build_state_filter(self, parent) -> None:
        """Add State dropdown under Search scope."""
        self._nsopw_ensure_state_var()
        ctk.CTkLabel(
            parent,
            text="State",
            font=FONT_SM,
            text_color=C["muted"],
            anchor="w",
        ).pack(fill="x", pady=(6, 1))
        self.nsopw_state_combo = ctk.CTkComboBox(
            parent,
            variable=self.nsopw_state_var,
            values=["All · scrape:mixed · 0 enriched / 0 total"],
            fg_color=C["bg"],
            border_color=C["border"],
            button_color=C["elevated"],
            text_color=C["text"],
            dropdown_fg_color=C["panel"],
            dropdown_text_color=C["text"],
            # Longest labels: AMERICANSAMOA · scrape:limited · N enriched / M total
            width=300,
            height=28,
        )
        self.nsopw_state_combo.pack(fill="x")
        ctk.CTkLabel(
            parent,
            text=(
                "Limits NSOPW search to one jurisdiction. "
                "scrape:yes = bulk path · limited = NSOPW/search only. "
                "Counts = enriched / total in local DB."
            ),
            font=FONT_SM,
            text_color=C["dim"],
            anchor="w",
            wraplength=280,
            justify="left",
        ).pack(fill="x", pady=(2, 0))
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=(4, 0))
        ctk.CTkButton(
            row,
            text="Refresh counts",
            width=120,
            height=26,
            fg_color=C["elevated"],
            hover_color=C["border"],
            text_color=C["text"],
            border_width=1,
            border_color=C["border"],
            command=self._nsopw_refresh_state_dropdown,
        ).pack(side="left")
        try:
            self._nsopw_refresh_state_dropdown()
        except Exception:
            fallback = "All · scrape:mixed · 0 enriched / 0 total"
            self.nsopw_state_var.set(fallback)
            self._nsopw_state_map = {fallback: None}
