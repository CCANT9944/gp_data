from __future__ import annotations

from pathlib import Path
from typing import Mapping

from .settings_defaults import (
    DEFAULT_COLUMN_ORDER,
    DEFAULT_COLUMN_WIDTHS,
    DEFAULT_LABELS,
    DEFAULT_VISIBLE_COLUMNS,
    MAX_RECENT_CSV_PREVIEW_PATHS,
)
from .settings_types import AppSettings, CsvPreviewPathState


def _default_settings() -> dict:
    return {
        "labels": DEFAULT_LABELS.copy(),
        "column_order": DEFAULT_COLUMN_ORDER.copy(),
        "column_widths": dict(DEFAULT_COLUMN_WIDTHS),
        "visible_columns": DEFAULT_VISIBLE_COLUMNS.copy(),
        "gp_highlight_threshold": None,
        "csv_preview_last_path": None,
        "csv_preview_recent_paths": [],
        "csv_preview_visible_columns_by_path": {},
        "csv_preview_visible_column_keys_by_path": {},
        "csv_preview_sort_by_path": {},
    }


def _default_app_settings() -> AppSettings:
    return AppSettings(
        labels=DEFAULT_LABELS.copy(),
        column_order=DEFAULT_COLUMN_ORDER.copy(),
        column_widths=dict(DEFAULT_COLUMN_WIDTHS),
        visible_columns=DEFAULT_VISIBLE_COLUMNS.copy(),
        gp_highlight_threshold=None,
        csv_preview_last_path=None,
        csv_preview_recent_paths=[],
        csv_preview_state_by_path={},
        csv_preview_visible_columns_by_path={},
        csv_preview_visible_column_keys_by_path={},
        csv_preview_sort_by_path={},
    )


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _normalized_labels(raw_labels) -> list[str]:
    labels = raw_labels if isinstance(raw_labels, list) else DEFAULT_LABELS
    labels = [str(x) for x in labels]
    if len(labels) < len(DEFAULT_LABELS):
        labels = labels + DEFAULT_LABELS[len(labels):]
    return labels[: len(DEFAULT_LABELS)]


def _normalized_column_order(raw_order) -> list[str]:
    default_set = set(DEFAULT_COLUMN_ORDER)
    seen: set[str] = set()
    ordered: list[str] = []

    if isinstance(raw_order, list):
        for item in raw_order:
            value = str(item)
            if value in default_set and value not in seen:
                ordered.append(value)
                seen.add(value)

    for item in DEFAULT_COLUMN_ORDER:
        if item not in seen:
            ordered.append(item)
    return ordered


def _normalized_column_widths(raw_widths) -> dict[str, int]:
    widths = dict(DEFAULT_COLUMN_WIDTHS)
    if not isinstance(raw_widths, dict):
        return widths
    for key, value in raw_widths.items():
        name = str(key)
        if name not in widths:
            continue
        try:
            width = int(value)
        except (TypeError, ValueError):
            continue
        if width < 24:
            continue
        widths[name] = width
    return widths


def _normalized_visible_columns(raw_visible) -> list[str]:
    if not isinstance(raw_visible, list):
        return DEFAULT_VISIBLE_COLUMNS.copy()

    allowed = set(DEFAULT_COLUMN_ORDER)
    seen: set[str] = set()
    visible: list[str] = []
    for item in raw_visible:
        value = str(item)
        if value in allowed and value not in seen:
            visible.append(value)
            seen.add(value)

    return visible or DEFAULT_VISIBLE_COLUMNS.copy()


def _normalized_gp_highlight_threshold(raw_threshold) -> float | None:
    if raw_threshold is None or raw_threshold == "":
        return None
    try:
        threshold = float(raw_threshold)
    except (TypeError, ValueError):
        return None
    if threshold < 0 or threshold > 100:
        return None
    return threshold


def _normalized_csv_preview_last_path(raw_path) -> str | None:
    if raw_path is None:
        return None
    text = str(raw_path).strip()
    return text or None


def _normalized_csv_preview_recent_paths(raw_paths, last_path: str | None = None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()

    def _append_path(raw_path) -> None:
        path = _normalized_csv_preview_last_path(raw_path)
        if path is None or path in seen:
            return
        normalized.append(path)
        seen.add(path)

    _append_path(last_path)
    if isinstance(raw_paths, list):
        for raw_path in raw_paths:
            _append_path(raw_path)

    return normalized[:MAX_RECENT_CSV_PREVIEW_PATHS]


def _normalized_csv_preview_visible_columns(raw_visible_columns) -> dict[str, list[int]]:
    normalized: dict[str, list[int]] = {}
    if not isinstance(raw_visible_columns, dict):
        return normalized

    for raw_path, raw_columns in raw_visible_columns.items():
        path = _normalized_csv_preview_last_path(raw_path)
        if path is None or not isinstance(raw_columns, list):
            continue

        seen: set[int] = set()
        columns: list[int] = []
        for raw_index in raw_columns:
            try:
                index = int(raw_index)
            except (TypeError, ValueError):
                continue
            if index < 0 or index in seen:
                continue
            columns.append(index)
            seen.add(index)

        if columns:
            normalized[path] = columns

    return normalized


def _normalized_csv_preview_visible_column_keys(raw_visible_column_keys) -> dict[str, list[str]]:
    normalized: dict[str, list[str]] = {}
    if not isinstance(raw_visible_column_keys, dict):
        return normalized

    for raw_path, raw_keys in raw_visible_column_keys.items():
        path = _normalized_csv_preview_last_path(raw_path)
        if path is None or not isinstance(raw_keys, list):
            continue

        seen: set[str] = set()
        keys: list[str] = []
        for raw_key in raw_keys:
            key = str(raw_key).strip().casefold()
            if not key or key in seen:
                continue
            keys.append(key)
            seen.add(key)

        if keys:
            normalized[path] = keys

    return normalized


def _normalized_csv_preview_sort_by_path(raw_sort_by_path) -> dict[str, dict[str, object]]:
    normalized: dict[str, dict[str, object]] = {}
    if not isinstance(raw_sort_by_path, dict):
        return normalized

    for raw_path, raw_sort in raw_sort_by_path.items():
        path = _normalized_csv_preview_last_path(raw_path)
        if path is None or not isinstance(raw_sort, dict):
            continue

        column_key = str(raw_sort.get("column_key", "")).strip().casefold()
        if not column_key:
            continue

        normalized[path] = {
            "column_key": column_key,
            "descending": bool(raw_sort.get("descending", False)),
        }

    return normalized


def _normalized_csv_preview_state_by_path(raw_state_by_path) -> dict[str, CsvPreviewPathState]:
    normalized: dict[str, CsvPreviewPathState] = {}
    if not isinstance(raw_state_by_path, dict):
        return normalized

    for raw_path, raw_state in raw_state_by_path.items():
        path = _normalized_csv_preview_last_path(raw_path)
        if path is None or not isinstance(raw_state, dict):
            continue

        visible_columns = _normalized_csv_preview_visible_columns({path: raw_state.get("visible_columns")}).get(path, [])
        visible_column_keys = _normalized_csv_preview_visible_column_keys({path: raw_state.get("visible_column_keys")}).get(path, [])
        sort = _normalized_csv_preview_sort_by_path({path: raw_state.get("sort")}).get(path, {})
        has_header_row = raw_state.get("has_header_row") if isinstance(raw_state.get("has_header_row"), bool) else None

        normalized[path] = CsvPreviewPathState(
            visible_columns=visible_columns,
            visible_column_keys=visible_column_keys,
            sort_column_key=str(sort.get("column_key")).strip().casefold() if sort.get("column_key") else None,
            sort_descending=bool(sort.get("descending", False)),
            has_header_row=has_header_row,
        )

    return normalized


def _normalized_app_settings(raw_data: Mapping[str, object] | None) -> AppSettings:
    data = raw_data if isinstance(raw_data, Mapping) else {}
    csv_preview_last_path = _normalized_csv_preview_last_path(data.get("csv_preview_last_path"))
    csv_preview_recent_paths = _normalized_csv_preview_recent_paths(data.get("csv_preview_recent_paths"), csv_preview_last_path)
    if csv_preview_last_path is None and csv_preview_recent_paths:
        csv_preview_last_path = csv_preview_recent_paths[0]
    csv_preview_state_by_path = _normalized_csv_preview_state_by_path(data.get("csv_preview_state_by_path"))
    csv_preview_visible_columns_by_path = _normalized_csv_preview_visible_columns(data.get("csv_preview_visible_columns_by_path"))
    csv_preview_visible_column_keys_by_path = _normalized_csv_preview_visible_column_keys(data.get("csv_preview_visible_column_keys_by_path"))
    csv_preview_sort_by_path = _normalized_csv_preview_sort_by_path(data.get("csv_preview_sort_by_path"))

    for path, state in list(csv_preview_state_by_path.items()):
        if state.visible_columns:
            csv_preview_visible_columns_by_path[path] = list(state.visible_columns)
        if state.visible_column_keys:
            csv_preview_visible_column_keys_by_path[path] = list(state.visible_column_keys)
        if state.sort_column_key:
            csv_preview_sort_by_path[path] = {
                "column_key": state.sort_column_key,
                "descending": state.sort_descending,
            }

    for path in set(csv_preview_visible_columns_by_path) | set(csv_preview_visible_column_keys_by_path) | set(csv_preview_sort_by_path):
        current_state = csv_preview_state_by_path.get(path, CsvPreviewPathState())
        csv_preview_state_by_path[path] = CsvPreviewPathState(
            visible_columns=csv_preview_visible_columns_by_path.get(path, current_state.visible_columns),
            visible_column_keys=csv_preview_visible_column_keys_by_path.get(path, current_state.visible_column_keys),
            sort_column_key=(csv_preview_sort_by_path.get(path) or {}).get("column_key", current_state.sort_column_key),
            sort_descending=bool((csv_preview_sort_by_path.get(path) or {}).get("descending", current_state.sort_descending)),
            has_header_row=current_state.has_header_row,
        )

    return AppSettings(
        labels=_normalized_labels(data.get("labels", DEFAULT_LABELS)),
        column_order=_normalized_column_order(data.get("column_order", DEFAULT_COLUMN_ORDER)),
        column_widths=_normalized_column_widths(data.get("column_widths", DEFAULT_COLUMN_WIDTHS)),
        visible_columns=_normalized_visible_columns(data.get("visible_columns", DEFAULT_VISIBLE_COLUMNS)),
        gp_highlight_threshold=_normalized_gp_highlight_threshold(data.get("gp_highlight_threshold")),
        csv_preview_last_path=csv_preview_last_path,
        csv_preview_recent_paths=csv_preview_recent_paths,
        csv_preview_state_by_path=csv_preview_state_by_path,
        csv_preview_visible_columns_by_path=csv_preview_visible_columns_by_path,
        csv_preview_visible_column_keys_by_path=csv_preview_visible_column_keys_by_path,
        csv_preview_sort_by_path=csv_preview_sort_by_path,
    )