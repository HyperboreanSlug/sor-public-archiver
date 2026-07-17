"""Persistent card export numbers for SORPA export cards.

Each *distinct person* gets one export number. Re-exporting the same person
reuses their number; the first export of a new person increments the sequence.

Numbers are stored in:
  - ``offenders.export_number`` (authoritative once assigned)
  - ``data/card_release.json`` (sequence + identity-key index)
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, Mapping, MutableMapping, Optional

from scraper.paths import project_root

_LOCK = threading.Lock()
_REL_PATH = "data/card_release.json"


def _store_path() -> Path:
    return project_root() / _REL_PATH


def person_card_key(record: Mapping[str, Any]) -> str:
    """Stable identity key for release-number assignment."""
    try:
        from scraper.database import Database

        stable = Database.stable_external_key(dict(record))
        if stable:
            return f"p:{stable}"
    except Exception:
        pass
    try:
        from scraper.database.identity import person_identity_key

        key = person_identity_key(dict(record))
        if key and key not in ("|", "|||"):
            return f"idk:{key}"
    except Exception:
        pass
    rid = record.get("id")
    if rid is not None and str(rid).strip():
        return f"row:{str(rid).strip()}"
    name = " ".join(
        str(record.get(k) or "").strip()
        for k in ("first_name", "middle_name", "last_name", "full_name")
        if record.get(k)
    ).casefold()
    state = str(record.get("state") or record.get("source_state") or "").strip().upper()
    dob = str(record.get("date_of_birth") or "").strip()
    fallback = "|".join(x for x in (name, state, dob) if x)
    return f"fb:{fallback}" if fallback else "fb:unknown"


def _coerce_export_num(raw: Any) -> Optional[int]:
    if raw is None or raw == "":
        return None
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return None
    return n if n >= 1 else None


def export_number_on_record(record: Optional[Mapping[str, Any]]) -> Optional[int]:
    """Read export number already on the record (DB column or flags). No assign."""
    if not record:
        return None
    for key in ("export_number", "card_export_no", "release_number"):
        n = _coerce_export_num(record.get(key))
        if n is not None:
            return n
    flags = record.get("flags")
    if isinstance(flags, str) and flags.strip():
        try:
            flags = json.loads(flags)
        except (TypeError, json.JSONDecodeError, ValueError):
            flags = None
    if isinstance(flags, dict):
        return _coerce_export_num(flags.get("export_number"))
    return None


def _load(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {"next": 1, "people": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {"next": 1, "people": {}}
    if not isinstance(raw, dict):
        return {"next": 1, "people": {}}
    people = raw.get("people")
    if not isinstance(people, dict):
        people = {}
    try:
        nxt = int(raw.get("next") or 1)
    except (TypeError, ValueError):
        nxt = 1
    if nxt < 1:
        nxt = 1
    clean: Dict[str, int] = {}
    for k, v in people.items():
        n = _coerce_export_num(v)
        if n is not None and str(k):
            clean[str(k)] = n
    return {"next": nxt, "people": clean}


def _save(path: Path, data: MutableMapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = {
        "next": int(data.get("next") or 1),
        "people": dict(data.get("people") or {}),
    }
    path.write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def peek_release_number(
    record: Mapping[str, Any], *, path: Optional[Path] = None
) -> Optional[int]:
    """Return this person's export number if known — never assigns a new one."""
    existing = export_number_on_record(record)
    if existing is not None:
        return existing
    key = person_card_key(record)
    store = Path(path) if path is not None else _store_path()
    with _LOCK:
        data = _load(store)
        n = data["people"].get(key)
        return int(n) if n is not None else None


def format_export_badge(num: Optional[int]) -> str:
    """Reports UI label, e.g. ``export #12``."""
    n = _coerce_export_num(num)
    if n is None:
        return ""
    return f"export #{n}"


def format_release_label(num: Optional[int]) -> str:
    """Footer text for a release number on the card image."""
    n = _coerce_export_num(num)
    if n is None:
        return ""
    return f"No. {n}"


def _persist_to_db(record: Mapping[str, Any], num: int) -> None:
    rid = record.get("id")
    if rid is None or str(rid).strip() == "":
        return
    try:
        from scraper.database import Database

        raw_path = record.get("_db_path") or record.get("db_path")
        if raw_path:
            db_path = str(raw_path)
        else:
            db_path = str(project_root() / "data" / "offenders.db")
        try:
            rid_i = int(rid)
        except (TypeError, ValueError):
            return
        db = Database(db_path)
        try:
            db.update_offender(rid_i, {"export_number": int(num)})
        finally:
            db.close()
    except Exception:
        pass


def _write_on_record(record: Any, num: int) -> None:
    """Best-effort mutate *record* so callers see the assigned number."""
    if isinstance(record, dict):
        record["export_number"] = int(num)


def release_number_for(
    record: Mapping[str, Any],
    *,
    path: Optional[Path] = None,
    persist_db: bool = True,
) -> int:
    """Return this person's export number, assigning a new one if first export.

    Also writes ``export_number`` onto *record* (when mutable) and into
    ``offenders.export_number`` when ``id`` is present.
    """
    key = person_card_key(record)
    store = Path(path) if path is not None else _store_path()
    existing = export_number_on_record(record)

    with _LOCK:
        data = _load(store)
        people: Dict[str, int] = data["people"]
        if existing is not None:
            num = int(existing)
            # Keep JSON index + next counter consistent with DB
            if people.get(key) != num:
                people[key] = num
                data["people"] = people
                data["next"] = max(int(data.get("next") or 1), num + 1)
                _save(store, data)
        elif key in people:
            num = int(people[key])
        else:
            num = int(data["next"])
            people[key] = num
            data["next"] = num + 1
            data["people"] = people
            _save(store, data)

    _write_on_record(record, num)
    if persist_db and export_number_on_record(record) == num:
        # Always persist when we have an id (idempotent UPDATE)
        _persist_to_db(record, num)
    elif persist_db:
        _persist_to_db(record, num)
    return num
