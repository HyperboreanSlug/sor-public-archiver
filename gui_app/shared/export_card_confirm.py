"""Auto-confirm misclassification when a share card is exported."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Optional


def mark_export_confirmed_incorrect(
    record: Mapping[str, Any],
    *,
    db_path: Optional[str] = None,
) -> bool:
    """Mark this person confirmed *incorrect* (misclassified) after card export.

    Writes ``ethnicity_review=incorrect`` into ``offenders.flags`` and
    ``report_verdicts.json`` so Reports / Misclassify show
    "Confirmed incorrect" without a manual click.
    """
    if not isinstance(record, (dict, MutableMapping)):
        rec: dict = dict(record)
    else:
        rec = record  # type: ignore[assignment]

    path = db_path or str(
        rec.get("_db_path") or rec.get("db_path") or ""
    ).strip()
    if not path:
        try:
            from scraper.paths import project_root

            path = str(project_root() / "data" / "offenders.db")
        except Exception:
            path = "data/offenders.db"

    ok = False
    try:
        from gui_app.shared.verdict_persist import persist_ethnicity_verdict

        success, flags_json, _err = persist_ethnicity_verdict(
            path, rec, "incorrect"
        )
        if success:
            ok = True
            if flags_json and isinstance(rec, dict):
                rec["flags"] = flags_json
    except Exception:
        pass

    # Mirror into Reports JSON store (id key is enough for reload)
    rid = rec.get("id") if isinstance(rec, dict) else None
    if rid is not None and str(rid).strip() != "":
        try:
            from scraper.paths import project_root

            vp = project_root() / "data" / "report_verdicts.json"
            data: dict = {}
            if vp.is_file():
                try:
                    raw = json.loads(vp.read_text(encoding="utf-8"))
                    if isinstance(raw, dict):
                        data = raw
                except (OSError, json.JSONDecodeError, TypeError):
                    data = {}
            key = f"id:{int(rid)}"
            data[key] = "confirmed"
            data[str(key)] = "confirmed"
            vp.parent.mkdir(parents=True, exist_ok=True)
            vp.write_text(
                json.dumps(data, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            ok = True
        except Exception:
            pass
    return ok
