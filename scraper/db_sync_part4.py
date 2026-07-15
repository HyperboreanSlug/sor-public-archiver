from __future__ import annotations

from scraper.db_sync_common import *  # noqa: F401,F403

def should_prompt_first_run(settings: Dict[str, Any], db_path: Path) -> bool:
    """True when user has never chosen *and* no usable local DB is present."""
    if settings.get("db_sync_prompted"):
        return False
    if settings.get("db_sync_enabled"):
        return False
    try:
        if db_path.is_file() and db_path.stat().st_size > 10_000:
            # Local DB already present — do not force a download prompt.
            return False
    except OSError:
        pass
    return True


