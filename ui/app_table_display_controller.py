from __future__ import annotations

import logging
import tkinter as tk
from time import perf_counter
from tkinter import ttk
from typing import Sequence

from ..data_manager import DataManager
from ..models import Record
from ..settings import SettingsStore
from .form import InputForm
from .record_logic import filtered_records, record_matches_query
from .table import METRIC_LABELS, RecordTable


LOGGER = logging.getLogger(__name__)


def _log_table_display_performance(operation: str, started_at: float, **fields: object) -> None:
    if not LOGGER.isEnabledFor(logging.DEBUG):
        return
    duration_ms = (perf_counter() - started_at) * 1000.0
    details = ", ".join(f"{key}={value}" for key, value in fields.items())
    if details:
        LOGGER.debug("Table display %s took %.1fms (%s)", operation, duration_ms, details)
        return
    LOGGER.debug("Table display %s took %.1fms", operation, duration_ms)


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
        refresh_records_view,
        current_search_query,
        current_records,
        ask_string,
        ask_yes_no,
        show_error,
        show_info,
        bulk_rename_type,
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
        self._refresh_records_view = refresh_records_view
        self._current_search_query = current_search_query
        self._current_records = current_records
        self._ask_string = ask_string
        self._ask_yes_no = ask_yes_no
        self._show_error = show_error
        self._show_info = show_info
        self._bulk_rename_type = bulk_rename_type
        self._type_filter_value: str | None = None
        self._type_menu_cache_signature: tuple[int, int] | None = None
        self._type_menu_cached_records: list[Record] = []
        self._type_menu_cached_options: list[str] = []

    def _type_menu_storage_signature(self) -> tuple[int, int] | None:
        try:
            stat = self._data_manager.path.stat()
        except OSError:
            return None
        return stat.st_mtime_ns, stat.st_size

    def _type_menu_records_and_options(self) -> tuple[list[Record], list[str], str]:
        current_records = list(self._current_records())
        signature = self._type_menu_storage_signature()

        if current_records and not self._type_menu_cached_options:
            records = current_records
            type_options = self.record_type_options(records)
            self._type_menu_cache_signature = signature
            self._type_menu_cached_records = list(records)
            self._type_menu_cached_options = list(type_options)
            return records, type_options, "current-records"

        if self._type_menu_cached_options and signature == self._type_menu_cache_signature:
            return list(self._type_menu_cached_records), list(self._type_menu_cached_options), "cache"

        records = self._data_manager.load_all()
        type_options = self.record_type_options(records)
        self._type_menu_cache_signature = signature
        self._type_menu_cached_records = list(records)
        self._type_menu_cached_options = list(type_options)
        return records, type_options, "storage"

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

    def record_matches_current_filter(self, record: Record, records: Sequence[Record] | None = None) -> bool:
        query = self._current_search_query()
        if self._type_filter_value and self.normalized_type_value(record.field1) != self._type_filter_value:
            return False
        filtered_records_for_query = self.apply_type_filter(list(records) if records is not None else list(self._current_records()))
        return record_matches_query(record, query, filtered_records_for_query)

    def set_type_filter(self, value: str | None) -> None:
        self._type_filter_value = value
        self._type_filter_menu_value.set(value or "")
        self._refresh_records_view()

    def _type_option_for_value(self, value: str | None, type_options: Sequence[str]) -> str | None:
        normalized_value = self.normalized_type_value(value)
        if not normalized_value:
            return None
        return next(
            (type_name for type_name in type_options if self.normalized_type_value(type_name) == normalized_value),
            None,
        )

    def _prompt_type_selection(
        self,
        *,
        title: str,
        prompt: str,
        type_options: Sequence[str],
        initial_value: str | None = None,
    ) -> str | None:
        dialog = tk.Toplevel(self._owner)
        dialog.title(title)
        dialog.geometry("320x320")
        dialog.resizable(False, False)

        body = ttk.Frame(dialog)
        body.pack(fill="both", expand=True, padx=10, pady=10)

        ttk.Label(body, text=prompt, justify="left", wraplength=280).pack(fill="x")

        list_frame = ttk.Frame(body)
        list_frame.pack(fill="both", expand=True, pady=(8, 0))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        listbox = tk.Listbox(list_frame, exportselection=False, height=min(max(len(type_options), 6), 12))
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=listbox.yview)
        listbox.configure(yscrollcommand=scrollbar.set)
        listbox.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        for type_name in type_options:
            listbox.insert("end", type_name)

        result: str | None = None

        def _selected_type() -> str | None:
            selection = listbox.curselection()
            if not selection:
                return None
            return str(listbox.get(selection[0]))

        def _close() -> None:
            dialog.destroy()

        def _choose(_event=None) -> str:
            nonlocal result
            selected_type = _selected_type()
            if selected_type is None:
                return "break"
            result = selected_type
            _close()
            return "break"

        button_row = ttk.Frame(dialog)
        button_row.pack(fill="x", padx=10, pady=(0, 10))
        choose_button = ttk.Button(button_row, text="Select", command=_choose, state="disabled")
        choose_button.pack(side="right", padx=(4, 0))
        ttk.Button(button_row, text="Cancel", command=_close).pack(side="right")

        def _sync_selection(_event=None) -> None:
            choose_button.configure(state="normal" if _selected_type() is not None else "disabled")

        initial_index = next(
            (
                index
                for index, type_name in enumerate(type_options)
                if self.normalized_type_value(type_name) == self.normalized_type_value(initial_value)
            ),
            None,
        )
        if initial_index is not None:
            listbox.selection_set(initial_index)
            listbox.see(initial_index)

        listbox.bind("<<ListboxSelect>>", _sync_selection, add="+")
        listbox.bind("<Double-Button-1>", _choose, add="+")
        listbox.bind("<Return>", _choose, add="+")
        dialog.bind("<Escape>", lambda _event: _close(), add="+")
        dialog.protocol("WM_DELETE_WINDOW", _close)
        _sync_selection()

        try:
            dialog.transient(self._owner.winfo_toplevel())
            dialog.grab_set()
        except tk.TclError:
            LOGGER.debug("Unable to make type picker dialog modal", exc_info=True)

        listbox.focus_set()
        self._owner.wait_window(dialog)
        return result

    def _prompt_bulk_rename_type(self, type_options: list[str], records: list[Record]) -> None:
        if not type_options:
            self._show_error("No types available", "There are no saved types to edit.")
            return

        current_type = self._type_option_for_value(self._type_filter_value, type_options)
        source_type = self._prompt_type_selection(
            title="Edit type",
            prompt="Choose the type you want to rename.",
            type_options=type_options,
            initial_value=current_type,
        )
        if source_type is None:
            return

        target_type = self._ask_string(
            "Edit type",
            f"Rename '{source_type}' to what?",
            parent=self._owner,
            initialvalue=source_type,
        )
        if target_type is None:
            return
        if not target_type.strip():
            self._show_error("Invalid type", "Type cannot be empty.")
            return

        source_normalized = self.normalized_type_value(source_type)
        target_existing_type = self._type_option_for_value(target_type, type_options)
        if target_existing_type is not None and self.normalized_type_value(target_existing_type) != source_normalized:
            matching_count = sum(
                1
                for record in records
                if self.normalized_type_value(record.field1) == source_normalized
            )
            should_merge = self._ask_yes_no(
                "Merge types",
                f"{target_existing_type} already exists.\n\nMerge {matching_count} '{source_type}' record(s) into '{target_existing_type}'?",
            )
            if not should_merge:
                return

        result = self._bulk_rename_type(
            source_type,
            target_type,
            backup_action=f"renaming the type '{source_type}'",
            error_title="Type update failed",
            error_action="update the selected type",
        )
        if result is None:
            return

        changed_count, resolved_target_type = result
        if self._type_filter_value == source_normalized:
            self.set_type_filter(self.normalized_type_value(resolved_target_type))

        record_label = "record" if changed_count == 1 else "records"
        self._show_info(
            "Type updated",
            f"Updated {changed_count} {record_label} from {source_type} to {resolved_target_type}.",
        )

    def show_type_filter_menu(self) -> None:
        started_at = perf_counter()
        records, type_options, source = self._type_menu_records_and_options()

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
        self._type_filter_menu.add_command(
            label="Edit type...",
            command=lambda: self._prompt_bulk_rename_type(type_options, records),
            state="normal" if type_options else "disabled",
        )
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
        _log_table_display_performance(
            "show type filter menu",
            started_at,
            records=len(records),
            type_options=len(type_options),
            source=source,
        )

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