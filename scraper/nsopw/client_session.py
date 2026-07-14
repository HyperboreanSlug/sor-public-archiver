"""NSOPW client session / warm-up mixin."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from scraper.nsopw.client_types import (
    DEFAULT_DELAY,
    NSOPW_SEARCH_PAGE,
    REQUEST_TIMEOUT,
    _make_http_session,
)


class NSOPWClientSessionMixin:
    def __init__(self, delay: float = DEFAULT_DELAY, timeout: float = REQUEST_TIMEOUT):
        self.delay = max(0.0, float(delay))
        self.timeout = timeout
        self.session, self.http_backend = _make_http_session()
        self._warmed = False

    def close(self) -> None:
        try:
            self.session.close()
        except Exception:
            pass

    def _token(self) -> str:
        """Same-day validation token (MM/DD/YYYY), as used by NSOPW clients."""
        return datetime.now().strftime("%m/%d/%Y")

    def _ensure_warm(self) -> None:
        """Hit the public search page once so Origin/Referer look organic."""
        if self._warmed:
            return
        try:
            self.session.get(
                NSOPW_SEARCH_PAGE,
                timeout=min(30.0, float(self.timeout)),
                headers={
                    "Accept": (
                        "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
                    ),
                },
            )
        except Exception:
            pass
        self._warmed = True
