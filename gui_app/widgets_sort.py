"""Tree column sort and iid↔record mapping helpers."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from tkinter import ttk

from gui_app.widgets_tree import tree_cell_sort_key


def enable_tree_column_sort(
    tree: ttk.Treeview,
    columns: List[str],
    labels: Optional[Dict[str, str]] = None,
) -> None:
    labels = labels or {c: c.upper() for c in columns}
    state: Dict[str, Any] = {"col": None, "reverse": False}

    def apply_sort(col: str, reverse: bool, update_headings: bool = True) -> None:
        rows = [(tree.set(iid, col), iid) for iid in tree.get_children("")]
        rows.sort(key=lambda t: tree_cell_sort_key(t[0]), reverse=reverse)
        for idx, (_val, iid) in enumerate(rows):
            tree.move(iid, "", idx)
        state["col"] = col
        state["reverse"] = reverse
        tree._sort_state = state  # type: ignore[attr-defined]
        if update_headings:
            for c in columns:
                base = labels.get(c, c.upper())
                if c == col:
                    arrow = " ▼" if reverse else " ▲"
                    tree.heading(c, text=base + arrow, command=lambda cc=c: on_heading(cc))
                else:
                    tree.heading(c, text=base, command=lambda cc=c: on_heading(cc))

    def on_heading(col: str) -> None:
        reverse = state["col"] == col and not state["reverse"]
        apply_sort(col, reverse)

    def reapply() -> None:
        col = state.get("col")
        if col:
            apply_sort(col, bool(state.get("reverse")), update_headings=False)

    tree._sort_state = state  # type: ignore[attr-defined]
    tree._reapply_sort = reapply  # type: ignore[attr-defined]
    for c in columns:
        tree.heading(c, text=labels.get(c, c.upper()), command=lambda cc=c: on_heading(cc))


def tree_rows_reset(tree: ttk.Treeview) -> None:
    tree._rec_by_iid = {}  # type: ignore[attr-defined]


def tree_row_bind(tree: ttk.Treeview, iid: str, record: Any) -> str:
    mapping = getattr(tree, "_rec_by_iid", None)
    if mapping is None:
        mapping = {}
        tree._rec_by_iid = mapping  # type: ignore[attr-defined]
    mapping[iid] = record
    return iid


def tree_row_record(tree: ttk.Treeview, iid: str) -> Optional[Any]:
    return getattr(tree, "_rec_by_iid", {}).get(iid)


def tree_selected_record(tree: ttk.Treeview) -> Optional[Any]:
    sel = tree.selection()
    if not sel:
        return None
    return tree_row_record(tree, sel[0])


def tree_row_forget(tree: ttk.Treeview, iid: str) -> None:
    getattr(tree, "_rec_by_iid", {}).pop(iid, None)


def tree_iid_for_record(tree: ttk.Treeview, record: Any) -> Optional[str]:
    mapping = getattr(tree, "_rec_by_iid", {})
    rid = record.get("id") if hasattr(record, "get") else None
    url = str(record.get("source_url") or "") if hasattr(record, "get") else ""
    for iid, rec in mapping.items():
        if rec is record:
            return iid
        if rid is not None and hasattr(rec, "get") and rec.get("id") == rid:
            return iid
        if url and hasattr(rec, "get") and str(rec.get("source_url") or "") == url:
            return iid
    return None
