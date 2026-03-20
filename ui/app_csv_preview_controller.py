from __future__ import annotations

import logging
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from ..settings import SettingsStore


LOGGER = logging.getLogger(__name__)


class _CsvPreviewLaunchController:
    def __init__(
        self,
        app: tk.Misc,
        settings: SettingsStore,
        open_last_csv_button: ttk.Button,
        open_recent_csv_button: ttk.Menubutton,
        recent_csv_menu: tk.Menu,
        warn_settings_save_failure,
        get_geometry,
        set_status,
        clear_status,
        ask_open_filename,
        ask_yes_no_cancel,
        show_error,
        open_csv_preview_dialog,
        csv_preview_error_type,
        on_open_recent_csv_preview,
    ) -> None:
        self._app = app
        self._settings = settings
        self._open_last_csv_button = open_last_csv_button
        self._open_recent_csv_button = open_recent_csv_button
        self._recent_csv_menu = recent_csv_menu
        self._warn_settings_save_failure = warn_settings_save_failure
        self._get_geometry = get_geometry
        self._set_status = set_status
        self._clear_status = clear_status
        self._ask_open_filename = ask_open_filename
        self._ask_yes_no_cancel = ask_yes_no_cancel
        self._show_error = show_error
        self._open_csv_preview_dialog = open_csv_preview_dialog
        self._csv_preview_error_type = csv_preview_error_type
        self._on_open_recent_csv_preview = on_open_recent_csv_preview

    def update_open_last_csv_button_state(self) -> None:
        recent_paths = self._settings.load_csv_preview_recent_paths()
        existing_paths = [path for path in recent_paths if Path(path).exists()]
        last_path = existing_paths[0] if existing_paths else None

        if existing_paths != recent_paths or self._settings.load_csv_preview_last_path() != last_path:
            try:
                self._settings.update(csv_preview_last_path=last_path, csv_preview_recent_paths=existing_paths)
            except (OSError, TypeError, ValueError) as exc:
                LOGGER.warning("Unable to normalize remembered CSV preview paths", exc_info=True)
                self._warn_settings_save_failure("the recent CSV preview list", exc)

        state = "normal" if existing_paths else "disabled"
        self._open_last_csv_button.config(state=state)
        self._open_recent_csv_button.config(state=state)

        self._recent_csv_menu.delete(0, "end")
        for saved_path in existing_paths:
            self._recent_csv_menu.add_command(
                label=saved_path,
                command=lambda value=saved_path: self._on_open_recent_csv_preview(value),
            )

    def open_csv_preview_path(
        self,
        csv_path: Path,
        *,
        remember: bool,
        has_header_row: bool,
        status_message: str,
    ) -> None:
        self._set_status(status_message)
        width, height = self._get_geometry()
        try:
            self._open_csv_preview_dialog(csv_path, width, height, has_header_row)
        except self._csv_preview_error_type as exc:
            self._show_error("CSV preview unavailable", str(exc))
            return
        finally:
            self._clear_status()

        if remember:
            try:
                self._settings.remember_csv_preview_path(str(csv_path))
            except (OSError, TypeError, ValueError) as exc:
                LOGGER.warning("Unable to persist recent CSV preview paths", exc_info=True)
                self._warn_settings_save_failure("the recent CSV preview list", exc)
            self.update_open_last_csv_button_state()

    def resolve_csv_preview_has_header_row(self, csv_path: Path, *, prompt: bool) -> bool | None:
        normalized_path = str(csv_path)
        saved_choice = self._settings.load_csv_preview_has_header_row(normalized_path)
        if saved_choice is not None and not prompt:
            return saved_choice

        remembered_text = ""
        if saved_choice is not None:
            remembered_text = "\n\nRemembered choice for this file: first row is {}headers.".format("" if saved_choice else "not ")
        choice = self._ask_yes_no_cancel(
            "CSV header row",
            "Does this CSV already contain a header row?\n\n"
            "Yes: use the first row as column names.\n"
            "No: generate Column 1, Column 2, Column 3, ... and keep the first row as data."
            f"{remembered_text}",
        )
        if choice is None:
            return None
        has_header_row = bool(choice)
        try:
            self._settings.save_csv_preview_has_header_row(normalized_path, has_header_row)
        except (OSError, TypeError, ValueError) as exc:
            LOGGER.warning("Unable to persist CSV preview header mode", exc_info=True)
            self._warn_settings_save_failure("the CSV header option", exc)
        return has_header_row

    def on_open_csv_preview(self) -> None:
        path = self._ask_open_filename()
        if not path:
            return
        has_header_row = self.resolve_csv_preview_has_header_row(Path(path), prompt=True)
        if has_header_row is None:
            return
        self.open_csv_preview_path(Path(path), remember=True, has_header_row=has_header_row, status_message="Processing CSV...")

    def on_open_last_csv_preview(self) -> None:
        recent_paths = self._settings.load_csv_preview_recent_paths()
        if not recent_paths:
            self.update_open_last_csv_button_state()
            return
        csv_path = Path(recent_paths[0])
        if not csv_path.exists():
            self._show_error("CSV preview unavailable", "The remembered CSV file could not be found.")
            try:
                self._settings.save_csv_preview_recent_paths([path for path in recent_paths if path != str(csv_path)])
            except (OSError, TypeError, ValueError) as exc:
                LOGGER.warning("Unable to clear missing remembered CSV preview path", exc_info=True)
                self._warn_settings_save_failure("the recent CSV preview list", exc)
            self.update_open_last_csv_button_state()
            return
        has_header_row = self.resolve_csv_preview_has_header_row(csv_path, prompt=False)
        if has_header_row is None:
            return
        self.open_csv_preview_path(csv_path, remember=True, has_header_row=has_header_row, status_message="Processing last CSV...")

    def on_open_recent_csv_preview(self, saved_path: str) -> None:
        csv_path = Path(saved_path)
        if not csv_path.exists():
            self._show_error("CSV preview unavailable", "The selected recent CSV file could not be found.")
            try:
                self._settings.save_csv_preview_recent_paths(
                    [path for path in self._settings.load_csv_preview_recent_paths() if path != saved_path]
                )
            except (OSError, TypeError, ValueError) as exc:
                LOGGER.warning("Unable to clear missing recent CSV preview path", exc_info=True)
                self._warn_settings_save_failure("the recent CSV preview list", exc)
            self.update_open_last_csv_button_state()
            return
        has_header_row = self.resolve_csv_preview_has_header_row(csv_path, prompt=False)
        if has_header_row is None:
            return
        self.open_csv_preview_path(csv_path, remember=True, has_header_row=has_header_row, status_message="Processing recent CSV...")