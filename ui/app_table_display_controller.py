from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk
from typing import Sequence

from ..data_manager import DataManager
from ..models import Record
from ..settings import SettingsStore
from .form import InputForm
from .record_logic import filtered_records, record_matches_query
from .table import METRIC_LABELS, RecordTable


LOGGER = logging.getLogger(__name__)


class _TableDisplayController:
    def __init__(
        self,
        owner: tk.Misc,
        settings: SettingsStore,
        data_manager: DataManager,
        form: InputForm,
        table: RecordTable,
        gp_highlight_menu: tk.Menu,
        type_filter_menu: tk.Menu,
        type_filter_menu_value: tk.StringVar,
        warn_settings_save_failure,
        load_records,
        current_search_query,
        ask_string,
        show_error,
        show_info,
    ) -> None:
        self._owner = owner
        self._settings = settings
        self._data_manager = data_manager
        self._form = form
        self._table = table
        self._gp_highlight_menu = gp_highlight_menu
        self._type_filter_menu = type_filter_menu
        self._type_filter_menu_value = type_filter_menu_value
        self._warn_settings_save_failure = warn_settings_save_failure
        self._load_records = load_records
        self._current_search_query = current_search_query
        self._ask_string = ask_string
        self._show_error = show_error
        self._show_info = show_info
        self._type_filter_value: str | None = None

    def normalized_type_value(self, value: str | None) -> str:
        return (value or "").strip().lower()

    def record_type_options(self, records: list[Record]) -> list[str]:
        return sorted(
            {
                (record.field1 or "").strip()
                for record in records
                if (record.field1 or "").strip()
            },
            key=str.lower,
        )

    def apply_type_filter(self, records: list[Record]) -> list[Record]:
        if not self._type_filter_value:
            return records
        return [
            record
            for record in records
            if self.normalized_type_value(record.field1) == self._type_filter_value
        ]

    def filtered_records(self, records: list[Record]) -> list[Record]:
        return filtered_records(self.apply_type_filter(records), self._current_search_query())

    def record_matches_current_filter(self, record: Record) -> bool:
        query = self._current_search_query()
        filtered_records_for_query = self.apply_type_filter(self._data_manager.load_all())
        if self._type_filter_value and self.normalized_type_value(record.field1) != self._type_filter_value:
            return False
        return record_matches_query(record, query, filtered_records_for_query)

    def set_type_filter(self, value: str | None) -> None:
        self._type_filter_value = value
        self._type_filter_menu_value.set(value or "")
        self._load_records()

    def show_type_filter_menu(self) -> None:
        records = self._data_manager.load_all()
        type_options = self.record_type_options(records)

        self._type_filter_menu.delete(0, "end")
        if type_options:
            for type_name in type_options:
                normalized_value = self.normalized_type_value(type_name)
                self._type_filter_menu.add_radiobutton(
                    label=type_name,
                    value=normalized_value,
                    variable=self._type_filter_menu_value,
                    command=lambda value=normalized_value: self.set_type_filter(value),
                )
        else:
            self._type_filter_menu.add_command(label="No types available", state="disabled")

        self._type_filter_menu.add_separator()
        self._type_filter_menu.add_command(label="Remove type filter", command=lambda: self.set_type_filter(None))

        try:
            self._type_filter_menu.tk_popup(self._owner.winfo_pointerx(), self._owner.winfo_pointery())
        except tk.TclError:
            LOGGER.debug("Unable to show type filter menu", exc_info=True)
        finally:
            try:
                self._type_filter_menu.grab_release()
            except tk.TclError:
                LOGGER.debug("Unable to release type filter menu grab", exc_info=True)

    def set_gp_highlight_threshold(self, threshold: float | None) -> None:
        self._table.set_gp_highlight_threshold(threshold)
        try:
            self._settings.save_gp_highlight_threshold(threshold)
        except (OSError, TypeError, ValueError) as exc:
            LOGGER.warning("Unable to persist GP highlight threshold", exc_info=True)
            self._warn_settings_save_failure("the GP highlight preference", exc)

    def prompt_custom_gp_highlight_threshold(self) -> None:
        current_threshold = self._table.get_gp_highlight_threshold()
        initial_value = "" if current_threshold is None else f"{current_threshold:g}"
        response = self._ask_string(
            "Highlight GP rows",
            "Highlight rows with GP smaller than what percentage?\n\nEnter a number like 70 or 70.5.\nLeave blank to clear highlighting.",
            parent=self._owner,
            initialvalue=initial_value,
        )
        if response is None:
            return
        text = response.strip().rstrip("%")
        if not text:
            self.set_gp_highlight_threshold(None)
            return
        try:
            threshold = float(text)
        except ValueError:
            self._show_error("Invalid GP threshold", "Enter a GP percentage like 70 or 70.5.")
            return
        if threshold < 0 or threshold > 100:
            self._show_error("Invalid GP threshold", "GP highlight threshold must be between 0 and 100.")
            return
        self.set_gp_highlight_threshold(threshold)

    def show_gp_highlight_menu(self) -> None:
        try:
            self._gp_highlight_menu.tk_popup(self._owner.winfo_pointerx(), self._owner.winfo_pointery())
        finally:
            try:
                self._gp_highlight_menu.grab_release()
            except tk.TclError:
                LOGGER.debug("Unable to release GP highlight menu grab", exc_info=True)

    def on_labels_changed(self, labels: Sequence[str]) -> None:
        self._table.update_column_labels(labels)

    def on_column_order_changed(self, columns: Sequence[str]) -> None:
        try:
            self._settings.save_column_order(list(columns))
        except (OSError, TypeError, ValueError) as exc:
            LOGGER.warning("Unable to persist column order", exc_info=True)
            self._warn_settings_save_failure("the column order", exc)

    def on_column_widths_changed(self, column_widths: dict[str, int]) -> None:
        try:
            self._settings.save_column_widths(column_widths)
        except (OSError, TypeError, ValueError) as exc:
            LOGGER.warning("Unable to persist column widths", exc_info=True)
            self._warn_settings_save_failure("the column widths", exc)

    def on_visible_columns_changed(self, visible_columns: Sequence[str]) -> None:
        try:
            self._settings.save_visible_columns(list(visible_columns))
        except (OSError, TypeError, ValueError) as exc:
            LOGGER.warning("Unable to persist visible columns", exc_info=True)
            self._warn_settings_save_failure("the visible columns", exc)

    def column_label(self, column: str) -> str:
        if column.startswith("field") and column[5:].isdigit():
            idx = int(column[5:]) - 1
            if 0 <= idx < len(self._form.labels):
                return self._form.labels[idx]
        return METRIC_LABELS.get(column, column)

    def on_manage_columns(self) -> None:
        win = tk.Toplevel(self._owner)
        win.title("Columns")
        win.geometry("320x360")

        body = ttk.Frame(win)
        body.pack(fill="both", expand=True, padx=10, pady=10)

        visible = set(self._table.get_visible_columns())
        vars_by_column: dict[str, tk.BooleanVar] = {}
        for row, column in enumerate(self._table.get_column_order()):
            var = tk.BooleanVar(value=column in visible)
            vars_by_column[column] = var
            ttk.Checkbutton(body, text=self.column_label(column), variable=var).grid(row=row, column=0, sticky="w", pady=2)

        def apply_columns() -> None:
            selected = [column for column in self._table.get_column_order() if vars_by_column[column].get()]
            if not selected:
                self._show_info("Columns", "At least one column must stay visible.")
                return
            self._table.set_visible_columns(selected)
            win.destroy()

        buttons = ttk.Frame(win)
        buttons.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(buttons, text="Apply", command=apply_columns).pack(side="right", padx=4)
        ttk.Button(buttons, text="Cancel", command=win.destroy).pack(side="right", padx=4)