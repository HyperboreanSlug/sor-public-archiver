"""Build RecordSidebar widget tree (layout only)."""
from __future__ import annotations

from typing import Any

import customtkinter as ctk

from gui_app.theme import C, FONT_BOLD, FONT_SM

ACTUAL_RACE_OPTIONS = [
    "Hispanic",
    "Indian",
    "Asian",
    "African American",
    "Black",
    "White",
    "Arabic",
    "European",
    "Jewish",
    "Portuguese",
    "Native American",
    "Other",
    "Unknown",
]

_DETAIL_KEYS = (
    ("Name", ("full_name", "name")),
    ("Crime", ("crime", "offense_description", "offense_type")),
    ("Race", ("race",)),
    ("Likely ethnicity", ("likely_ethnicity",)),
    ("Confidence", ("confidence", "name_confidence")),
    ("Sex", ("sex", "gender")),
    ("Age", ("age",)),
    ("DOB", ("date_of_birth",)),
    ("State", ("state", "source_state")),
    ("County", ("county",)),
    ("City", ("city",)),
    ("Risk", ("risk_level",)),
    ("Registered", ("registration_date",)),
    ("Convicted", ("conviction_date",)),
    ("Height", ("height",)),
    ("Weight", ("weight",)),
    ("Hair", ("hair_color", "hair")),
    ("Eyes", ("eye_color", "eyes")),
    ("Source URL", ("source_url",)),
    ("Report HTML", ("report_html_path", "html_path")),
    ("Photo path", ("photo_path",)),
)


def first_field(record: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return str(value)
    return "—"


def build_sidebar_widgets(sidebar: Any, parent: Any, photo_size: tuple[int, int]) -> None:
    """Attach widget attributes onto *sidebar* (RecordSidebar instance)."""
    sidebar.frame = ctk.CTkFrame(parent, fg_color=C["panel"], width=380, corner_radius=10)
    sidebar.frame.grid_propagate(False)
    sidebar.frame.grid_columnconfigure(0, weight=1)

    ctk.CTkLabel(
        sidebar.frame, text="Details", font=FONT_BOLD, text_color=C["text"]
    ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 2))

    sidebar.photo = ctk.CTkLabel(
        sidebar.frame,
        text="Select a record",
        text_color=C["muted"],
        width=photo_size[0],
        height=photo_size[1],
        fg_color=C["elevated"],
        corner_radius=8,
    )
    sidebar.photo.grid(row=1, column=0, padx=10, pady=(2, 6), sticky="nsew")

    btn_row = ctk.CTkFrame(sidebar.frame, fg_color="transparent")
    btn_row.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 4))
    btn_row.grid_columnconfigure((0, 1), weight=1)
    sidebar.open_btn = ctk.CTkButton(
        btn_row, text="Open source URL", command=sidebar._open_source,
        state="disabled", height=30,
    )
    sidebar.open_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4))
    sidebar.open_photo_btn = ctk.CTkButton(
        btn_row, text="Open photo", command=sidebar._open_photo_file,
        state="disabled", height=30,
    )
    sidebar.open_photo_btn.grid(row=0, column=1, sticky="ew", padx=(4, 0))

    sidebar.export_btn = ctk.CTkButton(
        sidebar.frame, text="Export card to Desktop", command=sidebar._export_card,
        state="disabled", height=30, fg_color=C["accent_dim"],
        hover_color=C["accent"], text_color=C["text"],
    )
    sidebar.export_btn.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 4))

    verdict_row = ctk.CTkFrame(sidebar.frame, fg_color="transparent")
    verdict_row.grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 4))
    verdict_row.grid_columnconfigure((0, 1), weight=1)
    sidebar.correct_btn = ctk.CTkButton(
        verdict_row, text="Classified correctly", fg_color=C["success"],
        hover_color="#68b888", text_color="#0c0c0e",
        command=lambda: sidebar._emit_verdict("correct"), state="disabled", height=30,
    )
    sidebar.correct_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4))
    sidebar.incorrect_btn = ctk.CTkButton(
        verdict_row, text="Classified incorrectly", fg_color=C["danger"],
        hover_color="#c96a6a", text_color="#0c0c0e",
        command=lambda: sidebar._emit_verdict("incorrect"), state="disabled", height=30,
    )
    sidebar.incorrect_btn.grid(row=0, column=1, sticky="ew", padx=(4, 0))

    sidebar.race_banner = ctk.CTkLabel(
        sidebar.frame, text="Marked race: —", font=FONT_BOLD, text_color=C["text"],
        fg_color=C["accent_dim"], corner_radius=8, height=40, anchor="center",
    )
    sidebar.race_banner.grid(row=5, column=0, sticky="ew", padx=12, pady=(2, 4))

    sidebar.verdict_status = ctk.CTkLabel(
        sidebar.frame, text="", font=FONT_SM, text_color=C["muted"], anchor="w"
    )
    sidebar.verdict_status.grid(row=6, column=0, sticky="ew", padx=12, pady=(0, 2))

    actual_row = ctk.CTkFrame(sidebar.frame, fg_color="transparent")
    actual_row.grid(row=7, column=0, sticky="ew", padx=12, pady=(0, 4))
    actual_row.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(
        actual_row, text="Actual race", font=FONT_SM, text_color=C["muted"]
    ).grid(row=0, column=0, sticky="w")
    sidebar.actual_race = ctk.CTkComboBox(
        actual_row, values=list(ACTUAL_RACE_OPTIONS),
        command=sidebar._emit_actual_race, state="disabled",
    )
    sidebar.actual_race.set("Unknown")
    sidebar.actual_race.grid(row=0, column=1, sticky="ew", padx=(8, 0))

    sidebar.details = ctk.CTkTextbox(
        sidebar.frame, fg_color=C["bg"], text_color=C["text"], font=FONT_SM,
        wrap="word", activate_scrollbars=True, height=140,
    )
    sidebar.details.grid(row=8, column=0, sticky="nsew", padx=12, pady=(0, 10))
    sidebar.details.insert("end", "Select a row to preview mugshot and booking fields.")
    sidebar.details.configure(state="disabled")

    sidebar.frame.grid_rowconfigure(1, weight=3)
    sidebar.frame.grid_rowconfigure(8, weight=2)
