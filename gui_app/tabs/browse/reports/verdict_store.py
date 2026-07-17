"""Report confirmation verdict store (JSON + DB flags)."""
from __future__ import annotations

import json
from typing import Any, Dict, List

from gui_app.paths import ROOT


class ReportsVerdictStoreMixin:
    @staticmethod
    def _normalize_report_verdict(raw: Any) -> str:
        """Map any stored/UI/flag spelling → Reports keys.

        Reports vocabulary:
          confirmed = confirmed incorrect (misclassification stands)
          correct   = confirmed correct (listed race OK)
          skip / unreviewed
        DB flags use ethnicity_review=incorrect|correct — map incorrect→confirmed.
        """
        v = str(raw or "").strip().lower()
        if v in ("incorrect", "confirmed", "misclass", "wrong"):
            return "confirmed"
        if v in ("correct", "ok", "right"):
            return "correct"
        if v in ("skip", "skipped"):
            return "skip"
        if v in ("unreviewed", "unconfirmed", "pending", ""):
            return "unreviewed"
        return "unreviewed"

    def _load_report_verdicts(self) -> None:
        path = getattr(self, "_report_verdicts_path", None) or (
            ROOT / "data" / "report_verdicts.json"
        )
        try:
            if path.is_file():
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    out: Dict[str, str] = {}
                    for k, v in data.items():
                        nv = self._normalize_report_verdict(v)
                        if nv in ("confirmed", "correct", "skip"):
                            out[str(k)] = nv
                    self._report_verdicts = out
                    return
        except Exception:
            pass
        if not hasattr(self, "_report_verdicts") or self._report_verdicts is None:
            self._report_verdicts = {}

    def _save_report_verdicts(self) -> None:
        path = getattr(self, "_report_verdicts_path", None) or (
            ROOT / "data" / "report_verdicts.json"
        )
        try:
            if not hasattr(self, "_report_verdicts") or self._report_verdicts is None:
                self._report_verdicts = {}
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(self._report_verdicts, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        except Exception as exc:
            if hasattr(self, "log_queue"):
                try:
                    self.log_queue.put(f"Reports verdicts save failed: {exc}")
                except Exception:
                    pass

    @staticmethod
    def _report_item_key(mc) -> str:
        rec = mc.record or {}
        rid = rec.get("id")
        if rid is not None and str(rid).strip() != "":
            return f"id:{rid}"
        name = (
            f"{rec.get('first_name', '') or ''} {rec.get('last_name', '') or ''}"
        ).strip() or (rec.get("full_name") or "")
        return f"n:{name}|{mc.expected_race}|{mc.likely_ethnicity}|{mc.confidence}"

    def _report_verdict_lookup_keys(self, mc) -> List[str]:
        """All keys that may hold a saved verdict for this row (stable + legacy)."""
        keys: List[str] = []
        primary = self._report_item_key(mc)
        keys.append(primary)
        rec = mc.record or {}
        rid = rec.get("id")
        if rid is not None and str(rid).strip() != "":
            keys.append(f"id:{rid}")
        try:
            keys.append(self._report_person_key(mc))
        except Exception:
            pass
        seen = set()
        out: List[str] = []
        for k in keys:
            if k and k not in seen:
                seen.add(k)
                out.append(k)
        return out

    @staticmethod
    def _report_person_key(mc) -> str:
        """Collapse near-duplicate listings of the same person for the report list.

        Includes middle name + DOB so NIRAJ V PATEL and NIRAJ RASHMIBABU PATEL
        do not collapse together.
        """
        from scraper.database import Database
        from scraper.database.identity import person_identity_key

        rec = mc.record or {}
        try:
            stable = Database.stable_external_key(rec)
            if stable:
                return f"p:{stable}"
        except Exception:
            pass
        try:
            norm = Database.normalize_identity_url(rec.get("source_url") or "")
            if norm:
                return f"u:{norm}"
        except Exception:
            pass
        try:
            return f"idk:{person_identity_key(rec)}"
        except Exception:
            pass
        fn = (rec.get("first_name") or "").strip().casefold()
        mn = (rec.get("middle_name") or "").strip().casefold()
        ln = (rec.get("last_name") or "").strip().casefold()
        st = (
            rec.get("state") or rec.get("source_state") or ""
        ).strip().upper()
        dob = (rec.get("date_of_birth") or "").strip().casefold()
        if fn and ln:
            return f"n:{fn}|{mn}|{ln}|{st}|{dob}"
        rid = rec.get("id")
        if rid is not None and str(rid).strip() != "":
            return f"id:{rid}"
        name = (
            f"{rec.get('first_name', '') or ''} {rec.get('last_name', '') or ''}"
        ).strip() or (rec.get("full_name") or "")
        return (
            f"n:{name}|{getattr(mc, 'expected_race', '')}|"
            f"{getattr(mc, 'likely_ethnicity', '')}|{getattr(mc, 'confidence', '')}"
        )

    def _verdict_for_mc(self, mc) -> str:
        """Resolve verdict; prefer non-unreviewed if any alias key has a decision.

        Also reads ``ethnicity_review`` from offenders.flags (Misclassify sidebar
        or Reports persist). Always returns Reports vocabulary
        (``confirmed`` / ``correct`` / ``skip`` / ``unreviewed``) — never raw
        ``incorrect`` from flags.
        """
        if not hasattr(self, "_report_verdicts") or self._report_verdicts is None:
            self._report_verdicts = {}
        try:
            from scraper.ethnicity_review import ethnicity_review_verdict

            flag_v = ethnicity_review_verdict(getattr(mc, "record", None))
            nv = self._normalize_report_verdict(flag_v)
            if nv in ("correct", "confirmed"):
                return nv
        except Exception:
            pass
        found = "unreviewed"
        for k in self._report_verdict_lookup_keys(mc):
            v = self._normalize_report_verdict(self._report_verdicts.get(k) or "")
            if v in ("confirmed", "correct", "skip"):
                return v
            if v == "unreviewed":
                found = "unreviewed"
        return found

    def _persist_mc_verdict_flags(self, mc, reports_verdict: str) -> None:
        """Mirror Reports verdict into offenders.flags ethnicity_review."""
        v = self._normalize_report_verdict(reports_verdict)
        if v not in ("correct", "confirmed"):
            return
        flag = "incorrect" if v == "confirmed" else "correct"
        rec = getattr(mc, "record", None)
        if not isinstance(rec, dict):
            return
        db_path = str(getattr(self, "db_path", None) or "data/offenders.db")
        try:
            from gui_app.shared.verdict_persist import persist_ethnicity_verdict

            ok, flags_json, err = persist_ethnicity_verdict(db_path, rec, flag)
            if ok and flags_json:
                rec["flags"] = flags_json
                mc.record = rec
            elif err and hasattr(self, "log_queue"):
                self.log_queue.put(f"Reports flag save failed: {err}")
        except Exception as exc:
            if hasattr(self, "log_queue"):
                try:
                    self.log_queue.put(f"Reports flag save error: {exc}")
                except Exception:
                    pass

    def _set_verdict_for_mc(self, mc, verdict: str, *, save: bool = True) -> None:
        if not hasattr(self, "_report_verdicts") or self._report_verdicts is None:
            self._report_verdicts = {}
        v = self._normalize_report_verdict(verdict)
        keys = self._report_verdict_lookup_keys(mc)
        if v == "unreviewed":
            for key in keys:
                self._report_verdicts.pop(key, None)
        else:
            # Write primary + id alias so later key shape changes still resolve
            for key in keys:
                self._report_verdicts[key] = v
            # Keep Misclassify Confirmation column + filters in sync
            if v in ("correct", "confirmed"):
                self._persist_mc_verdict_flags(mc, v)
        if save:
            self._save_report_verdicts()

    def _set_ethnicity_for_mc(self, mc, ethnicity: str) -> None:
        """Persist a manual ethnicity correction on the misclass row + DB."""
        eth = (ethnicity or "").strip() or "Unknown"
        mc.likely_ethnicity = eth
        names = list(mc.matching_names or [])
        if "manual_override" not in names:
            names = ["manual_override"] + names
        mc.matching_names = names
        rec = mc.record if isinstance(mc.record, dict) else {}
        rec["likely_ethnicity"] = eth
        mc.record = rec
        rid = rec.get("id")
        if rid is not None:
            try:
                from scraper.database import Database

                db = Database(self.db_path)
                try:
                    db.update_offender(int(rid), {"likely_ethnicity": eth})
                finally:
                    db.close()
            except Exception:
                pass

    def _ethnicity_compatible_with_record(self, mc) -> bool:
        """True if name-based ethnicity now matches recorded race (not a mismatch)."""
        try:
            from scraper.searcher import _is_compatible

            rec = mc.record or {}
            return bool(
                _is_compatible(
                    mc.likely_ethnicity or "",
                    (rec.get("race") or mc.expected_race or "").strip(),
                    recorded_ethnicity=(rec.get("ethnicity") or "").strip() or None,
                    last_name=(rec.get("last_name") or "").strip() or None,
                )
            )
        except Exception:
            return False
