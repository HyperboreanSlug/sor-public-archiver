"""Resolve stored mugshot paths and gate DeepFace usability."""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Union


def resolve_local_photo(path: Union[str, Path, None]) -> Optional[Path]:
    """Resolve a stored photo_path against cwd and project root."""
    if path is None:
        return None
    raw = str(path).strip()
    if not raw:
        return None
    candidates = [Path(raw)]
    try:
        from scraper.paths import project_root

        root = project_root()
        candidates.extend([root / raw, root / raw.replace("\\", "/")])
    except Exception:
        pass
    for p in candidates:
        try:
            if p.is_file() and p.stat().st_size > 0:
                return p
        except OSError:
            continue
    return None


def photo_usable_for_scan(path: Union[str, Path, None]) -> bool:
    """True when *path* exists on disk and is not chrome / placeholder."""
    from scraper.mugshot_ethnicity.photo_quality import is_non_mugshot

    resolved = resolve_local_photo(path)
    if resolved is None:
        return False
    return not is_non_mugshot(resolved)
