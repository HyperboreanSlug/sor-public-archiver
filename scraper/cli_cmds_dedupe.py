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

def cmd_dedupe(args: argparse.Namespace) -> None:
    """Check and/or remove duplicate offender rows in the database."""
    from .database import DUPLICATE_STRATEGIES, Database

    db_path = args.database or "data/offenders.db"
    db = Database(db_path)
    strategy = (args.strategy or "source_url").strip().lower()
    do_remove = bool(args.remove)
    dry_run = bool(args.dry_run) or not do_remove
    # --check is default when not --remove; --dry-run with --remove previews deletes
    if args.check and not do_remove:
        dry_run = True

    try:
        print(f"\n{'='*60}")
        print("  Duplicate check / removal")
        print(f"{'='*60}")
        print(f"  Database: {db_path}")
        print(f"  Total offenders: {db.get_total_count():,}")

        if strategy == "all":
            from .database import DEFAULT_DEDUPE_STRATEGIES

            strats = list(DEFAULT_DEDUPE_STRATEGIES)
            if args.include_name_state:
                strats.append("name_state")
            summary = db.count_duplicates(strats)
            print("\n  Duplicate summary (extra = beyond keeper; safe = OK to auto-remove):")
            for s, info in summary["by_strategy"].items():
                print(
                    f"    {s:<16}  groups={info['groups']:>5,}  "
                    f"extra={info['extra_rows']:>6,}  "
                    f"safe_extra={info.get('safe_extra_rows', 0):>6,}  "
                    f"unsafe_groups={info.get('unsafe_groups', 0):>4,}"
                )
            print(
                f"\n  Safe removable rows: {summary.get('total_safe_extra_rows', 0):,}  "
                f"(raw extra sum may include CAPTCHA/portal clusters)"
            )

            if do_remove:
                print(
                    f"\n  Removing duplicates ({'DRY RUN' if dry_run else 'LIVE'}) "
                    f"in order: {', '.join(strats)}"
                    f"{'' if args.force_unsafe else ' [safe URL groups only]'}"
                )
                result = db.remove_duplicates_all(
                    strats,
                    dry_run=dry_run,
                    merge_fields=not args.no_merge,
                    safe_only=not args.force_unsafe,
                )
                for r in result["strategies"]:
                    print(
                        f"    {r['strategy']:<16}  groups={r['groups']:,}  "
                        f"{'would delete' if dry_run else 'deleted'}={r['deleted']:,}  "
                        f"skipped_unsafe={r.get('skipped_unsafe', 0):,}  "
                        f"merged_fields={r['merged_fields']:,}"
                    )
                print(
                    f"\n  Total {'would delete' if dry_run else 'deleted'}: "
                    f"{result['total_deleted']:,}"
                )
                print(f"  Offenders now: {result['total_offenders']:,}")
            else:
                print("\n  Tip: re-run with --remove to delete safe extras (add --dry-run first).")
        else:
            if strategy not in DUPLICATE_STRATEGIES:
                print(f"  Unknown strategy {strategy!r}. Choose: all, {', '.join(DUPLICATE_STRATEGIES)}")
                return
            groups = db.find_duplicate_groups(strategy, limit_groups=args.max_show)
            full = db.find_duplicate_groups(strategy)
            full_extra = sum(max(0, g["count"] - 1) for g in full)
            safe_extra = sum(max(0, g["count"] - 1) for g in full if g.get("safe", True))
            unsafe_n = sum(1 for g in full if not g.get("safe", True))
            print(f"\n  Strategy: {strategy}")
            print(
                f"  Groups: {len(full):,}  ·  extra rows: {full_extra:,}  "
                f"·  safe extra: {safe_extra:,}  ·  unsafe groups: {unsafe_n:,}"
            )
            if groups:
                print(f"\n  Sample groups (up to {args.max_show}):")
                for g in groups[: args.max_show]:
                    tag = "" if g.get("safe", True) else " [UNSAFE portal/CAPTCHA — not auto-removed]"
                    print(
                        f"    keep id={g['keep_id']} ({g['keep_preview']})  "
                        f"count={g['count']}  remove={g['remove_ids'][:6]}"
                        f"{'…' if len(g['remove_ids']) > 6 else ''}{tag}"
                    )
                    print(f"      key: {str(g['key'])[:80]}")

            if do_remove:
                print(f"\n  Removing ({'DRY RUN' if dry_run else 'LIVE'})…")
                result = db.remove_duplicates(
                    strategy,
                    dry_run=dry_run,
                    merge_fields=not args.no_merge,
                    safe_only=not args.force_unsafe,
                )
                print(
                    f"  Groups={result['groups']:,}  "
                    f"{'would delete' if dry_run else 'deleted'}={result['deleted']:,}  "
                    f"skipped_unsafe={result.get('skipped_unsafe', 0):,}  "
                    f"merged_fields={result['merged_fields']:,}"
                )
                print(f"  Offenders now: {db.get_total_count():,}")
            elif not groups and full_extra == 0:
                print("  No duplicates found for this strategy.")
            else:
                print("\n  Tip: re-run with --remove to delete safe extras (add --dry-run first).")
        print(f"{'='*60}\n")
    finally:
        db.close()


