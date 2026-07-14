"""Reusable GUI widgets, charts, and tree helpers."""
from __future__ import annotations

from gui_app.widgets_charts import render_bar_chart, render_pie_chart
from gui_app.widgets_sort import (
    enable_tree_column_sort,
    tree_iid_for_record,
    tree_row_bind,
    tree_row_forget,
    tree_row_record,
    tree_rows_reset,
    tree_selected_record,
)
from gui_app.widgets_tree import (
    bind_tree_scroll_isolation,
    card,
    format_race_display,
    format_state_display,
    hpaned,
    misclass_race_bucket,
    muted,
    section_label,
    stretch_columns,
    tree_cell_sort_key,
    tree_frame,
    vpaned,
    wire_wide_scroll,
)

# Underscore aliases (match original gui.py call sites; avoid shadowing locals named card)
_card = card
_section_label = section_label
_muted = muted
_tree_frame = tree_frame
_vpaned = vpaned
_hpaned = hpaned
_stretch_columns = stretch_columns
_format_state_display = format_state_display
_format_race_display = format_race_display
_render_bar_chart = render_bar_chart
_render_pie_chart = render_pie_chart
_wire_wide_scroll = wire_wide_scroll
_bind_tree_scroll_isolation = bind_tree_scroll_isolation
_misclass_race_bucket = misclass_race_bucket
_enable_tree_column_sort = enable_tree_column_sort
