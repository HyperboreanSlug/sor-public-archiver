"""Compose a shareable offender mugshot card and save it to the Desktop."""
from __future__ import annotations

from gui_app.shared.export_card_fields import (
    os_environ_get,
    person_name as _person_name,
    desktop_dir as _desktop_dir,
    safe_filename as _safe_filename,
    load_font as _load_font,
    location as _location,
    crime as _crime,
    arrest_datetime as _arrest_datetime,
)
from gui_app.shared.export_card_photo import (
    resolve_photo_path as _resolve_photo_path,
    load_mugshot as _load_mugshot,
    is_backdrop as _is_backdrop,
    is_rope_gold as _is_rope_gold,
    prepared_seal as _prepared_seal,
    load_seal as _load_seal,
    with_opacity as _with_opacity,
    wrap_text as _wrap_text,
    draw_seal_watermark as _draw_seal_watermark,
)
from gui_app.shared.export_card_render import (
    render_export_card,
    export_record_card_to_desktop,
)

__all__ = [
    "render_export_card",
    "export_record_card_to_desktop",
    "os_environ_get",
    "_person_name",
    "_desktop_dir",
    "_safe_filename",
    "_load_font",
    "_location",
    "_crime",
    "_arrest_datetime",
    "_resolve_photo_path",
    "_load_mugshot",
    "_is_backdrop",
    "_is_rope_gold",
    "_prepared_seal",
    "_load_seal",
    "_with_opacity",
    "_wrap_text",
    "_draw_seal_watermark",
]
