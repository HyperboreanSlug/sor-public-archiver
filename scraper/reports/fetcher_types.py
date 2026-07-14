"""Jurisdiction report fetcher (HTML, demographics, photos)."""
from __future__ import annotations

# Pull all util names into this module namespace (including _private constants).
import scraper.reports.util as _reports_util

for _name in dir(_reports_util):
    if _name.startswith("__"):
        continue
    globals()[_name] = getattr(_reports_util, _name)
del _name, _reports_util

# Typing / common names used in signatures (also provided by util loop)
from typing import Any, Dict, List, Optional, Set, Tuple  # noqa: E402
from pathlib import Path  # noqa: E402


