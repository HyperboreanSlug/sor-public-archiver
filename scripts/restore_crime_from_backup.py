"""Restore crime fields wrongly cleared as SMT junk (from a DB backup).

Only restores when backup crime has real offense words and current is empty.
Strips leading 'Scars, Marks and Tattoos —' chrome when present.
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scraper.reports.fetcher_crime import is_demographic_crime_junk  # noqa: E402

_SMT_PREFIX = re.compile(
    r"(?i)^scars?,?\s*marks?\s*(?:and|&)?\s*tattoos?\s*[-–—:|/]*\s*"
)
_OFFENSE = re.compile(
    r"(?i)\b(?:rape|assault|battery|molest|abuse|sodomy|indecent|porn|sex(?:ual)?|"
    r"lewd|kidnap|fail(?:ure)?\s+to\s+regist|csc|criminal\s+sexual|exploitation|"
    r"enticing|voyeur|exposure|incest|homicide|murder|solicitation|sodomy|"
    r"carnal|indecency|rape|stat(?:utory)?)\b"
)


def _clean_crime(c: str) -> str:
    t = " ".join((c or "").split()).strip()
    t = _SMT_PREFIX.sub("", t).strip()
    # Drop trailing "More Information *" registry chrome
    t = re.sub(r"(?i)\s*\*\s*,?\s*More Information\b.*$", "", t).strip(" ,;—-")
    return t


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--database", default=str(ROOT / "data" / "offenders.db"))
    ap.add_argument(
        "--backup",
        default="",
        help="Backup .db path (default: newest in data/backups)",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    db = Path(args.database)
    if args.backup:
        bak = Path(args.backup)
    else:
        cands = sorted(
            (ROOT / "data" / "backups").glob("*.db"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        bak = cands[0] if cands else Path()
    if not db.is_file() or not bak.is_file():
        print("missing db or backup", db, bak)
        return 1

    conn = sqlite3.connect(str(db))
    conn.execute("ATTACH DATABASE ? AS bak", (str(bak),))
    rows = conn.execute(
        """
        SELECT m.id, b.crime AS old_crime, m.crime AS new_crime, m.full_name
        FROM bak.offenders b
        JOIN main.offenders m ON m.id = b.id
        WHERE IFNULL(b.crime,'') != ''
          AND IFNULL(m.crime,'') = ''
        """
    ).fetchall()
    restored = 0
    skipped = 0
    for rid, old, _new, name in rows:
        cleaned = _clean_crime(old or "")
        if not cleaned or not _OFFENSE.search(cleaned):
            skipped += 1
            continue
        if is_demographic_crime_junk(cleaned):
            skipped += 1
            continue
        restored += 1
        if args.dry_run:
            if restored <= 8:
                print(f"  would restore id={rid} {name}: {cleaned[:100]}")
            continue
        conn.execute(
            "UPDATE offenders SET crime=?, offense_description=? WHERE id=?",
            (cleaned, cleaned, rid),
        )
    if not args.dry_run:
        conn.commit()
    conn.close()
    print(
        f"{'would restore' if args.dry_run else 'restored'} {restored} "
        f"(skipped {skipped}) from {bak.name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
