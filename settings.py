from __future__ import annotations
from dataclasses import dataclass
import json
from pathlib import Path
from typing import List, Mapping, Optional

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
}
DEFAULT_PATH = Path(__file__).parent / "settings.json"


@dataclass(frozen=True)
class AppSettings:
    labels: list[str]
    column_order: list[str]
    column_widths: dict[str, int]
    visible_columns: list[str]
    gp_highlight_threshold: float | None
    csv_preview_last_path: str | None

    def to_dict(self) -> dict:
        return {
            "labels": list(self.labels),
            "column_order": list(self.column_order),
            "column_widths": dict(self.column_widths),
            "visible_columns": list(self.visible_columns),
            "gp_highlight_threshold": self.gp_highlight_threshold,
            "csv_preview_last_path": self.csv_preview_last_path,
        }


def _default_settings() -> dict:
    return {
        "labels": DEFAULT_LABELS.copy(),
        "column_order": DEFAULT_COLUMN_ORDER.copy(),
        "column_widths": dict(DEFAULT_COLUMN_WIDTHS),
        "visible_columns": DEFAULT_VISIBLE_COLUMNS.copy(),
        "gp_highlight_threshold": None,
        "csv_preview_last_path": None,
    }


def _default_app_settings() -> AppSettings:
    return AppSettings(
        labels=DEFAULT_LABELS.copy(),
        column_order=DEFAULT_COLUMN_ORDER.copy(),
        column_widths=dict(DEFAULT_COLUMN_WIDTHS),
        visible_columns=DEFAULT_VISIBLE_COLUMNS.copy(),
        gp_highlight_threshold=None,
        csv_preview_last_path=None,
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


def _normalized_app_settings(raw_data: Mapping[str, object] | None) -> AppSettings:
    data = raw_data if isinstance(raw_data, Mapping) else {}
    return AppSettings(
        labels=_normalized_labels(data.get("labels", DEFAULT_LABELS)),
        column_order=_normalized_column_order(data.get("column_order", DEFAULT_COLUMN_ORDER)),
        column_widths=_normalized_column_widths(data.get("column_widths", DEFAULT_COLUMN_WIDTHS)),
        visible_columns=_normalized_visible_columns(data.get("visible_columns", DEFAULT_VISIBLE_COLUMNS)),
        gp_highlight_threshold=_normalized_gp_highlight_threshold(data.get("gp_highlight_threshold")),
        csv_preview_last_path=_normalized_csv_preview_last_path(data.get("csv_preview_last_path")),
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
        return self.update(csv_preview_last_path=csv_preview_last_path)


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
