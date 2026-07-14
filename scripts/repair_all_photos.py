"""
Repair offender photos across all states without holding the DB open during HTTP.

  - Detect GIF / shared / tiny / HTML-asset placeholders when photo_url exists
  - Download into data/report_pages/{ST}/photos/
  - Short DB connections for read + update (busy_timeout)

Usage (from repo root):
  python scripts/repair_all_photos.py
"""
from __future__ import annotations

import hashlib
import re
import sys
import time
from collections import Counter, defaultdict
from hashlib import sha1
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scraper.database import Database
from scraper.report_fetcher import ReportFetcher

MIN_MUGSHOT = 2000
SHARED_MIN = 3
HTML_DIR = ROOT / "data" / "report_pages"


def _parts(p: Path):
    return [x.lower() for x in p.parts]


def is_weak(path: str, *, shared_ids: set, rid: int) -> str:
    pp = (path or "").strip()
    if not pp:
        return "no_path"
    p = Path(pp)
    if not p.is_file():
        return "missing_file"
    try:
        sz = p.stat().st_size
    except OSError:
        return "missing_file"
    if p.suffix.lower() == ".gif":
        return "gif"
    if sz < MIN_MUGSHOT and "photos" not in _parts(p):
        return "tiny"
    if rid in shared_ids:
        return "shared"
    if any(x.endswith("_assets") or x == "assets" for x in _parts(p)):
        return "html_asset"
    return ""


def open_db() -> Database:
    db = Database(str(ROOT / "data" / "offenders.db"))
    try:
        db._conn.execute("PRAGMA busy_timeout=120000")
    except Exception:
        pass
    return db


def main() -> None:
    db_path = ROOT / "data" / "offenders.db"
    if not db_path.is_file():
        print("No database at", db_path)
        return

    db = open_db()
    rows = list(
        db._conn.execute(
            """
            SELECT id, state, source_state, photo_path, photo_url, source_url
            FROM offenders
            """
        )
    )
    db.close()

    hash_ids: dict[str, list[int]] = defaultdict(list)
    for r in rows:
        pp = (r["photo_path"] or "").strip()
        if not pp:
            continue
        p = Path(pp)
        if p.is_file():
            h = hashlib.md5(p.read_bytes()).hexdigest()
            hash_ids[h].append(r["id"])
    shared_ids: set[int] = set()
    for ids in hash_ids.values():
        if len(ids) >= SHARED_MIN:
            shared_ids.update(ids)

    targets = []
    for r in rows:
        pu = (r["photo_url"] or "").strip()
        if not pu:
            continue
        reason = is_weak(r["photo_path"] or "", shared_ids=shared_ids, rid=r["id"])
        if not reason:
            continue
        st = (r["state"] or r["source_state"] or "UNK").upper()
        st = re.sub(r"[^A-Z]", "", st)[:2] or "UNK"
        targets.append(
            {
                "id": r["id"],
                "state": st,
                "photo_url": pu,
                "source_url": (r["source_url"] or "").strip(),
                "reason": reason,
            }
        )

    print(f"Targets with photo_url needing repair: {len(targets)}")
    print("Reasons:", dict(Counter(t["reason"] for t in targets)))
    print("By state:", dict(Counter(t["state"] for t in targets).most_common(15)))

    fetcher = ReportFetcher(delay=0.15)
    ok = fail = 0
    pending_updates: list[tuple[str | None, int]] = []

    def flush_updates() -> None:
        nonlocal pending_updates
        if not pending_updates:
            return
        for attempt in range(8):
            try:
                dbw = open_db()
                try:
                    for path, rid in pending_updates:
                        dbw._conn.execute(
                            "UPDATE offenders SET photo_path = ? WHERE id = ?",
                            (path, rid),
                        )
                    dbw._conn.commit()
                finally:
                    dbw.close()
                pending_updates = []
                return
            except Exception as e:
                if "locked" in str(e).lower() and attempt < 7:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                print(f"  flush error: {e}")
                return

    try:
        for i, t in enumerate(targets, 1):
            jur = t["state"]
            photo_dir = HTML_DIR / jur / "photos"
            stem = sha1(
                (t["photo_url"] + "|" + (t["source_url"] or "")).encode(
                    "utf-8", errors="replace"
                )
            ).hexdigest()[:16]
            path = fetcher.download_photo(
                t["photo_url"],
                photo_dir,
                referer=t["source_url"] or "https://www.nsopw.gov/",
                stem=stem,
                reject_gif=True,
            )
            good = False
            if path:
                p = Path(path)
                if (
                    p.is_file()
                    and p.stat().st_size >= 500
                    and p.suffix.lower() != ".gif"
                    and "photos" in _parts(p)
                ):
                    good = True
            if good:
                pending_updates.append((path, t["id"]))
                ok += 1
                if ok <= 12 or ok % 40 == 0:
                    print(
                        f"  [{i}/{len(targets)}] ok id={t['id']} {jur} "
                        f"{Path(path).name} {Path(path).stat().st_size}B ({t['reason']})"
                    )
            else:
                pending_updates.append((None, t["id"]))
                fail += 1
                if fail <= 15:
                    print(
                        f"  [{i}/{len(targets)}] fail id={t['id']} {jur} "
                        f"{t['reason']} {t['photo_url'][:65]}"
                    )
            if len(pending_updates) >= 15:
                flush_updates()
        flush_updates()
    finally:
        fetcher.close()

    # Final audit (short connection)
    dbr = open_db()
    hash_ids = defaultdict(list)
    gif = tiny = path_n = url_no = neither = 0
    for r in dbr._conn.execute(
        "SELECT id, photo_path, photo_url FROM offenders"
    ):
        pp = (r["photo_path"] or "").strip()
        pu = (r["photo_url"] or "").strip()
        if not pp and not pu:
            neither += 1
            continue
        if not pp and pu:
            url_no += 1
            continue
        path_n += 1
        p = Path(pp)
        if not p.is_file():
            continue
        data = p.read_bytes()
        hash_ids[hashlib.md5(data).hexdigest()].append(r["id"])
        if p.suffix.lower() == ".gif":
            gif += 1
        if len(data) < MIN_MUGSHOT:
            tiny += 1
    shared_rows = sum(len(v) for v in hash_ids.values() if len(v) >= SHARED_MIN)
    dbr.close()

    print()
    print(f"Repair done: ok={ok} fail/cleared={fail}")
    print(
        f"After: paths={path_n} unique={len(hash_ids)} gif={gif} "
        f"tiny={tiny} shared_rows={shared_rows} url_no_path={url_no} neither={neither}"
    )


if __name__ == "__main__":
    main()
