"""Upload selected public DB release assets to GitHub (gh CLI or API)."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import List, Set

from scraper.db_publish_assets import release_notes, which


def upload_progress_msg(done: int, total: int, label: str) -> str:
    total = max(int(total), 1)
    pct = int(round(100.0 * min(done, total) / total))
    return f"{label} ({max(0, min(100, pct))}%)"


def publish_gh(
    repo: str,
    tag: str,
    assets: List[Path],
    man: dict,
    *,
    prune_photos: bool = False,
) -> int:
    """Create/update release; upload assets with --clobber."""
    notes = release_notes(man)
    check = subprocess.call(
        ["gh", "release", "view", tag, "--repo", repo],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if check != 0:
        create = [
            "gh",
            "release",
            "create",
            tag,
            "--repo",
            repo,
            "--title",
            "Public database archive",
            "--notes",
            notes,
        ]
        print("Creating release… (0%)")
        rc = subprocess.call(create)
        if rc != 0:
            print("gh release create failed", rc)
            return rc
    else:
        subprocess.call(
            ["gh", "release", "edit", tag, "--repo", repo, "--notes", notes],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if prune_photos:
            gh_prune_obsolete_photos(repo, tag, {a.name for a in assets})

    total_b = sum(p.stat().st_size for p in assets if p.is_file()) or 1
    done_b = 0
    env = os.environ.copy()
    env.setdefault("GH_PROMPT_DISABLED", "1")
    for path in assets:
        if not path.is_file():
            continue
        size = path.stat().st_size
        print(upload_progress_msg(done_b, total_b, f"Uploading {path.name} ({size:,} bytes)"))
        cmd = [
            "gh",
            "release",
            "upload",
            tag,
            str(path),
            "--repo",
            repo,
            "--clobber",
        ]
        rc = subprocess.call(cmd, env=env)
        if rc != 0:
            print(f"Upload failed for {path.name} rc={rc}")
            return rc
        done_b += size
        print(upload_progress_msg(done_b, total_b, f"OK {path.name}"))
    print("Done. (100%)")
    print(f"https://github.com/{repo}/releases/tag/{tag}")
    return 0


def gh_prune_obsolete_photos(repo: str, tag: str, keep: Set[str]) -> None:
    """Delete remote photo parts not in the current upload set (shard resize)."""
    photo_keep = {n for n in keep if n.startswith("offenders.photos.")}
    if not photo_keep:
        return
    try:
        cp = subprocess.run(
            ["gh", "api", f"repos/{repo}/releases/tags/{tag}"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if cp.returncode != 0:
            return
        data = json.loads(cp.stdout or "{}")
    except Exception:
        return
    for asset in data.get("assets") or []:
        name = (asset or {}).get("name") or ""
        if not name.startswith("offenders.photos.") or name in photo_keep:
            continue
        aid = asset.get("id")
        if not aid:
            continue
        print(f"Removing obsolete remote photo asset {name}…")
        subprocess.call(
            ["gh", "api", "-X", "DELETE", f"repos/{repo}/releases/assets/{aid}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def publish_api(
    repo: str,
    tag: str,
    assets: List[Path],
    token: str,
    man: dict,
    *,
    prune_photos: bool = False,
) -> int:
    import urllib.error
    import urllib.request

    api = "https://api.github.com"
    asset_names = {a.name for a in assets if a.is_file()}

    def req(
        method: str,
        url: str,
        data: bytes | None = None,
        content_type: str = "",
        timeout: int = 600,
    ):
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "SOR-Public-Archiver-Publish",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if content_type:
            headers["Content-Type"] = content_type
        r = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.read()

    try:
        _status, body = req("GET", f"{api}/repos/{repo}/releases/tags/{tag}")
        rel = json.loads(body.decode())
        print(f"Updating existing release id={rel.get('id')}")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            print("GET release failed", e)
            return 1
        payload = json.dumps(
            {
                "tag_name": tag,
                "name": "Public database archive",
                "body": release_notes(man),
                "draft": False,
                "prerelease": False,
            }
        ).encode()
        _status, body = req(
            "POST",
            f"{api}/repos/{repo}/releases",
            data=payload,
            content_type="application/json",
        )
        rel = json.loads(body.decode())
        print(f"Created release id={rel.get('id')}")

    upload_url = (rel.get("upload_url") or "").split("{")[0]
    photo_keep = {n for n in asset_names if n.startswith("offenders.photos.")}
    for asset in rel.get("assets") or []:
        name = asset.get("name") or ""
        drop = name in asset_names
        if (
            prune_photos
            and photo_keep
            and name.startswith("offenders.photos.")
            and name not in photo_keep
        ):
            drop = True
        if not drop:
            continue
        aid = asset.get("id")
        try:
            req("DELETE", f"{api}/repos/{repo}/releases/assets/{aid}")
            print("Deleted old asset", name)
        except Exception as e:
            print("Could not delete asset", e)

    total_b = sum(p.stat().st_size for p in assets if p.is_file()) or 1
    done_b = 0
    for path in assets:
        if not path.is_file():
            continue
        url = f"{upload_url}?name={path.name}"
        size = path.stat().st_size
        print(upload_progress_msg(done_b, total_b, f"Uploading {path.name} ({size:,} bytes)"))
        try:
            curl = which("curl")
            if curl and size > 50 * 1024 * 1024:
                cmd = [
                    curl,
                    "-sS",
                    "-X",
                    "POST",
                    "-H",
                    f"Authorization: Bearer {token}",
                    "-H",
                    "Accept: application/vnd.github+json",
                    "-H",
                    "Content-Type: application/octet-stream",
                    "-H",
                    "User-Agent: SOR-Public-Archiver-Publish",
                    "--data-binary",
                    f"@{path}",
                    url,
                ]
                cp = subprocess.run(cmd, capture_output=True, timeout=7200)
                if cp.returncode != 0:
                    err = (cp.stderr or b"").decode("utf-8", errors="replace")[:400]
                    print(f"  FAIL curl rc={cp.returncode} {err}")
                    return 1
                done_b += size
                print(upload_progress_msg(done_b, total_b, f"OK curl ({path.name})"))
                continue
            with open(path, "rb") as f:
                data = f.read()
            status, _body = req(
                "POST",
                url,
                data=data,
                content_type="application/octet-stream",
                timeout=3600,
            )
            done_b += size
            print(upload_progress_msg(done_b, total_b, f"OK HTTP {status}"))
        except urllib.error.HTTPError as e:
            print(f"  FAIL {e.code} {e.read()[:500]}")
            return 1
        except MemoryError:
            print(
                f"  FAIL: {path.name} too large for in-memory upload and curl missing."
            )
            return 1
        except Exception as e:
            print(f"  FAIL {e}")
            return 1
    print("Done. (100%)")
    print(
        f"Download: https://github.com/{repo}/releases/download/{tag}/"
        f"{(assets[0].name if assets else 'MANIFEST.json')}"
    )
    return 0
