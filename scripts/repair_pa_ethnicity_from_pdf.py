"""Fill PA ethnicity from Megan's Law public report PDFs.

PhysDesc HTML only has Race; Ethnicity is on View Report PDF.
"""
from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scraper.reports.fetcher import ReportFetcher  # noqa: E402
from scraper.reports.pdf_fields import (  # noqa: E402
    extract_pdf_text,
    fields_from_pdf_text,
    find_pa_public_report_url,
)

DB = ROOT / "data" / "offenders.db"


def main() -> int:
    dry = "--dry-run" in sys.argv
    limit = 0
    only_id = 0
    for a in sys.argv[1:]:
        if a.startswith("--limit="):
            limit = int(a.split("=", 1)[1])
        if a.startswith("--id="):
            only_id = int(a.split("=", 1)[1])

    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    if only_id:
        rows = conn.execute(
            "SELECT id, full_name, ethnicity, race, source_url, report_html_path, "
            "source_state, state FROM offenders WHERE id = ?",
            (only_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, full_name, ethnicity, race, source_url, report_html_path,
                   source_state, state
            FROM offenders
            WHERE (state = 'PA' OR source_state LIKE '%PA%')
              AND (ethnicity IS NULL OR TRIM(ethnicity) = '')
              AND report_html_path IS NOT NULL AND TRIM(report_html_path) != ''
            ORDER BY id
            """
        ).fetchall()
    if limit > 0:
        rows = rows[:limit]

    fetcher = ReportFetcher(delay=0.35)
    updated = 0
    failed = 0
    samples: list[str] = []

    for i, r in enumerate(rows):
        oid = int(r["id"])
        html_rel = (r["report_html_path"] or "").strip()
        html_path = None
        for cand in (
            Path(html_rel),
            ROOT / html_rel,
            ROOT / html_rel.replace("\\", "/"),
        ):
            if cand.is_file():
                html_path = cand
                break
        if html_path is None:
            failed += 1
            continue

        html = html_path.read_text(encoding="utf-8", errors="replace")
        # Prefer archived_from comment as base
        base = (r["source_url"] or "").strip()
        if "archived_from:" in html[:500]:
            for line in html.splitlines()[:5]:
                if "archived_from:" in line:
                    base = line.split("archived_from:", 1)[1].strip()
                    break
        pdf_url = find_pa_public_report_url(html, base)
        if not pdf_url:
            # Build from offender id in path / external
            import re

            m = re.search(r"OffenderID=(\d+)", html, re.I)
            if not m:
                m = re.search(r"PhysDesc/(\d+)", html, re.I)
            if m:
                pdf_url = (
                    "https://www.meganslaw.psp.pa.gov/Reports/"
                    f"MegansOffenderReports?OffenderID={m.group(1)}"
                    "&ReportName=OffenderPublicRpt"
                )
        if not pdf_url:
            failed += 1
            continue

        try:
            # Warm session via terms / physdesc when needed
            warm = (base or pdf_url).split("?")[0]
            if "meganslaw.psp.pa.gov" in warm:
                try:
                    fetcher.fetch_demographics(
                        warm if "PhysDesc" in warm or "OffenderDetails" in warm else base or warm,
                        save_html=False,
                        jurisdiction="PA",
                    )
                except Exception:
                    pass
            resp, _ = fetcher._get_with_https_fallback(pdf_url)
            passed = fetcher._click_through_disclaimers(resp, max_hops=3)
            if passed is not None:
                resp = passed
                body = getattr(resp, "content", b"") or b""
                if body[:4] != b"%PDF":
                    resp, _ = fetcher._get_with_https_fallback(pdf_url)
            body = getattr(resp, "content", b"") or b""
            if body[:4] != b"%PDF":
                failed += 1
                if len(samples) < 8:
                    samples.append(
                        f"  id={oid} not pdf ct={resp.headers.get('Content-Type')} "
                        f"url={getattr(resp, 'url', '')}"
                    )
                continue
            fields = fields_from_pdf_text(extract_pdf_text(body))
            eth = (fields.get("ethnicity") or "").strip()
            if not eth:
                failed += 1
                continue
            race = (fields.get("race") or "").strip()
            if not dry:
                if race and not (r["race"] or "").strip():
                    conn.execute(
                        "UPDATE offenders SET ethnicity = ?, race = ? WHERE id = ?",
                        (eth, race, oid),
                    )
                else:
                    conn.execute(
                        "UPDATE offenders SET ethnicity = ? WHERE id = ?",
                        (eth, oid),
                    )
            updated += 1
            if "ALVAREZ" in (r["full_name"] or "").upper() or len(samples) < 10:
                samples.append(f"  id={oid} {r['full_name']!r} -> {eth!r}")
        except Exception as e:
            failed += 1
            if len(samples) < 8:
                samples.append(f"  id={oid} err {e}")

        if (i + 1) % 25 == 0:
            if not dry:
                conn.commit()
            print(f"  … {i+1}/{len(rows)} updated={updated} failed={failed}")
            time.sleep(0.2)

    if not dry:
        conn.commit()
    fetcher.close()
    conn.close()
    print(
        f"{'DRY ' if dry else ''}done rows={len(rows)} "
        f"updated={updated} failed={failed}"
    )
    for s in samples:
        print(s)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
