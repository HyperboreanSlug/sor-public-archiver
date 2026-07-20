"""Restore rows stripped because HTML chrome was treated as a person name.

After identity audit --repair, findings like HTML name 'Known Aliases' or
'Division of Criminal Justice Services' were nuclear-mismatched and cleared
source_url / report_html_path. Those are UI chrome, not people.

Reads the audit CSV and restores html_path + source_url when the extracted
html_name is not a real person name under the current gate.
Does NOT restore true wrong-person cases (e.g. Jorge → Eugene Williams).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scraper.database import Database
from scraper.reports.identity_gate import _looks_like_person_name


def _flags_list(raw) -> list:
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if not raw:
        return []
    try:
        p = json.loads(str(raw))
        if isinstance(p, list):
            return [str(x) for x in p]
        if isinstance(p, dict):
            return [str(x) for x in (p.get("tags") or [])]
    except (TypeError, json.JSONDecodeError):
        pass
    return [str(raw)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--report",
        default="data/reports/identity_audit_jorge_fix.csv",
    )
    ap.add_argument("--db", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    report = Path(args.report)
    if not report.is_file():
        print(f"missing report: {report}")
        return 1

    # offender_id -> best chrome false-positive finding
    restore: dict[int, dict] = {}
    with report.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if (row.get("severity") or "").lower() != "nuclear":
                continue
            if (row.get("code") or "") != "html_name_mismatch":
                continue
            hn = (row.get("html_name") or "").strip()
            if not hn:
                continue
            # Only restore when extracted "name" is chrome under current rules
            if _looks_like_person_name(hn):
                continue
            try:
                oid = int(row.get("offender_id") or 0)
            except ValueError:
                continue
            if not oid:
                continue
            restore[oid] = row

    print(f"chrome false-positive nuclear rows in CSV: {len(restore):,}")
    if args.limit and args.limit > 0:
        restore = dict(list(restore.items())[: int(args.limit)])

    db = Database(args.db)
    restored = 0
    skipped = 0
    try:
        for oid, row in restore.items():
            rec = db._conn.execute(
                "SELECT * FROM offenders WHERE id=?", (oid,)
            ).fetchone()
            if not rec:
                skipped += 1
                continue
            rec = dict(rec)
            html_path = (row.get("html_path") or "").strip()
            src_url = (row.get("source_url") or "").strip()
            changed = False
            if html_path and not (rec.get("report_html_path") or "").strip():
                # Prefer path if file exists
                p = Path(html_path)
                if not p.is_file():
                    p = ROOT / html_path
                if p.is_file():
                    rec["report_html_path"] = html_path
                    changed = True
            if src_url and not (rec.get("source_url") or "").strip():
                rec["source_url"] = src_url
                changed = True
            if not changed:
                skipped += 1
                continue
            # Drop false identity_html_mismatch when we restored chrome-only fail
            flags = _flags_list(rec.get("flags"))
            cleaned = []
            for t in flags:
                tl = t.lower()
                if "identity_html_mismatch" in tl:
                    continue
                if "name_mismatch" in tl and not _looks_like_person_name(
                    t.split(":", 2)[-1] if ":" in t else ""
                ):
                    # drop identity:name_mismatch:Known Aliases style
                    continue
                cleaned.append(t)
            rec["flags"] = json.dumps(cleaned)
            restored += 1
            if args.dry_run:
                print(
                    f"  would restore id={oid} {rec.get('full_name')}: "
                    f"html={html_path[:60]!r} url={src_url[:50]!r}"
                )
                continue
            db.update_offender(
                oid,
                {
                    "report_html_path": rec.get("report_html_path"),
                    "source_url": rec.get("source_url"),
                    "flags": rec.get("flags"),
                },
            )
        print(f"restored={restored} skipped={skipped} dry_run={args.dry_run}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
