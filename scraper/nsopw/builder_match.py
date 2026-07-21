from __future__ import annotations

import re

from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple


from scraper.nsopw.builder_types import *  # noqa: F401,F403
from scraper.database import Database
from scraper.ethnic_names import get_ethnic_database
from scraper.reports.fetcher import ReportFetcher
from scraper.nsopw.client import (
    DEFAULT_JURISDICTIONS,
    NSOPWClient,
    NSOPWOffender,
    normalize_jurisdiction_code,
)
from scraper.nsopw.parallel import JurisdictionReportPool, ReportJob

class BuilderMatchMixin:
    @staticmethod
    def _normalize_dob_key(raw: Optional[str]) -> str:
        """Normalize DOB strings to YYYYMMDD digits for equality checks."""
        s = (raw or "").strip()
        if not s:
            return ""
        digits = re.sub(r"\D", "", s)
        if len(digits) == 8:
            # Prefer YYYYMMDD when year looks plausible
            y_first = int(digits[:4])
            if 1900 <= y_first <= 2100:
                return digits
            # MMDDYYYY
            return digits[4:8] + digits[:2] + digits[2:4]
        if len(digits) == 6:
            # YYMMDD — ambiguous; keep as-is for exact compare only
            return digits
        return digits


    @staticmethod
    def _pick_nsopw_hit_for_person(
        rec: Dict[str, Any],
        hits: List[Any],
    ) -> Optional[Any]:
        """Choose the best NSOPW hit for an existing DB person.

        Safety rules (wrong-person attachment is worse than a miss):
        - Exact last-name token match required (no substring-in-fullname).
        - First name must match exactly or as a clear prefix (≥3 chars).
        - State must match when both sides have a state.
        - DOB must match when both sides have DOB; conflict → reject.
        - Ambiguous ties (same top score) → return None (do not guess).
        """
        if not hits:
            return None

        def _tok(s: Any) -> str:
            return (str(s or "").strip().lower())

        want_first = _tok(rec.get("first_name")).split()[:1]
        want_first_s = want_first[0] if want_first else ""
        want_last = _tok(rec.get("last_name"))
        want_middle = _tok(rec.get("middle_name")).split()[:1]
        want_middle_s = want_middle[0] if want_middle else ""
        want_state = (
            rec.get("state") or rec.get("source_state") or ""
        ).strip().upper()
        if want_state in ("", "UNK", "US", "YY", "XX"):
            want_state = ""
        want_dob = BuilderMatchMixin._normalize_dob_key(
            rec.get("date_of_birth")
        )
        try:
            want_age = int(rec.get("age")) if rec.get("age") not in (None, "") else None
        except (TypeError, ValueError):
            want_age = None

        if not want_last:
            return None

        scored: List[tuple] = []
        for hit in hits:
            hf = _tok(getattr(hit, "first_name", None))
            hl = _tok(getattr(hit, "last_name", None))
            hm = _tok(getattr(hit, "middle_name", None))
            st = (
                getattr(hit, "state", None)
                or getattr(hit, "jurisdiction_id", None)
                or ""
            ).strip().upper()
            if st in ("", "UNK", "US"):
                st = ""
            hit_dob = BuilderMatchMixin._normalize_dob_key(
                getattr(hit, "date_of_birth", None)
            )
            try:
                hit_age = (
                    int(getattr(hit, "age", None))
                    if getattr(hit, "age", None) not in (None, "")
                    else None
                )
            except (TypeError, ValueError):
                hit_age = None

            # Exact last name only — never substring (Hall ≠ Marshall)
            if not hl or hl != want_last:
                continue

            # DOB conflict rejects
            if want_dob and hit_dob and want_dob != hit_dob:
                continue
            # Age conflict when no DOB (allow ±1)
            if (
                want_age is not None
                and hit_age is not None
                and not want_dob
                and not hit_dob
                and abs(want_age - hit_age) > 1
            ):
                continue
            # State conflict rejects when both known
            if want_state and st and want_state != st and want_state not in st:
                continue

            s = 5  # last-name exact
            first_ok = False
            if want_first_s and hf:
                if hf == want_first_s:
                    s += 4
                    first_ok = True
                elif len(want_first_s) >= 3 and (
                    hf.startswith(want_first_s) or want_first_s.startswith(hf)
                ):
                    s += 2
                    first_ok = True
            elif not want_first_s:
                # No first name on record — allow last+state+DOB only
                first_ok = bool(want_dob and hit_dob and want_dob == hit_dob)

            if not first_ok and not (want_dob and hit_dob and want_dob == hit_dob):
                # Need first-name evidence OR matching DOB
                continue

            if want_state and st and (st == want_state or want_state in st):
                s += 3
            elif want_state and not st:
                pass  # unknown hit state — no bonus, not rejected
            elif want_state and st:
                continue  # already handled above; keep for clarity

            if want_dob and hit_dob and want_dob == hit_dob:
                s += 5
            if want_middle_s and hm and (
                hm == want_middle_s or hm.startswith(want_middle_s)
            ):
                s += 1
            if getattr(hit, "image_uri", None) or getattr(hit, "offender_uri", None):
                s += 1

            # Minimum: last(5)+first prefix(2)=7, or last+DOB(5)=10
            if s < 7:
                continue
            scored.append((s, hit))

        if not scored:
            return None
        scored.sort(key=lambda t: t[0], reverse=True)
        top = scored[0][0]
        tops = [h for s, h in scored if s == top]
        # Ambiguous homonyms — do not guess
        if len(tops) > 1:
            return None
        return tops[0]


    def _primary_fetch_url(self, url: str, state: str = "") -> str:
        """Pick a single openable http(s) URL from a possibly merged source_url."""
        raw = (url or "").strip()
        if not raw:
            return ""
        try:
            from scraper.public_links import resolve_public_source_url, split_source_urls

            resolved = resolve_public_source_url(raw, state=state or None)
            if resolved and resolved.lower().startswith("http"):
                return resolved
            parts = split_source_urls(raw)
            if parts:
                return parts[0]
        except Exception:
            pass
        if " | " in raw:
            raw = raw.split(" | ", 1)[0].strip()
        return raw if raw.lower().startswith("http") else ""


    def _url_exists(self, url: str) -> bool:
        u = (url or "").strip()
        if not u:
            return False
        if u in self._known_urls:
            return True
        row = self.db._conn.execute(
            "SELECT 1 FROM offenders WHERE source_url = ? LIMIT 1",
            (u,),
        ).fetchone()
        if row is not None:
            self._known_urls.add(u)
            return True
        return False


    def _remember_url(self, url: str) -> None:
        u = (url or "").strip()
        if u:
            self._known_urls.add(u)


