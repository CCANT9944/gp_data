from __future__ import annotations

import logging
import tkinter as tk
from pathlib import Path
from time import perf_counter

from ..data_manager import DataManager, export_records_to_csv
from ..models import Record


LOGGER = logging.getLogger(__name__)


def _log_storage_performance(operation: str, started_at: float, **fields: object) -> None:
    if not LOGGER.isEnabledFor(logging.DEBUG):
        return
    duration_ms = (perf_counter() - started_at) * 1000.0
    details = ", ".join(f"{key}={value}" for key, value in fields.items())
    if details:
        LOGGER.debug("Storage action %s took %.1fms (%s)", operation, duration_ms, details)
        return
    LOGGER.debug("Storage action %s took %.1fms", operation, duration_ms)


class _AppStorageActionsController:
    def __init__(self, app: tk.Misc, data_manager: DataManager, show_storage_error, load_records, ask_save_filename, show_info, open_manage_backups) -> None:
        self._app = app
        self._data_manager = data_manager
        self._show_storage_error = show_storage_error
        self._load_records = load_records
        self._ask_save_filename = ask_save_filename
        self._show_info = show_info
        self._open_manage_backups = open_manage_backups

    def on_export(self, displayed_records: list[Record]) -> None:
        path = self._ask_save_filename()
        if not path:
            return
        started_at = perf_counter()
        try:
            export_records_to_csv(Path(path), displayed_records)
            self._show_info("Export", f"Exported to {path}")
            _log_storage_performance("export records", started_at, rows=len(displayed_records), path=path)
        except (OSError, RuntimeError, ValueError) as exc:
            self._show_storage_error("Export failed", "export records", Path(path), exc)

    def on_manage_backups(self):
        return self._open_manage_backups()