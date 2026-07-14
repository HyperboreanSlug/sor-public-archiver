"""RecordSidebar show/clear/bind methods."""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from gui_app.shared.record_sidebar_photo import resolve_photo_path
from gui_app.shared.record_sidebar_ui import ACTUAL_RACE_OPTIONS
from gui_app.theme import C


class RecordSidebarShowMixin:
    """Selection binding, show/clear, size adjustments."""

    def bind_after(self, after_fn: Callable[..., Any]) -> None:
        self._after = after_fn
        if not self._pumping:
            self._pumping = True
            self._pump_ui()

    def bind_verdict(
        self, callback: Optional[Callable[[Dict[str, Any], str], None]]
    ) -> None:
        self._on_verdict = callback

    def bind_actual_race(
        self, callback: Optional[Callable[[Dict[str, Any], str], None]]
    ) -> None:
        self._on_actual_race = callback

    def _emit_verdict(self, verdict: str) -> None:
        if not self._record or not self._on_verdict:
            return
        self._on_verdict(dict(self._record), verdict)

    def _emit_actual_race(self, choice: str) -> None:
        if self._syncing_actual or not self._record or not self._on_actual_race:
            return
        actual = (choice or self.actual_race.get() or "").strip() or "Unknown"
        self._record["likely_ethnicity"] = actual
        self._on_actual_race(dict(self._record), actual)
        self._fill_text(self._record)

    @staticmethod
    def review_label(record: Optional[Dict[str, Any]]) -> str:
        flags = (record or {}).get("flags")
        if isinstance(flags, str):
            try:
                import json

                flags = json.loads(flags)
            except Exception:
                flags = {}
        if not isinstance(flags, dict):
            return ""
        review = str(flags.get("ethnicity_review") or "").strip().lower()
        if review == "correct":
            return "Marked: classified correctly"
        if review == "incorrect":
            return "Marked: classified incorrectly"
        return ""

    def _pump_ui(self) -> None:
        try:
            while True:
                fn = self._ui_q.get_nowait()
                try:
                    fn()
                except Exception:
                    pass
        except Exception:
            pass
        if self._after:
            self._after(50, self._pump_ui)

    def _schedule(self, fn: Callable[[], None]) -> None:
        self._ui_q.put(fn)

    def _on_sidebar_configure(self, _event=None) -> None:
        if not self._after:
            return
        if self._resize_after is not None:
            try:
                self.frame.after_cancel(self._resize_after)
            except Exception:
                pass
        self._resize_after = self.frame.after(120, self._apply_photo_slot_size)

    def _apply_photo_slot_size(self) -> None:
        self._resize_after = None
        size = self._target_photo_size()
        if size == self.photo_size:
            return
        self.photo_size = size
        self.photo.configure(width=size[0], height=size[1])
        if self._record:
            self._load_photo(self._record, self._load_token)

    def _target_photo_size(self) -> tuple[int, int]:
        try:
            fw = int(self.frame.winfo_width())
            fh = int(self.frame.winfo_height())
        except Exception:
            return self.photo_size
        if fw < 80 or fh < 80:
            return self.photo_size
        side = min(fw - 20, max(180, fh - 360))
        side = max(200, min(side, 480))
        return (side, side)

    @staticmethod
    def _marked_race_text(record: Optional[Dict[str, Any]]) -> str:
        from scraper.searcher import format_race_label

        if not record:
            return "Marked race: —"
        label = format_race_label(str(record.get("race") or "").strip())
        if not label or label == "—":
            label = "Unknown"
        return f"Marked race: {label}"

    def clear(self, message: str = "Select a record") -> None:
        self._load_token += 1
        self._record = None
        self._image_ref = None
        self.photo.configure(image="", text=message)
        self.open_btn.configure(state="disabled")
        self.open_photo_btn.configure(state="disabled")
        self.export_btn.configure(state="disabled")
        self.correct_btn.configure(state="disabled")
        self.incorrect_btn.configure(state="disabled")
        self.actual_race.configure(state="disabled")
        self.race_banner.configure(text="Marked race: —")
        self.verdict_status.configure(text="", text_color=C["muted"])
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("end", message)
        self.details.configure(state="disabled")

    def show(self, record: Optional[Dict[str, Any]]) -> None:
        if not record:
            self.clear()
            return
        self._record = dict(record)
        self._load_token += 1
        token = self._load_token
        self.photo_size = self._target_photo_size()
        self.photo.configure(width=self.photo_size[0], height=self.photo_size[1])
        self._fill_text(self._record)
        self.race_banner.configure(text=self._marked_race_text(self._record))
        has_url = bool(str(self._record.get("source_url") or "").strip())
        self.open_btn.configure(state="normal" if has_url else "disabled")
        photo_path = resolve_photo_path(self._record.get("photo_path"))
        self.open_photo_btn.configure(
            state="normal" if photo_path and photo_path.is_file() else "disabled"
        )
        self.export_btn.configure(state="normal")
        enabled = "normal" if self._on_verdict else "disabled"
        self.correct_btn.configure(state=enabled)
        self.incorrect_btn.configure(state=enabled)
        label = self.review_label(self._record)
        if "incorrect" in label:
            self.verdict_status.configure(text=label, text_color=C["danger"])
        elif "correct" in label:
            self.verdict_status.configure(text=label, text_color=C["success"])
        else:
            self.verdict_status.configure(text=label or "", text_color=C["muted"])
        likely = (
            str(
                self._record.get("likely_ethnicity")
                or self._record.get("race")
                or "Unknown"
            ).strip()
            or "Unknown"
        )
        opts = list(ACTUAL_RACE_OPTIONS)
        if likely not in opts:
            opts = [likely] + opts
        self._syncing_actual = True
        try:
            self.actual_race.configure(
                values=opts,
                state="normal" if self._on_actual_race else "disabled",
            )
            self.actual_race.set(likely)
        finally:
            self._syncing_actual = False
        self._load_photo(self._record, token)
