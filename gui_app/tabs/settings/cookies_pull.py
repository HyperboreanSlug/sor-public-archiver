"""CookiePull"""
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


class SettingsCookiePullMixin:
    def _settings_start_cookie_autopull(
        self,
        url: str,
        *,
        duration_s: float = 180.0,
        interval_s: float = 4.0,
        join_existing: bool = False,
    ) -> None:
        """After opening a blocked URL, poll browser cookie DBs and import matches."""
        import threading
        import time

        url = (url or "").strip()
        if not url:
            return

        # Track multiple hosts when batch-opening
        pending = getattr(self, "_cookie_autopull_urls", None)
        if pending is None:
            self._cookie_autopull_urls = []
            pending = self._cookie_autopull_urls
        if url not in pending:
            pending.append(url)
        self._cookie_autopull_url = url
        self._cookie_autopull_stop = False

        thr = getattr(self, "_cookie_autopull_thread", None)
        if thr is not None and thr.is_alive():
            if join_existing:
                return  # worker already looping pending list
            # Restart: stop old then start new
            self._cookie_autopull_stop = True
            try:
                thr.join(timeout=0.5)
            except Exception:
                pass
            self._cookie_autopull_stop = False

        def worker() -> None:
            from scraper.browser_cookies import host_from_url, pull_and_store
            from scraper.cookie_jar import CaptchaQueue

            deadline = time.time() + float(duration_s)
            last_status = ""
            success_hosts: set = set()
            try:
                while time.time() < deadline and not getattr(
                    self, "_cookie_autopull_stop", False
                ):
                    urls = list(getattr(self, "_cookie_autopull_urls", []) or [url])
                    any_new = False
                    for u in urls:
                        if getattr(self, "_cookie_autopull_stop", False):
                            break
                        host = host_from_url(u)
                        if not host or host in success_hosts:
                            continue
                        try:
                            result = pull_and_store(u)
                        except Exception as e:
                            msg = f"Cookie pull error ({host}): {e}"
                            if msg != last_status:
                                last_status = msg
                                try:
                                    self.after(
                                        0,
                                        lambda m=msg: self._settings_set_cookie_pull_status(
                                            m, color=C["danger"]
                                        ),
                                    )
                                except Exception:
                                    pass
                            continue
                        n = int(result.get("imported") or result.get("count") or 0)
                        notes = "; ".join(result.get("notes") or [])[:120]
                        if n > 0:
                            success_hosts.add(host)
                            any_new = True
                            try:
                                CaptchaQueue().mark_cookies_pulled(u, n)
                            except Exception:
                                pass
                            msg = (
                                f"Auto-pulled {n} cookie(s) for {host}. "
                                f"Requeue incomplete reports to retry. ({notes})"
                            )
                            last_status = msg

                            def ui_ok(m=msg, h=host, count=n):
                                self._settings_set_cookie_pull_status(
                                    m, color=C["success"]
                                )
                                try:
                                    self.settings_cookie_status.configure(
                                        text=f"Browser pull: {count} cookie(s) → {h}"
                                    )
                                except Exception:
                                    pass
                                self._settings_refresh_captcha_queue()

                            try:
                                self.after(0, ui_ok)
                            except Exception:
                                pass
                        else:
                            msg = (
                                f"Watching browser cookies for {host}… "
                                f"complete CAPTCHA in Chrome/Edge, leave the tab open. "
                                f"({notes or 'no cookies yet'})"
                            )
                            if msg != last_status:
                                last_status = msg
                                try:
                                    self.after(
                                        0,
                                        lambda m=msg: self._settings_set_cookie_pull_status(
                                            m, color=C["dim"]
                                        ),
                                    )
                                except Exception:
                                    pass
                    if success_hosts and len(success_hosts) >= len(
                        {host_from_url(u) for u in urls if host_from_url(u)}
                    ):
                        break
                    if any_new and len(urls) == 1:
                        break
                    time.sleep(float(interval_s))
            finally:
                if not success_hosts and not getattr(self, "_cookie_autopull_stop", False):
                    try:
                        self.after(
                            0,
                            lambda: self._settings_set_cookie_pull_status(
                                "Auto-pull timed out — complete the challenge, then click "
                                "“Pull cookies from browser”, or paste cookies manually.",
                                color=C["accent"],
                            ),
                        )
                    except Exception:
                        pass

        t = threading.Thread(
            target=worker, name="cookie-autopull", daemon=True
        )
        self._cookie_autopull_thread = t
        t.start()
        self._settings_set_cookie_pull_status(
            "Auto-pull started — complete the browser challenge; cookies will import when ready.",
            color=C["accent"],
        )


    def _settings_pull_browser_cookies_now(self) -> None:
        """One-shot pull from Chrome/Edge/Firefox for last opened / domain field."""
        import threading

        from scraper.browser_cookies import host_from_url

        url = (getattr(self, "_cookie_autopull_url", None) or "").strip()
        if not url:
            try:
                from scraper.cookie_jar import CaptchaQueue

                item = CaptchaQueue().peek_next()
                if item:
                    url = (item.get("url") or "").strip()
            except Exception:
                pass
        if not url:
            domain = ""
            try:
                domain = (self.settings_cookie_domain.get() or "").strip()
            except Exception:
                pass
            url = domain
        if not url:
            messagebox.showinfo(
                "Pull cookies",
                "Open a blocked URL first, or set Default domain to the site host "
                "(e.g. offender.fdle.state.fl.us).",
            )
            return

        host = host_from_url(url) or url
        self._settings_set_cookie_pull_status(
            f"Pulling cookies for {host}…", color=C["accent"]
        )

        def worker() -> None:
            try:
                from scraper.browser_cookies import pull_and_store
                from scraper.cookie_jar import CaptchaQueue

                result = pull_and_store(url)
                n = int(result.get("imported") or result.get("count") or 0)
                notes = "; ".join(result.get("notes") or [])[:160]
                if n > 0:
                    try:
                        CaptchaQueue().mark_cookies_pulled(url, n)
                    except Exception:
                        pass
                    msg = f"Pulled {n} cookie(s) for {host}. ({notes})"
                    color = C["success"]
                else:
                    msg = (
                        f"No cookies found for {host}. Finish the challenge in Chrome/Edge "
                        f"with the tab still open, then try again. ({notes})"
                    )
                    color = C["danger"]

                def ui():
                    self._settings_set_cookie_pull_status(msg, color=color)
                    try:
                        self.settings_cookie_status.configure(
                            text=msg if n else "No browser cookies imported"
                        )
                    except Exception:
                        pass
                    self._settings_refresh_captcha_queue()

                try:
                    self.after(0, ui)
                except Exception:
                    pass
            except Exception as e:
                try:
                    self.after(
                        0,
                        lambda: self._settings_set_cookie_pull_status(
                            f"Pull failed: {e}", color=C["danger"]
                        ),
                    )
                except Exception:
                    pass

        threading.Thread(
            target=worker, name="cookie-pull-now", daemon=True
        ).start()


