"""
Rewrite dead Texas publicsite.dps.texas.gov rapsheet URLs to live sor.dps.texas.gov.

Old (503 / dead):
  https://publicsite.dps.texas.gov/SexOffenderRegistry/Search/Rapsheet?sid=…
  https://publicsite.dps.texas.gov/sexoffenderregistry/search/rapsheet   (no sid)

New:
  https://sor.dps.texas.gov/PublicSite/Search/Rapsheet?sid={SID}
  https://sor.dps.texas.gov/PublicSite/Search   (no sid)

Usage:
  python scripts/repair_tx_dps_urls.py --dry-run
  python scripts/repair_tx_dps_urls.py
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

from scraper.public_links import split_source_urls  # noqa: E402
from scraper.public_links_tx import (  # noqa: E402
    extract_tx_sid,
    is_tx_dps_url,
    normalize_tx_dps_url,
    tx_rapsheet_url,
)


def _rewrite_blob(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return text
    low = text.lower()
    if "dps.texas" not in low and "sid=" not in low:
        return text
    parts = split_source_urls(text)
    if not parts:
        if is_tx_dps_url(text) or "sid=" in low:
            return normalize_tx_dps_url(text)
        return text
    out = []
    for p in parts:
        if is_tx_dps_url(p) or (
            "sid=" in p.lower() and "texas" in p.lower()
        ):
            out.append(normalize_tx_dps_url(p))
        else:
            out.append(p)
    return " | ".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--database", default=str(ROOT / "data" / "offenders.db"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    db = Path(args.database)
    if not db.is_file():
        print(f"Missing DB: {db}")
        return 1

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, source_url, external_id, source_state, state
        FROM offenders
        WHERE IFNULL(source_url,'') LIKE '%dps.texas%'
           OR IFNULL(source_url,'') LIKE '%texas.gov%SexOffender%'
           OR IFNULL(external_id,'') LIKE '%dps.texas%'
           OR (
                (UPPER(IFNULL(source_state,'')) LIKE '%TX%'
                 OR UPPER(IFNULL(state,'')) LIKE '%TX%')
                AND (
                    IFNULL(source_url,'') LIKE '%sid=%'
                    OR IFNULL(external_id,'') GLOB '[0-9]*'
                )
           )
        """
    ).fetchall()

    updated = 0
    for r in rows:
        rid = int(r["id"])
        su = r["source_url"] or ""
        ext = r["external_id"] or ""
        new_su = _rewrite_blob(su) if su else su
        new_ext = ext
        # Prefer bare SID as external_id
        sid = extract_tx_sid(new_su) or extract_tx_sid(ext)
        if not sid and re.fullmatch(r"\d{5,12}", (ext or "").strip()):
            sid = ext.strip()
        if sid:
            new_ext = sid
            if not new_su or is_tx_dps_url(new_su) or "sid=" in (new_su or "").lower():
                new_su = tx_rapsheet_url(sid)
        if new_su == su and new_ext == ext:
            continue
        updated += 1
        if args.dry_run:
            if updated <= 6:
                print(f"  id={rid}")
                print(f"    url: {(su or '')[:90]} → {(new_su or '')[:90]}")
                print(f"    ext: {(ext or '')[:40]} → {(new_ext or '')[:40]}")
            continue
        conn.execute(
            "UPDATE offenders SET source_url=?, external_id=? WHERE id=?",
            (new_su or None, new_ext or None, rid),
        )

    if not args.dry_run:
        conn.commit()
    conn.close()
    print(f"{'would update' if args.dry_run else 'updated'} {updated} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
