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

def cmd_search(args: argparse.Namespace) -> None:
    """Search offender database."""
    from .searcher import SexOffenderSearcher

    db_path = args.database or "data/offenders.db"
    searcher = SexOffenderSearcher(db_path=db_path)

    try:
        if args.name:
            results = searcher.search_by_name(
                name=args.name,
                state=args.state,
                race=args.race,
                limit=args.limit
            )
            print(f"\n{'='*60}")
            print(f"  Search Results for '{args.name}'")
            print(f"{'='*60}")
            print(f"  Total matching: {results.total_count}")
            print(f"  Query time: {results.query_time_ms:.1f}ms")

            if results.records:
                print(f"\n  {'Name':<35} {'Race':<12} {'State':<6} {'Age':>4} {'County':<20}")
                print(f"  {'-'*87}")
                for r in results.records[:args.limit]:
                    name = f"{r.get('first_name', '') or ''} {r.get('last_name', '') or ''}".strip()
                    race = (r.get("race") or "N/A")[:12]
                    state = (r.get("state") or "N/A")[:6]
                    age = r.get("age", "")
                    county = (r.get("county") or "N/A")[:20]
                    print(f"  {name:<35} {race:<12} {state:<6} {str(age):>4} {county:<20}")

            if args.export:
                searcher.db.export_to_csv(
                    args.export,
                    filters={"name": args.name, "state": args.state, "race": args.race},
                )
                print(f"\n  Exported to: {args.export}")

        elif args.race:
            results = searcher.search_by_race(
                race=args.race,
                state=args.state,
                limit=args.limit
            )
            scope = f" in {args.state}" if args.state else ""
            print(f"\n{'='*60}")
            print(f"  Records with race '{args.race}'{scope}: {len(results.records)}")
            print(f"{'='*60}")

            if results.records:
                print(f"\n  {'Name':<35} {'Race':<12} {'State':<6} {'Age':>4}")
                print(f"  {'-'*60}")
                for r in results.records[:min(args.limit, 50)]:
                    name = f"{r.get('first_name', '') or ''} {r.get('last_name', '') or ''}".strip()
                    race = (r.get("race") or "N/A")[:12]
                    state = (r.get("state") or "N/A")[:6]
                    age = r.get("age", "")
                    print(f"  {name:<35} {race:<12} {state:<6} {str(age):>4}")

            if args.export:
                searcher.db.export_to_csv(
                    args.export,
                    filters={"race": args.race, "state": args.state},
                )
                print(f"\n  Exported to: {args.export}")

        elif args.state:
            results = searcher.search_by_state(
                state=args.state,
                limit=args.limit
            )
            print(f"\n{'='*60}")
            print(f"  Offenders in {args.state}: {len(results.records)}")
            print(f"{'='*60}")

            if results.records:
                for r in results.records[:20]:
                    name = f"{r.get('first_name', '') or ''} {r.get('last_name', '') or ''}".strip()
                    race = (r.get("race") or "N/A")
                    age = r.get("age", "")
                    print(f"  {name:<35} Race: {race:<12} Age: {str(age):>4}")

            if args.export:
                searcher.db.export_to_csv(args.export, filters={"state": args.state})
                print(f"\n  Exported to: {args.export}")

        else:
            # Show summary stats
            total = searcher.get_total_count()
            race_dist = searcher.get_race_distribution()
            state_dist = searcher.get_state_distribution()

            print(f"\n{'='*60}")
            print("  Sex Offender Database Summary")
            print(f"{'='*60}")
            print(f"\n  Total records: {total:,}")

            print("\n  Race Distribution:")
            for dist in race_dist:
                race = dist.get("race") or "N/A"
                count = dist.get("count", 0)
                pct = (count / total * 100) if total else 0
                bar = "#" * int(pct / 2)
                print(f"    {race:<15} {count:>8,}  {pct:6.1f}%  {bar}")

            print("\n  Top States:")
            for dist in state_dist[:10]:
                state = dist.get("state") or "N/A"
                count = dist.get("count", 0)
                pct = (count / total * 100) if total else 0
                bar = "#" * int(pct / 2)
                print(f"    {state:<6} {count:>8,}  {pct:6.1f}%  {bar}")

            print(f"\n{'='*60}\n")
    finally:
        searcher.close()


def cmd_misclassify(args: argparse.Namespace) -> None:
    """Find potential race/ethnicity misclassifications."""
    from .searcher import SexOffenderSearcher

    db_path = args.database or "data/offenders.db"
    searcher = SexOffenderSearcher(db_path=db_path)

    min_confidence = args.confidence
    limit = args.limit
    ethnicity = args.ethnicity

    print(f"\n{'='*60}")
    print("  Analyzing for Misclassifications")
    print(f"{'='*60}")
    print(f"  Ethnicity filter: {ethnicity}")
    print(f"  Min confidence: {min_confidence}")
    print(f"  Max records to analyze: {limit}")
    print()

    try:
        eth_filter = None if ethnicity in ("all", "", None) else ethnicity
        results = searcher.analyze_ethnicities(
            min_confidence=min_confidence,
            limit=limit,
            ethnicity_filter=eth_filter,
        )
        if eth_filter:
            title = f"Misclassifications ({ethnicity})"
        else:
            title = "All Potential Misclassifications"

        print(f"  {title}")
        print(f"\n  Found {len(results)} potential misclassifications:\n")
        print(f"  {'Name':<35} {'Recorded Race':<15} {'Likely Ethnicity':<20} {'Confidence':>10}")
        print(f"  {'-'*82}")

        for mc in results[:args.max_display]:
            name = f"{mc.record.get('first_name', '') or ''} {mc.record.get('last_name', '') or ''}".strip()
            race = (mc.expected_race or "N/A")[:15]
            likely = mc.likely_ethnicity[:20]
            conf = f"{mc.confidence:.3f}"
            print(f"  {name:<35} {race:<15} {likely:<20} {conf:>10}")

        if args.export:
            eth_filter = None if ethnicity == "all" else ethnicity
            count = searcher.export_misclassifications(
                args.export,
                min_confidence=min_confidence,
                limit=limit,
                ethnicity_filter=eth_filter,
            )
            print(f"\n  Exported {count} records to: {args.export}")

        print(f"\n{'='*60}\n")
    finally:
        searcher.close()


def cmd_export(args: argparse.Namespace) -> None:
    """Export filtered data from the database."""
    from .searcher import SexOffenderSearcher

    db_path = args.database or "data/offenders.db"
    searcher = SexOffenderSearcher(db_path=db_path)

    try:
        filters = {}
        if args.state:
            filters["state"] = args.state
        if args.race:
            filters["race"] = args.race
        if args.name:
            filters["name"] = args.name

        if args.name and not args.state and not args.race:
            # Name-only path uses search results for consistent ranking
            results = searcher.search_by_name(args.name, limit=args.limit)
            with open(args.output, "w", newline="", encoding="utf-8") as f:
                if results.records:
                    writer = csv.DictWriter(f, fieldnames=list(results.records[0].keys()))
                    writer.writeheader()
                    for record in results.records[:args.limit]:
                        writer.writerow(record)
                else:
                    writer = csv.DictWriter(f, fieldnames=["id"])
                    writer.writeheader()
            print(f"Exported {len(results.records)} records to {args.output}")
        else:
            count = searcher.export_filtered(args.output, filters=filters)
            print(f"Exported {count} records to {args.output}")
    finally:
        searcher.close()


