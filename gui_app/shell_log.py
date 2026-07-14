"""Channel-scoped activity log (Live Feed vs Full Scrape isolation)."""
from __future__ import annotations

import queue
from collections import deque
from typing import Deque, Dict, Optional, Tuple

# Channel keys written by log / log_live / log_full.
LOG_GLOBAL = "global"
LOG_RB_LIVE = "rb_live"
LOG_RB_FULL = "rb_full"

_MAX_LINES = 400


class ChannelLogMixin:
    """Buffers activity lines per channel; activity box shows the active channel only."""

    def _init_channel_log(self) -> None:
        self.log_queue: queue.Queue[Tuple[str, str]] = queue.Queue()
        self._log_buffers: Dict[str, Deque[str]] = {
            LOG_GLOBAL: deque(maxlen=_MAX_LINES),
            LOG_RB_LIVE: deque(maxlen=_MAX_LINES),
            LOG_RB_FULL: deque(maxlen=_MAX_LINES),
        }
        self._log_display_channel = LOG_GLOBAL

    def log(self, message: str, *, channel: Optional[str] = None) -> None:
        ch = channel or LOG_GLOBAL
        self.log_queue.put((ch, str(message)))

    def log_live(self, message: str) -> None:
        """Verbose Live Feed progress — only visible on the Live Feed sub-tab."""
        self.log(message, channel=LOG_RB_LIVE)

    def log_full(self, message: str) -> None:
        """Verbose Full Scrape progress — only visible on the Full Scrape sub-tab."""
        self.log(message, channel=LOG_RB_FULL)

    def _active_log_channel(self) -> str:
        try:
            main = self.tab_host.tabview.get()
        except Exception:
            return LOG_GLOBAL
        if main != "RecentlyBooked":
            return LOG_GLOBAL
        host = getattr(self, "_rb_tab_host", None)
        try:
            sub = host.tabview.get() if host is not None else "Live Feed"
        except Exception:
            sub = "Live Feed"
        if sub == "Live Feed":
            return LOG_RB_LIVE
        if sub == "Full Scrape":
            return LOG_RB_FULL
        return LOG_GLOBAL

    def _drain_log(self) -> None:
        active = self._active_log_channel()
        # Keep display channel in sync (also reloads when user switches tabs).
        if active != getattr(self, "_log_display_channel", LOG_GLOBAL):
            self._switch_log_display(active)
        try:
            while True:
                channel, message = self.log_queue.get_nowait()
                line = message.rstrip()
                buf = self._log_buffers.get(channel)
                if buf is None:
                    buf = deque(maxlen=_MAX_LINES)
                    self._log_buffers[channel] = buf
                buf.append(line)
                if channel == self._log_display_channel:
                    try:
                        self.activity_log.insert("end", line + "\n")
                        self.activity_log.see("end")
                    except Exception:
                        pass
        except queue.Empty:
            pass
        try:
            self.after(250, self._drain_log)
        except Exception:
            pass

    def _switch_log_display(self, channel: str) -> None:
        """Replace activity box contents with the selected channel buffer."""
        self._log_display_channel = channel
        lines = list(self._log_buffers.get(channel) or ())
        try:
            self.activity_log.delete("1.0", "end")
            if lines:
                self.activity_log.insert("end", "\n".join(lines) + "\n")
                self.activity_log.see("end")
        except Exception:
            pass

    def _on_log_context_change(self, _name=None) -> None:
        """Main or RB sub-tab changed — show the matching activity channel."""
        self._switch_log_display(self._active_log_channel())
