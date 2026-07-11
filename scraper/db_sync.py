"""Download / update the public offenders SQLite archive from GitHub.

The archive is published as a Release asset (``offenders.db.zip``) plus
``MANIFEST.json`` (sha256, size, record_count). Paths inside the DB are
project-relative; no local user-profile paths.

Default source: ``HyperboreanSlug/sor-public-archiver`` release tag
``database-latest``.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Public GitHub repository that hosts the database release asset (not a person).
DEFAULT_GITHUB_REPO = "HyperboreanSlug/sor-public-archiver"
DEFAULT_RELEASE_TAG = "database-latest"
DEFAULT_ASSET_NAME = "offenders.db.zip"
DEFAULT_MANIFEST_NAME = "MANIFEST.json"
DEFAULT_DB_REL = Path("data/offenders.db")
USER_AGENT = "SOR-Public-Archiver-DB-Sync/1.0"


@dataclass
class SyncResult:
    ok: bool
    action: str  # skipped | downloaded | updated | error
    message: str
    record_count: Optional[int] = None
    sha256: Optional[str] = None
    bytes_written: int = 0


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log(log: Optional[Callable[[str], None]], msg: str) -> None:
    if log:
        try:
            log(msg)
        except Exception:
            pass


def _http_get(url: str, timeout: float = 120.0) -> bytes:
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/octet-stream"})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _http_get_json(url: str, timeout: float = 60.0) -> Any:
    req = Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"},
    )
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve_release_urls(
    repo: str = DEFAULT_GITHUB_REPO,
    tag: str = DEFAULT_RELEASE_TAG,
    asset_name: str = DEFAULT_ASSET_NAME,
    manifest_name: str = DEFAULT_MANIFEST_NAME,
) -> Tuple[str, str]:
    """
    Return (zip_url, manifest_url).

    Prefers the GitHub Releases API; falls back to the stable download URL pattern.
    """
    repo = (repo or DEFAULT_GITHUB_REPO).strip().strip("/")
    tag = (tag or DEFAULT_RELEASE_TAG).strip()
    asset_name = (asset_name or DEFAULT_ASSET_NAME).strip()
    manifest_name = (manifest_name or DEFAULT_MANIFEST_NAME).strip()

    api = f"https://api.github.com/repos/{repo}/releases/tags/{tag}"
    try:
        data = _http_get_json(api)
        assets = data.get("assets") or []
        by_name = {a.get("name"): a for a in assets if isinstance(a, dict)}
        zip_a = by_name.get(asset_name) or {}
        man_a = by_name.get(manifest_name) or {}
        zip_url = zip_a.get("browser_download_url") or ""
        man_url = man_a.get("browser_download_url") or ""
        if zip_url:
            return zip_url, man_url
    except Exception:
        pass

    base = f"https://github.com/{repo}/releases/download/{tag}"
    return f"{base}/{asset_name}", f"{base}/{manifest_name}"


def fetch_remote_manifest(
    repo: str = DEFAULT_GITHUB_REPO,
    tag: str = DEFAULT_RELEASE_TAG,
) -> Optional[Dict[str, Any]]:
    _, man_url = resolve_release_urls(repo=repo, tag=tag)
    if not man_url:
        return None
    try:
        raw = _http_get(man_url, timeout=60.0)
        data = json.loads(raw.decode("utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def local_db_fingerprint(db_path: Path) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "exists": db_path.is_file(),
        "size_bytes": 0,
        "record_count": None,
        "sha256": None,
    }
    if not db_path.is_file():
        return out
    out["size_bytes"] = int(db_path.stat().st_size)
    try:
        out["sha256"] = sha256_file(db_path)
    except Exception:
        pass
    try:
        conn = sqlite3.connect(f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True)
        try:
            out["record_count"] = int(
                conn.execute("SELECT COUNT(*) FROM offenders").fetchone()[0]
            )
        finally:
            conn.close()
    except Exception:
        pass
    return out


def needs_update(
    db_path: Path,
    remote: Optional[Dict[str, Any]],
) -> bool:
    """True if local DB is missing or remote MANIFEST reports a different zip sha."""
    if not remote:
        return not db_path.is_file()
    if not db_path.is_file() or db_path.stat().st_size < 1000:
        return True
    # Compare against optional local stamp file written after last successful sync
    stamp = db_path.with_suffix(db_path.suffix + ".sync.json")
    if stamp.is_file():
        try:
            local = json.loads(stamp.read_text(encoding="utf-8"))
            if local.get("remote_sha256") and remote.get("sha256"):
                return local.get("remote_sha256") != remote.get("sha256")
        except Exception:
            pass
    # No stamp: update if remote record_count is higher (best-effort)
    try:
        local_fp = local_db_fingerprint(db_path)
        rc_local = local_fp.get("record_count")
        rc_remote = remote.get("record_count")
        if rc_local is not None and rc_remote is not None:
            return int(rc_remote) > int(rc_local)
    except Exception:
        pass
    return False


def download_and_install_db(
    dest: Optional[Path] = None,
    *,
    repo: str = DEFAULT_GITHUB_REPO,
    tag: str = DEFAULT_RELEASE_TAG,
    force: bool = False,
    log: Optional[Callable[[str], None]] = None,
) -> SyncResult:
    """
    Download ``offenders.db.zip`` from GitHub Releases into *dest*.

    Replaces existing DB atomically (write temp → replace). Writes a
    ``.sync.json`` stamp beside the DB.
    """
    dest = Path(dest) if dest else DEFAULT_DB_REL
    dest = dest if dest.is_absolute() else (Path.cwd() / dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    _log(log, f"Checking remote database ({repo} @ {tag})…")
    remote = fetch_remote_manifest(repo=repo, tag=tag)
    if remote:
        _log(
            log,
            f"Remote: records={remote.get('record_count')} "
            f"sha={str(remote.get('sha256') or '')[:12]}… "
            f"size={remote.get('size_bytes')}",
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

    zip_url, _ = resolve_release_urls(repo=repo, tag=tag)
    _log(log, f"Downloading {zip_url} …")
    try:
        blob = _http_get(zip_url, timeout=600.0)
    except HTTPError as e:
        return SyncResult(False, "error", f"HTTP {e.code} downloading database: {e.reason}")
    except URLError as e:
        return SyncResult(False, "error", f"Network error: {e.reason}")
    except Exception as e:
        return SyncResult(False, "error", f"Download failed: {e}")

    if remote and remote.get("sha256"):
        got = hashlib.sha256(blob).hexdigest()
        if got.lower() != str(remote["sha256"]).lower():
            return SyncResult(
                False,
                "error",
                f"SHA-256 mismatch (got {got[:16]}… expected {str(remote['sha256'])[:16]}…)",
            )

    existed = dest.is_file() and dest.stat().st_size > 1000
    tmp_dir = Path(tempfile.mkdtemp(prefix="sor_db_sync_"))
    try:
        zip_path = tmp_dir / "offenders.db.zip"
        zip_path.write_bytes(blob)
        extract_dir = tmp_dir / "out"
        extract_dir.mkdir()
        with zipfile.ZipFile(zip_path, "r") as zf:
            # Prefer offenders.db at root
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
                # Windows may flatten path
                candidates = list(extract_dir.rglob("offenders.db"))
                if not candidates:
                    return SyncResult(False, "error", "Failed to extract offenders.db")
                extracted = candidates[0]

        # Quick integrity check
        try:
            conn = sqlite3.connect(str(extracted))
            n = int(conn.execute("SELECT COUNT(*) FROM offenders").fetchone()[0])
            conn.close()
        except Exception as e:
            return SyncResult(False, "error", f"Extracted DB failed integrity check: {e}")

        # Backup existing
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
        os.replace(str(tmp_dest), str(dest))

        stamp = {
            "remote_sha256": (remote or {}).get("sha256"),
            "remote_record_count": (remote or {}).get("record_count") or n,
            "synced_at_utc": _utc_now(),
            "repo": repo,
            "tag": tag,
            "local_record_count": n,
        }
        stamp_path = dest.with_suffix(dest.suffix + ".sync.json")
        stamp_path.write_text(json.dumps(stamp, indent=2) + "\n", encoding="utf-8")

        action = "updated" if existed else "downloaded"
        msg = f"{'Updated' if existed else 'Downloaded'} database ({n:,} records)"
        _log(log, msg)
        return SyncResult(
            ok=True,
            action=action,
            message=msg,
            record_count=n,
            sha256=(remote or {}).get("sha256"),
            bytes_written=int(dest.stat().st_size),
        )
    finally:
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass


def should_prompt_first_run(settings: Dict[str, Any], db_path: Path) -> bool:
    """True when user has never chosen, and no usable local DB is present."""
    if settings.get("db_sync_prompted"):
        return False
    if settings.get("db_sync_enabled"):
        return False
    if db_path.is_file() and db_path.stat().st_size > 10_000:
        # Have a local DB already — still offer once? User asked initial open.
        # Only prompt when never asked, even if DB exists (offer updates).
        return True
    return True
