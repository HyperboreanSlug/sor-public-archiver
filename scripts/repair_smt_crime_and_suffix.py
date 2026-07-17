"""
Repair crime fields polluted by SMT/tattoo tables, and restore NSOPW Jr/Sr suffixes.

- Clears crime/offense_* when text is SMT/demographic junk
- Re-parses report_html when available to fill real offenses
- Restores name.suffix from raw_data_json into full_name / last_name

Usage:
  python scripts/repair_smt_crime_and_suffix.py --dry-run
  python scripts/repair_smt_crime_and_suffix.py
  python scripts/repair_smt_crime_and_suffix.py --id 1625
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scraper.reports.fetcher import ReportFetcher  # noqa: E402
from scraper.reports.fetcher_crime import is_demographic_crime_junk  # noqa: E402

_SUFFIX_RE = re.compile(r"\b(JR|SR|II|III|IV|2ND|3RD|4TH|JUNIOR|SENIOR)\.?$", re.I)


def _suffix_from_raw(raw_json: str) -> str:
    if not raw_json:
        return ""
    try:
        obj = json.loads(raw_json)
    except Exception:
        return ""
    if not isinstance(obj, dict):
        return ""
    name = obj.get("name") if isinstance(obj.get("name"), dict) else {}
    suf = (name.get("suffix") or name.get("nameSuffix") or "").strip()
    return re.sub(r"^[,\s]+", "", suf).strip()


def _apply_suffix(full: str, last: str, first: str, mid: str, suf: str) -> tuple:
    if not suf:
        return full, last, first, mid
    suf_u = suf.upper().rstrip(".")
    full_s = (full or "").strip()
    last_s = (last or "").strip()
    if full_s and _SUFFIX_RE.search(full_s):
        # already has a suffix
        new_full = full_s
    else:
        base = full_s or " ".join(p for p in (first, mid, last_s) if p)
        new_full = f"{base} {suf}".strip() if base else suf
    if last_s and _SUFFIX_RE.search(last_s):
        new_last = last_s
    else:
        new_last = f"{last_s} {suf}".strip() if last_s else suf
    return new_full, new_last, first, mid


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--database", default=str(ROOT / "data" / "offenders.db"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--id", type=int, default=0, help="Only repair one offenders.id")
    args = ap.parse_args()

    db = Path(args.database)
    if not db.is_file():
        print(f"Missing DB: {db}")
        return 1

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    if args.id:
        rows = conn.execute(
            "SELECT * FROM offenders WHERE id = ?", (args.id,)
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT * FROM offenders
            WHERE (crime IS NOT NULL AND TRIM(crime) != '')
               OR (IFNULL(raw_data_json,'') LIKE '%\"suffix\"%')
               OR (IFNULL(raw_data_json,'') LIKE '%suffix%')
            """
        ).fetchall()

    fetcher = ReportFetcher(delay=0)
    n_crime = 0
    n_name = 0
    try:
        for r in rows:
            rid = int(r["id"])
            updates: dict = {}
            crime = (r["crime"] or "").strip()
            odesc = (r["offense_description"] or "").strip() if "offense_description" in r.keys() else ""
            otype = (r["offense_type"] or "").strip() if "offense_type" in r.keys() else ""

            need_crime = bool(
                (crime and is_demographic_crime_junk(crime))
                or (odesc and is_demographic_crime_junk(odesc))
                or (otype and is_demographic_crime_junk(otype))
            )
            if need_crime:
                updates["crime"] = None
                updates["offense_description"] = None
                updates["offense_type"] = None
                html_path = (r["report_html_path"] or "").strip()
                if html_path:
                    p = Path(html_path)
                    if not p.is_file():
                        p = ROOT / html_path
                    if p.is_file():
                        try:
                            html = p.read_text(encoding="utf-8", errors="replace")
                            found = fetcher._from_html(html, r["source_url"] or "")
                            new_c = (found.get("crime") or "").strip()
                            if new_c and not is_demographic_crime_junk(new_c):
                                updates["crime"] = new_c
                                updates["offense_description"] = new_c
                                if found.get("full_name") and not (
                                    r["full_name"] or ""
                                ).upper().endswith("JR"):
                                    # Prefer HTML name when it includes suffix
                                    html_name = found.get("full_name")
                                    if html_name and len(str(html_name)) >= len(
                                        str(r["full_name"] or "")
                                    ):
                                        updates["full_name"] = html_name
                        except Exception as e:
                            print(f"  id={rid} reparse fail: {e}")
                n_crime += 1

            suf = _suffix_from_raw(r["raw_data_json"] or "")
            if suf:
                nf, nl, _, _ = _apply_suffix(
                    r["full_name"] or "",
                    r["last_name"] or "",
                    r["first_name"] or "",
                    r["middle_name"] or "",
                    suf,
                )
                if nf != (r["full_name"] or "") or nl != (r["last_name"] or ""):
                    updates["full_name"] = nf
                    updates["last_name"] = nl
                    n_name += 1

            if not updates:
                continue
            if args.dry_run:
                if n_crime + n_name <= 8 or rid == args.id:
                    print(f"id={rid} would set {updates}")
                continue
            cols = ", ".join(f"{k}=?" for k in updates)
            conn.execute(
                f"UPDATE offenders SET {cols} WHERE id=?",
                (*updates.values(), rid),
            )
    finally:
        fetcher.close()

    if not args.dry_run:
        conn.commit()
    conn.close()
    mode = "would touch" if args.dry_run else "updated"
    print(f"{mode}: crime_fixes≈{n_crime} name_suffix_fixes≈{n_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
