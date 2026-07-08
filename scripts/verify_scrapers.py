#!/usr/bin/env python3
"""Live verification of scrapers for key jurisdictions."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scraper.scrapers.base import ScraperFactory


def main() -> None:
    print("=== Factory routing ===")
    for abbr in ["GA", "DC", "AZ", "FL", "AL", "TX", "CA"]:
        s = ScraperFactory.create(abbr, delay=0.3)
        print(f"  {abbr}: {type(s).__name__}")
        s.close()

    print("\n=== LIVE bulk scrapes ===")
    for abbr in ["GA", "DC", "AZ", "FL", "AL"]:
        s = ScraperFactory.create(abbr, delay=0.5)
        try:
            recs = s.scrape()
            sample = ""
            if recs:
                r = recs[0]
                name = r.get("last_name") or r.get("full_name") or r.get("NAME")
                sample = f" state={r.get('state')} name={name} keys={list(r.keys())[:6]}"
            print(f"{abbr}: {len(recs)} records{sample}")
        except Exception as e:
            print(f"{abbr}: EXCEPTION {type(e).__name__}: {e}")
        finally:
            s.close()


if __name__ == "__main__":
    main()
