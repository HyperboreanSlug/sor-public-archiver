from __future__ import annotations

import json
import re

from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple


from scraper.nsopw.builder_types import *  # noqa: F401,F403
from scraper.database import Database
from scraper.ethnic_names import get_ethnic_database
from scraper.reports.fetcher import ReportFetcher
from scraper.nsopw.client import (
    DEFAULT_JURISDICTIONS,
    NSOPWClient,
    NSOPWOffender,
    normalize_jurisdiction_code,
)
from scraper.nsopw.parallel import JurisdictionReportPool, ReportJob

class BuilderPhotoMixin:
    def _ensure_photo(
        self,
        record: Dict[str, Any],
        hit: Any,
        jurisdiction: str,
        fetcher: Optional[ReportFetcher] = None,
    ) -> None:
        """Download / attach a local offender photo when possible.

        Priority:
          1. Dedicated NSOPW/state photo URL (imageUri / photo_url) — real mugshot
          2. Best image from archived report HTML assets (JPEG/PNG preferred)
          3. Keep existing path only if it is already a solid mugshot file

        HTML assets often include large site chrome GIFs (FL FDLE banners ~30KB).
        Those must never block a dedicated CallImage / imageUri download.

        ``fetcher`` lets a parallel report worker download through its own HTTP
        session (defaults to the builder's shared fetcher for the sequential
        path).
        """
        fetcher = fetcher or self.reports
        min_primary = int(getattr(fetcher, "MIN_PRIMARY_PHOTO_BYTES", 2000) or 2000)
        min_any = int(getattr(fetcher, "MIN_PHOTO_BYTES", 80) or 80)

        def _file_ok(path: str, min_bytes: int) -> bool:
            try:
                p = Path(path)
                return p.is_file() and p.stat().st_size >= min_bytes
            except OSError:
                return False

        def _looks_like_mugshot(path: str) -> bool:
            """True for local files that are likely offender photos, not site chrome."""
            try:
                p = Path(path)
                if not p.is_file():
                    return False
                sz = p.stat().st_size
                if sz < min_any:
                    return False
                try:
                    from scraper.mugshot_ethnicity.photo_quality import is_non_mugshot

                    if is_non_mugshot(p):
                        return False
                except Exception:
                    pass
                ext = p.suffix.lower()
                # GIFs on state sites are almost always logos/banners/spacers
                if ext == ".gif":
                    return False
                # Files under HTML *_assets/ are frequently shared site chrome
                # (even large PNGs). Only trust dedicated …/photos/ downloads
                # as final mugshots when a photo_url exists.
                parts_l = [x.lower() for x in p.parts]
                in_assets = any(x.endswith("_assets") or x == "assets" for x in parts_l)
                in_photos = "photos" in parts_l
                if ext in (".jpg", ".jpeg", ".png", ".webp", ".bmp"):
                    if in_photos and sz >= 500:
                        return True
                    if in_assets:
                        # Asset only counts as mugshot if fairly large JPEG-like
                        # and not a known tiny placeholder size band
                        return ext in (".jpg", ".jpeg") and sz >= 5000
                    return sz >= min_primary
                return False
            except OSError:
                return False

        def _set_path(path: str, *, from_url: bool = False) -> None:
            # Never persist GIFs as the offender photo
            if path and str(path).lower().endswith(".gif"):
                return
            try:
                from scraper.mugshot_ethnicity.photo_quality import is_non_mugshot

                if path and is_non_mugshot(path):
                    return
            except Exception:
                pass
            record["photo_path"] = path
            with self._stats_lock:
                self.stats.photos_saved += 1
            if not from_url:
                return
            try:
                flags = json.loads(record.get("flags") or "[]")
                if not isinstance(flags, list):
                    flags = [str(flags)]
            except json.JSONDecodeError:
                flags = []
            if "photo_archived" not in flags:
                flags.append("photo_archived")
            record["flags"] = json.dumps(flags)

        existing = (record.get("photo_path") or "").strip()
        existing_is_mugshot = bool(existing and _looks_like_mugshot(existing))
        existing_in_photos = bool(
            existing and "photos" in [x.lower() for x in Path(existing).parts]
        )

        from scraper.report_fetcher import extract_dedicated_photo_urls, photo_state_from_url

        def _download_dedicated(url: str) -> Optional[str]:
            """Download mugshot into html_dir/<jur>/photos/ and return local path."""
            host_st = photo_state_from_url(url)
            jur_raw = (
                host_st
                or jurisdiction
                or record.get("state")
                or record.get("source_state")
                or "UNK"
            )
            jur = re.sub(r"[^A-Za-z0-9_-]", "", str(jur_raw).upper())[:12] or "UNK"
            # WatchSystems CDN serves many states — keep under NSOPW/record jurisdiction
            if "watchsystems.com" in url.lower() and not host_st:
                jur = re.sub(
                    r"[^A-Za-z0-9_-]",
                    "",
                    str(jurisdiction or record.get("state") or record.get("source_state") or "UNK").upper(),
                )[:12] or "UNK"
            photo_dir = self.html_dir / jur / "photos"
            stem = sha1(
                (url + "|" + (record.get("source_url") or "")).encode(
                    "utf-8", errors="replace"
                )
            ).hexdigest()[:16]
            referer = (record.get("source_url") or "").strip()
            if not referer and "watchsystems.com" in url.lower():
                referer = "https://www.icrimewatch.net/"
            if not referer:
                referer = "https://www.nsopw.gov/"
            return fetcher.download_photo(
                url,
                photo_dir,
                referer=referer,
                stem=stem,
                reject_gif=True,
            )

        # 1) Dedicated mugshot URL when present — always preferred over HTML assets
        photo_url = (
            (record.get("photo_url") or "").strip()
            or (getattr(hit, "image_uri", None) or "").strip()
        )
        # Recover WatchSystems /pictures/ URL from archived HTML when imageUri missing
        html_path = (record.get("report_html_path") or "").strip()
        if not photo_url and html_path:
            try:
                raw_html = Path(html_path).read_text(encoding="utf-8", errors="replace")
                dedicated = extract_dedicated_photo_urls(raw_html)
                if dedicated:
                    photo_url = dedicated[0]
            except Exception:
                pass

        if photo_url:
            try:
                from scraper.mugshot_ethnicity.photo_quality import (
                    url_has_empty_image_id,
                    url_looks_like_chrome,
                )

                if url_has_empty_image_id(photo_url) or url_looks_like_chrome(photo_url):
                    # FL CallImage?imgID= / SC ImageId=0 — never download or keep
                    record["photo_url"] = None
                    photo_url = ""
                    if existing and not existing_in_photos:
                        record["photo_path"] = None
                        existing = ""
                        existing_is_mugshot = False
            except Exception:
                low = photo_url.lower()
                if "imgid=0" in low or "imageid=0" in low or "imgid=&" in low or low.endswith("imgid="):
                    record["photo_url"] = None
                    photo_url = ""

        if photo_url:
            record["photo_url"] = photo_url
            # Only skip network if we already have a dedicated photos/ download
            if not (existing_is_mugshot and existing_in_photos):
                path = _download_dedicated(photo_url)
                if path and _file_ok(path, min_any) and not str(path).lower().endswith(".gif"):
                    _set_path(path, from_url=True)
                    return

        if existing_is_mugshot and existing_in_photos:
            return
        if existing_is_mugshot and not photo_url:
            # Keep decent asset JPEG only when no dedicated URL exists
            return

        # 2) Best image from report HTML assets (not GIF; prefer portrait JPEG)
        if html_path:
            best = self._best_asset_photo(html_path, min_bytes=min_any)
            if best and _looks_like_mugshot(best):
                try:
                    rel = str(Path(best).relative_to(Path.cwd()))
                except ValueError:
                    rel = best
                _set_path(rel, from_url=False)
                return

        # 3) Keep a weak existing path only if nothing better is available
        if existing and _file_ok(existing, min_any) and not existing.lower().endswith(".gif"):
            try:
                from scraper.mugshot_ethnicity.photo_quality import is_non_mugshot

                if is_non_mugshot(existing):
                    record["photo_path"] = None
                    return
            except Exception:
                pass
            # Prefer clearing shared asset placeholders so integrity shows missing
            parts_l = [x.lower() for x in Path(existing).parts]
            if any(x.endswith("_assets") for x in parts_l) and photo_url:
                record["photo_path"] = None
                return
            return
        # Drop GIF / chrome placeholders so integrity shows missing photo
        if existing and existing.lower().endswith(".gif"):
            record["photo_path"] = None
            return
        try:
            from scraper.mugshot_ethnicity.photo_quality import is_non_mugshot

            if existing and is_non_mugshot(existing):
                record["photo_path"] = None
        except Exception:
            pass


    @staticmethod
    def _best_asset_photo(html_path: str, *, min_bytes: int = 80) -> Optional[str]:
        """Pick the most likely mugshot under {stem}_assets next to archived HTML."""
        hp = Path(html_path)
        assets = hp.parent / f"{hp.stem}_assets"
        if not assets.is_dir():
            return None
        best: Optional[Tuple[int, int, Path]] = None  # score, size, path
        try:
            from scraper.mugshot_ethnicity.photo_quality import is_non_mugshot
        except Exception:
            is_non_mugshot = lambda _p: False  # type: ignore
        for cand in assets.iterdir():
            if not cand.is_file():
                continue
            if cand.suffix.lower() not in (
                ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"
            ):
                continue
            try:
                sz = cand.stat().st_size
            except OSError:
                continue
            if sz < min_bytes:
                continue
            try:
                if is_non_mugshot(cand):
                    continue
            except Exception:
                pass
            name = cand.name.lower()
            ext = cand.suffix.lower()
            score = 0
            # FL and others ship large banner/logo GIFs — never prefer them
            if ext == ".gif":
                score -= 40
            if ext in (".jpg", ".jpeg", ".png", ".webp"):
                score += 12
            for bad in (
                "logo", "icon", "sprite", "pixel", "spacer", "banner", "button",
                "header", "footer", "nav", "seal", "badge", "map",
                "help", "question", "chat", "tooltip", "info",
            ):
                if bad in name:
                    score -= 25
            for good in ("photo", "offender", "mug", "portrait", "face", "sor", "image"):
                if good in name:
                    score += 10
            if sz >= 2000:
                score += 8
            # Mild size preference (aspect ratio below matters more for AL banners)
            score += min(sz // 20000, 3)
            # Prefer portrait/square; penalize wide office banners (~800x200)
            try:
                from PIL import Image

                with Image.open(cand) as im:
                    w, h = im.size
                if w > 0 and h > 0:
                    if min(w, h) < 40:
                        score -= 25
                    # SC speech-bubble help icons are ~108×109 solid-color PNGs
                    if max(w, h) <= 128 and sz < 15_000:
                        score -= 20
                    ratio = max(w, h) / float(min(w, h))
                    if ratio >= 2.4:
                        score -= 30
                    ar = w / float(h)
                    if 0.55 <= ar <= 1.35:
                        score += 14
            except Exception:
                pass
            if best is None or (score, sz) > (best[0], best[1]):
                best = (score, sz, cand)
        if best is None:
            return None
        # Reject GIF winners entirely
        if best[2].suffix.lower() == ".gif":
            return None
        return str(best[2])


