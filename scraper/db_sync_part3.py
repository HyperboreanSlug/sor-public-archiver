from __future__ import annotations

import json
import os
import sqlite3
import shutil
import tempfile

from scraper.db_sync_common import *  # noqa: F401,F403

def download_and_install_db(
    dest: Optional[Path] = None,
    *,
    repo: str = DEFAULT_GITHUB_REPO,
    tag: str = DEFAULT_RELEASE_TAG,
    force: bool = False,
    log: Optional[Callable[[str], None]] = None,
) -> SyncResult:
    """
    Download ``offenders.db.zip`` (+ mugshot parts) from GitHub Releases into *dest*.

    Replaces existing DB atomically (write temp → replace). Extracts photos under
    the project root beside ``data/``. Writes a ``.sync.json`` stamp beside the DB.
    """
    dest = Path(dest) if dest else DEFAULT_DB_REL
    if not dest.is_absolute():
        try:
            from scraper.paths import resolve_under_root

            dest = resolve_under_root(dest, default=str(DEFAULT_DB_REL))
        except Exception:
            dest = (Path.cwd() / dest).resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    project_root = project_root_for_db(dest)

    _log(log, f"Checking remote database ({repo} @ {tag})…")
    remote = fetch_remote_manifest(repo=repo, tag=tag)
    if remote:
        photo_n = int(remote.get("photo_file_count") or 0)
        photo_sz = int(remote.get("photo_size_bytes") or 0)
        _log(
            log,
            f"Remote: records={remote.get('record_count')} "
            f"sha={str(remote.get('sha256') or '')[:12]}… "
            f"db={remote.get('size_bytes')} "
            f"photos={photo_n} ({photo_sz / (1024 ** 3):.2f} GiB)",
        )
    else:
        _log(log, "Remote MANIFEST not available — will try asset URL directly")

    if not force and not needs_update(dest, remote):
        fp = local_db_fingerprint(dest)
        return SyncResult(
            ok=True,
            action="skipped",
            message="Local database is up to date",
            record_count=fp.get("record_count"),
            sha256=(remote or {}).get("sha256"),
        )

    zip_url, _, extra_urls = resolve_release_urls(repo=repo, tag=tag)
    # Prefer MANIFEST photo list (ordered) for URLs / hashes
    photo_specs: List[Dict[str, Any]] = []
    if remote and isinstance(remote.get("photos"), list):
        for p in remote["photos"]:
            if isinstance(p, dict) and p.get("name"):
                photo_specs.append(p)
    if not photo_specs:
        for name in sorted(extra_urls):
            photo_specs.append({"name": name, "sha256": None})

    # Fill download URLs
    base = f"https://github.com/{repo}/releases/download/{tag}"
    for spec in photo_specs:
        name = str(spec["name"])
        if name not in extra_urls:
            extra_urls[name] = f"{base}/{name}"

    existed = dest.is_file() and dest.stat().st_size > 1000
    tmp_dir = Path(tempfile.mkdtemp(prefix="sor_db_sync_"))
    photos_extracted = 0
    bytes_written = 0
    try:
        zip_path = tmp_dir / "offenders.db.zip"
        _log(log, f"Downloading {zip_url} …")
        try:
            _http_download_file(
                zip_url,
                zip_path,
                timeout=600.0,
                expected_sha256=(remote or {}).get("sha256"),
                log=log,
                label="database zip",
            )
        except HTTPError as e:
            return SyncResult(False, "error", f"HTTP {e.code} downloading database: {e.reason}")
        except URLError as e:
            return SyncResult(False, "error", f"Network error: {e.reason}")
        except ValueError as e:
            return SyncResult(False, "error", str(e))
        except Exception as e:
            return SyncResult(False, "error", f"Download failed: {e}")

        bytes_written += zip_path.stat().st_size
        extract_dir = tmp_dir / "out"
        extract_dir.mkdir()
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            member = None
            for n in names:
                if n.replace("\\", "/").endswith("offenders.db") and not n.endswith("/"):
                    member = n
                    break
            if not member:
                return SyncResult(False, "error", "Zip does not contain offenders.db")
            zf.extract(member, extract_dir)
            extracted = extract_dir / member
            if not extracted.is_file():
                candidates = list(extract_dir.rglob("offenders.db"))
                if not candidates:
                    return SyncResult(False, "error", "Failed to extract offenders.db")
                extracted = candidates[0]

        try:
            conn = sqlite3.connect(str(extracted))
            n = int(conn.execute("SELECT COUNT(*) FROM offenders").fetchone()[0])
            conn.close()
        except Exception as e:
            return SyncResult(False, "error", f"Extracted DB failed integrity check: {e}")

        # Download + extract mugshot parts into project root
        for spec in photo_specs:
            name = str(spec["name"])
            url = extra_urls.get(name) or f"{base}/{name}"
            part_path = tmp_dir / name
            _log(log, f"Downloading mugshots {name} …")
            try:
                _http_download_file(
                    url,
                    part_path,
                    timeout=1800.0,
                    expected_sha256=spec.get("sha256"),
                    log=log,
                    label=name,
                )
            except HTTPError as e:
                if e.code == 404:
                    _log(log, f"  Skipping missing photo asset {name}")
                    continue
                return SyncResult(
                    False, "error", f"HTTP {e.code} downloading {name}: {e.reason}"
                )
            except Exception as e:
                return SyncResult(False, "error", f"Photo download failed ({name}): {e}")
            bytes_written += part_path.stat().st_size
            try:
                photos_extracted += _extract_photo_zip(part_path, project_root, log=log)
            except Exception as e:
                return SyncResult(False, "error", f"Photo extract failed ({name}): {e}")
            try:
                part_path.unlink()
            except OSError:
                pass

        if dest.is_file():
            bak = dest.with_suffix(
                dest.suffix + f".bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )
            try:
                shutil.copy2(dest, bak)
                _log(log, f"Backed up previous DB → {bak.name}")
            except Exception as e:
                _log(log, f"Could not backup previous DB: {e}")

        tmp_dest = dest.with_suffix(dest.suffix + ".download")
        if tmp_dest.exists():
            tmp_dest.unlink()
        shutil.copy2(extracted, tmp_dest)
        try:
            os.replace(str(tmp_dest), str(dest))
        except OSError as e:
            # Windows: cannot replace while another process holds the file open
            try:
                tmp_dest.unlink()
            except OSError:
                pass
            return SyncResult(
                False,
                "error",
                f"Could not install database (file in use?): {e}. "
                "Close other SORPA windows and try again.",
            )
        # Drop leftover WAL/SHM so SQLite does not pair a new main file with
        # an old journal (looks like "database failed to load" / empty / corrupt).
        try:
            from scraper.paths import clear_sqlite_sidecars

            clear_sqlite_sidecars(dest)
        except Exception:
            for suffix in ("-wal", "-shm"):
                side = dest.parent / f"{dest.name}{suffix}"
                try:
                    if side.is_file():
                        side.unlink()
                except OSError:
                    pass

        stamp = {
            "remote_sha256": (remote or {}).get("sha256"),
            "remote_record_count": (remote or {}).get("record_count") or n,
            "remote_photos_fingerprint": _photo_fingerprint(remote),
            "photos_extracted": photos_extracted,
            "synced_at_utc": _utc_now(),
            "repo": repo,
            "tag": tag,
            "local_record_count": n,
            "project_root": str(project_root),
        }
        stamp_path = dest.with_suffix(dest.suffix + ".sync.json")
        stamp_path.write_text(json.dumps(stamp, indent=2) + "\n", encoding="utf-8")

        action = "updated" if existed else "downloaded"
        photo_bit = (
            f", {photos_extracted:,} mugshots"
            if photos_extracted
            else (", photos unchanged" if photo_specs else "")
        )
        msg = (
            f"{'Updated' if existed else 'Downloaded'} database "
            f"({n:,} records{photo_bit})"
        )
        _log(log, msg)
        return SyncResult(
            ok=True,
            action=action,
            message=msg,
            record_count=n,
            sha256=(remote or {}).get("sha256"),
            bytes_written=bytes_written,
            photos_extracted=photos_extracted,
        )
    finally:
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass


