"""CAPTCHA"""
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


class SettingsCaptchaMixin:
    def _settings_refresh_captcha_queue(self) -> None:
        try:
            from scraper.cookie_jar import CaptchaQueue, CookieJarStore

            q = CaptchaQueue()
            items = q.list_items()
            jar = CookieJarStore()
            hosts = jar.summary()
            host_txt = ", ".join(f"{h}({n})" for h, n in list(hosts.items())[:6]) or "none"
            if not items:
                self.settings_captcha_status.configure(
                    text=f"Queue empty · saved cookie hosts: {host_txt}"
                )
            else:
                last = items[-1]
                self.settings_captcha_status.configure(
                    text=(
                        f"Queued: {len(items)} · latest [{last.get('jurisdiction') or '?'}] "
                        f"{last.get('reason')}: {(last.get('url') or '')[:70]}… · "
                        f"cookies: {host_txt}"
                    )
                )
        except Exception as e:
            if hasattr(self, "settings_captcha_status"):
                self.settings_captcha_status.configure(text=f"Queue error: {e}")


    def _settings_open_next_captcha(self) -> None:
        try:
            from scraper.cookie_jar import CaptchaQueue
            from scraper.browser_cookies import host_from_url

            q = CaptchaQueue()
            items = q.list_items()
            if not items:
                messagebox.showinfo("CAPTCHA queue", "No blocked URLs queued.")
                return
            item = items[-1]
            url = item.get("url") or ""
            if not url:
                messagebox.showinfo("CAPTCHA queue", "Queued item has no URL.")
                return
            webbrowser.open(url)
            try:
                q.mark_opened(url)
            except Exception:
                pass
            host = host_from_url(url)
            try:
                if host and hasattr(self, "settings_cookie_domain"):
                    self.settings_cookie_domain.set(host)
            except Exception:
                pass
            self.settings_captcha_status.configure(
                text=(
                    f"Opened in browser — complete the challenge, then wait "
                    f"(auto-pull cookies for {host or 'host'}). {url[:55]}…"
                )
            )
            self._settings_start_cookie_autopull(url)
        except Exception as e:
            messagebox.showerror("Open URL", str(e))


    def _settings_open_captcha_batch(self) -> None:
        try:
            from scraper.cookie_jar import CaptchaQueue
            from scraper.browser_cookies import host_from_url

            q = CaptchaQueue()
            items = q.list_items()
            if not items:
                messagebox.showinfo("CAPTCHA queue", "No blocked URLs queued.")
                return
            opened_urls: List[str] = []
            for item in reversed(items[-5:]):
                url = item.get("url") or ""
                if url:
                    webbrowser.open(url)
                    try:
                        q.mark_opened(url)
                    except Exception:
                        pass
                    opened_urls.append(url)
            self.settings_captcha_status.configure(
                text=(
                    f"Opened {len(opened_urls)} blocked URL(s). "
                    "Complete challenges — auto-pulling cookies…"
                )
            )
            # Autopull for each host (sequentially polled)
            for url in opened_urls:
                self._settings_start_cookie_autopull(url, join_existing=True)
            if opened_urls:
                try:
                    host = host_from_url(opened_urls[0])
                    if host and hasattr(self, "settings_cookie_domain"):
                        self.settings_cookie_domain.set(host)
                except Exception:
                    pass
        except Exception as e:
            messagebox.showerror("Open URLs", str(e))


    def _settings_clear_captcha_queue(self) -> None:
        try:
            from scraper.cookie_jar import CaptchaQueue

            self._cookie_autopull_stop = True
            CaptchaQueue().clear()
            self._settings_refresh_captcha_queue()
            if hasattr(self, "settings_cookie_pull_status"):
                self.settings_cookie_pull_status.configure(text="")
        except Exception as e:
            messagebox.showerror("Clear queue", str(e))


