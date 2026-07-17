"""Repair ghost export card numbers; keep intentional sequence only.

Keeps numbers 1-12 on their current holders (real Desktop exports through
Pedro Sauceda). Moves Sean Dalipsingh from 26 -> 13. Clears all other
export_number values and rebuilds data/card_release.json.

Usage:
  python scripts/repair_export_numbers.py
  python scripts/repair_export_numbers.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DB = ROOT / "data" / "offenders.db"
STORE = ROOT / "data" / "card_release.json"

# Intentional afternoon trail ends at Sauceda #12; next real export was
# Dalipsingh (was ghost-bumped to 26).
KEEP_MAX = 12
DALIPSINGH_ID = 155027
DALIPSINGH_NUM = 13


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not DB.is_file():
        print(f"missing db: {DB}")
        return 1

    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    rows = list(
        con.execute(
            "SELECT id, first_name, last_name, export_number, external_id, "
            "state, source_url FROM offenders WHERE export_number IS NOT NULL "
            "ORDER BY export_number, id"
        )
    )
    print(f"rows with export_number: {len(rows)}")

    # Prefer first id per number for 1..KEEP_MAX (drops duplicate #1 Barry etc.)
    keep_by_num: dict[int, sqlite3.Row] = {}
    for r in rows:
        n = int(r["export_number"])
        if 1 <= n <= KEEP_MAX and n not in keep_by_num:
            keep_by_num[n] = r

    keep_ids = {int(r["id"]) for r in keep_by_num.values()}
    keep_ids.add(DALIPSINGH_ID)

    planned: list[tuple[int, int | None, str]] = []
    for r in rows:
        rid = int(r["id"])
        old = int(r["export_number"])
        name = f"{r['first_name']} {r['last_name']}"
        if rid == DALIPSINGH_ID:
            new = DALIPSINGH_NUM
        elif rid in keep_ids and 1 <= old <= KEEP_MAX:
            new = old
        else:
            new = None
        if new != old:
            planned.append((rid, new, f"{name}: {old} -> {new}"))

    print("changes:")
    for _, _, msg in planned:
        print(f"  {msg}")
    print(f"  keep ids: {sorted(keep_ids)}")
    print(f"  next will be: {DALIPSINGH_NUM + 1}")

    if args.dry_run:
        print("dry-run: no writes")
        con.close()
        return 0

    # Clear all, then re-apply kept numbers
    con.execute("UPDATE offenders SET export_number = NULL WHERE export_number IS NOT NULL")
    for num, r in sorted(keep_by_num.items()):
        con.execute(
            "UPDATE offenders SET export_number = ? WHERE id = ?",
            (num, int(r["id"])),
        )
    con.execute(
        "UPDATE offenders SET export_number = ? WHERE id = ?",
        (DALIPSINGH_NUM, DALIPSINGH_ID),
    )
    con.commit()

    # Rebuild card_release.json from DB rows + stable keys
    from gui_app.shared.export_card_release import person_card_key

    people: dict[str, int] = {}
    final = list(
        con.execute(
            "SELECT * FROM offenders WHERE export_number IS NOT NULL "
            "ORDER BY export_number"
        )
    )
    for r in final:
        rec = dict(r)
        key = person_card_key(rec)
        people[key] = int(rec["export_number"])
        print(f"  kept #{rec['export_number']}: {rec.get('first_name')} "
              f"{rec.get('last_name')} key={key}")

    nxt = max(people.values(), default=0) + 1
    payload = {"next": nxt, "people": people}
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    con.close()
    print(f"wrote {STORE} next={nxt} people={len(people)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
