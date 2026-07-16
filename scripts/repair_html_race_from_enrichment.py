"""
Recover live-scrape race into sources_json from report_enrichment.

Fixes rows where bulk CSV re-tag collapsed HTML race (e.g. JACKSON W vs Black).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scraper.database import Database
from scraper.database.sources_race_verify import recover_report_enrichment_into_sources


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", default=None, help="Path to offenders.db")
    p.add_argument("--limit", type=int, default=0, help="Max rows to scan (0=all)")
    p.add_argument("--id", type=int, default=0, help="Repair a single offender id")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    db = Database(args.db)
    try:
        if args.id:
            rows = [db.get_offender_by_id(args.id)]
            rows = [r for r in rows if r]
        else:
            sql = (
                "SELECT * FROM offenders WHERE raw_data_json LIKE '%report_enrichment%'"
            )
            if args.limit and args.limit > 0:
                sql += f" LIMIT {int(args.limit)}"
            rows = [dict(r) for r in db._conn.execute(sql).fetchall()]

        updated = 0
        scanned = 0
        for rec in rows:
            scanned += 1
            before = rec.get("race")
            if not recover_report_enrichment_into_sources(rec):
                continue
            after = rec.get("race")
            oid = rec.get("id")
            print(f"  id={oid} {rec.get('full_name') or ''} race {before!r} → {after!r}")
            if args.dry_run or oid is None:
                updated += 1
                continue
            patch = {
                k: rec.get(k)
                for k in ("sources_json", "race", "flags")
                if rec.get(k) is not None
            }
            if db.update_offender(int(oid), patch):
                updated += 1
        print(f"scanned={scanned} updated={updated} dry_run={args.dry_run}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
