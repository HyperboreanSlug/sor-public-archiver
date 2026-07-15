"""Download / update the public offenders SQLite archive from GitHub.

The archive is published as Release assets:
  - ``offenders.db.zip`` (+ ``MANIFEST.json``)
  - ``offenders.photos.NNN.zip`` (mugshots under ``data/report_pages/*/photos/``)

Paths inside the DB are project-relative; photos extract next to the DB's
``data/`` folder so ``photo_path`` resolves for Browse / detail views.

Default source: ``HyperboreanSlug/SORPA`` release tag
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
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Public GitHub repository that hosts the database release asset (not a person).
DEFAULT_GITHUB_REPO = "HyperboreanSlug/SORPA"
DEFAULT_RELEASE_TAG = "database-latest"
DEFAULT_ASSET_NAME = "offenders.db.zip"
DEFAULT_MANIFEST_NAME = "MANIFEST.json"
DEFAULT_DB_REL = Path("data/offenders.db")
USER_AGENT = "SOR-Public-Archiver-DB-Sync/1.0"
PHOTO_ASSET_PREFIX = "offenders.photos."


@dataclass
class SyncResult:
    ok: bool
    action: str  # skipped | downloaded | updated | error
    message: str
    record_count: Optional[int] = None
    sha256: Optional[str] = None
    bytes_written: int = 0
    photos_extracted: int = 0


