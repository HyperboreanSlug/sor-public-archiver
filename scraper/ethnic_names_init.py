from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from scraper.ethnic_names_base import *  # noqa: F401,F403

class EthnicInitMixin:
    def __init__(self):
        self.hispanic_surnames: Set[str] = set()
        self.asian_surnames: Dict[str, Set[str]] = {}
        self.indian_surnames: Set[str] = set()
        self.indian_surnames_by_group: Dict[str, Set[str]] = {}
        self.indian_high_confidence_surnames: Set[str] = set()
        self.indian_surname_exclusions: Set[str] = set()
        self.indian_ambiguous_surnames: Set[str] = set()
        self.indian_first_names: Set[str] = set()
        self.hispanic_first_names: Set[str] = set()
        self.anglo_western_first_names: Set[str] = set()
        self.slavic_first_names: Set[str] = set()
        self.african_american_first_names: Set[str] = set()
        self.african_american_surnames: Set[str] = set()
        self.native_american_surnames: Set[str] = set()
        self.european_surnames: Dict[str, Set[str]] = {}
        self.jewish_surnames: Set[str] = set()
        self.portuguese_surnames: Set[str] = set()
        self.arabic_surnames: Set[str] = set()
        self.african_surnames: Dict[str, Set[str]] = {}

        self._lookups_ready = False
        self._load_ethnic_names()


