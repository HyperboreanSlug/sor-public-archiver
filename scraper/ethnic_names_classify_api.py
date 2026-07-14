from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from scraper.ethnic_names_base import *  # noqa: F401,F403

class EthnicClassifyApiMixin:
    def get_likely_ethnicity(
        self,
        surname: str,
        first_name: Optional[str] = None,
        middle_name: Optional[str] = None,
    ) -> Tuple[str, float]:
        """Get the most likely ethnicity for a name."""
        ethnicity, confidence, _ = self.classify_by_name(
            surname, first_name=first_name, middle_name=middle_name
        )
        return (ethnicity, confidence)


    def is_hispanic_surname(self, surname: str) -> bool:
        self._build_lookup_sets()
        return surname.strip().lower() in self._hispanic_lc


    def is_asian_surname(self, surname: str) -> Tuple[bool, str]:
        self._build_lookup_sets()
        surname_lc = surname.strip().lower()
        for group, names in self._asian_lc.items():
            if surname_lc in names:
                return True, group
        return False, ""


    def is_indian_surname(self, surname: str) -> bool:
        self._build_lookup_sets()
        lc = surname.strip().lower()
        if lc in self._indian_excl_lc:
            return False
        return lc in self._indian_lc


    def is_indian_high_confidence_surname(self, surname: str) -> bool:
        self._build_lookup_sets()
        lc = surname.strip().lower()
        if lc in self._indian_excl_lc:
            return False
        return lc in self._indian_hc_lc


    def is_indian_ambiguous_surname(self, surname: str) -> bool:
        self._build_lookup_sets()
        return surname.strip().lower() in self._indian_amb_lc


    def subcategories(self, ethnicity: str) -> List[str]:
        eth = (ethnicity or "").lower().strip()
        if eth in (
            "indian_high_confidence",
            "high_confidence_indian",
            "high-confidence indian",
            "indian_hc",
        ):
            return ["all"]
        if eth == "asian":
            return ["all"] + sorted(self.asian_surnames.keys(), key=str.lower)
        if eth == "indian":
            groups = sorted((self.indian_surnames_by_group or {}).keys(), key=str.lower)
            if "high_confidence" in groups:
                groups = ["high_confidence"] + [g for g in groups if g != "high_confidence"]
            return ["all"] + groups if groups else ["all"]
        if eth == "european":
            return ["all"] + sorted(self.european_surnames.keys(), key=str.lower)
        if eth == "african":
            return ["all"] + sorted(self.african_surnames.keys(), key=str.lower)
        return ["all"]


    def has_subcategories(self, ethnicity: str) -> bool:
        return len(self.subcategories(ethnicity)) > 1


    def is_african_american_surname(self, surname: str) -> bool:
        self._build_lookup_sets()
        return surname.strip().lower() in self._african_american_lc


