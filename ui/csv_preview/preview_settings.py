from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from gp_data.settings import SettingsStore

from .helpers import (
    _column_identity_keys,
    _column_index_from_identity_key,
    _visible_column_indices_from_keys,
    _visible_column_keys,
)
from .loader import CsvPreviewData


@dataclass(frozen=True)
class _PreviewDialogSettingsBindings:
    initial_visible_column_indices: list[int] | None
    initial_sort_column_index: int | None
    initial_sort_descending: bool
    on_visible_columns_changed: Callable[[list[str], list[int]], None]
    on_sort_changed: Callable[[list[str], int | None, bool], None]


def build_preview_dialog_settings_bindings(
    data: CsvPreviewData,
    settings_store: SettingsStore,
    show_error,
) -> _PreviewDialogSettingsBindings:
    normalized_path = str(data.path)
    current_settings = settings_store.load()
    saved_state = current_settings.csv_preview_state_by_path.get(normalized_path)
    saved_visible_column_keys = (
        list(saved_state.visible_column_keys)
        if saved_state is not None
        else list(current_settings.csv_preview_visible_column_keys_by_path.get(normalized_path, [])) or None
    )
    initial_visible_column_indices = _visible_column_indices_from_keys(
        data.headers,
        saved_visible_column_keys,
    )
    if initial_visible_column_indices is None:
        initial_visible_column_indices = (
            list(saved_state.visible_columns)
            if saved_state is not None and saved_state.visible_columns
            else list(current_settings.csv_preview_visible_columns_by_path.get(normalized_path, [])) or None
        )

    saved_sort = (
        {"column_key": saved_state.sort_column_key, "descending": saved_state.sort_descending}
        if saved_state is not None and saved_state.sort_column_key
        else dict(current_settings.csv_preview_sort_by_path.get(normalized_path, {})) or None
    )
    initial_sort_column_index = None
    initial_sort_descending = False
    if saved_sort is not None:
        initial_sort_column_index = _column_index_from_identity_key(data.headers, saved_sort.get("column_key"))
        initial_sort_descending = bool(saved_sort.get("descending", False)) if initial_sort_column_index is not None else False

    def _save_visible_columns(headers: list[str], visible_indices: list[int]) -> None:
        try:
            settings_store.save_csv_preview_visible_column_keys(
                normalized_path,
                _visible_column_keys(headers, visible_indices),
            )
        except (OSError, TypeError, ValueError) as exc:
            show_error("CSV preview settings unavailable", f"Could not save CSV preview columns.\n\nReason: {exc}")

    def _save_sort(headers: list[str], column_index: int | None, descending: bool) -> None:
        column_key = None
        if column_index is not None and 0 <= column_index < len(headers):
            column_key = _column_identity_keys(headers)[column_index]
        try:
            settings_store.save_csv_preview_sort(normalized_path, column_key, descending=descending)
        except (OSError, TypeError, ValueError) as exc:
            show_error("CSV preview settings unavailable", f"Could not save CSV preview sort.\n\nReason: {exc}")

    return _PreviewDialogSettingsBindings(
        initial_visible_column_indices=initial_visible_column_indices,
        initial_sort_column_index=initial_sort_column_index,
        initial_sort_descending=initial_sort_descending,
        on_visible_columns_changed=_save_visible_columns,
        on_sort_changed=_save_sort,
    )