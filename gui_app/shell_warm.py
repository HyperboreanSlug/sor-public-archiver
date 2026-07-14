"""Idle-preload lazy tabs so first click is near-instant."""
from __future__ import annotations

from typing import List, Optional, Tuple


class ShellWarmMixin:
    """After first paint, build remaining tab bodies in small idle steps."""

    def _schedule_tab_warmup(self) -> None:
        """Kick off background tab builds once the window is interactive."""
        if getattr(self, "_tab_warm_started", False):
            return
        self._tab_warm_started = True
        # Let Browse + first paint settle, then warm one tab at a time
        try:
            self.after(450, self._tab_warm_step)
        except Exception:
            pass

    def _tab_warm_queue(self) -> List[Tuple[str, str]]:
        """(host_attr, tab_name) jobs. host_attr '' = main lazy host."""
        jobs: List[Tuple[str, str]] = []
        # Main tabs (Browse already ensured at startup)
        for name in ("NSOPW", "DeepFace", "Settings"):
            jobs.append(("", name))
        # Nested Browse sub-tabs (Search already loaded with Browse)
        for name in (
            "Integrity",
            "Misclassify",
            "Statistics",
            "Reports",
            "DeepFace",
        ):
            jobs.append(("_browse_lazy", name))
        # Settings nested (General built when Settings warms; then Scrape)
        jobs.append(("_settings_lazy", "Scrape"))
        # DeepFace nested Setup after Scan
        jobs.append(("_deepface_lazy", "Setup"))
        return jobs

    def _tab_warm_step(self) -> None:
        if getattr(self, "_closing", False):
            return
        q = getattr(self, "_tab_warm_jobs", None)
        if q is None:
            self._tab_warm_jobs = self._tab_warm_queue()
            q = self._tab_warm_jobs
        if not q:
            return
        host_attr, name = q.pop(0)
        try:
            host = (
                getattr(self, "_main_lazy", None)
                if not host_attr
                else getattr(self, host_attr, None)
            )
            if host is not None and hasattr(host, "warm"):
                if not host.is_loaded(name):
                    host.warm(name)
        except Exception:
            pass
        # Yield to the event loop between heavy CTk builds
        try:
            self.after(80, self._tab_warm_step)
        except Exception:
            pass
