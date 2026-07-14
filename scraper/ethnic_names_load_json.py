from __future__ import annotations

import json

from typing import Any, Dict, List, Optional, Set, Tuple

from scraper.ethnic_names_base import *  # noqa: F401,F403

class EthnicLoadJsonMixin:
    def _load_ethnic_names(self):
        """Load ethnic names from the JSON file."""
        json_path = Path(__file__).parent / "ethnic_names.json"

        if not json_path.exists():
            self._use_defaults()
            return

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.hispanic_surnames = set(data.get("hispanic_surnames", []))

        asian_data = data.get("asian_surnames", {})
        for group, names in asian_data.items():
            if group.lower() in ("indian", "south_asian", "southasian"):
                if isinstance(names, list):
                    self.indian_surnames.update(n.strip() for n in names if n and n.strip())
                continue
            if isinstance(names, list):
                self.asian_surnames[group] = set(n.strip() for n in names)

        top_indian = data.get("indian_surnames", [])
        if isinstance(top_indian, dict):
            for group, names in top_indian.items():
                if not isinstance(names, list):
                    continue
                cleaned = {n.strip() for n in names if n and str(n).strip()}
                self.indian_surnames_by_group[group] = cleaned
                self.indian_surnames.update(cleaned)
        elif isinstance(top_indian, list):
            self.indian_surnames.update(n.strip() for n in top_indian if n and n.strip())

        hc = data.get("indian_high_confidence_surnames", [])
        if isinstance(hc, list):
            self.indian_high_confidence_surnames = {
                n.strip() for n in hc if n and str(n).strip()
            }
            self.indian_surnames.update(self.indian_high_confidence_surnames)
            if self.indian_high_confidence_surnames:
                self.indian_surnames_by_group.setdefault(
                    "high_confidence", set()
                ).update(self.indian_high_confidence_surnames)

        # Hard exclusions — never Indian
        excl_raw = data.get("indian_surname_exclusions", [])
        self.indian_surname_exclusions = {
            n.strip() for n in (excl_raw or []) if n and str(n).strip()
        }
        if self.indian_surname_exclusions:
            excl_lc = {n.lower() for n in self.indian_surname_exclusions}
            self.indian_surnames = {
                n for n in self.indian_surnames if n.lower() not in excl_lc
            }
            self.indian_high_confidence_surnames = {
                n for n in self.indian_high_confidence_surnames
                if n.lower() not in excl_lc
            }
            for group, names in list(self.indian_surnames_by_group.items()):
                self.indian_surnames_by_group[group] = {
                    n for n in names if n.lower() not in excl_lc
                }

        amb = data.get("indian_ambiguous_surnames", [])
        self.indian_ambiguous_surnames = {
            n.strip() for n in (amb or []) if n and str(n).strip()
        }

        self.indian_first_names = {
            n.strip() for n in (data.get("indian_first_names") or []) if n and str(n).strip()
        }
        self.hispanic_first_names = {
            n.strip()
            for n in (data.get("hispanic_first_names") or [])
            if n and str(n).strip()
        }
        self.anglo_western_first_names = {
            n.strip()
            for n in (data.get("anglo_western_first_names") or [])
            if n and str(n).strip()
        }
        self.slavic_first_names = {
            n.strip()
            for n in (data.get("slavic_first_names") or [])
            if n and str(n).strip()
        }
        self.african_american_first_names = {
            n.strip()
            for n in (data.get("african_american_first_names") or [])
            if n and str(n).strip()
        }

        self.african_american_surnames = set(data.get("african_american_surnames", []))
        self.native_american_surnames = set(data.get("native_american_surnames", []))

        european_data = data.get("european_surnames", {})
        for country, names in european_data.items():
            if isinstance(names, list):
                self.european_surnames[country] = set(n.strip() for n in names)

        self.jewish_surnames = set(data.get("jewish_surnames", []))
        self.portuguese_surnames = set(data.get("portuguese_surnames", []))
        self.arabic_surnames = set(data.get("arabic_surnames", []))

        african_data = data.get("african_surnames", {})
        for region, names in african_data.items():
            if isinstance(names, list):
                self.african_surnames[region] = set(n.strip() for n in names)


    def _use_defaults(self):
        """Use default embedded name lists."""
        self.hispanic_surnames = {
            "Garcia", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez",
            "Perez", "Sanchez", "Ramirez", "Torres", "Flores", "Rivera", "Gomez",
            "Diaz", "Cruz", "Morales", "Ortiz", "Ramos", "Gutierrez", "Alvarez",
        }
        self.asian_surnames = {
            "chinese": {"Chen", "Wang", "Li", "Zhang", "Liu"},
            "korean": {"Kim", "Park", "Choi"},
            "japanese": {"Tanaka", "Suzuki", "Yamamoto"},
        }
        self.indian_surnames = {
            "Patel", "Shah", "Singh", "Kumar", "Gupta", "Sharma", "Reddy", "Nair",
        }
        self.indian_high_confidence_surnames = set(self.indian_surnames)
        self.indian_surnames_by_group = {"high_confidence": set(self.indian_surnames)}
        self.indian_first_names = {"Rahul", "Priya", "Amit", "Neha", "Raj"}
        self.hispanic_first_names = {"Alberto", "Carlos", "Maria", "Jose"}
        self.anglo_western_first_names = {"Amy", "John", "Robert", "Emily", "Andrey"}
        self.slavic_first_names = {"Andrei", "Ivan", "Dmitri", "Sergei"}
        self.african_american_first_names = {
            "DeShawn", "DeAndre", "Jamal", "Tyrone", "Lakisha", "Latoya",
        }
        self.indian_ambiguous_surnames = {"Gill", "Perera", "Silva"}


