from __future__ import annotations

from .formulas import DEFAULT_FORMULA_EXPRESSIONS

MAX_RECENT_CSV_PREVIEW_PATHS = 8

DEFAULT_LABELS = ["Field 1", "Field 2", "Field 3", "Field 4", "Field 5", "Field 6", "Field 7"]
DEFAULT_COLUMN_ORDER = [
    "field1",
    "field2",
    "field3",
    "field4",
    "field5",
    "field6",
    "field7",
    "gp",
    "cash_margin",
    "gp70",
]
DEFAULT_COLUMN_WIDTHS = {
    "field1": 140,
    "field2": 140,
    "field3": 80,
    "field4": 80,
    "field5": 80,
    "field6": 80,
    "field7": 80,
    "gp": 80,
    "cash_margin": 80,
    "gp70": 80,
}
DEFAULT_VISIBLE_COLUMNS = DEFAULT_COLUMN_ORDER.copy()
DEFAULT_SETTINGS = {
    "labels": DEFAULT_LABELS,
    "column_order": DEFAULT_COLUMN_ORDER,
    "column_widths": DEFAULT_COLUMN_WIDTHS,
    "visible_columns": DEFAULT_VISIBLE_COLUMNS,
    "gp_highlight_threshold": None,
    "show_formula_panel": True,
    "formula_expressions": dict(DEFAULT_FORMULA_EXPRESSIONS),
    "csv_preview_last_path": None,
    "csv_preview_recent_paths": [],
    "csv_preview_visible_columns_by_path": {},
    "csv_preview_visible_column_keys_by_path": {},
    "csv_preview_sort_by_path": {},
}