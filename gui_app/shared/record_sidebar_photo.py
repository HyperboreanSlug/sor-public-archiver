"""Photo path resolve and async load for RecordSidebar."""
from __future__ import annotations

import io
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

import customtkinter as ctk
import requests

from scraper.config import USER_AGENT


def resolve_photo_path(raw: Any) -> Optional[Path]:
    text = str(raw or "").strip()
    if not text:
        return None
    path = Path(text)
    if path.is_file():
        return path
    alt = Path.cwd() / path
    if alt.is_file():
        return alt
    return path if path.exists() else None


def fit_image_to_box(img: Any, box: Tuple[int, int]) -> Any:
    """Return a RGB copy of *img* that fits entirely inside *box* (contain)."""
    from PIL import Image

    max_w = max(16, int(box[0]))
    max_h = max(16, int(box[1]))
    try:
        resample = Image.Resampling.LANCZOS
    except AttributeError:
        resample = Image.LANCZOS  # type: ignore[attr-defined]
    out = img.convert("RGB").copy()
    out.thumbnail((max_w, max_h), resample)
    if out.width > max_w or out.height > max_h:
        out.thumbnail((max_w, max_h), resample)
    return out


def render_fitted_ctk_image(pil_source: Any, box: Tuple[int, int]) -> Any:
    """Fit *pil_source* into *box* and return a CTkImage (or None)."""
    if pil_source is None:
        return None
    try:
        fitted = fit_image_to_box(pil_source, box)
        size = (fitted.width, fitted.height)
        return ctk.CTkImage(light_image=fitted, dark_image=fitted, size=size)
    except Exception:
        return None


def load_sidebar_photo(
    *,
    record: Dict[str, Any],
    token: int,
    photo_size: Tuple[int, int],
    load_token_fn: Callable[[], int],
    schedule_fn: Callable[[Callable[[], None]], None],
    set_photo_fn: Callable[..., None],
    store_source_fn: Optional[Callable[[Any], None]] = None,
) -> None:
    """Background-load mugshot bytes; fit to *photo_size* and apply on UI thread."""
    path = resolve_photo_path(record.get("photo_path"))
    url = str(record.get("photo_url") or "").strip()
    box = (max(16, int(photo_size[0])), max(16, int(photo_size[1])))
    set_photo_fn(None, "Loading photo…")

    def work() -> None:
        pil_source = None
        pil_fit = None
        message = "No photo"
        try:
            from PIL import Image

            data: Optional[bytes] = None
            if path and path.is_file():
                data = path.read_bytes()
            elif url:
                resp = requests.get(
                    url,
                    timeout=25,
                    headers={
                        "User-Agent": USER_AGENT,
                        "Accept": "image/webp,image/*,*/*;q=0.8",
                        "Referer": "https://www.nsopw.gov/",
                    },
                )
                resp.raise_for_status()
                data = resp.content
            if data:
                img = Image.open(io.BytesIO(data))
                if getattr(img, "n_frames", 1) > 1:
                    img.seek(0)
                pil_source = img.convert("RGB")
                pil_fit = fit_image_to_box(pil_source, box)
            elif not url:
                message = "No photo URL"
        except Exception as exc:
            message = f"Photo unavailable ({type(exc).__name__}: {exc})"

        def apply() -> None:
            if token != load_token_fn():
                return
            if store_source_fn is not None:
                try:
                    store_source_fn(pil_source)
                except Exception:
                    pass
            if pil_fit is None:
                set_photo_fn(None, message)
                return
            try:
                size: Tuple[int, int] = (pil_fit.width, pil_fit.height)
                image = ctk.CTkImage(
                    light_image=pil_fit, dark_image=pil_fit, size=size
                )
                set_photo_fn(image)
            except Exception as exc:
                set_photo_fn(
                    None, f"Photo display failed ({type(exc).__name__})"
                )

        schedule_fn(apply)

    threading.Thread(target=work, daemon=True).start()
