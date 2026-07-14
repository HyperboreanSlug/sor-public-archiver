"""Reports: select cards and export watermarked 1×2 / 2×2 grids."""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from tkinter import messagebox


class ReportsExportGridMixin:
    def _reports_export_selected_init(self) -> None:
        if not hasattr(self, "_report_export_selected"):
            self._report_export_selected: Dict[str, Dict[str, Any]] = {}

    def _reports_export_key(self, mc) -> str:
        rec = dict(getattr(mc, "record", None) or {})
        try:
            if rec.get("id") is not None:
                return f"id:{int(rec['id'])}"
        except (TypeError, ValueError):
            pass
        try:
            keys = self._report_verdict_lookup_keys(mc)
            if keys:
                return f"k:{keys[0]}"
        except Exception:
            pass
        name = (
            " ".join(
                p
                for p in (
                    rec.get("first_name") or "",
                    rec.get("last_name") or "",
                )
                if str(p).strip()
            )
            or rec.get("full_name")
            or "row"
        )
        return f"n:{name}:{rec.get('state') or ''}"

    def _reports_is_export_selected(self, mc) -> bool:
        self._reports_export_selected_init()
        return self._reports_export_key(mc) in self._report_export_selected

    def _reports_set_export_selected(self, mc, selected: bool) -> None:
        self._reports_export_selected_init()
        key = self._reports_export_key(mc)
        if selected:
            rec = dict(getattr(mc, "record", None) or {})
            # Prefer listed registry race for watermarked share cards
            try:
                listed = getattr(mc, "expected_race", None)
                if listed and str(listed).strip():
                    rec["race"] = str(listed).strip()
            except Exception:
                pass
            self._report_export_selected[key] = rec
        else:
            self._report_export_selected.pop(key, None)
        self._reports_update_export_status()

    def _reports_selected_records(self) -> List[Dict[str, Any]]:
        self._reports_export_selected_init()
        return list(self._report_export_selected.values())

    def _reports_clear_export_selection(self) -> None:
        self._reports_export_selected_init()
        self._report_export_selected.clear()
        try:
            self._reports_rebuild_cards(refilter=False)
        except Exception:
            pass
        self._reports_update_export_status()

    def _reports_update_export_status(self) -> None:
        n = len(self._reports_selected_records())
        if hasattr(self, "report_export_sel_label"):
            try:
                self.report_export_sel_label.configure(
                    text=f"Selected for grid: {n}"
                )
            except Exception:
                pass

    def _reports_export_grid(self, layout: str) -> None:
        """Export checked names as a watermarked 1×2 or 2×2 card grid."""
        from gui_app.shared.export_card import (
            export_grid_to_desktop,
            layout_capacity,
            normalize_layout,
        )

        layout = normalize_layout(layout)
        recs = self._reports_selected_records()
        cap = layout_capacity(layout)
        if not recs:
            messagebox.showinfo(
                "Export grid",
                "Check one or more report cards, then export 1×2 or 2×2.",
            )
            return
        if len(recs) > cap:
            messagebox.showwarning(
                "Export grid",
                f"{layout} holds at most {cap} cards.\n"
                f"You have {len(recs)} selected — uncheck some, or use 2×2.",
            )
            return

        if hasattr(self, "report_status"):
            try:
                self.report_status.configure(
                    text=f"Exporting {layout} grid ({len(recs)} cards)…"
                )
            except Exception:
                pass

        records = [dict(r) for r in recs]

        def work():
            return export_grid_to_desktop(records, layout=layout)

        def done(result=None, error=None):
            if error is not None:
                messagebox.showerror("Export grid", str(error))
                return
            path = result
            msg = f"Grid {layout} → {getattr(path, 'name', path)}"
            try:
                if hasattr(self, "report_status"):
                    self.report_status.configure(text=msg)
                if hasattr(self, "stats_label"):
                    self.stats_label.configure(text=msg)
            except Exception:
                pass
            try:
                self.log_queue.put(f"Reports grid export: {path}")
            except Exception:
                pass
            # No confirmation dialog — status bar + log are enough

        if hasattr(self, "run_bg"):
            self.run_bg(work, done, name="report-grid-export")
        else:
            try:
                done(result=work(), error=None)
            except Exception as e:
                done(result=None, error=e)
