"""Overnight multi-state enrich: re-fetch flyers, fill data, flag dead links.

Usage:
  python scripts/enrich_state_overnight.py            # FL first, then other states by record count
  python scripts/enrich_state_overnight.py FL,TX,CA   # explicit state order

Resumable — skips rows already flagged dead (blocked:http_404) or HTML-verified,
so it can be re-run nightly and picks up where it left off. When one state is
done it moves on to the next. Progress → data/reports/enrich_overnight.log.
"""
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Windows consoles default to cp1252; force UTF-8 so names/details log cleanly.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from scraper.nsopw_builder import NSOPWEthnicDatabaseBuilder


def _state_order(builder, explicit: str):
    """FL first, then remaining states ordered by how many records have a URL."""
    if explicit:
        return [s.strip().upper() for s in explicit.split(",") if s.strip()]
    counts: Counter = Counter()
    cur = builder.db._conn.execute(
        "SELECT source_state FROM offenders "
        "WHERE source_url IS NOT NULL AND TRIM(source_url) != ''"
    )
    for (ss,) in cur:
        primary = (ss or "").split("|")[0].strip().upper()
        if len(primary) == 2:
            counts[primary] += 1
    ordered = [s for s, _ in counts.most_common()]
    if "FL" in ordered:
        ordered.remove("FL")
    return ["FL"] + ordered


def main() -> int:
    explicit = sys.argv[1] if len(sys.argv) > 1 else ""
    log_path = ROOT / "data" / "reports" / "enrich_overnight.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    lf = open(log_path, "a", encoding="utf-8")

    def log(msg: str) -> None:
        line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
        print(line, flush=True)
        try:
            lf.write(line + "\n")
            lf.flush()
        except Exception:
            pass

    builder = NSOPWEthnicDatabaseBuilder(
        db_path=str(ROOT / "data" / "offenders.db"),
        report_delay=1.5,
        report_threads=1,
        html_dir=str(ROOT / "data" / "report_pages"),
    )
    try:
        states = _state_order(builder, explicit)
        log(f"=== Overnight enrich queue: {', '.join(states)} ===")
        for state in states:
            log(f"=== Starting enrich for {state} ===")
            try:
                stats = builder.enrich_state(state, save_html=True, log=log)
                log(f"=== Finished {state}: {stats} ===")
            except Exception as e:
                log(f"=== {state} ERROR: {type(e).__name__}: {e} ===")
        log("=== All queued states processed ===")
    finally:
        try:
            builder.close()
        except Exception:
            pass
        try:
            lf.close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
