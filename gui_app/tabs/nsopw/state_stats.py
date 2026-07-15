"""NSOPW jurisdiction list + local enriched/total counts for the state filter."""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

# Display order: US states then territories (NSOPW codes)
STATE_ORDER: Tuple[str, ...] = (
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI",
    "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN",
    "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH",
    "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA",
    "WV", "WI", "WY", "GU", "PR", "USVI", "AMERICANSAMOA", "CNMI",
)

_BULK_METHODS = frozenset({"direct", "arcgis", "hybrid", "html", "api"})


def registry_scrape_label(code: str) -> str:
    """yes = bulk/automated scrape path; limited = NSOPW/search only."""
    try:
        from scraper.config import REGISTRIES

        for r in REGISTRIES:
            if (r.abbr or "").upper() == code.upper():
                if (r.scrape_method or "").lower() in _BULK_METHODS:
                    return "yes"
                return "limited"
    except Exception:
        pass
    return "limited"


def _primary_state_sql_expr() -> str:
    return """
    UPPER(TRIM(
      CASE
        WHEN instr(COALESCE(NULLIF(TRIM(state), ''), NULLIF(TRIM(source_state), ''), ''), ' | ') > 0
          THEN substr(
            COALESCE(NULLIF(TRIM(state), ''), NULLIF(TRIM(source_state), ''), ''),
            1,
            instr(COALESCE(NULLIF(TRIM(state), ''), NULLIF(TRIM(source_state), ''), ''), ' | ') - 1
          )
        ELSE COALESCE(NULLIF(TRIM(state), ''), NULLIF(TRIM(source_state), ''), '?')
      END
    ))
    """


def load_state_record_stats(db_path: str) -> Dict[str, Tuple[int, int]]:
    """{STATE: (enriched, total)}. Enriched ≈ photo + race + crime + URL."""
    out: Dict[str, Tuple[int, int]] = {}
    try:
        from scraper.database import Database

        db = Database(db_path)
        try:
            st_expr = _primary_state_sql_expr()
            sql = f"""
            SELECT {st_expr} AS st,
              COUNT(*) AS total,
              SUM(CASE
                WHEN (photo_path IS NOT NULL AND TRIM(photo_path) != '')
                 AND (race IS NOT NULL AND TRIM(race) != '')
                 AND (
                   (crime IS NOT NULL AND TRIM(crime) != '')
                   OR (offense_description IS NOT NULL AND TRIM(offense_description) != '')
                   OR (offense_type IS NOT NULL AND TRIM(offense_type) != '')
                 )
                 AND (source_url IS NOT NULL AND TRIM(source_url) != '')
                THEN 1 ELSE 0 END) AS enriched
            FROM offenders
            GROUP BY st
            """
            for row in db._conn.execute(sql):
                st = (row["st"] or "?").strip().upper() or "?"
                out[st] = (int(row["enriched"] or 0), int(row["total"] or 0))
        finally:
            db.close()
    except Exception:
        pass
    return out


def format_state_option(
    code: str, *, scrape: str, enriched: int, total: int
) -> str:
    pct = (100.0 * enriched / total) if total else 0.0
    return (
        f"{code} · scrape:{scrape} · "
        f"{enriched:,} enriched ({pct:.1f}%) / {total:,} total"
    )


def build_state_dropdown_values(
    db_path: str,
    jurisdictions: Optional[Sequence[str]] = None,
) -> Tuple[List[str], Dict[str, Optional[List[str]]]]:
    """Combo labels and map display string → jurisdictions list (None = all)."""
    from scraper.nsopw.client import DEFAULT_JURISDICTIONS

    stats = load_state_record_stats(db_path)
    codes = list(jurisdictions) if jurisdictions else list(DEFAULT_JURISDICTIONS)
    ordered: List[str] = []
    seen: set = set()
    code_set = {x.upper() for x in codes}
    for c in STATE_ORDER:
        cu = c.upper()
        if cu in code_set or cu in stats:
            ordered.append(cu)
            seen.add(cu)
    for c in codes:
        cu = c.upper()
        if cu not in seen:
            ordered.append(cu)
            seen.add(cu)

    total_enr = sum(e for e, _ in stats.values())
    total_n = sum(t for _, t in stats.values())
    all_pct = (100.0 * total_enr / total_n) if total_n else 0.0
    all_label = (
        f"All · scrape:mixed · "
        f"{total_enr:,} enriched ({all_pct:.1f}%) / {total_n:,} total"
    )
    values = [all_label]
    mapping: Dict[str, Optional[List[str]]] = {all_label: None}

    for code in ordered:
        enr, tot = stats.get(code, (0, 0))
        label = format_state_option(
            code,
            scrape=registry_scrape_label(code),
            enriched=enr,
            total=tot,
        )
        values.append(label)
        mapping[label] = [code]

    return values, mapping
