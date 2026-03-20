from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CsvPreviewPathState:
    visible_columns: list[int] = None  # type: ignore[assignment]
    visible_column_keys: list[str] = None  # type: ignore[assignment]
    sort_column_key: str | None = None
    sort_descending: bool = False
    has_header_row: bool | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "visible_columns", list(self.visible_columns or []))
        object.__setattr__(self, "visible_column_keys", list(self.visible_column_keys or []))

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {}
        if self.visible_columns:
            data["visible_columns"] = list(self.visible_columns)
        if self.visible_column_keys:
            data["visible_column_keys"] = list(self.visible_column_keys)
        if self.sort_column_key:
            data["sort"] = {
                "column_key": self.sort_column_key,
                "descending": self.sort_descending,
            }
        if self.has_header_row is not None:
            data["has_header_row"] = self.has_header_row
        return data


@dataclass(frozen=True)
class AppSettings:
    labels: list[str]
    column_order: list[str]
    column_widths: dict[str, int]
    visible_columns: list[str]
    gp_highlight_threshold: float | None
    csv_preview_last_path: str | None
    csv_preview_recent_paths: list[str]
    csv_preview_state_by_path: dict[str, CsvPreviewPathState]
    csv_preview_visible_columns_by_path: dict[str, list[int]]
    csv_preview_visible_column_keys_by_path: dict[str, list[str]]
    csv_preview_sort_by_path: dict[str, dict[str, object]]

    def to_dict(self) -> dict:
        return {
            "labels": list(self.labels),
            "column_order": list(self.column_order),
            "column_widths": dict(self.column_widths),
            "visible_columns": list(self.visible_columns),
            "gp_highlight_threshold": self.gp_highlight_threshold,
            "csv_preview_last_path": self.csv_preview_last_path,
            "csv_preview_recent_paths": list(self.csv_preview_recent_paths),
            "csv_preview_state_by_path": {
                path: state.to_dict() for path, state in self.csv_preview_state_by_path.items()
            },
            "csv_preview_visible_columns_by_path": {
                path: list(columns) for path, columns in self.csv_preview_visible_columns_by_path.items()
            },
            "csv_preview_visible_column_keys_by_path": {
                path: list(keys) for path, keys in self.csv_preview_visible_column_keys_by_path.items()
            },
            "csv_preview_sort_by_path": {
                path: {"column_key": str(sort_state["column_key"]), "descending": bool(sort_state["descending"])}
                for path, sort_state in self.csv_preview_sort_by_path.items()
            },
        }