"""Reports: select cards, single-card export, and 1×2 / 2×2 grids."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from tkinter import messagebox


class ReportsExportGridMixin:
    def _reports_record_for_export(self, mc) -> Dict[str, Any]:
        """Snapshot record for card export (listed race preferred)."""
        rec = dict(getattr(mc, "record", None) or {})
        try:
            listed = getattr(mc, "expected_race", None)
            if listed and str(listed).strip():
                rec["race"] = str(listed).strip()
        except Exception:
            pass
        # Prefer app DB path so export_number lands on the open database
        dbp = getattr(self, "db_path", None)
        if dbp:
            rec["_db_path"] = str(dbp)
        return rec

    def _reports_sync_export_number(self, mc, record: Dict[str, Any]) -> None:
        """Copy assigned export_number onto the live misclass/report row."""
        num = record.get("export_number")
        if num is None:
            try:
                from gui_app.shared.export_card_release import peek_release_number

                num = peek_release_number(record)
            except Exception:
                num = None
        if num is None:
            return
        try:
            num_i = int(num)
        except (TypeError, ValueError):
            return
        if isinstance(getattr(mc, "record", None), dict):
            mc.record["export_number"] = num_i
        # Also refresh any tree-side cache of the same offender
        rid = (mc.record or {}).get("id") if isinstance(mc.record, dict) else None
        by_iid = getattr(self, "_misclass_records_by_iid", None) or {}
        if rid is not None:
            for rec in by_iid.values():
                if isinstance(rec, dict) and rec.get("id") == rid:
                    rec["export_number"] = num_i

    def _reports_register_card_ui(self, mc, **widgets) -> None:
        """Keep weak refs so export can update a badge without rebuilding the page."""
        if not hasattr(self, "_report_card_ui") or self._report_card_ui is None:
            self._report_card_ui: Dict[str, Dict[str, Any]] = {}
        try:
            key = self._reports_export_key(mc)
        except Exception:
            return
        slot = self._report_card_ui.get(key) or {}
        slot.update({k: v for k, v in widgets.items() if v is not None})
        slot["mc"] = mc
        self._report_card_ui[key] = slot

    def _reports_clear_card_ui_registry(self) -> None:
        """Drop card widget map (called when the page is rebuilt)."""
        self._report_card_ui = {}

    def _reports_refresh_verdict_ui(self, mc) -> None:
        """Update verdict chip on one card after auto-confirm on export."""
        try:
            key = self._reports_export_key(mc)
        except Exception:
            return
        ui = (getattr(self, "_report_card_ui", None) or {}).get(key) or {}
        status = ui.get("status_lbl")
        if status is None:
            return
        v = "confirmed"
        try:
            if hasattr(self, "_verdict_for_mc"):
                v = self._verdict_for_mc(mc) or "confirmed"
        except Exception:
            pass
        try:
            status.configure(
                text=self._reports_verdict_label_short(v),
                text_color=self._reports_verdict_color(v),
            )
        except Exception:
            try:
                status.configure(text=self._reports_verdict_label_short(v))
            except Exception:
                pass
        # Border color on card frame if registered
        card = ui.get("card")
        if card is not None:
            try:
                from gui_app.theme import C as _C

                border = {
                    "confirmed": _C["danger"],
                    "correct": _C["success"],
                    "skip": _C["dim"],
                    "unreviewed": _C["border"],
                }.get(str(v).lower(), _C["border"])
                card.configure(border_color=border)
            except Exception:
                pass

    def _reports_refresh_export_badge(self, mc, record: Optional[Dict[str, Any]] = None) -> None:
        """Update export # on one card in place — no full page rebuild."""
        try:
            from gui_app.shared.export_card_release import (
                format_export_badge,
                peek_release_number,
            )
        except Exception:
            return
        rec = record or self._reports_record_for_export(mc)
        try:
            badge = format_export_badge(
                rec.get("export_number")
                if rec.get("export_number") is not None
                else peek_release_number(rec)
            )
        except Exception:
            badge = ""
        key = ""
        try:
            key = self._reports_export_key(mc)
        except Exception:
            pass
        ui = (getattr(self, "_report_card_ui", None) or {}).get(key) or {}

        # List-view badge label (always present after cards_add change)
        lbl = ui.get("export_badge_lbl")
        if lbl is not None:
            try:
                from gui_app.theme import C as _C

                lbl.configure(
                    text=f"  {badge}" if badge else "",
                    text_color=_C["accent"] if badge else _C["dim"],
                )
            except Exception:
                try:
                    lbl.configure(text=f"  {badge}" if badge else "")
                except Exception:
                    pass

        # Grid-view meta line embeds badge + conf · state
        meta = ui.get("meta_lbl")
        if meta is not None:
            conf_label = str(ui.get("conf_label") or "").strip()
            state = str(ui.get("state") or "").strip()
            left = f"{conf_label} · {state}".strip(" ·")
            if badge:
                left = f"{badge} · {left}" if left else badge
            try:
                from gui_app.theme import C as _C

                meta.configure(
                    text=left or "—",
                    text_color=_C["accent"] if badge else _C["muted"],
                )
            except Exception:
                try:
                    meta.configure(text=left or "—")
                except Exception:
                    pass

    def _reports_export_single_card(self, mc, btn=None) -> None:
        """Export one watermarked mugshot card to the Desktop (no dialog on success)."""
        record = self._reports_record_for_export(mc)
        if not record:
            return
        if btn is not None:
            try:
                btn.configure(state="disabled", text="…")
            except Exception:
                pass

        def work():
            from gui_app.shared.export_card import export_record_card_to_desktop

            path = export_record_card_to_desktop(record)
            return {"path": path, "record": record}

        def done(result=None, error=None):
            if btn is not None:
                try:
                    btn.configure(state="normal", text="Export")
                except Exception:
                    pass
            if error is not None:
                messagebox.showerror("Export card", str(error))
                return
            payload = result if isinstance(result, dict) else {"path": result}
            path = payload.get("path")
            rec_out = payload.get("record") or record
            self._reports_sync_export_number(mc, rec_out)
            # Export implies verified misclass → Confirmed incorrect
            try:
                if hasattr(self, "_set_verdict_for_mc"):
                    self._set_verdict_for_mc(mc, "confirmed", save=True)
                if isinstance(getattr(mc, "record", None), dict) and isinstance(
                    rec_out, dict
                ):
                    if rec_out.get("flags") is not None:
                        mc.record["flags"] = rec_out["flags"]
            except Exception:
                pass
            # In-place badge only — do not rebuild the whole report page
            try:
                self._reports_refresh_export_badge(mc, rec_out)
            except Exception:
                pass
            try:
                self._reports_refresh_verdict_ui(mc)
            except Exception:
                pass
            num = rec_out.get("export_number")
            badge = f" · export #{num}" if num else ""
            msg = f"Card → {getattr(path, 'name', path)}{badge} · confirmed incorrect"
            try:
                if hasattr(self, "report_status"):
                    self.report_status.configure(text=msg)
                if hasattr(self, "stats_label"):
                    self.stats_label.configure(text=msg)
            except Exception:
                pass
            try:
                self.log_queue.put(f"Reports card export: {path}{badge}")
            except Exception:
                pass

        if hasattr(self, "run_bg"):
            self.run_bg(work, done, name="report-card-export")
        else:
            try:
                done(result=work(), error=None)
            except Exception as e:
                done(result=None, error=e)

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
            self._report_export_selected[key] = self._reports_record_for_export(mc)
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
                self.report_export_sel_label.configure(text=f"Sel {n}")
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
                "Check one or more cards, then export 1×2 or 2×2.\n"
                "(Export button alone writes a single card to the Desktop.)",
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

        records = []
        dbp = str(getattr(self, "db_path", None) or "")
        for r in recs:
            d = dict(r)
            if dbp:
                d["_db_path"] = dbp
            records.append(d)

        def work():
            return export_grid_to_desktop(records, layout=layout)

        def done(result=None, error=None):
            if error is not None:
                messagebox.showerror("Export grid", str(error))
                return
            path = result
            # Persist export #s already written during render; refresh badges
            nums = []
            for rec in records:
                n = rec.get("export_number")
                if n is not None:
                    nums.append(str(n))
            badge = f" · export #{', #'.join(nums)}" if nums else ""
            msg = (
                f"Grid {layout} → {getattr(path, 'name', path)}{badge}"
                f" · confirmed incorrect"
            )
            try:
                if hasattr(self, "report_status"):
                    self.report_status.configure(text=msg)
                if hasattr(self, "stats_label"):
                    self.stats_label.configure(text=msg)
            except Exception:
                pass
            # Mirror numbers + auto-confirm onto live rows (no full rebuild)
            try:
                for rec in records:
                    n = rec.get("export_number")
                    rid = rec.get("id")
                    for mc in list(getattr(self, "_report_items", None) or []):
                        r = getattr(mc, "record", None)
                        if not isinstance(r, dict):
                            continue
                        if rid is None or r.get("id") != rid:
                            continue
                        if n is not None:
                            r["export_number"] = n
                        if rec.get("flags") is not None:
                            r["flags"] = rec["flags"]
                        try:
                            if hasattr(self, "_set_verdict_for_mc"):
                                self._set_verdict_for_mc(
                                    mc, "confirmed", save=True
                                )
                        except Exception:
                            pass
                        try:
                            self._reports_refresh_export_badge(mc, r)
                        except Exception:
                            pass
                        try:
                            self._reports_refresh_verdict_ui(mc)
                        except Exception:
                            pass
                    for sel in list(
                        (getattr(self, "_report_export_selected", None) or {}).values()
                    ):
                        if isinstance(sel, dict) and sel.get("id") == rid:
                            if n is not None:
                                sel["export_number"] = n
                            if rec.get("flags") is not None:
                                sel["flags"] = rec["flags"]
            except Exception:
                pass
            try:
                self.log_queue.put(
                    f"Reports grid export: {path}{badge} · confirmed incorrect"
                )
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
