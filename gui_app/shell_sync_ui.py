"""Non-blocking top-right DB sync progress indicator for the shell header."""
from __future__ import annotations

import re
from typing import Optional

# Parse overall completion from log lines ending in "(45%)" or "… (45.2%)".
_PCT_RE = re.compile(r"\((\d{1,3}(?:\.\d+)?)%\s*\)\s*$")
# Fallback: any parenthesized percent in the message.
_PCT_ANY_RE = re.compile(r"\((\d{1,3}(?:\.\d+)?)%\)")


class ShellSyncUiMixin:
    """Header progress bar + total % label; never blocks the main UI."""

    def _build_header_sync_indicator(self, header) -> None:
        import customtkinter as ctk
        from gui_app.theme import C, FONT_SM

        self._db_sync_panel = ctk.CTkFrame(header, fg_color="transparent")
        # Not packed until sync starts

        self._db_sync_status_label = ctk.CTkLabel(
            self._db_sync_panel,
            text="Syncing database…",
            font=FONT_SM,
            text_color=C["accent"],
            anchor="e",
            width=220,
        )
        self._db_sync_status_label.pack(side="top", anchor="e", padx=(4, 0))

        bar_row = ctk.CTkFrame(self._db_sync_panel, fg_color="transparent")
        bar_row.pack(side="top", anchor="e", pady=(2, 0), padx=(4, 0))

        self._db_sync_progress = ctk.CTkProgressBar(
            bar_row,
            width=140,
            height=8,
            progress_color=C["accent"],
            fg_color=C["elevated"],
            corner_radius=4,
        )
        self._db_sync_progress.pack(side="left", padx=(0, 6))
        self._db_sync_progress.set(0)

        self._db_sync_pct_label = ctk.CTkLabel(
            bar_row,
            text="0%",
            font=FONT_SM,
            text_color=C["accent"],
            anchor="e",
            width=40,
        )
        self._db_sync_pct_label.pack(side="left")

        self._db_sync_ui_visible = False
        self._db_sync_indeterminate = False
        self._db_sync_last_pct: Optional[float] = None

    def _db_sync_set_pct(self, pct: float) -> None:
        """Update bar + percent label (main thread)."""
        pct = max(0.0, min(100.0, float(pct)))
        frac = pct / 100.0
        bar = getattr(self, "_db_sync_progress", None)
        if bar is not None:
            if getattr(self, "_db_sync_indeterminate", False):
                try:
                    bar.stop()
                except Exception:
                    pass
                self._db_sync_indeterminate = False
            bar.set(frac)
        lab = getattr(self, "_db_sync_pct_label", None)
        if lab is not None:
            try:
                lab.configure(text=f"{int(round(pct))}%")
            except Exception:
                pass
        self._db_sync_last_pct = pct

    def _db_sync_ui_show(self, message: str = "Syncing database…") -> None:
        if getattr(self, "_closing", False):
            return
        panel = getattr(self, "_db_sync_panel", None)
        if panel is None:
            return
        try:
            self._db_sync_ui_visible = True
            if not panel.winfo_ismapped():
                # before=stats → panel is rightmost among side=right widgets
                panel.pack(
                    side="right",
                    padx=(6, 10),
                    pady=4,
                    before=getattr(self, "stats_label", None),
                )
            self._db_sync_status_label.configure(text=(message or "Syncing…")[:72])
            bar = self._db_sync_progress
            bar.set(0)
            try:
                self._db_sync_pct_label.configure(text="0%")
            except Exception:
                pass
            self._db_sync_last_pct = 0.0
            try:
                bar.start()
                self._db_sync_indeterminate = True
            except Exception:
                self._db_sync_indeterminate = False
                bar.set(0.05)
            try:
                self.stats_label.configure(text="")
            except Exception:
                pass
        except Exception:
            pass

    def _db_sync_ui_update(self, message: str) -> None:
        """Thread-safe status/progress update (schedules onto UI thread)."""
        if getattr(self, "_closing", False):
            return
        msg = (message or "").strip()
        if not msg:
            return

        def apply() -> None:
            if getattr(self, "_closing", False):
                return
            if not getattr(self, "_db_sync_ui_visible", False):
                self._db_sync_ui_show(msg)
            # Prefer overall % at end of line; strip it from status for readability
            m = _PCT_RE.search(msg) or _PCT_ANY_RE.search(msg)
            short = msg
            if m:
                try:
                    self._db_sync_set_pct(float(m.group(1)))
                except Exception:
                    pass
                short = (msg[: m.start()] + msg[m.end() :]).strip(" -–—:")
            if len(short) > 56:
                short = "…" + short[-54:]
            try:
                self._db_sync_status_label.configure(text=short or msg[:56])
            except Exception:
                pass

        try:
            self.after(0, apply)
        except Exception:
            pass

    def _db_sync_ui_hide(self, final_message: Optional[str] = None) -> None:
        if getattr(self, "_closing", False):
            return
        panel = getattr(self, "_db_sync_panel", None)
        try:
            bar = getattr(self, "_db_sync_progress", None)
            if bar is not None and getattr(self, "_db_sync_indeterminate", False):
                try:
                    bar.stop()
                except Exception:
                    pass
            self._db_sync_indeterminate = False
            if panel is not None and panel.winfo_ismapped():
                panel.pack_forget()
            self._db_sync_ui_visible = False
            self._db_sync_last_pct = None
            if hasattr(self, "stats_label"):
                if final_message:
                    text = final_message.strip()
                    if len(text) > 72:
                        text = text[:69] + "…"
                    self.stats_label.configure(text=text or "Ready")
                else:
                    self.stats_label.configure(text="Ready")
        except Exception:
            pass

    def _db_sync_ui_complete_bar(self) -> None:
        """Fill bar to 100% before hide (main thread)."""
        try:
            self._db_sync_set_pct(100.0)
        except Exception:
            pass
