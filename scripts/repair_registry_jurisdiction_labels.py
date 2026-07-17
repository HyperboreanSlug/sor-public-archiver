"""Align offenders.state / source_state / sources_json with registry URL host.

Out-of-state registrants were often labeled by residential address (e.g. FL)
while source_url pointed at another state's flyer (e.g. GA). This repair sets
the registry host as the primary jurisdiction and reorders multi-state tags.

Skips multi-agency hosts (iCrimeWatch / NSOPW) where host ≠ a single state.

Usage (from SORPA root)::

    python scripts/repair_registry_jurisdiction_labels.py
    python scripts/repair_registry_jurisdiction_labels.py --dry-run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scraper.database import Database
from scraper.database.sources import dumps_sources, jurisdiction_from_url, parse_sources
from scraper.public_links import split_source_urls

_SHARED_HOSTS = (
    "icrimewatch",
    "sheriffalerts",
    "communitynotification",
    "nsopw.gov",
)


def url_reg_jur(url: str) -> str:
    u = (url or "").lower()
    if any(h in u for h in _SHARED_HOSTS):
        return ""
    return jurisdiction_from_url(url) or ""


def primary(s: str) -> str:
    s = (s or "").strip().upper()
    if not s:
        return ""
    return s.split("|")[0].strip().upper()


def merge_states(primary_jur: str, old: str) -> str:
    old = (old or "").strip()
    if not old:
        return primary_jur
    parts: list[str] = []
    for p in old.replace(",", "|").split("|"):
        p = p.strip().upper()
        if p and p not in parts:
            parts.append(p)
    if primary_jur in parts:
        parts = [primary_jur] + [p for p in parts if p != primary_jur]
    else:
        parts = [primary_jur] + parts
    return " | ".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/offenders.db")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    db = Database(args.db)
    c = db._conn
    candidates = []
    for row in c.execute(
        """
        SELECT id, state, source_state, source_url, sources_json
        FROM offenders
        WHERE source_url IS NOT NULL AND TRIM(source_url) != ''
        """
    ):
        urls = split_source_urls(row["source_url"] or "")
        jurs = [url_reg_jur(u) for u in urls if url_reg_jur(u)]
        if not jurs or len(set(jurs)) != 1:
            continue
        uj = jurs[0]
        pst = primary(row["state"])
        psst = primary(row["source_state"])
        if pst == uj and (not psst or psst == uj):
            continue
        candidates.append((row, uj))

    print(f"candidates: {len(candidates):,}")
    if args.dry_run:
        db.close()
        return 0

    updated = 0
    src_fixed = 0
    for row, uj in candidates:
        patch = {
            "state": merge_states(uj, row["state"] or ""),
            "source_state": merge_states(uj, row["source_state"] or ""),
        }
        try:
            srcs = parse_sources(row["sources_json"])
        except Exception:
            srcs = []
        changed = False
        for s in srcs:
            su = str(s.get("source_url") or "")
            sj_url = url_reg_jur(su)
            if not sj_url:
                continue
            sj = str(s.get("jurisdiction") or "").strip().upper()
            if sj == sj_url:
                continue
            s["jurisdiction"] = sj_url
            lab = str(s.get("label") or "")
            if lab.startswith(sj + " ") or lab.startswith(sj + " report"):
                s["label"] = lab.replace(sj, sj_url, 1)
            elif "report" in lab.lower() or not lab:
                s["label"] = f"{sj_url} report HTML"
            changed = True
            src_fixed += 1
        if changed:
            patch["sources_json"] = dumps_sources(srcs)
        if db.update_offender(int(row["id"]), patch):
            updated += 1

    print(f"rows updated: {updated:,}")
    print(f"source entries retagged: {src_fixed:,}")
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
