from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk

from .loader import CsvPreviewData, load_csv_preview


MIN_PREVIEW_WIDTH = 800
MIN_PREVIEW_HEIGHT = 420
DEFAULT_COLUMN_WIDTH = 140
MAX_COLUMN_WIDTH = 320
MIN_COLUMN_WIDTH = 80
ROW_INSERT_CHUNK_SIZE = 250


def _column_width(header: str) -> int:
    estimated = max(MIN_COLUMN_WIDTH, min(MAX_COLUMN_WIDTH, (len(header) * 10) + 24))
    return max(DEFAULT_COLUMN_WIDTH, estimated)


def _build_tree(parent: tk.Misc, data: CsvPreviewData) -> ttk.Treeview:
    column_ids = [f"col_{index}" for index in range(data.column_count)]
    tree = ttk.Treeview(parent, columns=column_ids, show="headings")
    for column_id, header in zip(column_ids, data.headers):
        tree.heading(column_id, text=header)
        tree.column(column_id, width=_column_width(header), minwidth=MIN_COLUMN_WIDTH, stretch=False, anchor="w")
    return tree


def _summary_text(data: CsvPreviewData, *, loaded_rows: int | None = None) -> str:
    if loaded_rows is None or loaded_rows >= data.row_count:
        return f"{data.path.name} | {data.row_count} rows | {data.column_count} columns | {data.encoding}"
    return f"{data.path.name} | Loading {loaded_rows}/{data.row_count} rows | {data.column_count} columns | {data.encoding}"


def _populate_rows_in_chunks(
    win: tk.Toplevel,
    tree: ttk.Treeview,
    data: CsvPreviewData,
    summary_var: tk.StringVar,
    start_index: int = 0,
) -> None:
    if not win.winfo_exists() or not tree.winfo_exists():
        return

    end_index = min(start_index + ROW_INSERT_CHUNK_SIZE, data.row_count)
    for row in data.rows[start_index:end_index]:
        tree.insert("", "end", values=row)

    summary_var.set(_summary_text(data, loaded_rows=end_index))
    if end_index < data.row_count:
        win.after_idle(_populate_rows_in_chunks, win, tree, data, summary_var, end_index)


def create_csv_preview_dialog(
    parent: tk.Misc,
    data: CsvPreviewData,
    *,
    width: int,
    height: int,
) -> tk.Toplevel:
    win = tk.Toplevel(parent)
    win.title(f"CSV Preview - {data.path.name}")
    win.geometry(f"{max(width, MIN_PREVIEW_WIDTH)}x{max(height, MIN_PREVIEW_HEIGHT)}")

    container = ttk.Frame(win)
    container.pack(fill="both", expand=True, padx=8, pady=8)
    container.columnconfigure(0, weight=1)
    container.rowconfigure(1, weight=1)

    summary_var = tk.StringVar(value=_summary_text(data, loaded_rows=0 if data.row_count else None))
    summary = ttk.Label(
        container,
        textvariable=summary_var,
        anchor="w",
    )
    summary.grid(row=0, column=0, sticky="ew", pady=(0, 6))

    table_frame = ttk.Frame(container)
    table_frame.grid(row=1, column=0, sticky="nsew")
    table_frame.columnconfigure(0, weight=1)
    table_frame.rowconfigure(0, weight=1)

    tree = _build_tree(table_frame, data)
    y_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
    x_scroll = ttk.Scrollbar(table_frame, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

    tree.grid(row=0, column=0, sticky="nsew")
    y_scroll.grid(row=0, column=1, sticky="ns")
    x_scroll.grid(row=1, column=0, sticky="ew")

    button_row = ttk.Frame(container)
    button_row.grid(row=2, column=0, sticky="ew", pady=(8, 0))
    ttk.Button(button_row, text="Close", command=win.destroy).pack(side="right")

    if data.row_count:
        win.after_idle(_populate_rows_in_chunks, win, tree, data, summary_var)

    return win


def open_csv_preview_dialog(
    parent: tk.Misc,
    csv_path: str | Path,
    *,
    width: int,
    height: int,
) -> tk.Toplevel:
    data = load_csv_preview(csv_path)
    return create_csv_preview_dialog(parent, data, width=width, height=height)