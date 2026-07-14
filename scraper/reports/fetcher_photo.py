from __future__ import annotations

import requests

from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple


from scraper.reports.fetcher_types import *  # noqa: F401,F403
from scraper.reports.util import (  # noqa: F401
    _CAPTCHA_MARKERS,
    _DISCLAIMER_MARKERS,
    _LABEL_MAP,
    _LONG_VALUE_KEYS,
    _MAX_CRIME_LEN,
    _PHOTO_HOST_STATE,
    _clean_value,
    _normalize_label,
    _normalize_url,
    photo_state_from_url,
    photo_url_variants,
    extract_dedicated_photo_urls,
)

class FetcherPhotoMixin:
    def download_photo(
        self,
        photo_url: str,
        photo_dir: Path,
        *,
        referer: str = "",
        stem: str = "",
        min_bytes: Optional[int] = None,
        reject_gif: bool = False,
    ) -> Optional[str]:
        """
        Download a single photo URL into photo_dir.
        Returns path relative to cwd when possible.

        Retries with verify=False on TLS/certificate failures (common on some
        state SOR hosts with curl_cffi / incomplete CA stores on Windows).

        SC DisplayImage: tries Thumb=true/false variants when the first response
        is empty, HTML, or a non-image GIF stub.
        """
        base = _normalize_url((photo_url or "").strip())
        if not base.lower().startswith(("http://", "https://")):
            return None
        low_u = base.lower()
        # No photo on record (SC ImageId=0; FL empty CallImage?imgID=)
        try:
            from scraper.mugshot_ethnicity.photo_quality import (
                url_has_empty_image_id,
                url_looks_like_chrome,
            )

            if url_has_empty_image_id(base) or url_looks_like_chrome(base):
                return None
        except Exception:
            if "imgid=0" in low_u or "imageid=0" in low_u or "image_id=0" in low_u:
                return None
        min_sz = self.MIN_PHOTO_BYTES if min_bytes is None else int(min_bytes)
        try:
            photo_dir = Path(photo_dir)
            photo_dir.mkdir(parents=True, exist_ok=True)
            # Stable stem from the *original* URL so variants share one file
            key = stem or sha1(base.encode("utf-8", errors="replace")).hexdigest()[:16]
            # Skip if already have a solid file for this stem
            for existing in photo_dir.glob(f"{key}.*"):
                if existing.is_file() and existing.stat().st_size >= min_sz:
                    if reject_gif and existing.suffix.lower() == ".gif":
                        try:
                            existing.unlink(missing_ok=True)  # type: ignore[call-arg]
                        except TypeError:
                            try:
                                if existing.is_file():
                                    existing.unlink()
                            except OSError:
                                pass
                        except OSError:
                            pass
                        continue
                    # Reject empty/broken / non-mugshot cached stubs
                    try:
                        head = existing.read_bytes()[:16]
                    except OSError:
                        continue
                    if head[:3] == b"\xff\xd8\xff" or head[:8] == b"\x89PNG\r\n\x1a\n":
                        pass
                    elif head[:6] in (b"GIF87a", b"GIF89a") and reject_gif:
                        continue
                    elif len(head) < 8:
                        continue
                    try:
                        from scraper.mugshot_ethnicity.photo_quality import (
                            is_non_mugshot,
                        )

                        if is_non_mugshot(existing):
                            try:
                                existing.unlink()
                            except OSError:
                                pass
                            continue
                    except Exception:
                        pass
                    try:
                        return str(existing.relative_to(Path.cwd()))
                    except ValueError:
                        return str(existing)

            # Prefer a referer on the same registry host (SC/TN need this)
            parsed_photo = urlparse(base)
            host_referer = ""
            if parsed_photo.scheme and parsed_photo.netloc:
                host_referer = f"{parsed_photo.scheme}://{parsed_photo.netloc}/"
            referers: List[str] = []
            for r in (referer, host_referer, "https://www.nsopw.gov/"):
                r = (r or "").strip()
                if r and r not in referers:
                    referers.append(r)
            if not referers:
                referers = [""]

            for cand in photo_url_variants(base):
                for ref in referers:
                    path = self._download_photo_once(
                        cand,
                        photo_dir,
                        key=key,
                        referer=ref,
                        min_sz=min_sz,
                        reject_gif=reject_gif,
                    )
                    if path:
                        return path
            return None
        except Exception:
            return None


    def _download_photo_once(
        self,
        url: str,
        photo_dir: Path,
        *,
        key: str,
        referer: str,
        min_sz: int,
        reject_gif: bool,
    ) -> Optional[str]:
        """Single GET + validate + write. Returns local path or None."""
        headers: Dict[str, str] = {
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        }
        if referer:
            headers["Referer"] = referer
            parsed = urlparse(referer)
            if parsed.scheme and parsed.netloc:
                headers.setdefault("Origin", f"{parsed.scheme}://{parsed.netloc}")

        resp = self._get_photo_response(url, headers=headers)
        if resp is None:
            return None
        if getattr(resp, "status_code", 0) >= 400:
            return None
        body = resp.content or b""
        if len(body) < min_sz:
            return None
        # Reject HTML error pages saved as images (SC often returns the portal HTML)
        head = body[:200].lstrip().lower()
        if head.startswith(b"<!doctype") or head.startswith(b"<html") or head.startswith(b"<?xml"):
            return None
        ct = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ct and not (
            ct.startswith("image/")
            or ct in ("application/octet-stream", "binary/octet-stream", "")
        ):
            if "json" in ct or "text/" in ct or "html" in ct:
                return None
        # Sniff magic (authoritative — SC labels PNG as Image/gif)
        ext = Path(urlparse(url).path).suffix.lower()
        if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"):
            ext = ""
        if body[:3] == b"\xff\xd8\xff":
            ext = ".jpg"
        elif body[:8] == b"\x89PNG\r\n\x1a\n":
            ext = ".png"
        elif body[:6] in (b"GIF87a", b"GIF89a"):
            ext = ".gif"
        elif body[:4] == b"RIFF" and len(body) > 12 and body[8:12] == b"WEBP":
            ext = ".webp"
        elif not ext:
            guess = mimetypes.guess_extension(ct) or ""
            if guess == ".jpe":
                guess = ".jpg"
            ext = guess if guess in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp") else ".jpg"
        if reject_gif and ext == ".gif":
            return None
        # Reject 1×1 / seals / silhouettes / banner chrome before writing
        try:
            from scraper.mugshot_ethnicity.photo_quality import bytes_non_mugshot_reason

            bad = bytes_non_mugshot_reason(body, url=url, ext=ext)
            if bad:
                return None
        except Exception:
            pass
        # Content-Type image/gif with non-GIF magic is fine (already sniffed)
        dest = photo_dir / f"{key}{ext}"
        dest.write_bytes(body)
        # Double-check after write (dims/heuristics on file)
        try:
            from scraper.mugshot_ethnicity.photo_quality import is_non_mugshot

            if is_non_mugshot(dest):
                try:
                    dest.unlink()
                except OSError:
                    pass
                return None
        except Exception:
            pass
        try:
            return str(dest.relative_to(Path.cwd()))
        except ValueError:
            return str(dest)


    def _get_photo_response(self, url: str, *, headers: Dict[str, str]) -> Any:
        """GET image bytes; fall back to verify=False on TLS failures."""
        last_err: Optional[Exception] = None
        for verify in (True, False):
            try:
                return self.session.get(
                    url,
                    timeout=self.timeout,
                    headers=headers or None,
                    allow_redirects=True,
                    verify=verify,
                )
            except Exception as e:
                last_err = e
                msg = str(e).lower()
                # Only retry without verify on SSL/cert problems
                if verify and (
                    "ssl" in msg
                    or "certificate" in msg
                    or "cert" in msg
                    or "curl: (60)" in msg
                    or "certificate_verify" in msg
                ):
                    continue
                if verify:
                    # Other errors: still try once without verify (some stacks
                    # wrap TLS failures poorly).
                    continue
                break
        # Last-ditch: stock requests (different CA store than curl_cffi)
        try:
            return requests.get(
                url,
                timeout=self.timeout,
                headers={**dict(getattr(self.session, "headers", {}) or {}), **headers},
                allow_redirects=True,
                verify=False,
            )
        except Exception:
            if last_err:
                raise last_err
            return None


