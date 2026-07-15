"""Choose which release files to upload for a public DB publish."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import List, Set


def which(cmd: str) -> str:
    from shutil import which as _which

    return _which(cmd) or ""


def git_cred_token() -> str:
    """Password/token from git credential helper (same as git push)."""
    try:
        p = subprocess.run(
            ["git", "credential", "fill"],
            input="protocol=https\nhost=github.com\n\n",
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except Exception:
        return ""
    if p.returncode != 0:
        return ""
    for line in (p.stdout or "").splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1].strip()
    return ""


def release_notes(man: dict) -> str:
    photos = man.get("photo_file_count") or 0
    parts = man.get("photo_part_count") or 0
    deltas = man.get("deltas") or []
    return (
        "Public U.S. sex offender registry SQLite archive for SOR Public Archiver.\n\n"
        f"- Records: {man.get('record_count')}\n"
        f"- Format: {man.get('format', 1)} (base + {len(deltas)} delta pack(s))\n"
        f"- Mugshots: {photos} files in {parts} zip part(s)\n"
        "- Clients apply `offenders.delta.NNNN.zip` after the base for small updates\n"
        "- Paths are project-relative under `data/report_pages/*/photos/`\n"
    )


def select_upload_assets(
    *,
    man_path: Path,
    zip_path: Path,
    delta_paths: List[Path],
    photo_paths: List[Path],
    skip_photos: bool,
    full_base: bool,
    remote_names: Set[str],
) -> List[Path]:
    """
    Choose release assets to upload.

    ``skip_photos`` must not re-upload multi‑GB mugshot zips on every delta
    publish. Base zip is only re-uploaded on ``full_base`` or when missing
    remotely. Photos upload only when not skipping (or remote has none yet).
    """
    assets: List[Path] = [man_path]
    remote_has_base = "offenders.db.zip" in remote_names
    if zip_path.is_file() and (full_base or not remote_has_base):
        assets.insert(0, zip_path)
    for p in delta_paths:
        if p.is_file():
            assets.append(p)
    remote_photos = {n for n in remote_names if n.startswith("offenders.photos.")}
    if not skip_photos:
        assets.extend([p for p in photo_paths if p.is_file()])
    elif photo_paths and not remote_photos:
        assets.extend([p for p in photo_paths if p.is_file()])
    seen: set[str] = set()
    out: List[Path] = []
    for a in assets:
        if a.name in seen or not a.is_file():
            continue
        seen.add(a.name)
        out.append(a)
    return out


def remote_asset_names(repo: str, tag: str, *, token: str = "") -> Set[str]:
    """Best-effort names of assets already on the GitHub release."""
    import urllib.request

    api = f"https://api.github.com/repos/{repo}/releases/tags/{tag}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "SOR-Public-Archiver-Publish",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        req = urllib.request.Request(api, headers=headers)
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        try:
            cp = subprocess.run(
                ["gh", "api", f"repos/{repo}/releases/tags/{tag}"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if cp.returncode != 0:
                return set()
            data = json.loads(cp.stdout or "{}")
        except Exception:
            return set()
    names: Set[str] = set()
    for a in data.get("assets") or []:
        if isinstance(a, dict) and a.get("name"):
            names.add(str(a["name"]))
    return names
