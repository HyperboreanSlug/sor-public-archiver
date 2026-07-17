"""Persistent card release numbers for SORPA export cards.

Each *distinct person* gets one release number. Re-exporting the same person
reuses their number; the first export of a new person increments the sequence.
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
    # Coerce values to int
    clean: Dict[str, int] = {}
    for k, v in people.items():
        try:
            n = int(v)
        except (TypeError, ValueError):
            continue
        if n >= 1 and str(k):
            clean[str(k)] = n
    return {"next": nxt, "people": clean}


def _save(path: Path, data: MutableMapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = {
        "next": int(data.get("next") or 1),
        "people": dict(data.get("people") or {}),
    }
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def release_number_for(record: Mapping[str, Any], *, path: Optional[Path] = None) -> int:
    """Return this person's release number, assigning a new one if first export."""
    key = person_card_key(record)
    store = Path(path) if path is not None else _store_path()
    with _LOCK:
        data = _load(store)
        people: Dict[str, int] = data["people"]
        if key in people:
            return int(people[key])
        num = int(data["next"])
        people[key] = num
        data["next"] = num + 1
        data["people"] = people
        _save(store, data)
        return num


def format_release_label(num: int) -> str:
    """Footer text for a release number."""
    if num < 1:
        return ""
    return f"No. {num}"
