"""Overall (total) progress for public DB sync/publish UI and logs."""
from __future__ import annotations

from typing import Callable, List, Optional


class OverallProgress:
    """Byte-weighted progress that logs messages ending in ``(N%)`` for the UI bar."""

    def __init__(
        self,
        total: int = 0,
        log: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.total = max(int(total), 0)
        self.done = 0
        self.log = log
        self._last_pct = -1
        self._file_base = 0
        self._file_weight = 0

    def ensure_total(self, minimum: int) -> None:
        if minimum > self.total:
            self.total = int(minimum)

    def add_total(self, n: int) -> None:
        self.total = max(0, self.total + int(n))

    @property
    def pct(self) -> float:
        if self.total <= 0:
            return 0.0
        return 100.0 * min(self.done, self.total) / self.total

    def report(self, msg: str, *, force: bool = False) -> None:
        total = max(self.total, 1)
        pct = int(round(100.0 * min(self.done, total) / total))
        pct = max(0, min(100, pct))
        if not force and pct == self._last_pct:
            return
        self._last_pct = pct
        text = f"{msg} ({pct}%)" if msg else f"{pct}%"
        if self.log:
            try:
                self.log(text)
            except Exception:
                pass

    def advance(self, n: int, msg: str = "", *, force: bool = False) -> None:
        self.done = max(0, self.done + int(n))
        if msg or force:
            self.report(msg, force=bool(msg) or force)

    def begin_file(self, weight: int) -> None:
        """Start a sub-file whose download contributes *weight* bytes to overall."""
        self._file_base = self.done
        self._file_weight = max(0, int(weight))

    def update_file(
        self,
        written: int,
        file_total: Optional[int],
        msg: str,
        *,
        min_step: int = 1,
    ) -> None:
        """Map in-file progress into the reserved weight window."""
        w = self._file_weight
        if w <= 0:
            self.report(msg)
            return
        if file_total and file_total > 0:
            frac = min(1.0, max(0.0, float(written) / float(file_total)))
            target = self._file_base + int(w * frac)
        else:
            # Unknown size: creep up to 90% of weight by raw bytes
            target = self._file_base + min(w * 9 // 10, max(0, int(written)))
        if target < self.done and written > 0:
            return
        prev_pct = self._last_pct
        self.done = target
        # Throttle to whole-percent updates unless forced by caller message change
        pct = int(round(self.pct))
        if pct != prev_pct or min_step == 0:
            self.report(msg, force=True)

    def finish_file(self, msg: str = "") -> None:
        target = self._file_base + self._file_weight
        if target > self.done:
            self.done = target
        self._file_weight = 0
        if msg:
            self.report(msg, force=True)

    def complete(self, msg: str = "Done") -> None:
        if self.total > 0:
            self.done = self.total
        self.report(msg, force=True)


def estimate_sync_weights(
    *,
    need_base: bool,
    remote: Optional[dict],
    pending: List,
    need_photos: List,
) -> tuple:
    """Return (base_w, delta_ws, photo_ws, extract_w, install_w) for OverallProgress."""
    base_w = 0
    if need_base:
        base_w = int((remote or {}).get("size_bytes") or 0) or 120_000_000
    delta_ws = [
        int(d.get("size_bytes") or 0) or 2_000_000
        for d in pending
        if isinstance(d, dict)
    ]
    photo_ws = [
        int(p.get("size_bytes") or 0) or 50_000_000
        for p in need_photos
        if isinstance(p, dict)
    ]
    return base_w, delta_ws, photo_ws, sum(photo_ws) // 7, (5_000_000 if need_base else 0)
