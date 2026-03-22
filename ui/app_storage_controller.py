from __future__ import annotations

import tkinter as tk
from pathlib import Path

from ..data_manager import CSVDataManager, DataManager
from ..models import Record


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
        try:
            tmp = CSVDataManager(Path(path))
            tmp._write_all(displayed_records)
            self._show_info("Export", f"Exported to {path}")
        except (OSError, RuntimeError, ValueError) as exc:
            self._show_storage_error("Export failed", "export records", Path(path), exc)

    def on_manage_backups(self):
        return self._open_manage_backups()