"""Photo path resolve and async load for RecordSidebar."""
from __future__ import annotations

import io
import threading
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

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


def load_sidebar_photo(
    *,
    record: Dict[str, Any],
    token: int,
    photo_size: Tuple[int, int],
    load_token_fn,
    schedule_fn,
    set_photo_fn,
) -> None:
    """Background-load mugshot bytes; apply CTkImage on the UI thread."""
    path = resolve_photo_path(record.get("photo_path"))
    url = str(record.get("photo_url") or "").strip()
    set_photo_fn(None, "Loading photo…")

    def work() -> None:
        pil_rgb = None
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
                pil_rgb = img.convert("RGB")
                pil_rgb.thumbnail(photo_size)
            elif not url:
                message = "No photo URL"
        except Exception as exc:
            message = f"Photo unavailable ({type(exc).__name__}: {exc})"

        def apply() -> None:
            if token != load_token_fn():
                return
            if pil_rgb is None:
                set_photo_fn(None, message)
                return
            try:
                size: Tuple[int, int] = (pil_rgb.width, pil_rgb.height)
                image = ctk.CTkImage(
                    light_image=pil_rgb, dark_image=pil_rgb, size=size
                )
                set_photo_fn(image)
            except Exception as exc:
                set_photo_fn(
                    None, f"Photo display failed ({type(exc).__name__})"
                )

        schedule_fn(apply)

    threading.Thread(target=work, daemon=True).start()
