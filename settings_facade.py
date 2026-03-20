from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from .settings_types import CsvPreviewPathState


def build_settings_api(store_factory: Callable[[Optional[Path]], Any]) -> dict[str, Callable[..., object]]:
    def _store(path: Optional[Path]) -> Any:
        return store_factory(path)

    def _make_loader(method_name: str) -> Callable[[Optional[Path]], object]:
        def loader(path: Optional[Path] = None) -> object:
            return getattr(_store(path), method_name)()

        return loader

    def _make_saver(method_name: str) -> Callable[[object, Optional[Path]], None]:
        def saver(value: object, path: Optional[Path] = None) -> None:
            getattr(_store(path), method_name)(value)

        return saver

    def _make_csv_preview_loader(method_name: str) -> Callable[[str | None, Optional[Path]], object]:
        def loader(csv_preview_path: str | None, path: Optional[Path] = None) -> object:
            return getattr(_store(path), method_name)(csv_preview_path)

        return loader

    def _make_csv_preview_saver(method_name: str) -> Callable[[str | None, object, Optional[Path]], None]:
        def saver(csv_preview_path: str | None, value: object, path: Optional[Path] = None) -> None:
            getattr(_store(path), method_name)(csv_preview_path, value)

        return saver

    def load_settings(path: Optional[Path] = None) -> dict:
        return _store(path).load().to_dict()

    def save_settings(data: dict, path: Optional[Path] = None) -> None:
        _store(path).save(data)

    def save_csv_preview_sort(
        csv_preview_path: str | None,
        column_key: str | None,
        *,
        descending: bool = False,
        path: Optional[Path] = None,
    ) -> None:
        _store(path).save_csv_preview_sort(csv_preview_path, column_key, descending=descending)

    load_labels = _make_loader("load_labels")
    save_labels = _make_saver("save_labels")
    load_column_order = _make_loader("load_column_order")
    save_column_order = _make_saver("save_column_order")
    load_column_widths = _make_loader("load_column_widths")
    save_column_widths = _make_saver("save_column_widths")
    load_visible_columns = _make_loader("load_visible_columns")
    save_visible_columns = _make_saver("save_visible_columns")
    load_gp_highlight_threshold = _make_loader("load_gp_highlight_threshold")
    save_gp_highlight_threshold = _make_saver("save_gp_highlight_threshold")
    load_csv_preview_last_path = _make_loader("load_csv_preview_last_path")
    save_csv_preview_last_path = _make_saver("save_csv_preview_last_path")
    load_csv_preview_recent_paths = _make_loader("load_csv_preview_recent_paths")
    save_csv_preview_recent_paths = _make_saver("save_csv_preview_recent_paths")
    load_csv_preview_visible_columns = _make_csv_preview_loader("load_csv_preview_visible_columns")
    save_csv_preview_visible_columns = _make_csv_preview_saver("save_csv_preview_visible_columns")
    load_csv_preview_visible_column_keys = _make_csv_preview_loader("load_csv_preview_visible_column_keys")
    save_csv_preview_visible_column_keys = _make_csv_preview_saver("save_csv_preview_visible_column_keys")
    load_csv_preview_sort = _make_csv_preview_loader("load_csv_preview_sort")
    load_csv_preview_state = _make_csv_preview_loader("load_csv_preview_state")
    save_csv_preview_state = _make_csv_preview_saver("save_csv_preview_state")
    load_csv_preview_has_header_row = _make_csv_preview_loader("load_csv_preview_has_header_row")
    save_csv_preview_has_header_row = _make_csv_preview_saver("save_csv_preview_has_header_row")

    return {
        "load_settings": load_settings,
        "save_settings": save_settings,
        "load_labels": load_labels,
        "save_labels": save_labels,
        "load_column_order": load_column_order,
        "save_column_order": save_column_order,
        "load_column_widths": load_column_widths,
        "save_column_widths": save_column_widths,
        "load_visible_columns": load_visible_columns,
        "save_visible_columns": save_visible_columns,
        "load_gp_highlight_threshold": load_gp_highlight_threshold,
        "save_gp_highlight_threshold": save_gp_highlight_threshold,
        "load_csv_preview_last_path": load_csv_preview_last_path,
        "save_csv_preview_last_path": save_csv_preview_last_path,
        "load_csv_preview_recent_paths": load_csv_preview_recent_paths,
        "save_csv_preview_recent_paths": save_csv_preview_recent_paths,
        "load_csv_preview_visible_columns": load_csv_preview_visible_columns,
        "save_csv_preview_visible_columns": save_csv_preview_visible_columns,
        "load_csv_preview_visible_column_keys": load_csv_preview_visible_column_keys,
        "save_csv_preview_visible_column_keys": save_csv_preview_visible_column_keys,
        "load_csv_preview_sort": load_csv_preview_sort,
        "load_csv_preview_state": load_csv_preview_state,
        "save_csv_preview_state": save_csv_preview_state,
        "load_csv_preview_has_header_row": load_csv_preview_has_header_row,
        "save_csv_preview_has_header_row": save_csv_preview_has_header_row,
        "save_csv_preview_sort": save_csv_preview_sort,
    }