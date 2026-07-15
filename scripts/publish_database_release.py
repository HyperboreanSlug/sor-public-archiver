#!/usr/bin/env python3
"""
Prepare scrubbed public DB (base + deltas + mugshots) and publish to GitHub Releases.

Upload is gated to THIS local publisher instance only (data/db_publish.allow).
Other machines / app installs can only download.

Usage (from repo root)::

    python scripts/enable_db_publish.py   # once on publisher machine
    gh auth login
    python scripts/publish_database_release.py --use-gh
    python scripts/publish_database_release.py --use-gh --full-base
    python scripts/publish_database_release.py --use-gh --skip-photos

Default publishes a small delta when possible; use --full-base after large rebuilds.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REPO = "HyperboreanSlug/SORPA"
TAG = "database-latest"
PHOTO_GLOB = "offenders.photos.*.zip"
DELTA_GLOB = "offenders.delta.*.zip"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--use-gh", action="store_true", help="Use gh CLI to upload")
    ap.add_argument("--skip-scrub", action="store_true", help="Reuse existing release files")
    ap.add_argument("--full-base", action="store_true", help="Force full base zip")
    ap.add_argument(
        "--skip-photos",
        action="store_true",
        help="Do not repack or re-upload mugshots (reuse prior photo assets)",
    )
    ap.add_argument(
        "--force-photo-rebuild",
        action="store_true",
        help="Rebuild all photo shards even when fingerprints match",
    )
    ap.add_argument("--repo", default=REPO)
    ap.add_argument("--tag", default=TAG)
    args = ap.parse_args()

    os.chdir(ROOT)

    from scraper.db_publish_assets import (
        git_cred_token,
        remote_asset_names,
        select_upload_assets,
        which,
    )
    from scraper.db_publish_gate import require_publish_allowed
    from scraper.db_publish_upload import publish_api, publish_gh

    require_publish_allowed(ROOT)

    zip_path = ROOT / "releases" / "offenders.db.zip"
    man_path = ROOT / "releases" / "MANIFEST.json"

    if not args.skip_scrub:
        scrub = ROOT / "scripts" / "scrub_db_for_release.py"
        cmd = [sys.executable, str(scrub)]
        if args.full_base:
            cmd.append("--full-base")
        if args.skip_photos:
            cmd.append("--skip-photos")
        if args.force_photo_rebuild:
            cmd.append("--force-photo-rebuild")
        print("Scrubbing + packaging DB (base or delta) + photos…")
        rc = subprocess.call(cmd)
        if rc != 0:
            return rc

    if not man_path.is_file():
        print("Missing releases/MANIFEST.json")
        return 1

    man = json.loads(man_path.read_text(encoding="utf-8"))
    photo_paths = sorted((ROOT / "releases").glob(PHOTO_GLOB))
    delta_paths = sorted((ROOT / "releases").glob(DELTA_GLOB))

    print(
        f"MANIFEST records={man.get('record_count')} "
        f"format={man.get('format')} base={str(man.get('sha256') or '')[:16]}… "
        f"deltas={len(man.get('deltas') or [])}"
    )
    if zip_path.is_file():
        print(f"DB zip: {zip_path.stat().st_size:,} bytes")
    for p in delta_paths:
        print(f"  delta {p.name}: {p.stat().st_size:,} bytes")
    for p in photo_paths:
        print(f"  photo {p.name}: {p.stat().st_size:,} bytes")

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    if not token:
        token = git_cred_token()
    remote_names = remote_asset_names(args.repo, args.tag, token=token)

    assets = select_upload_assets(
        man_path=man_path,
        zip_path=zip_path,
        delta_paths=delta_paths,
        photo_paths=photo_paths,
        skip_photos=bool(args.skip_photos),
        full_base=bool(args.full_base),
        remote_names=remote_names,
    )
    skip_note = "  [skip-photos: not re-uploading mugshots]" if args.skip_photos else ""
    print(f"Upload set ({len(assets)}): " + ", ".join(a.name for a in assets) + skip_note)

    if args.use_gh and which("gh"):
        return publish_gh(
            args.repo, args.tag, assets, man, prune_photos=not args.skip_photos
        )
    if args.use_gh:
        print("gh CLI not found — falling back to API upload with git credentials.")
    if not token:
        names = " ".join(str(a) for a in assets)
        print(
            "No GITHUB_TOKEN/GH_TOKEN, git credential, or gh CLI.\n"
            "Assets ready under releases/ — upload manually:\n"
            f"  gh release create {args.tag} {names} --repo {args.repo} "
            f'--title "Public database" --notes "Public registry archive"\n'
        )
        return 2

    return publish_api(
        args.repo,
        args.tag,
        assets,
        token,
        man,
        prune_photos=not args.skip_photos,
    )


if __name__ == "__main__":
    raise SystemExit(main())
