"""Repair NV multi-column crime dumps and Start Date county pollution.

NV sexoffenders.nv.gov offense tables were scraped as:
  date; conviction description; court; name; location; institution
and RowHead pairing set county to the next row's "Start Date: …".

Re-parses archived report HTML when available; otherwise cleans crime heuristically.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scraper.reports.fetcher import ReportFetcher  # noqa: E402
from scraper.reports.fetcher_crime import is_demographic_crime_junk  # noqa: E402

DB = ROOT / "data" / "offenders.db"

_COURT_BIT = re.compile(
    r"(?i)\b(?:superior\s*court|circuit\s+court|district\s+court|"
    r"dept\.?\s+of\s+corrections|department\s+of\s+corrections)"
)
_DATE_ONLY = re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4}$")
_CITY_ST = re.compile(r"(?i)^[A-Za-z .'-]+,\s*[A-Z]{2}$")
_START_DATE_COUNTY = re.compile(r"(?i)^start\s+date\b")


def _resolve_html(rel: str) -> Optional[Path]:
    if not rel:
        return None
    for cand in (Path(rel), ROOT / rel, ROOT / rel.replace("\\", "/")):
        if cand.is_file():
            return cand
    return None


def _looks_multi_col_crime(text: str) -> bool:
    s = (text or "").strip()
    if not s:
        return False
    if _COURT_BIT.search(s):
        return True
    if s.count(";") >= 3 or s.count("|") >= 3:
        if re.search(r"(?i)\b(?:court|corrections|dept)\b", s):
            return True
    return False


def _heuristic_crime(text: str, full_name: str = "") -> str:
    """Pick the offense phrase from a multi-column NV/CA dump."""
    s = (text or "").strip()
    if not s:
        return ""
    parts = re.split(r"\s*[;|]\s*", s)
    name_tokens = {t for t in re.split(r"\s+", (full_name or "").upper()) if len(t) > 1}
    best = ""
    for p in parts:
        p = p.strip()
        if not p or len(p) < 3:
            continue
        if _DATE_ONLY.match(p) or _CITY_ST.match(p):
            continue
        if _COURT_BIT.search(p):
            continue
        up = p.upper()
        # Drop conviction-name cells (person's name)
        words = {w for w in re.split(r"\s+", up) if w}
        if name_tokens and words and words.issubset(name_tokens | {","}):
            continue
        offense_hit = bool(
            re.search(
                r"(?i)\b(?:rape|assault|battery|lewd|sex|child|molest|kidnap|"
                r"porn|indecent|fail|offense|conduct|sodomy|288|261|289)\b",
                p,
            )
        )
        if re.fullmatch(r"[A-Z][A-Z' \-.]{2,50}", p) and not offense_hit:
            continue
        if offense_hit:
            if len(p) > len(best):
                best = p
        elif not best and len(p) > 12:
            best = p
    return best[:800]


def _patch_from_html(fetcher: ReportFetcher, html_path: Path, base: str) -> Dict[str, Any]:
    html = html_path.read_text(encoding="utf-8", errors="replace")
    found = fetcher._from_html(html, base)
    out: Dict[str, Any] = {}
    crime = (found.get("crime") or "").strip()
    if crime and not is_demographic_crime_junk(crime):
        out["crime"] = crime
        out["offense_description"] = crime
        out["offense_type"] = crime if len(crime) < 120 else crime[:120]
    county = (found.get("county") or "").strip()
    if county and not _START_DATE_COUNTY.match(county):
        out["county"] = county
    conv = (found.get("conviction_date") or "").strip()
    if conv:
        out["conviction_date"] = conv
    return out


def _update_sources_json(raw: Optional[str], patch: Dict[str, Any]) -> Optional[str]:
    if not raw or not patch:
        return None
    try:
        sources = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(sources, list):
        return None
    changed = False
    for src in sources:
        if not isinstance(src, dict):
            continue
        fields = src.get("fields")
        if not isinstance(fields, dict):
            continue
        if src.get("type") != "report_html" and "report" not in str(src.get("origin") or ""):
            continue
        for k in ("crime", "offense_description", "county", "offense_type"):
            if k in patch and patch[k] is not None:
                if fields.get(k) != patch[k]:
                    fields[k] = patch[k]
                    changed = True
    return json.dumps(sources, ensure_ascii=False) if changed else None


def main() -> int:
    dry = "--dry-run" in sys.argv
    only_id = None
    for a in sys.argv[1:]:
        if a.startswith("--id="):
            only_id = int(a.split("=", 1)[1])

    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    q = """
        SELECT id, full_name, crime, offense_type, offense_description,
               county, conviction_date, source_url, report_html_path, sources_json
        FROM offenders
        WHERE county LIKE 'Start Date%'
           OR crime LIKE '%SUPERIOR COURT%'
           OR crime LIKE '%superior court%'
           OR crime LIKE '%courtof%'
           OR crime LIKE '%DEPT OF CORRECTIONS%'
           OR crime LIKE '%Dept of Corrections%'
           OR offense_description LIKE '%SUPERIOR COURT%'
           OR offense_description LIKE '%courtof%'
           OR offense_description LIKE '%DEPT OF CORRECTIONS%'
    """
    params: list = []
    if only_id is not None:
        q = """
            SELECT id, full_name, crime, offense_type, offense_description,
                   county, conviction_date, source_url, report_html_path, sources_json
            FROM offenders WHERE id = ?
        """
        params = [only_id]
    rows = conn.execute(q, params).fetchall()
    fetcher = ReportFetcher(delay=0)
    updated = 0
    crime_n = 0
    county_n = 0
    samples: list[str] = []

    for r in rows:
        oid = int(r["id"])
        name = r["full_name"] or ""
        patch: Dict[str, Any] = {}
        crime = (r["crime"] or "").strip()
        county = (r["county"] or "").strip()
        need_crime = _looks_multi_col_crime(crime) or _looks_multi_col_crime(
            r["offense_description"] or ""
        )
        need_county = bool(county and _START_DATE_COUNTY.match(county))

        html_path = _resolve_html(r["report_html_path"] or "")
        if html_path is not None and (need_crime or need_county):
            try:
                found = _patch_from_html(
                    fetcher, html_path, r["source_url"] or ""
                )
            except Exception as e:
                samples.append(f"  parse fail id={oid}: {e}")
                found = {}
            new_crime = (found.get("crime") or "").strip()
            if new_crime and (
                "email subject" in new_crime.lower()
                or "offendersid" in new_crime.lower()
            ):
                new_crime = ""
            if need_crime and new_crime:
                patch["crime"] = new_crime
                patch["offense_description"] = new_crime
                patch["offense_type"] = new_crime if len(new_crime) < 120 else new_crime[:120]
                if found.get("conviction_date") and not r["conviction_date"]:
                    patch["conviction_date"] = found["conviction_date"]
                crime_n += 1
            elif need_crime and html_path is not None and not new_crime:
                # HTML has offense table but empty description cells — clear dump
                patch["crime"] = None
                patch["offense_description"] = None
                patch["offense_type"] = None
                crime_n += 1
            if need_county and found.get("county"):
                patch["county"] = found["county"]
                county_n += 1

        if need_crime and "crime" not in patch:
            cleaned = _heuristic_crime(crime or (r["offense_description"] or ""), name)
            if cleaned and cleaned != crime:
                patch["crime"] = cleaned
                patch["offense_description"] = cleaned
                patch["offense_type"] = cleaned if len(cleaned) < 120 else cleaned[:120]
                crime_n += 1
            elif need_crime and _looks_multi_col_crime(crime):
                # Court/name dump with no recoverable offense phrase
                patch["crime"] = None
                patch["offense_description"] = None
                patch["offense_type"] = None
                crime_n += 1

        if need_county and "county" not in patch:
            # Prefer clearing garbage over leaving a registration start date
            patch["county"] = None
            county_n += 1

        if not patch:
            continue

        src_json = _update_sources_json(r["sources_json"], patch)
        if src_json:
            patch["sources_json"] = src_json

        updated += 1
        if "ALAWI" in name.upper() or len(samples) < 8:
            samples.append(
                f"  id={oid} {name!r}: "
                + ", ".join(f"{k}={str(v)[:70]!r}" for k, v in patch.items() if k != "sources_json")
            )
        if not dry:
            cols = ", ".join(f"{k} = ?" for k in patch)
            conn.execute(
                f"UPDATE offenders SET {cols} WHERE id = ?",
                (*patch.values(), oid),
            )

    if not dry:
        conn.commit()
    print(
        f"{'DRY ' if dry else ''}updated={updated} crime_fixed={crime_n} "
        f"county_fixed={county_n} candidates={len(rows)}"
    )
    for s in samples:
        print(s)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
