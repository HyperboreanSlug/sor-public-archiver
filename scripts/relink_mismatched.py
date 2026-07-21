"""Re-search NSOPW by name for identity-mismatch records to find correct links.

Records flagged ``identity_html_mismatch`` whose stored URL is an FDLE flyer
built from PERSON_NBR point at the WRONG person. Clear the poisoned URL/HTML and
NSOPW-search by name to find the correct listing, then write it back. The enrich
keeps the bad URL (it only re-fetches existing URLs), so this pass relinks them.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scraper.nsopw_builder import NSOPWEthnicDatabaseBuilder


def _strip_mismatch_flags(rec) -> str:
    """Return flags JSON with identity-mismatch tags removed (link is now correct)."""
    raw = rec.get("flags")
    tags = []
    mode = "list"
    obj = None
    if isinstance(raw, list):
        tags = [str(t) for t in raw]
    elif isinstance(raw, dict):
        obj = raw
        tags = [str(t) for t in (raw.get("tags") or [])]
        mode = "dict"
    elif isinstance(raw, str) and raw.strip():
        try:
            p = json.loads(raw)
            if isinstance(p, list):
                tags = [str(t) for t in p]
            elif isinstance(p, dict):
                obj = p
                tags = [str(t) for t in (p.get("tags") or [])]
                mode = "dict"
            else:
                tags = [str(raw)]
        except Exception:
            tags = [str(raw)]
    kept = [
        t
        for t in tags
        if "identity_html_mismatch" not in t.lower()
        and "name_mismatch" not in t.lower()
        and "dob_mismatch" not in t.lower()
        and not t.lower().startswith("identity:")
    ]
    if mode == "dict":
        obj = obj or {}
        obj["tags"] = kept
        return json.dumps(obj, ensure_ascii=False)
    return json.dumps(kept, ensure_ascii=False)


def main():
    log_path = ROOT / "data" / "reports" / "relink_mismatched.log"
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

    log("=== relink mismatched: starting ===")
    builder = NSOPWEthnicDatabaseBuilder(
        db_path=str(ROOT / "data" / "offenders.db"),
        report_delay=1.5,
        report_threads=1,
        html_dir=str(ROOT / "data" / "report_pages"),
    )
    try:
        rows = builder.db._conn.execute(
            "SELECT * FROM offenders WHERE flags LIKE '%identity_html_mismatch%' "
            "AND (source_url LIKE '%flyer.jsf?personId=%' "
            "     OR source_url LIKE '%flyer.jsf?personid=%')"
        ).fetchall()
        total = len(rows)
        log(f"found {total} identity-mismatch records with FDLE flyer URLs")
        relinked = not_found = errors = 0
        for i, row in enumerate(rows, 1):
            rec = dict(row)
            first = (rec.get("first_name") or "").strip()
            last = (rec.get("last_name") or "").strip()
            if not first or not last:
                continue
            if builder.search_limiter.wait(lambda: False):
                log("cancelled")
                break
            try:
                hits = builder.client.search_by_name(first, last)
            except Exception as e:
                errors += 1
                log(f"  search error id={rec.get('id')}: {e}")
                continue
            best = builder._pick_nsopw_hit_for_person(rec, hits)
            if best is None:
                not_found += 1
                continue
            hit_rec = best.to_record()
            new_url = (hit_rec.get("source_url") or "").strip()
            old_url = (rec.get("source_url") or "").strip()
            if not new_url or new_url == old_url:
                not_found += 1
                continue
            patch = {
                "source_url": new_url,
                "external_id": (hit_rec.get("external_id") or rec.get("external_id") or ""),
                "report_html_path": None,  # drop wrong-person archived HTML
                "flags": _strip_mismatch_flags(rec),
            }
            try:
                builder.db.update_offender(int(rec["id"]), patch)
                relinked += 1
            except Exception as e:
                errors += 1
                log(f"  update error id={rec.get('id')}: {e}")
            if i % 50 == 0 or i == total:
                log(
                    f"  {i}/{total} relinked={relinked} "
                    f"not_found={not_found} errors={errors}"
                )
        log(f"=== relink done: relinked={relinked} not_found={not_found} errors={errors} ===")
    finally:
        try:
            builder.close()
        except Exception:
            pass
        try:
            lf.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
