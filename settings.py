from __future__ import annotations
import json
from pathlib import Path
from typing import List, Optional

DEFAULT_LABELS = ["Field 1", "Field 2", "Field 3", "Field 4", "Field 5", "Field 6", "Field 7"]
DEFAULT_SETTINGS = {"labels": DEFAULT_LABELS}
DEFAULT_PATH = Path(__file__).parent / "settings.json"


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def load_settings(path: Optional[Path] = None) -> dict:
    path = Path(path) if path else DEFAULT_PATH
    if not path.exists():
        return {"labels": DEFAULT_LABELS.copy()}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {"labels": DEFAULT_LABELS.copy()}

    labels = data.get("labels", DEFAULT_LABELS)
    labels = [str(x) for x in labels]
    # pad to 5 labels if needed
    if len(labels) < len(DEFAULT_LABELS):
        labels = labels + DEFAULT_LABELS[len(labels):]
    return {"labels": labels}


def save_settings(data: dict, path: Optional[Path] = None) -> None:
    path = Path(path) if path else DEFAULT_PATH
    _ensure_parent(path)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_labels(path: Optional[Path] = None) -> List[str]:
    return load_settings(path)["labels"]


def save_labels(labels: List[str], path: Optional[Path] = None) -> None:
    save_settings({"labels": list(labels)}, path)
