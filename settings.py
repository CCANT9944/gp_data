from __future__ import annotations
import json
from pathlib import Path
from typing import List, Optional

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
}
DEFAULT_PATH = Path(__file__).parent / "settings.json"


def _default_settings() -> dict:
    return {
        "labels": DEFAULT_LABELS.copy(),
        "column_order": DEFAULT_COLUMN_ORDER.copy(),
        "column_widths": dict(DEFAULT_COLUMN_WIDTHS),
        "visible_columns": DEFAULT_VISIBLE_COLUMNS.copy(),
    }


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


def load_settings(path: Optional[Path] = None) -> dict:
    path = Path(path) if path else DEFAULT_PATH
    if not path.exists():
        return _default_settings()
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return _default_settings()
    if not isinstance(data, dict):
        return _default_settings()

    labels = _normalized_labels(data.get("labels", DEFAULT_LABELS))
    column_order = _normalized_column_order(data.get("column_order", DEFAULT_COLUMN_ORDER))
    column_widths = _normalized_column_widths(data.get("column_widths", DEFAULT_COLUMN_WIDTHS))
    visible_columns = _normalized_visible_columns(data.get("visible_columns", DEFAULT_VISIBLE_COLUMNS))
    return {
        "labels": labels,
        "column_order": column_order,
        "column_widths": column_widths,
        "visible_columns": visible_columns,
    }


def save_settings(data: dict, path: Optional[Path] = None) -> None:
    path = Path(path) if path else DEFAULT_PATH
    _ensure_parent(path)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_labels(path: Optional[Path] = None) -> List[str]:
    return load_settings(path)["labels"]


def save_labels(labels: List[str], path: Optional[Path] = None) -> None:
    data = load_settings(path)
    data["labels"] = _normalized_labels(list(labels))
    save_settings(data, path)


def load_column_order(path: Optional[Path] = None) -> List[str]:
    return load_settings(path)["column_order"]


def save_column_order(column_order: List[str], path: Optional[Path] = None) -> None:
    data = load_settings(path)
    data["column_order"] = _normalized_column_order(list(column_order))
    save_settings(data, path)


def load_column_widths(path: Optional[Path] = None) -> dict[str, int]:
    return load_settings(path)["column_widths"]


def save_column_widths(column_widths: dict[str, int], path: Optional[Path] = None) -> None:
    data = load_settings(path)
    data["column_widths"] = _normalized_column_widths(dict(column_widths))
    save_settings(data, path)


def load_visible_columns(path: Optional[Path] = None) -> List[str]:
    return load_settings(path)["visible_columns"]


def save_visible_columns(visible_columns: List[str], path: Optional[Path] = None) -> None:
    data = load_settings(path)
    data["visible_columns"] = _normalized_visible_columns(list(visible_columns))
    save_settings(data, path)
