"""Settings shell: nested General + Scrape sub-tabs."""
from __future__ import annotations

from typing import Optional

import customtkinter as ctk

from gui_app.lazy_tabs import LazyTabHost
from gui_app.theme import C


class SettingsShellMixin:
    def _build_settings(self, tab):
        """Settings host with General (prefs) and Scrape (bulk registries)."""
        tab.configure(fg_color=C["surface"])
        sub = ctk.CTkTabview(
            tab,
            fg_color=C["surface"],
            segmented_button_fg_color=C["elevated"],
            segmented_button_selected_color=C["accent_dim"],
            segmented_button_selected_hover_color=C["select"],
            segmented_button_unselected_color=C["elevated"],
            segmented_button_unselected_hover_color=C["panel"],
            text_color=C["text"],
            corner_radius=10,
            border_width=0,
        )
        sub.pack(fill="both", expand=True, padx=6, pady=6)
        self.settings_tabs = sub

        host = LazyTabHost(sub, on_change=self._on_settings_subtab_change)
        self._settings_lazy = host
        host.register(
            "General", lambda p: self._build_settings_general(p) or True
        )
        host.register("Scrape", lambda p: self._build_scrape(p) or True)

        try:
            sub.set("General")
        except Exception:
            pass
        host.ensure("General")
        return host

    def _on_settings_subtab_change(self, name: Optional[str] = None) -> None:
        try:
            name = name or self.settings_tabs.get()
        except Exception:
            name = "General"
        if name == "General" and hasattr(self, "_settings_refresh_status"):
            try:
                self._settings_refresh_status()
            except Exception:
                pass
        # Activity log visibility depends on Scrape sub-tab
        try:
            self._on_main_tab_change("Settings")
        except Exception:
            pass

    def _settings_scrape_active(self) -> bool:
        """True when Settings → Scrape is the visible sub-tab."""
        try:
            if self.tabs.get() != "Settings":
                return False
        except Exception:
            return False
        try:
            return (self.settings_tabs.get() or "") == "Scrape"
        except Exception:
            return False
