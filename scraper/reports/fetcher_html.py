from __future__ import annotations

from bs4 import BeautifulSoup

import time
import re

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

class FetcherHtmlMixin:
    def _save_html(
        self,
        content: bytes,
        report_url: str,
        html_dir: Path,
        jurisdiction: str,
        final_url: str = "",
        download_images: bool = True,
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Write report HTML to disk; rewrite <img> src to local copies when possible.

        Returns (html_path, primary_photo_path) — either may be None.
        """
        try:
            jur = re.sub(r"[^A-Za-z0-9_-]", "", (jurisdiction or "UNK").upper())[:12] or "UNK"
            digest = sha1((final_url or report_url).encode("utf-8", errors="replace")).hexdigest()[:16]
            folder = Path(html_dir) / jur
            folder.mkdir(parents=True, exist_ok=True)
            dest = folder / f"{digest}.html"
            assets = folder / f"{digest}_assets"
            base = final_url or report_url

            header = (
                f"<!-- archived_from: {html_lib.escape(final_url or report_url)} -->\n"
                f"<!-- archived_at_utc: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} -->\n"
                f"<!-- photos_embedded: {str(bool(download_images)).lower()} -->\n"
            ).encode("utf-8")

            text = content.decode("utf-8", errors="replace")
            primary_photo: Optional[str] = None

            if download_images:
                text, primary_photo = self._embed_images_in_html(
                    text,
                    base_url=base,
                    assets_dir=assets,
                    assets_rel_name=f"{digest}_assets",
                    referer=base,
                )

            body_bytes = text.encode("utf-8", errors="replace")
            if not (dest.exists() and dest.stat().st_size > 100):
                dest.write_bytes(header + body_bytes)
            elif download_images:
                # Refresh archive so images are embedded even if HTML existed without them
                dest.write_bytes(header + body_bytes)

            try:
                html_path = str(dest.relative_to(Path.cwd()))
            except ValueError:
                html_path = str(dest)

            # Prefer photo already under assets next to HTML (never GIF chrome)
            if not primary_photo and assets.is_dir():
                ranked: List[Tuple[int, Path]] = []
                for p in assets.iterdir():
                    if not p.is_file():
                        continue
                    ext = p.suffix.lower()
                    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".bmp"):
                        continue  # skip .gif site chrome
                    try:
                        sz = p.stat().st_size
                    except OSError:
                        continue
                    if sz < self.MIN_PHOTO_BYTES:
                        continue
                    score = sz + (50_000 if ext in (".jpg", ".jpeg") else 0)
                    ranked.append((score, p))
                if ranked:
                    ranked.sort(key=lambda t: t[0], reverse=True)
                    p = ranked[0][1]
                    try:
                        primary_photo = str(p.relative_to(Path.cwd()))
                    except ValueError:
                        primary_photo = str(p)

            return html_path, primary_photo
        except OSError:
            return None, None


    def _embed_images_in_html(
        self,
        html: str,
        *,
        base_url: str,
        assets_dir: Path,
        assets_rel_name: str,
        referer: str = "",
    ) -> Tuple[str, Optional[str]]:
        """
        Download remote images referenced by the report and rewrite HTML to local paths.
        Returns (modified_html, best_photo_path).
        """
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            return html, None

        assets_dir.mkdir(parents=True, exist_ok=True)
        url_to_local: Dict[str, str] = {}
        primary: Optional[str] = None
        candidates: List[Tuple[int, str, str]] = []  # score, abs_url, local_path

        def _abs(src: str) -> str:
            s = (src or "").strip()
            if not s or s.startswith("data:") or s.startswith("javascript:"):
                return ""
            return urljoin(base_url, s)

        def _score_url(u: str, el_tag: str = "img") -> int:
            low = u.lower()
            score = 10
            for bad in (
                "logo", "icon", "sprite", "pixel", "tracking", "1x1", "spacer",
                "banner", "button", "header", "footer", "seal", "badge", "map",
                "help", "question", "chat", "tooltip", "qrcode", "qr-code", "/qr",
            ):
                if bad in low:
                    score -= 8
            for good in (
                "photo", "offender", "mug", "portrait", "image", "pic", "face",
                "sor", "reg", "callimage", "imgid", "displayimage", "pictures/",
            ):
                if good in low:
                    score += 8
            # Dedicated mugshot endpoints / CDNs beat decorative chrome
            if (
                "callimage" in low
                or "imgid=" in low
                or "/sorimage/" in low
                or "displayimage" in low
            ):
                score += 20
            # AL iCrimewatch: real mugshots live under /pictures/; office headers under /offices/
            if "watchsystems.com" in low and "/pictures/" in low:
                score += 35
            if "/pictures/" in low:
                score += 15
            if "/offices/" in low:
                score -= 40
            if el_tag == "img":
                score += 2
            if any(low.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp")):
                score += 5
            if low.endswith(".gif") or ".gif?" in low:
                score -= 25
            return score

        def _aspect_score(local_path: str) -> int:
            """Prefer portrait/square mugshots; penalize wide banners and tiny icons."""
            try:
                from PIL import Image

                with Image.open(local_path) as im:
                    w, h = im.size
                if w < 1 or h < 1:
                    return -15
                if min(w, h) < 40:
                    return -25
                ratio = max(w, h) / float(min(w, h))
                # Sheriff office banners are often ~800x200 (ratio 4)
                if ratio >= 2.4:
                    return -30
                # Typical mugshot / headshot
                ar = w / float(h)
                if 0.55 <= ar <= 1.35:
                    return 12
                return 0
            except Exception:
                return 0

        # Collect img src (+ srcset first url) and meta og:image
        img_srcs: List[Tuple[Any, str]] = []
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src") or img.get("data-original") or ""
            if not src and img.get("srcset"):
                src = (img.get("srcset") or "").split(",")[0].strip().split(" ")[0]
            if src:
                img_srcs.append((img, src))

        for meta in soup.find_all("meta"):
            prop = (meta.get("property") or meta.get("name") or "").lower()
            if prop in ("og:image", "twitter:image", "twitter:image:src"):
                content = meta.get("content") or ""
                if content:
                    img_srcs.append((meta, content))

        for el, src in img_srcs:
            abs_u = _abs(src)
            if not abs_u:
                continue
            # Skip seals / spacers / tracking before network I/O
            try:
                from scraper.mugshot_ethnicity.photo_quality import url_looks_like_chrome

                if url_looks_like_chrome(abs_u):
                    continue
            except Exception:
                pass
            # Alt text: skip explicit chrome labels
            try:
                alt0 = (el.get("alt") or "").strip().lower() if hasattr(el, "get") else ""
            except Exception:
                alt0 = ""
            if alt0 and any(
                k in alt0
                for k in (
                    "seal",
                    "logo",
                    "spacer",
                    "skip navigation",
                    "banner",
                    "icon",
                    "sheriff's office",
                    "sheriffs office",
                    "qr code",
                    "qrcode",
                    "mobile app",
                )
            ):
                # Keep real "offender photo" etc.
                if not any(k in alt0 for k in ("offender", "mug", "registrant", "photo of")):
                    continue
            if abs_u in url_to_local:
                local = url_to_local[abs_u]
            else:
                stem = sha1(abs_u.encode("utf-8", errors="replace")).hexdigest()[:14]
                local = self.download_photo(
                    abs_u, assets_dir, referer=referer or base_url, stem=stem
                )
                if not local:
                    continue
                url_to_local[abs_u] = local
                score = _score_url(abs_u, getattr(el, "name", "img") or "img")
                # Alt text: icrimewatch sets alt='Offender photo' on the mugshot
                try:
                    alt = (el.get("alt") or "").strip().lower() if hasattr(el, "get") else ""
                except Exception:
                    alt = ""
                if alt:
                    if any(k in alt for k in ("offender", "mug", "photo of", "registrant")):
                        score += 30
                    elif "photo" in alt and "office" not in alt:
                        score += 18
                    if any(
                        k in alt
                        for k in (
                            "sheriff", "office", "search", "email", "tip", "logo",
                            "qr", "mobile app",
                        )
                    ):
                        score -= 25
                try:
                    fsz = Path(local).stat().st_size
                    fext = Path(local).suffix.lower()
                except OSError:
                    fsz = 0
                    fext = ""
                # Size boost: real mugshots are usually multi-KB; shared site
                # chrome (icons/badges) is often 1–2KB and repeats across records.
                # Large GIFs (FL banners ~30KB) must still lose to JPEG CallImage.
                if fext == ".gif":
                    score -= 30
                if fext in (".jpg", ".jpeg", ".png", ".webp"):
                    score += 10
                if fsz >= self.MIN_PRIMARY_PHOTO_BYTES:
                    score += 8
                elif fsz >= 800:
                    score += 2
                else:
                    score -= 10
                # Mild size preference — but aspect ratio matters more than raw KB
                # (AL office banners are often larger files than mugshots).
                score += min(fsz // 20000, 3)
                score += _aspect_score(local)
                candidates.append((score, fsz, abs_u, local))

            # Rewrite to relative path next to the HTML file
            local_name = Path(local).name
            rel = f"{assets_rel_name}/{local_name}"
            if getattr(el, "name", "") == "img":
                el["src"] = rel
                if el.get("data-src"):
                    el["data-src"] = rel
                if el.get("srcset"):
                    el["srcset"] = rel
            elif getattr(el, "name", "") == "meta":
                el["content"] = rel

        if candidates:
            # Prefer high score, then larger file; never pick non-mugshot chrome
            try:
                from scraper.mugshot_ethnicity.photo_quality import is_non_mugshot
            except Exception:
                is_non_mugshot = lambda _p: False  # type: ignore
            candidates.sort(key=lambda t: (t[0], t[1]), reverse=True)
            for best in candidates:
                local_p = best[3]
                try:
                    if is_non_mugshot(local_p):
                        continue
                except Exception:
                    pass
                # Only treat as primary mugshot if large enough; otherwise leave
                # photo_path for _ensure_photo to fill from NSOPW imageUri.
                if best[1] >= self.MIN_PRIMARY_PHOTO_BYTES or best[0] >= 20:
                    primary = local_p
                    break
                if best[1] >= 500:
                    primary = local_p
                    break

        try:
            out = str(soup)
        except Exception:
            out = html
        return out, primary


