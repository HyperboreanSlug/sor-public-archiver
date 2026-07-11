"""Scrub local PII from a copy of offenders.db for public release."""
import json, re, shutil, sqlite3, hashlib, zipfile
from pathlib import Path
from datetime import datetime, timezone

SRC = Path("data/offenders.db")
OUT_DIR = Path("releases")
OUT_DIR.mkdir(exist_ok=True)
SCRUBBED = OUT_DIR / "offenders_scrubbed.db"
ZIP_PATH = OUT_DIR / "offenders.db.zip"

if SCRUBBED.exists():
    SCRUBBED.unlink()
shutil.copy2(SRC, SCRUBBED)

conn = sqlite3.connect(str(SCRUBBED))
conn.execute("PRAGMA journal_mode=DELETE")

for t in ("nsopw_query_log",):
    try:
        conn.execute(f"DROP TABLE IF EXISTS {t}")
    except Exception:
        pass

USER_PAT = re.compile(
    r"([A-Za-z]:[\\/]Users[\\/][^\\/\"']+[\\/])"
    r"|(/home/[^/\"']+/)"
    r"|(/Users/[^/\"']+/)",
    re.I,
)

def scrub_path(val):
    if not val:
        return val
    s = str(val)
    low = s.replace("/", "\\").lower()
    for marker in ("data\\report_pages\\", "data\\"):
        idx = low.find(marker)
        if idx >= 0:
            return s[idx:].replace("/", "\\")
    s2 = USER_PAT.sub("", s)
    s2 = re.sub(r"^[A-Za-z]:\\", "", s2)
    return s2

cur = conn.execute(
    "SELECT id, photo_path, report_html_path, sources_json, raw_data_json FROM offenders"
)
updates = []
n_scrub = 0
while True:
    batch = cur.fetchmany(5000)
    if not batch:
        break
    for rid, photo, html, sources, raw in batch:
        new_photo = scrub_path(photo) if photo else photo
        new_html = scrub_path(html) if html else html
        new_sources, new_raw = sources, raw
        changed = (new_photo != photo) or (new_html != html)
        if sources and re.search(r"Users|/[Uu]sers/|C:\\\\|C:/|/home/", sources):
            try:
                data = json.loads(sources)
            except Exception:
                data = None
            if isinstance(data, list):
                for src in data:
                    if not isinstance(src, dict):
                        continue
                    for k in ("html_path", "photo_path", "origin"):
                        if isinstance(src.get(k), str) and not str(src[k]).startswith("http"):
                            sf = scrub_path(src[k])
                            if sf != src[k]:
                                src[k] = sf
                                changed = True
                    fields = src.get("fields")
                    if isinstance(fields, dict):
                        for fk in ("photo_path", "report_html_path"):
                            if isinstance(fields.get(fk), str):
                                sf = scrub_path(fields[fk])
                                if sf != fields[fk]:
                                    fields[fk] = sf
                                    changed = True
                new_sources = json.dumps(data, ensure_ascii=False)
            else:
                ns = USER_PAT.sub("", sources)
                if ns != sources:
                    new_sources = ns
                    changed = True
        if raw and re.search(r"Users|/[Uu]sers/|C:\\\\|/home/", raw or ""):
            try:
                rdata = json.loads(raw)

                def walk(o):
                    if isinstance(o, dict):
                        return {k: walk(v) for k, v in o.items()}
                    if isinstance(o, list):
                        return [walk(v) for v in o]
                    if isinstance(o, str) and re.search(r"Users|C:\\\\|/home/", o) and not o.startswith("http"):
                        return scrub_path(o)
                    return o

                nr = json.dumps(walk(rdata), ensure_ascii=False)[:50000]
                if nr != raw:
                    new_raw = nr
                    changed = True
            except Exception:
                nr = USER_PAT.sub("", raw)
                if nr != raw:
                    new_raw = nr
                    changed = True
        if changed:
            n_scrub += 1
            updates.append((new_photo, new_html, new_sources, new_raw, rid))

print("rows_scrubbed", n_scrub)
conn.executemany(
    "UPDATE offenders SET photo_path=?, report_html_path=?, sources_json=?, raw_data_json=? WHERE id=?",
    updates,
)
conn.commit()
print("vacuum...")
conn.execute("VACUUM")
conn.close()

if ZIP_PATH.exists():
    ZIP_PATH.unlink()
print("zipping...")
with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
    zf.write(SCRUBBED, arcname="offenders.db")

size = ZIP_PATH.stat().st_size
sha = hashlib.sha256(ZIP_PATH.read_bytes()).hexdigest()
c2 = sqlite3.connect(str(SCRUBBED))
nrec = c2.execute("SELECT COUNT(*) FROM offenders").fetchone()[0]
leaks = c2.execute(
    "SELECT COUNT(*) FROM offenders WHERE "
    "photo_path LIKE '%\\\\Users\\\\%' OR report_html_path LIKE '%\\\\Users\\\\%' OR "
    "photo_path LIKE '%/Users/%' OR report_html_path LIKE '%/Users/%' OR "
    "sources_json LIKE '%\\\\Users\\\\%' OR sources_json LIKE '%/Users/%' OR "
    "raw_data_json LIKE '%\\\\Users\\\\%' OR raw_data_json LIKE '%/Users/%'"
).fetchone()[0]
c2.close()
manifest = {
    "asset": "offenders.db.zip",
    "db_name": "offenders.db",
    "sha256": sha,
    "size_bytes": size,
    "created_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "record_count": nrec,
    "notes": "Public U.S. sex offender registry archive. Paths are project-relative. No local user profile paths.",
}
(OUT_DIR / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print("zip_bytes", size, "records", nrec, "leaks", leaks, "sha", sha[:16])
