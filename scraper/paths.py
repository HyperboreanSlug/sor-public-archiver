"""Project-root and data-path resolution (portable across installs).

GUI and CLI must resolve ``data/offenders.db`` against the *install root*,
not ``Path.cwd()``. Relative settings survive folder moves and other machines;
stale absolute paths from another install are rejected and fall back.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional, Union

PathLike = Union[str, Path]

DEFAULT_DB_REL = "data/offenders.db"
DEFAULT_SETTINGS_REL = "data/app_settings.json"


def project_root() -> Path:
    """Directory that contains ``data/``, ``gui.py``, ``scraper/``."""
    env = (os.environ.get("SORPA_ROOT") or os.environ.get("ARCHIVER_ROOT") or "").strip()
    if env:
        try:
            p = Path(env).expanduser().resolve()
            if p.is_dir():
                return p
        except OSError:
            pass
    if getattr(sys, "frozen", False):
        # PyInstaller onedir: exe next to data/; onefile: still prefer exe dir
        try:
            return Path(sys.executable).resolve().parent
        except OSError:
            pass
    # scraper/paths.py → install root
    return Path(__file__).resolve().parent.parent


def settings_path() -> Path:
    return project_root() / DEFAULT_SETTINGS_REL


def resolve_under_root(
    path: Optional[PathLike],
    *,
    default: str = DEFAULT_DB_REL,
    root: Optional[Path] = None,
) -> Path:
    """Resolve a relative or absolute path against the install root."""
    base = root or project_root()
    raw = (str(path).strip() if path is not None else "") or default
    p = Path(raw).expanduser()
    if not p.is_absolute():
        return (base / p).resolve()
    try:
        return p.resolve()
    except OSError:
        return p


def portable_path_str(
    path: Optional[PathLike],
    *,
    default: str = DEFAULT_DB_REL,
    root: Optional[Path] = None,
) -> str:
    """Prefer project-relative form when *path* lives under the install root."""
    base = root or project_root()
    resolved = resolve_under_root(path, default=default, root=base)
    try:
        rel = resolved.relative_to(base.resolve())
        return rel.as_posix()
    except ValueError:
        return str(resolved)


def sanitize_db_path(
    path: Optional[PathLike],
    *,
    default: str = DEFAULT_DB_REL,
    root: Optional[Path] = None,
) -> str:
    """Return a portable db path string, falling back when absolute path is dead.

    Fixes cross-install breakage: settings saved as
    ``C:\\Users\\Other\\SORPA\\data\\offenders.db`` on another machine would
    otherwise create an empty DB at that path (or fail on a missing drive).
    """
    base = root or project_root()
    default_abs = (base / default).resolve()
    raw = (str(path).strip() if path is not None else "") or default
    p = Path(raw).expanduser()

    if not p.is_absolute():
        return Path(raw).as_posix() if raw else default

    try:
        resolved = p.resolve()
    except OSError:
        return default

    # Still under this install → store relative
    try:
        rel = resolved.relative_to(base.resolve())
        return rel.as_posix()
    except ValueError:
        pass

    # Absolute outside install:
    # - keep if the file already exists (custom DB location)
    # - keep if the parent dir exists (new file chosen via Browse)
    # - otherwise treat as stale foreign path from another machine
    try:
        if resolved.is_file():
            return str(resolved)
        if resolved.parent.is_dir():
            return str(resolved)
    except OSError:
        pass

    # Stale foreign path (other user / moved folder / missing drive)
    return default


def clear_sqlite_sidecars(db_path: Path) -> None:
    """Remove ``-wal`` / ``-shm`` next to *db_path* (best-effort).

    After an atomic replace of the main ``.db`` file, leftover WAL/SHM from a
    previous connection can make SQLite refuse to open or appear empty/corrupt.
    """
    db_path = Path(db_path)
    for suffix in ("-wal", "-shm"):
        side = db_path.parent / f"{db_path.name}{suffix}"
        try:
            if side.is_file():
                side.unlink()
        except OSError:
            pass
