from __future__ import annotations

import re

from typing import Any, Dict, List, Optional, Set, Tuple

from scraper.ethnic_names_base import *  # noqa: F401,F403

class EthnicSignalsMixin:
    @staticmethod
    def _fold_accents(text: str) -> str:
        """CRISTÓBAL → cristobal for list matching."""
        if not text:
            return ""
        nfkd = unicodedata.normalize("NFKD", text)
        return "".join(c for c in nfkd if not unicodedata.combining(c))


    @classmethod
    def _normalize_given_name(cls, first_name: Optional[str]) -> str:
        """First token of given name, letters only (handles 'MARY-ANN', 'J.')."""
        if not first_name:
            return ""
        raw = str(first_name).strip()
        if not raw:
            return ""
        # Take first whitespace token; strip punctuation
        token = raw.replace(",", " ").split()[0]
        token = re.sub(r"[^A-Za-zÀ-ÖØ-öø-ÿ\-']", "", token)
        token = token.strip("-'")
        return cls._fold_accents(token).lower()


    def _first_name_signal(self, first_name: Optional[str]) -> str:
        """
        Return one of: indian | african_american | hispanic | anglo | slavic | unknown

        Note: *Andrey* is treated as Western/white; *Andrei* as Slavic.
        Neither boosts Indian surname confidence.
        """
        self._build_lookup_sets()
        fn = self._normalize_given_name(first_name)
        if not fn or len(fn) < 2:
            return "unknown"
        # Prefer more specific lists; allow dual membership to favor indian
        # only when explicitly in indian list
        if fn in self._indian_first_lc:
            return "indian"
        # Distinctive African-American given names (DeShawn, Jamal, Lakisha…)
        if fn in self._aa_first_lc:
            return "african_american"
        # Slavic before Hispanic so Ivan/Andrei stay Slavic (not Spanish-default)
        if fn in self._slavic_first_lc:
            return "slavic"
        if fn in self._hispanic_first_lc:
            return "hispanic"
        if fn in self._anglo_first_lc:
            return "anglo"
        return "unknown"


    @staticmethod
    def _is_western_first_signal(signal: str) -> bool:
        """First names that contradict South Asian ethnicity claims."""
        return signal in ("anglo", "slavic", "hispanic")


    def _resolve_given_name_signal(
        self,
        first_name: Optional[str] = None,
        middle_name: Optional[str] = None,
    ) -> str:
        """
        Combine first + middle name signals for ethnicity confidence.

        Any Indic given name (first or middle) corroborates Indian surnames.
        Western / Slavic / Hispanic signals dampen when no Indic given name.
        """
        signals: List[str] = []
        for part in (first_name, middle_name):
            if not part:
                continue
            # Score each token in multi-word middle names (e.g. "ZAHEER UDDIN")
            tokens = re.split(r"[\s\-]+", str(part).strip())
            for tok in tokens:
                if not tok or len(tok) < 2:
                    continue
                # Skip bare initials
                if len(tok) == 1 or (len(tok) == 2 and tok.endswith(".")):
                    continue
                sig = self._first_name_signal(tok)
                if sig != "unknown":
                    signals.append(sig)
        if not signals:
            return "unknown"
        if "indian" in signals:
            return "indian"
        if "african_american" in signals:
            return "african_american"
        if "slavic" in signals:
            return "slavic"
        if "hispanic" in signals:
            return "hispanic"
        if "anglo" in signals:
            return "anglo"
        return "unknown"


