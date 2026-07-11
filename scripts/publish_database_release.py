#!/usr/bin/env python3
"""
Prepare a scrubbed public offenders.db.zip and publish it to GitHub Releases.

Usage (from repo root, with a GitHub token that can create releases)::

    set GITHUB_TOKEN=ghp_...
    python scripts/publish_database_release.py

Or with gh CLI::

    gh auth login
    python scripts/publish_database_release.py --use-gh

The script:
  1. Copies data/offenders.db
  2. Scrubs absolute / user-profile paths (no local author PII)
  3. Writes releases/offenders.db.zip + releases/MANIFEST.json
  4. Creates/updates release tag database-latest with those assets

Never commits the binary into git history by default.
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

REPO = "HyperboreanSlug/sor-public-archiver"
TAG = "database-latest"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--use-gh", action="store_true", help="Use gh CLI to upload")
    ap.add_argument("--skip-scrub", action="store_true", help="Reuse existing zip")
    ap.add_argument("--repo", default=REPO)
    ap.add_argument("--tag", default=TAG)
    args = ap.parse_args()

    os.chdir(ROOT)
    zip_path = ROOT / "releases" / "offenders.db.zip"
    man_path = ROOT / "releases" / "MANIFEST.json"

    if not args.skip_scrub:
        scrub = ROOT / "scripts" / "scrub_db_for_release.py"
        if not scrub.is_file():
            scrub = ROOT / "scripts" / "_scrub_db_for_release.py"
        print("Scrubbing + zipping…")
        rc = subprocess.call([sys.executable, str(scrub)])
        if rc != 0:
            return rc
    if not zip_path.is_file() or not man_path.is_file():
        print("Missing releases/offenders.db.zip or MANIFEST.json")
        return 1

    man = json.loads(man_path.read_text(encoding="utf-8"))
    print(
        f"Asset ready: {zip_path.stat().st_size:,} bytes, "
        f"records={man.get('record_count')}, sha={str(man.get('sha256'))[:16]}…"
    )

    # Sanity: no user home paths in zip contents check already done by scrub
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    if args.use_gh or not token:
        # Prefer gh if available
        gh = shutil_which("gh")
        if gh:
            return _publish_gh(args.repo, args.tag, zip_path, man_path)
        if not token:
            print(
                "No GITHUB_TOKEN/GH_TOKEN and gh CLI not found.\n"
                "Zip is ready under releases/ — upload manually:\n"
                f"  gh release create {args.tag} "
                f"{zip_path} {man_path} --repo {args.repo} "
                f"--title \"Public database\" --notes \"Public registry archive\"\n"
                "Or re-run with GITHUB_TOKEN set."
            )
            return 2

    return _publish_api(args.repo, args.tag, zip_path, man_path, token)


def shutil_which(cmd: str) -> str:
    from shutil import which

    return which(cmd) or ""


def _publish_gh(repo: str, tag: str, zip_path: Path, man_path: Path) -> int:
    notes = (
        "Public U.S. sex offender registry SQLite archive for SOR Public Archiver. "
        "Paths are project-relative. No local user-profile paths."
    )
    # Delete existing release if present (best-effort)
    subprocess.call(
        ["gh", "release", "delete", tag, "--repo", repo, "--yes"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Delete tag
    subprocess.call(
        ["git", "push", "origin", f":refs/tags/{tag}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    cmd = [
        "gh",
        "release",
        "create",
        tag,
        str(zip_path),
        str(man_path),
        "--repo",
        repo,
        "--title",
        "Public database archive",
        "--notes",
        notes,
    ]
    print("Running:", " ".join(cmd))
    return subprocess.call(cmd)


def _publish_api(
    repo: str, tag: str, zip_path: Path, man_path: Path, token: str
) -> int:
    import json as _json
    import urllib.error
    import urllib.request

    owner, name = repo.split("/", 1)
    api = "https://api.github.com"

    def req(method: str, url: str, data: bytes | None = None, content_type: str = ""):
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "SOR-Public-Archiver-Publish",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if content_type:
            headers["Content-Type"] = content_type
        r = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(r, timeout=300) as resp:
            body = resp.read()
            return resp.status, body

    # Ensure tag/release exists
    try:
        status, body = req("GET", f"{api}/repos/{repo}/releases/tags/{tag}")
        rel = _json.loads(body.decode())
        print(f"Updating existing release id={rel.get('id')}")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            print("GET release failed", e)
            return 1
        payload = _json.dumps(
            {
                "tag_name": tag,
                "name": "Public database archive",
                "body": (
                    "Public U.S. sex offender registry SQLite archive. "
                    "Paths project-relative; no local user-profile paths."
                ),
                "draft": False,
                "prerelease": False,
            }
        ).encode()
        status, body = req(
            "POST",
            f"{api}/repos/{repo}/releases",
            data=payload,
            content_type="application/json",
        )
        rel = _json.loads(body.decode())
        print(f"Created release id={rel.get('id')}")

    upload_url = (rel.get("upload_url") or "").split("{")[0]
    # Delete existing assets with same names
    for asset in rel.get("assets") or []:
        if asset.get("name") in (zip_path.name, man_path.name):
            aid = asset.get("id")
            try:
                req("DELETE", f"{api}/repos/{repo}/releases/assets/{aid}")
                print("Deleted old asset", asset.get("name"))
            except Exception as e:
                print("Could not delete asset", e)

    for path in (zip_path, man_path):
        url = f"{upload_url}?name={path.name}"
        data = path.read_bytes()
        print(f"Uploading {path.name} ({len(data):,} bytes)…")
        try:
            status, body = req(
                "POST",
                url,
                data=data,
                content_type="application/octet-stream",
            )
            print(f"  OK HTTP {status}")
        except urllib.error.HTTPError as e:
            print(f"  FAIL {e.code} {e.read()[:500]}")
            return 1
    print("Done.")
    print(
        f"Download: https://github.com/{repo}/releases/download/{tag}/{zip_path.name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
