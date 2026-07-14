#!/usr/bin/env python3
"""
CLI tool for mass-downloading and searching US sex offender databases.

Usage:
    # Scrape all states
    python -m scraper.cli scrape --all

    # Scrape specific states
    python -m scraper.cli scrape --states FL,TX,CA,NY

    # Search by name
    python -m scraper.cli search --name "Garcia"

    # Filter by race
    python -m scraper.cli search --race "White"

    # Find misclassifications (Hispanic names marked as White)
    python -m scraper.cli misclassify --ethnicity hispanic

    # Mugshot verify (name + face) / gross scan (face only)
    python -m scraper.cli mugshot-verify --ethnicity indian --limit 200
    python -m scraper.cli mugshot-scan --min-conf 0.85 --limit 500

    # Export results to CSV
    python -m scraper.cli export --output results.csv
"""

import argparse
import csv
from pathlib import Path

def cmd_nsopw(args: argparse.Namespace) -> None:
    """Search NSOPW for common ethnic surnames and build a local database."""
    from .nsopw_builder import NSOPWEthnicDatabaseBuilder

    first_names = None
    first_mode = getattr(args, "first_mode", "initials") or "initials"
    if args.first_names:
        first_names = [x.strip() for x in args.first_names.split(",") if x.strip()]
        first_mode = "custom"
    elif getattr(args, "initials_only", False):
        first_names = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        first_mode = "initials"

    jurisdictions = None
    if args.jurisdictions:
        jurisdictions = [x.strip().upper() for x in args.jurisdictions.split(",") if x.strip()]

    print("\n" + "=" * 60)
    print("  NSOPW Ethnic Name Search → Local Database")
    print("=" * 60)
    print("  Source: https://www.nsopw.gov/")
    print("  Short partials (e.g. M + AH) meet the 3-letter min and collapse surnames.")
    print("  Rate limits enforced; Conditions of Use apply.")
    print("=" * 60 + "\n")

    builder = NSOPWEthnicDatabaseBuilder(
        db_path=args.database or "data/offenders.db",
        delay=args.delay,
        report_delay=args.report_delay,
        html_dir=getattr(args, "html_dir", None) or "data/report_pages",
        report_threads=getattr(args, "report_threads", 1) or 1,
    )
    try:
        stats = builder.build(
            ethnicity=args.ethnicity,
            surnames_limit=args.surnames,
            all_surnames=bool(getattr(args, "all_surnames", False)),
            subcategory=getattr(args, "subcategory", None) or "all",
            first_names=first_names,
            first_mode=first_mode,
            jurisdictions=jurisdictions,
            max_searches=args.max_searches,
            max_names=(
                args.max_names
                if getattr(args, "max_names", None) is not None
                else args.max_reports
            ),
            skip_existing_urls=not args.force_reinsert,
            skip_completed_searches=not bool(getattr(args, "no_resume", False)),
            new_files_only=not bool(getattr(args, "redownload_html", False)),
            enrich_reports=not args.skip_reports,
            enrich_scope=getattr(args, "enrich_scope", "all") or "all",
            save_html=not getattr(args, "no_save_html", False),
        )
        print(f"\nDatabase: {args.database or 'data/offenders.db'}")
        print(f"Inserted {stats.inserted} new records "
              f"({stats.reports_with_demographics} with race/ethnicity from reports, "
              f"{stats.html_saved} HTML pages saved).")
    finally:
        builder.close()


