"""Misclassify display filters (listed race + photo) for the results tree."""
from __future__ import annotations

from pathlib import Path
from typing import List, Tuple


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

    def _misclass_photo_filter_on(self) -> bool:
        if hasattr(self, "_ensure_misclass_filter_vars"):
            self._ensure_misclass_filter_vars()
        var = getattr(self, "misclass_hide_no_photo_var", None)
        if var is None:
            return False
        try:
            return bool(var.get())
        except Exception:
            return False

    def _misclass_listed_want(self) -> str:
        if hasattr(self, "_ensure_misclass_filter_vars"):
            self._ensure_misclass_filter_vars()
        var = getattr(self, "misclass_listed_var", None)
        if var is None:
            return "All"
        try:
            want = (var.get() or "All").strip() or "All"
        except Exception:
            want = "All"
        return want if want in ("White", "Black", "Other", "All") else "All"

    def _misclass_apply_photo_filter(self, results: list) -> list:
        """Drop rows without photo when Photos only is checked."""
        if not self._misclass_photo_filter_on():
            return list(results)
        return [mc for mc in results if self._misclass_mc_has_photo(mc)]

    def _misclass_apply_listed_filter(self, results: list) -> list:
        """Keep mismatches whose registry-listed race matches Listed as."""
        want = self._misclass_listed_want()
        if want == "All":
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

    def _misclass_filter_breakdown(
        self, stats_results: list
    ) -> Tuple[list, List[str]]:
        """Apply display filters; return (tree_rows, human status fragments)."""
        bits: List[str] = []
        listed = self._misclass_apply_listed_filter(stats_results)
        want = self._misclass_listed_want()
        if want != "All":
            bits.append(f"Listed {want}: {len(listed):,}")
        tree = self._misclass_apply_photo_filter(listed)
        if self._misclass_photo_filter_on():
            hid = len(listed) - len(tree)
            if hid > 0:
                bits.append(f"photos-only hid {hid:,}")
        return tree, bits

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
        tree_results, filt_bits = self._misclass_filter_breakdown(filtered)
        shown = min(500, len(tree_results))
        note = (" · " + " · ".join(filt_bits)) if filt_bits else ""
        try:
            base = (
                f"{len(filtered):,} unreviewed mismatches"
                + note
                + (
                    f" · tree shows first {shown} of {len(tree_results):,}"
                    if len(tree_results) > 500
                    else f" · tree shows {shown:,}"
                )
            )
            if (
                self._misclass_photo_filter_on()
                and len(tree_results) < len(filtered)
            ):
                base += " · uncheck Photos only to show rows without mugshots"
            self.misclass_status.configure(text=base)
        except Exception:
            pass

    def _misclass_on_photo_filter_toggle(self) -> None:
        """Back-compat alias for display-filter toggle."""
        self._misclass_on_display_filter_toggle()
