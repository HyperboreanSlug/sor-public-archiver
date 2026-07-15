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
        """Show active SQLite path; count runs via background job queue."""
        try:
            from scraper.paths import project_root, resolve_under_root

            p = resolve_under_root(
                getattr(self, "db_path", None) or "data/offenders.db"
            )
            root = project_root()
            try:
                show = str(p.relative_to(root))
            except ValueError:
                show = str(p)
            if len(show) > 48:
                show = "…" + show[-46:]
        except Exception:
            show = str(getattr(self, "db_path", "data/offenders.db"))
            p = Path(show)

        cached = getattr(self, "_header_record_count", None)
        n = f"  ·  {cached:,} records" if cached is not None else ""
        if hasattr(self, "header_db_label"):
            try:
                self.header_db_label.configure(text=f"DB: {show}{n}")
            except Exception:
                pass

        if getattr(self, "_header_count_busy", False):
            return
        self._header_count_busy = True
        try:
            from scraper.paths import resolve_under_root

            db_path = str(
                resolve_under_root(
                    getattr(self, "db_path", None) or "data/offenders.db"
                )
            )
        except Exception:
            db_path = str(getattr(self, "db_path", None) or "data/offenders.db")
        path_show = show

        def work():
            from scraper.database import Database

            db = Database(db_path)
            try:
                return int(db.get_total_count() or 0)
            finally:
                db.close()

        def apply(result=None, error=None):
            self._header_count_busy = False
            count: Optional[int] = None if error else result
            if count is not None:
                self._header_record_count = count
            n2 = ""
            c = self._header_record_count
            if c is not None:
                n2 = f"  ·  {c:,} records"
            elif error is not None:
                err = str(error).strip().replace("\n", " ")
                if len(err) > 40:
                    err = err[:37] + "…"
                n2 = f"  ·  load failed ({err})" if err else "  ·  load failed"
                try:
                    if hasattr(self, "log_queue"):
                        self.log_queue.put(f"Database load error: {error}")
                except Exception:
                    pass
            if hasattr(self, "header_db_label"):
                try:
                    self.header_db_label.configure(text=f"DB: {path_show}{n2}")
                except Exception:
                    pass
            # stats_label is status-only (Ready / scrape / export). Do not
            # mirror the record count there — that lived on DB line only.

        if hasattr(self, "run_bg"):
            self.run_bg(work, apply, name="header-count")
        else:
            try:
                apply(result=work(), error=None)
            except Exception as e:
                apply(result=None, error=e)

    def _open_data_folder_header(self) -> None:
        try:
            from scraper.paths import project_root, resolve_under_root

            path = project_root() / "data"
            path.mkdir(parents=True, exist_ok=True)
            dbp = resolve_under_root(
                getattr(self, "db_path", None) or "data/offenders.db"
            )
            if dbp.parent.is_dir():
                path = dbp.parent
        except Exception:
            path = Path("data")
            path.mkdir(parents=True, exist_ok=True)
        self._open_path(path)
