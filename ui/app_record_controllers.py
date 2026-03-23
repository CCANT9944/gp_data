from __future__ import annotations

import logging
import tkinter as tk
from time import perf_counter
from tkinter import ttk

from ..data_manager import DataManager
from ..models import Record
from .form import InputForm
from .record_actions import RecordActions
from .table import RecordTable
from .view_helpers import clear_table_selection, focus_widget, recalc_form_field6, restore_table_selection


LOGGER = logging.getLogger(__name__)


def _log_record_list_performance(operation: str, started_at: float, **fields: object) -> None:
    if not LOGGER.isEnabledFor(logging.DEBUG):
        return
    duration_ms = (perf_counter() - started_at) * 1000.0
    details = ", ".join(f"{key}={value}" for key, value in fields.items())
    if details:
        LOGGER.debug("Record list %s took %.1fms (%s)", operation, duration_ms, details)
        return
    LOGGER.debug("Record list %s took %.1fms", operation, duration_ms)


class _RecordListController:
    def __init__(
        self,
        data_manager: DataManager,
        form: InputForm,
        table: RecordTable,
        search_entry: ttk.Entry,
        record_actions: RecordActions,
        show_storage_error,
        update_form_mode_ui,
        confirm_discard_form_changes,
        sort_records_for_display,
        filtered_records,
        record_matches_current_filter,
    ) -> None:
        self._data_manager = data_manager
        self._form = form
        self._table = table
        self._search_entry = search_entry
        self._record_actions = record_actions
        self._show_storage_error = show_storage_error
        self._update_form_mode_ui = update_form_mode_ui
        self._confirm_discard_form_changes = confirm_discard_form_changes
        self._sort_records_for_display = sort_records_for_display
        self._filtered_records = filtered_records
        self._record_matches_current_filter = record_matches_current_filter
        self._loaded_records: list[Record] = []
        self._displayed_records: list[Record] = []
        self._suspend_table_select = False

    @property
    def displayed_records(self) -> list[Record]:
        return self._displayed_records

    @property
    def loaded_records(self) -> list[Record]:
        return self._loaded_records

    def refresh_displayed_records(self, *, operation: str = "refresh displayed records") -> None:
        started_at = perf_counter()
        displayed = self._sort_records_for_display(self._filtered_records(self._loaded_records))
        self._displayed_records = displayed
        self._table.load(displayed)
        self._update_form_mode_ui()
        _log_record_list_performance(
            operation,
            started_at,
            loaded_records=len(self._loaded_records),
            displayed_records=len(displayed),
        )

    def refresh_saved_record(self, record: Record) -> None:
        existing_index = next((index for index, existing in enumerate(self._loaded_records) if existing.id == record.id), None)
        if existing_index is None:
            self._loaded_records.append(record)
        else:
            self._loaded_records[existing_index] = record

        self.refresh_displayed_records(operation="refresh saved record")
        if not self._record_matches_current_filter(record, self._loaded_records):
            return
        if not self._table.exists(record.id):
            return
        try:
            self._table.selection_set(record.id)
        except tk.TclError:
            LOGGER.debug("Unable to restore table selection for %s", record.id, exc_info=True)

    def on_table_select(self, event=None) -> None:
        if self._suspend_table_select:
            return
        selected_id = self._table.get_selected_id()
        if not selected_id:
            return
        current_record_id = self._form.current_record_id
        if selected_id != current_record_id and self._form.is_dirty():
            if not self._confirm_discard_form_changes():
                self._suspend_table_select = True
                try:
                    restore_table_selection(self._table, current_record_id)
                finally:
                    self._suspend_table_select = False
                return
        record = self._record_actions.record_by_id(selected_id)
        if record is None:
            return
        self._form.set_values(record.to_dict())
        self._update_form_mode_ui(record)

    def load_records(self) -> None:
        started_at = perf_counter()
        try:
            records = self._data_manager.load_all()
        except (OSError, RuntimeError, ValueError) as exc:
            LOGGER.warning("Unable to load records", exc_info=True)
            self._loaded_records = []
            self._displayed_records = []
            self._table.load([])
            self._update_form_mode_ui()
            self._show_storage_error("Storage unavailable", "load records", self._data_manager.path, exc)
            return
        self._loaded_records = list(records)
        self.refresh_displayed_records(operation="load records")
        _log_record_list_performance("load records from storage", started_at, loaded_records=len(self._loaded_records))

    def on_search(self) -> None:
        self.refresh_displayed_records(operation="search refresh")

    def on_clear_search(self) -> None:
        self._search_entry.delete(0, "end")
        self.refresh_displayed_records(operation="clear search")


class _RecordFormActionsController:
    def __init__(
        self,
        form: InputForm,
        table: RecordTable,
        record_actions: RecordActions,
        confirm_discard_form_changes,
        confirm_duplicate_record,
        update_form_mode_ui,
        ask_yes_no,
    ) -> None:
        self._form = form
        self._table = table
        self._record_actions = record_actions
        self._confirm_discard_form_changes = confirm_discard_form_changes
        self._confirm_duplicate_record = confirm_duplicate_record
        self._update_form_mode_ui = update_form_mode_ui
        self._ask_yes_no = ask_yes_no

    def on_new_item(self) -> None:
        if not self._confirm_discard_form_changes():
            return
        self.reset_to_new_item()

    def reset_to_new_item(self) -> None:
        self._form.clear()
        clear_table_selection(self._table)
        self._update_form_mode_ui()
        first_field = self._form.entries.get("field1")
        focus_widget(first_field)

    def on_form_submit(self) -> None:
        if self._form.current_record_id:
            self.on_save_changes()
            return
        self.on_add()

    def on_add(self) -> None:
        recalc_form_field6(self._form, "adding a new item")
        data = self._form.get_values()
        record = self._record_actions.build_record_or_show_error(data)
        if record is None:
            return

        if not self._confirm_duplicate_record(record, action_text="add another record"):
            return
        self._record_actions.save_new_record(record)

    def on_edit(self) -> None:
        record = self._record_actions.record_or_show_missing_error(
            self._table.get_selected_id(),
            selection_message="Please select a record to edit.",
        )
        if record is None:
            return
        self._form.set_values(record.to_dict())
        self._update_form_mode_ui(record)
        first_field = self._form.entries.get("field1")
        focus_widget(first_field)

    def on_save_changes(self) -> None:
        record = self._record_actions.record_or_show_missing_error(
            self._form.current_record_id or self._table.get_selected_id(),
            selection_message="Please select a record to edit.",
        )
        if record is None:
            return
        recalc_form_field6(self._form, "saving changes")
        values = self._form.get_values()
        updated = self._record_actions.build_record_or_show_error(values, record_id=record.id, created_at=record.created_at)
        if updated is None:
            return
        self._record_actions.save_existing_record(
            record,
            updated,
            duplicate_action_text="save this edit",
            backup_action="saving this edit",
            error_title="Save failed",
            error_action="save the edited record",
        )

    def on_delete(self) -> None:
        selected_id = self._record_actions.record_id_or_show_selection_error(
            self._table.get_selected_id(),
            "Please select a record to delete.",
        )
        if selected_id is None:
            return
        if self._form.is_dirty() and not self._confirm_discard_form_changes():
            return
        if self._ask_yes_no("Confirm", "Delete selected record?"):
            self._record_actions.delete_record(
                selected_id,
                backup_action="deleting this record",
                error_title="Delete failed",
                error_action="delete the selected record",
            )