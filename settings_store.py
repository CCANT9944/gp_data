from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, List, Mapping, Optional

from .settings_normalization import (
    _default_app_settings,
    _ensure_parent,
    _normalized_app_settings,
    _normalized_csv_preview_last_path,
    _normalized_csv_preview_recent_paths,
)
from .settings_types import AppSettings, CsvPreviewPathState


class SettingsStore:
    def __init__(self, path: Optional[Path] = None, *, default_path: Callable[[], Path] | None = None):
        self._default_path = default_path
        self.path = Path(path) if path else self._resolve_default_path()

    def _resolve_default_path(self) -> Path:
        if self._default_path is None:
            return Path(__file__).parent / "settings.json"
        return Path(self._default_path())

    def load(self) -> AppSettings:
        if not self.path.exists():
            return _default_app_settings()
        try:
            with self.path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return _default_app_settings()
        if not isinstance(data, dict):
            return _default_app_settings()
        return _normalized_app_settings(data)

    def save(self, data: Mapping[str, object]) -> AppSettings:
        normalized = _normalized_app_settings(data)
        _ensure_parent(self.path)
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(normalized.to_dict(), f, indent=2, ensure_ascii=False)
        return normalized

    def update(self, **changes: object) -> AppSettings:
        current = self.load().to_dict()
        current.update(changes)
        return self.save(current)

    def load_labels(self) -> List[str]:
        return self.load().labels

    def save_labels(self, labels: List[str]) -> AppSettings:
        return self.update(labels=list(labels))

    def load_column_order(self) -> List[str]:
        return self.load().column_order

    def save_column_order(self, column_order: List[str]) -> AppSettings:
        return self.update(column_order=list(column_order))

    def load_column_widths(self) -> dict[str, int]:
        return self.load().column_widths

    def save_column_widths(self, column_widths: dict[str, int]) -> AppSettings:
        return self.update(column_widths=dict(column_widths))

    def load_visible_columns(self) -> List[str]:
        return self.load().visible_columns

    def save_visible_columns(self, visible_columns: List[str]) -> AppSettings:
        return self.update(visible_columns=list(visible_columns))

    def load_gp_highlight_threshold(self) -> float | None:
        return self.load().gp_highlight_threshold

    def save_gp_highlight_threshold(self, threshold: float | None) -> AppSettings:
        return self.update(gp_highlight_threshold=threshold)

    def load_show_formula_panel(self) -> bool:
        return self.load().show_formula_panel

    def save_show_formula_panel(self, show_formula_panel: bool) -> AppSettings:
        return self.update(show_formula_panel=bool(show_formula_panel))

    def load_formula_expressions(self) -> dict[str, str]:
        return dict(self.load().formula_expressions)

    def save_formula_expressions(self, formula_expressions: Mapping[str, object]) -> AppSettings:
        return self.update(formula_expressions=dict(formula_expressions))

    def load_csv_preview_last_path(self) -> str | None:
        return self.load().csv_preview_last_path

    def save_csv_preview_last_path(self, csv_preview_last_path: str | None) -> AppSettings:
        recent_paths = self.load_csv_preview_recent_paths()
        if csv_preview_last_path is None:
            recent_paths = []
        return self.update(csv_preview_last_path=csv_preview_last_path, csv_preview_recent_paths=recent_paths)

    def load_csv_preview_recent_paths(self) -> List[str]:
        return self.load().csv_preview_recent_paths

    def save_csv_preview_recent_paths(self, csv_preview_recent_paths: List[str]) -> AppSettings:
        normalized = _normalized_csv_preview_recent_paths(csv_preview_recent_paths)
        last_path = normalized[0] if normalized else None
        return self.update(csv_preview_last_path=last_path, csv_preview_recent_paths=normalized)

    def remember_csv_preview_path(self, csv_preview_path: str | None) -> AppSettings:
        normalized_path = _normalized_csv_preview_last_path(csv_preview_path)
        if normalized_path is None:
            return self.save_csv_preview_recent_paths([])
        recent_paths = _normalized_csv_preview_recent_paths(self.load_csv_preview_recent_paths(), normalized_path)
        return self.update(csv_preview_last_path=normalized_path, csv_preview_recent_paths=recent_paths)

    def load_csv_preview_state(self, csv_preview_path: str | None) -> CsvPreviewPathState | None:
        normalized_path = _normalized_csv_preview_last_path(csv_preview_path)
        if normalized_path is None:
            return None
        saved = self.load().csv_preview_state_by_path.get(normalized_path)
        return saved if saved is not None else None

    def save_csv_preview_state(self, csv_preview_path: str | None, state: CsvPreviewPathState | None) -> AppSettings:
        normalized_path = _normalized_csv_preview_last_path(csv_preview_path)
        current = {path: saved_state.to_dict() for path, saved_state in self.load().csv_preview_state_by_path.items()}
        if normalized_path is None:
            return self.update(csv_preview_state_by_path=current)
        if state is None or not state.to_dict():
            current.pop(normalized_path, None)
        else:
            current[normalized_path] = state.to_dict()
        return self.update(csv_preview_state_by_path=current)

    def load_csv_preview_visible_columns(self, csv_preview_path: str | None) -> List[int] | None:
        normalized_path = _normalized_csv_preview_last_path(csv_preview_path)
        if normalized_path is None:
            return None
        saved = self.load().csv_preview_visible_columns_by_path.get(normalized_path)
        return list(saved) if saved is not None else None

    def save_csv_preview_visible_columns(self, csv_preview_path: str | None, visible_columns: List[int] | None) -> AppSettings:
        normalized_path = _normalized_csv_preview_last_path(csv_preview_path)
        current = dict(self.load().csv_preview_visible_columns_by_path)
        current_state = self.load_csv_preview_state(normalized_path) or CsvPreviewPathState()
        current_state_by_path = {path: state.to_dict() for path, state in self.load().csv_preview_state_by_path.items()}
        if normalized_path is None:
            return self.update(csv_preview_visible_columns_by_path=current)
        if not visible_columns:
            current.pop(normalized_path, None)
            current_state = CsvPreviewPathState(
                visible_columns=[],
                visible_column_keys=current_state.visible_column_keys,
                sort_column_key=current_state.sort_column_key,
                sort_descending=current_state.sort_descending,
                has_header_row=current_state.has_header_row,
            )
        else:
            current[normalized_path] = list(visible_columns)
            current_state = CsvPreviewPathState(
                visible_columns=list(visible_columns),
                visible_column_keys=current_state.visible_column_keys,
                sort_column_key=current_state.sort_column_key,
                sort_descending=current_state.sort_descending,
                has_header_row=current_state.has_header_row,
            )
        if current_state.to_dict():
            current_state_by_path[normalized_path] = current_state.to_dict()
        else:
            current_state_by_path.pop(normalized_path, None)
        return self.update(csv_preview_visible_columns_by_path=current, csv_preview_state_by_path=current_state_by_path)

    def load_csv_preview_visible_column_keys(self, csv_preview_path: str | None) -> List[str] | None:
        normalized_path = _normalized_csv_preview_last_path(csv_preview_path)
        if normalized_path is None:
            return None
        saved = self.load().csv_preview_visible_column_keys_by_path.get(normalized_path)
        return list(saved) if saved is not None else None

    def save_csv_preview_visible_column_keys(self, csv_preview_path: str | None, visible_column_keys: List[str] | None) -> AppSettings:
        normalized_path = _normalized_csv_preview_last_path(csv_preview_path)
        current = dict(self.load().csv_preview_visible_column_keys_by_path)
        current_state = self.load_csv_preview_state(normalized_path) or CsvPreviewPathState()
        current_state_by_path = {path: state.to_dict() for path, state in self.load().csv_preview_state_by_path.items()}
        if normalized_path is None:
            return self.update(csv_preview_visible_column_keys_by_path=current)
        if not visible_column_keys:
            current.pop(normalized_path, None)
            current_state = CsvPreviewPathState(
                visible_columns=current_state.visible_columns,
                visible_column_keys=[],
                sort_column_key=current_state.sort_column_key,
                sort_descending=current_state.sort_descending,
                has_header_row=current_state.has_header_row,
            )
        else:
            normalized_keys = [str(key).strip().casefold() for key in visible_column_keys if str(key).strip()]
            current[normalized_path] = normalized_keys
            current_state = CsvPreviewPathState(
                visible_columns=current_state.visible_columns,
                visible_column_keys=normalized_keys,
                sort_column_key=current_state.sort_column_key,
                sort_descending=current_state.sort_descending,
                has_header_row=current_state.has_header_row,
            )
        if current_state.to_dict():
            current_state_by_path[normalized_path] = current_state.to_dict()
        else:
            current_state_by_path.pop(normalized_path, None)
        return self.update(csv_preview_visible_column_keys_by_path=current, csv_preview_state_by_path=current_state_by_path)

    def load_csv_preview_sort(self, csv_preview_path: str | None) -> dict[str, object] | None:
        normalized_path = _normalized_csv_preview_last_path(csv_preview_path)
        if normalized_path is None:
            return None
        saved = self.load().csv_preview_sort_by_path.get(normalized_path)
        return dict(saved) if saved is not None else None

    def save_csv_preview_sort(
        self,
        csv_preview_path: str | None,
        column_key: str | None,
        *,
        descending: bool = False,
    ) -> AppSettings:
        normalized_path = _normalized_csv_preview_last_path(csv_preview_path)
        current = dict(self.load().csv_preview_sort_by_path)
        current_state = self.load_csv_preview_state(normalized_path) or CsvPreviewPathState()
        current_state_by_path = {path: state.to_dict() for path, state in self.load().csv_preview_state_by_path.items()}
        if normalized_path is None:
            return self.update(csv_preview_sort_by_path=current)

        normalized_key = str(column_key).strip().casefold() if column_key is not None else ""
        if not normalized_key:
            current.pop(normalized_path, None)
            current_state = CsvPreviewPathState(
                visible_columns=current_state.visible_columns,
                visible_column_keys=current_state.visible_column_keys,
                sort_column_key=None,
                sort_descending=False,
                has_header_row=current_state.has_header_row,
            )
        else:
            current[normalized_path] = {"column_key": normalized_key, "descending": bool(descending)}
            current_state = CsvPreviewPathState(
                visible_columns=current_state.visible_columns,
                visible_column_keys=current_state.visible_column_keys,
                sort_column_key=normalized_key,
                sort_descending=bool(descending),
                has_header_row=current_state.has_header_row,
            )
        if current_state.to_dict():
            current_state_by_path[normalized_path] = current_state.to_dict()
        else:
            current_state_by_path.pop(normalized_path, None)
        return self.update(csv_preview_sort_by_path=current, csv_preview_state_by_path=current_state_by_path)

    def load_csv_preview_has_header_row(self, csv_preview_path: str | None) -> bool | None:
        saved_state = self.load_csv_preview_state(csv_preview_path)
        if saved_state is None:
            return None
        return saved_state.has_header_row

    def save_csv_preview_has_header_row(self, csv_preview_path: str | None, has_header_row: bool | None) -> AppSettings:
        normalized_path = _normalized_csv_preview_last_path(csv_preview_path)
        current_state_by_path = {path: state.to_dict() for path, state in self.load().csv_preview_state_by_path.items()}
        current_state = self.load_csv_preview_state(normalized_path) or CsvPreviewPathState()
        if normalized_path is None:
            return self.update(csv_preview_state_by_path=current_state_by_path)

        current_state = CsvPreviewPathState(
            visible_columns=current_state.visible_columns,
            visible_column_keys=current_state.visible_column_keys,
            sort_column_key=current_state.sort_column_key,
            sort_descending=current_state.sort_descending,
            has_header_row=None if has_header_row is None else bool(has_header_row),
        )
        if current_state.to_dict():
            current_state_by_path[normalized_path] = current_state.to_dict()
        else:
            current_state_by_path.pop(normalized_path, None)
        return self.update(csv_preview_state_by_path=current_state_by_path)

    def load_csv_import_timestamp(self, storage_path: str | None, csv_preview_path: str | None) -> str | None:
        normalized_storage_path = _normalized_csv_preview_last_path(storage_path)
        normalized_csv_path = _normalized_csv_preview_last_path(csv_preview_path)
        if normalized_storage_path is None or normalized_csv_path is None:
            return None
        return self.load().csv_import_timestamps_by_storage_path.get(normalized_storage_path, {}).get(normalized_csv_path)

    def save_csv_import_timestamp(
        self,
        storage_path: str | None,
        csv_preview_path: str | None,
        imported_at: str | None,
    ) -> AppSettings:
        normalized_storage_path = _normalized_csv_preview_last_path(storage_path)
        normalized_csv_path = _normalized_csv_preview_last_path(csv_preview_path)
        current = {
            saved_storage_path: dict(path_timestamps)
            for saved_storage_path, path_timestamps in self.load().csv_import_timestamps_by_storage_path.items()
        }
        if normalized_storage_path is None or normalized_csv_path is None:
            return self.update(csv_import_timestamps_by_storage_path=current)

        normalized_imported_at = str(imported_at).strip() if imported_at is not None else ""
        if not normalized_imported_at:
            storage_history = current.get(normalized_storage_path)
            if storage_history is not None:
                storage_history.pop(normalized_csv_path, None)
                if not storage_history:
                    current.pop(normalized_storage_path, None)
        else:
            current.setdefault(normalized_storage_path, {})[normalized_csv_path] = normalized_imported_at

        return self.update(csv_import_timestamps_by_storage_path=current)