from __future__ import annotations
from pathlib import Path
from typing import Optional

from .settings_defaults import (
    DEFAULT_COLUMN_ORDER,
    DEFAULT_COLUMN_WIDTHS,
    DEFAULT_LABELS,
    DEFAULT_SETTINGS,
    DEFAULT_VISIBLE_COLUMNS,
    MAX_RECENT_CSV_PREVIEW_PATHS,
)
from .settings_facade import build_settings_api
from .settings_store import SettingsStore as _SettingsStore
from .settings_types import AppSettings, CsvPreviewPathState

DEFAULT_PATH = Path(__file__).parent / "settings.json"


class SettingsStore(_SettingsStore):
    def __init__(self, path: Optional[Path] = None):
        super().__init__(path, default_path=lambda: DEFAULT_PATH)


globals().update(build_settings_api(SettingsStore))
