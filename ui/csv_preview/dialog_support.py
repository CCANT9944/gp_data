from __future__ import annotations

import csv
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Callable

from .loader import CsvPreviewData


def _column_width(
    header: str,
    *,
    default_width: int,
    min_width: int,
    max_width: int,
) -> int:
    estimated = max(min_width, min(max_width, (len(header) * 10) + 24))
    return max(default_width, estimated)


def _column_ids(data: CsvPreviewData) -> list[str]:
    return [f"col_{index}" for index in range(data.column_count)]


def _rendered_preview_row_limit(
    column_count: int,
    *,
    max_rendered_preview_rows: int,
    min_rendered_preview_rows: int,
    max_rendered_preview_cells: int,
) -> int:
    safe_column_count = max(1, column_count)
    adaptive_limit = max_rendered_preview_cells // safe_column_count
    return max(min_rendered_preview_rows, min(max_rendered_preview_rows, adaptive_limit))


def _normalized_visible_column_indices(column_count: int, visible_indices: list[int] | None) -> list[int]:
    if not visible_indices:
        return list(range(column_count))

    normalized: list[int] = []
    seen: set[int] = set()
    for raw_index in visible_indices:
        try:
            index = int(raw_index)
        except (TypeError, ValueError):
            continue
        if index < 0 or index >= column_count or index in seen:
            continue
        normalized.append(index)
        seen.add(index)
    return normalized or list(range(column_count))


def _build_tree(
    parent: tk.Misc,
    data: CsvPreviewData,
    *,
    column_ids: list[str],
    column_width_for_header: Callable[[str], int],
    min_column_width: int,
) -> ttk.Treeview:
    tree = ttk.Treeview(parent, columns=column_ids, show="headings")
    for column_id, header in zip(column_ids, data.headers):
        tree.heading(column_id, text=header)
        tree.column(column_id, width=column_width_for_header(header), minwidth=min_column_width, stretch=False, anchor="w")
    return tree


def _default_csv_preview_export_path(source_path: Path) -> Path:
    return source_path.with_name(f"{source_path.stem}.preview.csv")


def _default_csv_preview_export_directory(source_path: Path) -> Path:
    favorites_dir = Path.home() / "Favorites"
    if favorites_dir.name.casefold() == "favorites":
        return favorites_dir / "csv_exports"
    return source_path.parent / "csv_exports"


def _prepare_csv_preview_export_directory(source_path: Path) -> Path:
    export_dir = _default_csv_preview_export_directory(source_path)
    try:
        export_dir.mkdir(parents=True, exist_ok=True)
        return export_dir
    except OSError:
        return source_path.parent


def _paths_match(first: Path, second: Path) -> bool:
    return str(first.resolve(strict=False)).casefold() == str(second.resolve(strict=False)).casefold()


def _write_csv_preview_export(dest_path: Path, headers: list[str], rows, *, encoding: str) -> None:
    with dest_path.open("w", encoding=encoding, newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def _widget_descends_from(widget: tk.Misc | None, ancestor: tk.Misc | None) -> bool:
    current = widget
    while current is not None:
        if current == ancestor:
            return True
        parent_name = current.winfo_parent()
        if not parent_name:
            return False
        try:
            current = current.nametowidget(parent_name)
        except KeyError:
            return False
    return False