"""Header path/count status for ArchiverApp."""
from __future__ import annotations

from pathlib import Path
from typing import Optional


class ShellHeaderMixin:
    """Top-bar DB path, record count, and open-data button."""

    def schedule_header_refresh(self, delay_ms: int = 0) -> None:
        """Thread-safe: refresh header DB path + record count on the UI thread."""
        try:
            if delay_ms and delay_ms > 0:
                self.after(int(delay_ms), self._refresh_header_db_path)
            else:
                self.after(0, self._refresh_header_db_path)
        except Exception:
            try:
                self._refresh_header_db_path()
            except Exception:
                pass

    def _poll_header_record_count(self) -> None:
        """Periodic refresh so the top counter tracks inserts/deletes."""
        if getattr(self, "_closing", False):
            return
        try:
            self._refresh_header_db_path()
        except Exception:
            pass
        interval = 2500 if getattr(self, "is_running", False) else 8000
        try:
            self.after(interval, self._poll_header_record_count)
        except Exception:
            pass

    def _refresh_header_db_path(self) -> None:
        """Show active SQLite path and live offender count in the header."""
        try:
            p = Path(self.db_path)
            if not p.is_absolute():
                p = (Path.cwd() / p).resolve()
            else:
                p = p.resolve()
            try:
                show = str(p.relative_to(Path.cwd()))
            except ValueError:
                show = str(p)
            if len(show) > 48:
                show = "…" + show[-46:]
            count: Optional[int] = None
            n = ""
            try:
                from scraper.database import Database

                db = Database(self.db_path)
                try:
                    count = int(db.get_total_count() or 0)
                    n = f"  ·  {count:,} records"
                    self._header_record_count = count
                finally:
                    db.close()
            except Exception:
                if self._header_record_count is not None:
                    n = f"  ·  {self._header_record_count:,} records"
            if hasattr(self, "header_db_label"):
                self.header_db_label.configure(text=f"DB: {show}{n}")
            if hasattr(self, "stats_label") and count is not None:
                try:
                    cur = (self.stats_label.cget("text") or "").strip()
                    idle_like = (
                        not cur
                        or cur == "Ready"
                        or cur.endswith(" records")
                        or cur.endswith("record")
                        or "selected" in cur.lower()
                    )
                    if idle_like and not getattr(self, "is_running", False):
                        self.stats_label.configure(text=f"{count:,} records")
                except Exception:
                    pass
        except Exception:
            if hasattr(self, "header_db_label"):
                try:
                    self.header_db_label.configure(text=f"DB: {self.db_path}")
                except Exception:
                    pass

    def _open_data_folder_header(self) -> None:
        path = Path("data")
        path.mkdir(parents=True, exist_ok=True)
        try:
            dbp = Path(self.db_path)
            if dbp.parent.is_dir():
                path = dbp.parent
        except Exception:
            pass
        self._open_path(path)
