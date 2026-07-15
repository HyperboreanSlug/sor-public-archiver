"""Misclassify display filters (listed race + photo) for the results tree."""
from __future__ import annotations

from pathlib import Path


class MisclassifyFiltersMixin:
    def _misclass_mc_has_photo(self, mc) -> bool:
        """True when the mismatch row has a mugshot file on disk."""
        rec = getattr(mc, "record", None) or {}
        photo = (rec.get("photo_path") or "").strip()
        if hasattr(self, "_reports_photo_exists"):
            return bool(self._reports_photo_exists(photo))
        if not photo:
            return False
        try:
            return Path(photo).is_file()
        except OSError:
            return False

    def _misclass_apply_photo_filter(self, results: list) -> list:
        """Drop rows without photo when Remove without photo is checked."""
        if hasattr(self, "_ensure_misclass_filter_vars"):
            self._ensure_misclass_filter_vars()
        hide = True
        var = getattr(self, "misclass_hide_no_photo_var", None)
        if var is not None:
            try:
                hide = bool(var.get())
            except Exception:
                hide = True
        if not hide:
            return list(results)
        return [mc for mc in results if self._misclass_mc_has_photo(mc)]

    def _misclass_apply_listed_filter(self, results: list) -> list:
        """Keep mismatches whose registry-listed race matches Listed as."""
        if hasattr(self, "_ensure_misclass_filter_vars"):
            self._ensure_misclass_filter_vars()
        want = "All"
        var = getattr(self, "misclass_listed_var", None)
        if var is not None:
            try:
                want = (var.get() or "All").strip() or "All"
            except Exception:
                want = "All"
        if want not in ("White", "Black", "Other"):
            return list(results)
        from gui_app.widgets import _misclass_race_bucket

        out = []
        for mc in results:
            race = getattr(mc, "expected_race", None) or ""
            if not race:
                rec = getattr(mc, "record", None) or {}
                race = rec.get("race") or ""
            if _misclass_race_bucket(race) == want:
                out.append(mc)
        return out

    def _misclass_apply_display_filters(self, results: list) -> list:
        """Photo + listed-as filters for the Misclassify results tree."""
        return self._misclass_apply_photo_filter(
            self._misclass_apply_listed_filter(results)
        )

    def _misclass_on_display_filter_toggle(self, *_args) -> None:
        """Re-populate the tree from cached Analyze results (no re-scan)."""
        if not getattr(self, "_misclass_results", None):
            return
        filtered = self._results_excluding_correct(self._misclass_results)
        try:
            self._populate_misclass_tree(filtered)
        except Exception:
            pass
        if not hasattr(self, "misclass_status"):
            return
        shown_list = self._misclass_apply_display_filters(filtered)
        shown = min(500, len(shown_list))
        total = len(filtered)
        n_hidden = total - len(shown_list)
        note = f" · {n_hidden} filtered out" if n_hidden > 0 else ""
        try:
            self.misclass_status.configure(
                text=(
                    f"{total} potential mismatches"
                    + (
                        f" · showing first {shown}"
                        if total > 500
                        else f" · showing {shown}"
                    )
                    + note
                    + " · select a row for photo"
                )
            )
        except Exception:
            pass

    def _misclass_on_photo_filter_toggle(self) -> None:
        """Back-compat alias for display-filter toggle."""
        self._misclass_on_display_filter_toggle()
