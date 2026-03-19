from __future__ import annotations
from dataclasses import dataclass
import json
from pathlib import Path
from typing import List, Mapping, Optional

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
    "csv_preview_last_path": None,
    "csv_preview_recent_paths": [],
    "csv_preview_visible_columns_by_path": {},
    "csv_preview_visible_column_keys_by_path": {},
    "csv_preview_sort_by_path": {},
}
DEFAULT_PATH = Path(__file__).parent / "settings.json"


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
    return labels[:len(DEFAULT_LABELS)]


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


class SettingsStore:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else DEFAULT_PATH

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


def load_settings(path: Optional[Path] = None) -> dict:
    return SettingsStore(path).load().to_dict()


def save_settings(data: dict, path: Optional[Path] = None) -> None:
    SettingsStore(path).save(data)


def load_labels(path: Optional[Path] = None) -> List[str]:
    return SettingsStore(path).load_labels()


def save_labels(labels: List[str], path: Optional[Path] = None) -> None:
    SettingsStore(path).save_labels(labels)


def load_column_order(path: Optional[Path] = None) -> List[str]:
    return SettingsStore(path).load_column_order()


def save_column_order(column_order: List[str], path: Optional[Path] = None) -> None:
    SettingsStore(path).save_column_order(column_order)


def load_column_widths(path: Optional[Path] = None) -> dict[str, int]:
    return SettingsStore(path).load_column_widths()


def save_column_widths(column_widths: dict[str, int], path: Optional[Path] = None) -> None:
    SettingsStore(path).save_column_widths(column_widths)


def load_visible_columns(path: Optional[Path] = None) -> List[str]:
    return SettingsStore(path).load_visible_columns()


def save_visible_columns(visible_columns: List[str], path: Optional[Path] = None) -> None:
    SettingsStore(path).save_visible_columns(visible_columns)


def load_gp_highlight_threshold(path: Optional[Path] = None) -> float | None:
    return SettingsStore(path).load_gp_highlight_threshold()


def save_gp_highlight_threshold(threshold: float | None, path: Optional[Path] = None) -> None:
    SettingsStore(path).save_gp_highlight_threshold(threshold)


def load_csv_preview_last_path(path: Optional[Path] = None) -> str | None:
    return SettingsStore(path).load_csv_preview_last_path()


def save_csv_preview_last_path(csv_preview_last_path: str | None, path: Optional[Path] = None) -> None:
    SettingsStore(path).save_csv_preview_last_path(csv_preview_last_path)


def load_csv_preview_recent_paths(path: Optional[Path] = None) -> List[str]:
    return SettingsStore(path).load_csv_preview_recent_paths()


def save_csv_preview_recent_paths(csv_preview_recent_paths: List[str], path: Optional[Path] = None) -> None:
    SettingsStore(path).save_csv_preview_recent_paths(csv_preview_recent_paths)


def load_csv_preview_visible_columns(csv_preview_path: str | None, path: Optional[Path] = None) -> List[int] | None:
    return SettingsStore(path).load_csv_preview_visible_columns(csv_preview_path)


def save_csv_preview_visible_columns(
    csv_preview_path: str | None,
    visible_columns: List[int] | None,
    path: Optional[Path] = None,
) -> None:
    SettingsStore(path).save_csv_preview_visible_columns(csv_preview_path, visible_columns)


def load_csv_preview_visible_column_keys(csv_preview_path: str | None, path: Optional[Path] = None) -> List[str] | None:
    return SettingsStore(path).load_csv_preview_visible_column_keys(csv_preview_path)


def save_csv_preview_visible_column_keys(
    csv_preview_path: str | None,
    visible_column_keys: List[str] | None,
    path: Optional[Path] = None,
) -> None:
    SettingsStore(path).save_csv_preview_visible_column_keys(csv_preview_path, visible_column_keys)


def load_csv_preview_sort(csv_preview_path: str | None, path: Optional[Path] = None) -> dict[str, object] | None:
    return SettingsStore(path).load_csv_preview_sort(csv_preview_path)


def load_csv_preview_state(csv_preview_path: str | None, path: Optional[Path] = None) -> CsvPreviewPathState | None:
    return SettingsStore(path).load_csv_preview_state(csv_preview_path)


def save_csv_preview_state(csv_preview_path: str | None, state: CsvPreviewPathState | None, path: Optional[Path] = None) -> None:
    SettingsStore(path).save_csv_preview_state(csv_preview_path, state)


def load_csv_preview_has_header_row(csv_preview_path: str | None, path: Optional[Path] = None) -> bool | None:
    return SettingsStore(path).load_csv_preview_has_header_row(csv_preview_path)


def save_csv_preview_has_header_row(csv_preview_path: str | None, has_header_row: bool | None, path: Optional[Path] = None) -> None:
    SettingsStore(path).save_csv_preview_has_header_row(csv_preview_path, has_header_row)


def save_csv_preview_sort(
    csv_preview_path: str | None,
    column_key: str | None,
    *,
    descending: bool = False,
    path: Optional[Path] = None,
) -> None:
    SettingsStore(path).save_csv_preview_sort(csv_preview_path, column_key, descending=descending)
