from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from scraper.ethnic_names_base import *  # noqa: F401,F403

class EthnicLookupMixin:
    def _build_lookup_sets(self) -> None:
        """Cache lowercased sets for O(1) membership checks."""
        if getattr(self, "_lookups_ready", False):
            return
        self._hispanic_lc = {n.lower() for n in self.hispanic_surnames}
        self._african_american_lc = {n.lower() for n in self.african_american_surnames}
        self._native_american_lc = {n.lower() for n in self.native_american_surnames}
        self._jewish_lc = {n.lower() for n in self.jewish_surnames}
        self._portuguese_lc = {n.lower() for n in self.portuguese_surnames}
        self._arabic_lc = {n.lower() for n in self.arabic_surnames}
        self._indian_excl_lc = {
            n.lower() for n in (self.indian_surname_exclusions or set())
        }
        self._indian_amb_lc = {
            n.lower() for n in (self.indian_ambiguous_surnames or set())
        }
        self._indian_lc = {
            n.lower() for n in self.indian_surnames
            if n.lower() not in self._indian_excl_lc
        }
        self._indian_hc_lc = {
            n.lower() for n in (self.indian_high_confidence_surnames or set())
            if n.lower() not in self._indian_excl_lc
        }
        self._indian_group_lc = {
            group: {
                n.lower() for n in names if n.lower() not in self._indian_excl_lc
            }
            for group, names in (self.indian_surnames_by_group or {}).items()
        }
        def _fold_set(names) -> set:
            out = set()
            for n in names or set():
                out.add(self._fold_accents(str(n)).lower())
            return out

        self._indian_first_lc = _fold_set(self.indian_first_names)
        self._hispanic_first_lc = _fold_set(self.hispanic_first_names)
        self._anglo_first_lc = _fold_set(self.anglo_western_first_names)
        self._slavic_first_lc = _fold_set(self.slavic_first_names)
        self._aa_first_lc = _fold_set(self.african_american_first_names)
        self._asian_lc = {
            group: {n.lower() for n in names}
            for group, names in self.asian_surnames.items()
        }
        self._european_lc = {
            country: {n.lower() for n in names}
            for country, names in self.european_surnames.items()
        }
        self._african_lc = {
            region: {n.lower() for n in names}
            for region, names in self.african_surnames.items()
        }
        self._lookups_ready = True


