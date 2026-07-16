"""Retry helpers for SQLite lock / busy contention."""
from __future__ import annotations

import random
import sqlite3
import time
from typing import Callable, Optional, TypeVar

T = TypeVar("T")

# Default: many short waits so long enrich runs survive GUI/other writers.
DEFAULT_LOCK_ATTEMPTS = 12
DEFAULT_LOCK_BASE_DELAY = 0.35
DEFAULT_LOCK_MAX_DELAY = 8.0


def is_db_locked_error(exc: BaseException) -> bool:
    """True for sqlite busy / locked / related OperationalError messages."""
    if isinstance(exc, sqlite3.OperationalError):
        msg = str(exc).lower()
        return any(
            tok in msg
            for tok in (
                "database is locked",
                "database is busy",
                "database table is locked",
                "locked",
                "busy",
            )
        )
    msg = str(exc).lower()
    return "database is locked" in msg or "database is busy" in msg


def retry_on_db_lock(
    fn: Callable[[], T],
    *,
    attempts: int = DEFAULT_LOCK_ATTEMPTS,
    base_delay: float = DEFAULT_LOCK_BASE_DELAY,
    max_delay: float = DEFAULT_LOCK_MAX_DELAY,
    log: Optional[Callable[[str], None]] = None,
    what: str = "DB write",
) -> T:
    """
    Call *fn* until it succeeds or lock retries are exhausted.

    Uses exponential backoff with a small jitter between attempts.
    Non-lock errors are re-raised immediately.
    """
    tries = max(1, int(attempts))
    last: Optional[BaseException] = None
    for i in range(tries):
        try:
            return fn()
        except Exception as e:
            last = e
            if not is_db_locked_error(e) or i >= tries - 1:
                raise
            delay = min(max_delay, base_delay * (2**i))
            delay *= 0.75 + 0.5 * random.random()
            if log:
                try:
                    log(
                        f"{what}: database locked "
                        f"(attempt {i + 1}/{tries}), retry in {delay:.1f}s…"
                    )
                except Exception:
                    pass
            time.sleep(delay)
    assert last is not None
    raise last
