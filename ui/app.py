from __future__ import annotations

import logging
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Sequence

from ..data_manager import CSVDataManager, DataManager
from ..models import Record, calculate_field6
from ..settings import SettingsStore
from .backup_dialog import open_manage_backups_dialog
from .csv_preview import CsvPreviewError, open_csv_preview_dialog
from .form import InputForm
from .record_actions import RecordActions
from .record_logic import filtered_records, record_matches_query
from .storage_feedback import describe_backup_failure, describe_startup_storage_issue, describe_storage_error
from .table import METRIC_LABELS, RecordTable
from .view_helpers import ProcessingDialogHandle, clear_table_selection, focus_record_in_table, focus_widget, recalc_form_field6, restore_table_selection


NEW_MODE_BANNER_BG = "#e7f1ff"
NEW_MODE_BANNER_FG = "#0b4f8a"
EDIT_MODE_BANNER_BG = "#fff1c9"
EDIT_MODE_BANNER_FG = "#7a4b00"
DIRTY_MODE_BANNER_BG = "#ffe2bf"
DIRTY_MODE_BANNER_FG = "#8a3d00"
GP_HIGHLIGHT_PRESETS = (50.0, 60.0, 70.0, 80.0)
DEFAULT_WINDOW_WIDTH = 1200
DEFAULT_WINDOW_HEIGHT = 620
WINDOW_SCREEN_MARGIN = 80
LOGGER = logging.getLogger(__name__)


class GPDataApp(tk.Tk):
    def __init__(self, storage_path: Path | None = None):
        super().__init__()
        self.title("GP Data Manager")

        self.data_manager = DataManager(storage_path)
        self._settings = SettingsStore()
        self._displayed_records: list[Record] = []
        self._type_filter_value: str | None = None
        self._type_filter_menu_value = tk.StringVar(value="")
        self._settings_warning_keys: set[str] = set()
        self._record_actions = RecordActions(
            self.data_manager,
            show_validation_error=lambda message: messagebox.showerror("Validation error", message),
            show_selection_error=lambda message: messagebox.showinfo("Select", message),
            show_missing_record_error=lambda: messagebox.showerror("Error", "Record not found"),
            confirm_duplicate_record=self._confirm_duplicate_record,
            create_safety_backup_or_confirm=self._create_safety_backup_or_confirm,
            show_storage_error=lambda title, action, exc: self._show_storage_error(title, action, self.data_manager.path, exc),
            apply_saved_record=self._apply_saved_record,
            load_records=self.load_records,
            reset_to_new_item=self._reset_to_new_item,
        )
        app_settings = self._settings.load()
        labels = app_settings.labels
        column_order = app_settings.column_order
        column_widths = app_settings.column_widths
        visible_columns = app_settings.visible_columns
        gp_highlight_threshold = app_settings.gp_highlight_threshold

        container = ttk.Frame(self)
        container.pack(fill="both", expand=True, padx=8, pady=8)

        left = ttk.Frame(container)
        left.pack(side="left", fill="y", padx=(0, 8))
        self.form = InputForm(
            left,
            labels=labels,
            on_rename=self.on_labels_changed,
            on_submit=self.on_form_submit,
            save_labels_callback=self._settings.save_labels,
            on_dirty_change=self._on_form_dirty_change,
        )
        self.form.pack(fill="y", expand=False)
        self._form_mode_var = tk.StringVar(value="NEW ITEM MODE")
        self._form_mode_label = tk.Label(
            left,
            textvariable=self._form_mode_var,
            anchor="w",
            padx=8,
            pady=6,
            relief="solid",
            borderwidth=1,
            font=("TkDefaultFont", 9, "bold"),
        )
        self._form_mode_label.pack(fill="x", pady=(6, 0))

        right = ttk.Frame(container)
        right.pack(side="left", fill="both", expand=True)
        self.table = RecordTable(right, columns=column_order, labels=labels, on_commit=self._on_table_commit, on_column_order_changed=self.on_column_order_changed, column_widths=column_widths, on_column_widths_changed=self.on_column_widths_changed, visible_columns=visible_columns, on_visible_columns_changed=self.on_visible_columns_changed, on_heading_click=self._on_table_heading_click)
        self.table.pack(fill="both", expand=True)

        controls = ttk.Frame(self)
        controls.pack(fill="x", padx=8, pady=6)
        ttk.Button(controls, text="New item", command=self.on_new_item).pack(side="left", padx=4)
        self._save_changes_button = ttk.Button(controls, text="Save changes", command=self.on_save_changes)
        self._save_changes_button.pack(side="left", padx=4)
        self._delete_selected_button = ttk.Button(controls, text="Delete selected", command=self.on_delete)
        self._delete_selected_button.pack(side="left", padx=4)
        ttk.Button(controls, text="Columns", command=self.on_manage_columns).pack(side="left", padx=4)
        ttk.Button(controls, text="Rename fields", command=self.form.rename_fields).pack(side="left", padx=4)
        ttk.Button(controls, text="Open CSV", command=self.on_open_csv_preview).pack(side="left", padx=4)
        self._open_last_csv_button = ttk.Button(controls, text="Last CSV", command=self.on_open_last_csv_preview)
        self._open_last_csv_button.pack(side="left", padx=4)
        self._recent_csv_menu = tk.Menu(self, tearoff=0)
        self._open_recent_csv_button = ttk.Menubutton(controls, text="Recent CSVs", direction="below")
        self._open_recent_csv_button.configure(menu=self._recent_csv_menu)
        self._open_recent_csv_button.pack(side="left", padx=4)

        ttk.Button(controls, text="Manage backups", command=self.on_manage_backups).pack(side="right", padx=4)
        ttk.Button(controls, text="Export CSV", command=self.on_export).pack(side="right", padx=4)

        self._search_entry = ttk.Entry(controls, width=20)
        self._search_entry.bind("<KeyRelease>", lambda e: self.on_search())
        ttk.Button(controls, text="Clear", command=self.on_clear_search).pack(side="right", padx=4)
        self._search_entry.pack(side="right", padx=4)
        ttk.Label(controls, text="Search").pack(side="right", padx=(4, 0))

        self._csv_preview_status = ProcessingDialogHandle(
            self,
            title="Processing CSV",
            eyebrow_text="CSV PREVIEW",
            detail_text="Loading the preview, checking metadata, and preparing visible rows.",
        )

        self.row_menu = tk.Menu(self, tearoff=0)
        self.row_menu.add_command(label="Load into form", command=self.on_edit)
        self.row_menu.add_command(label="Delete", command=self.on_delete)
        self.row_menu.add_separator()
        self.row_menu.add_command(label="Copy ID", command=self._copy_selected_id_to_clipboard)
        self._gp_highlight_menu = tk.Menu(self, tearoff=0)
        for threshold in GP_HIGHLIGHT_PRESETS:
            label = f"Highlight below {threshold:g}%"
            self._gp_highlight_menu.add_command(label=label, command=lambda value=threshold: self._set_gp_highlight_threshold(value))
        self._gp_highlight_menu.add_separator()
        self._gp_highlight_menu.add_command(label="Custom...", command=self._prompt_custom_gp_highlight_threshold)
        self._gp_highlight_menu.add_command(label="Clear GP highlight", command=lambda: self._set_gp_highlight_threshold(None))
        self._type_filter_menu = tk.Menu(self, tearoff=0)
        self.table.bind("<<TreeviewSelect>>", self._on_table_select)
        self.table.bind("<Button-3>", self._on_row_right_click)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self._suspend_table_select = False
        self._update_open_last_csv_button_state()
        self.table.set_gp_highlight_threshold(gp_highlight_threshold)
        self._apply_initial_window_geometry()
        self._update_form_mode_ui()
        self.load_records()
        self._warn_if_storage_issue()

    def _apply_initial_window_geometry(self) -> None:
        self.update_idletasks()
        width = max(DEFAULT_WINDOW_WIDTH, self.winfo_reqwidth())
        height = max(DEFAULT_WINDOW_HEIGHT, self.winfo_reqheight())

        screen_width = max(DEFAULT_WINDOW_WIDTH, self.winfo_screenwidth() - WINDOW_SCREEN_MARGIN)
        screen_height = max(DEFAULT_WINDOW_HEIGHT, self.winfo_screenheight() - WINDOW_SCREEN_MARGIN)
        width = min(width, screen_width)
        height = min(height, screen_height)

        self.geometry(f"{width}x{height}")
        self.minsize(width, height)

    def _warn_if_storage_issue(self) -> None:
        issue = self.data_manager.storage_issue()
        if issue is None:
            return
        messagebox.showwarning("Storage issue", describe_startup_storage_issue(self.data_manager.path, issue))

    def _show_storage_error(self, title: str, action: str, path: Path | None, exc: Exception, suffix: str | None = None) -> None:
        message = describe_storage_error(action, path, exc)
        if suffix:
            message = f"{message}\n\n{suffix}"
        messagebox.showerror(title, message)

    def _warn_settings_save_failure(self, action: str, exc: Exception) -> None:
        reason = str(exc).strip() or exc.__class__.__name__
        warning_key = f"{action}:{exc.__class__.__name__}:{reason}"
        if warning_key in self._settings_warning_keys:
            return
        self._settings_warning_keys.add(warning_key)
        messagebox.showwarning(
            "Settings not saved",
            f"Could not save {action} to settings.json.\n\nReason: {reason}\n\nThe change is visible now, but it may not still be there after restart.",
        )

    def _create_safety_backup_or_confirm(self, action: str) -> bool:
        try:
            self.data_manager.create_timestamped_backup()
            return True
        except (OSError, RuntimeError) as exc:
            LOGGER.warning("Unable to create a safety backup before %s", action, exc_info=True)
            return messagebox.askyesno("Backup unavailable", describe_backup_failure(action, self.data_manager.path, exc))

    def _confirm_duplicate_record(self, record: Record, exclude_id: str | None = None, action_text: str = "save") -> bool:
        duplicate = self.data_manager.find_duplicate_record(record, exclude_id=exclude_id)
        if duplicate is None:
            return True
        should_continue = messagebox.askyesno(
            "Duplicate item",
            f"{record.field1} / {record.field2} already exists.\n\n{action_text.capitalize()} anyway?",
        )
        if not should_continue:
            focus_record_in_table(self.table, duplicate.id, self.load_records)
            return False
        return True

    def _apply_saved_record(self, record: Record, *, refresh_form_mode: bool = True) -> None:
        self.form.set_values(record.to_dict())
        if refresh_form_mode:
            self._update_form_mode_ui(record)
        self._refresh_saved_record(record)

    def _on_table_select(self, event=None) -> None:
        if self._suspend_table_select:
            return
        sel_id = self.table.get_selected_id()
        if not sel_id:
            return
        current_record_id = self.form.current_record_id
        if sel_id != current_record_id and self.form.is_dirty():
            if not self._confirm_discard_form_changes():
                self._suspend_table_select = True
                try:
                    restore_table_selection(self.table, current_record_id)
                finally:
                    self._suspend_table_select = False
                return
        record = self._record_actions.record_by_id(sel_id)
        if record is None:
            return
        self.form.set_values(record.to_dict())
        self._update_form_mode_ui(record)

    def _confirm_discard_form_changes(self) -> bool:
        if not self.form.is_dirty():
            return True
        return messagebox.askyesno(
            "Discard changes",
            "You have unsaved changes in the form.\n\nDiscard them?",
        )

    def _on_form_dirty_change(self, is_dirty: bool) -> None:
        self._update_form_mode_ui()

    def _update_form_mode_ui(self, record: Record | None = None) -> None:
        current_record_id = self.form.current_record_id
        selected_record_id = self.table.get_selected_id()
        dirty = self.form.is_dirty()
        self._delete_selected_button.config(state="normal" if selected_record_id else "disabled")
        if current_record_id is None:
            self._save_changes_button.config(state="disabled")
            text = "NEW ITEM MODE"
            bg = NEW_MODE_BANNER_BG
            fg = NEW_MODE_BANNER_FG
            if dirty:
                text = "NEW ITEM MODE (UNSAVED CHANGES)"
                bg = DIRTY_MODE_BANNER_BG
                fg = DIRTY_MODE_BANNER_FG
            self._set_form_mode_banner(text, bg, fg)
            return
        if record is None or record.id != current_record_id:
            record = self._record_actions.record_by_id(current_record_id)
        self._save_changes_button.config(state="normal")
        if record is None:
            text = "EDITING SELECTED ITEM"
            bg = EDIT_MODE_BANNER_BG
            fg = EDIT_MODE_BANNER_FG
            if dirty:
                text = f"{text} (UNSAVED CHANGES)"
                bg = DIRTY_MODE_BANNER_BG
                fg = DIRTY_MODE_BANNER_FG
            self._set_form_mode_banner(text, bg, fg)
            return
        left = (record.field1 or "").strip() or "(blank)"
        right = (record.field2 or "").strip() or "(blank)"
        text = f"EDITING: {left} / {right}"
        bg = EDIT_MODE_BANNER_BG
        fg = EDIT_MODE_BANNER_FG
        if dirty:
            text = f"{text} (UNSAVED CHANGES)"
            bg = DIRTY_MODE_BANNER_BG
            fg = DIRTY_MODE_BANNER_FG
        self._set_form_mode_banner(text, bg, fg)

    def _set_form_mode_banner(self, text: str, bg: str, fg: str) -> None:
        self._form_mode_var.set(text)
        self._form_mode_label.config(bg=bg, fg=fg)

    def _current_search_query(self) -> str:
        return self._search_entry.get().strip().lower()

    def _normalized_type_value(self, value: str | None) -> str:
        return (value or "").strip().lower()

    def _record_type_options(self, records: list[Record]) -> list[str]:
        return sorted(
            {
                (record.field1 or "").strip()
                for record in records
                if (record.field1 or "").strip()
            },
            key=str.lower,
        )

    def _apply_type_filter(self, records: list[Record]) -> list[Record]:
        if not self._type_filter_value:
            return records
        return [
            record
            for record in records
            if self._normalized_type_value(record.field1) == self._type_filter_value
        ]

    def _sort_records_for_display(self, records: list[Record]) -> list[Record]:
        return sorted(
            records,
            key=lambda record: record.created_at.timestamp() if record.created_at is not None else 0.0,
            reverse=True,
        )

    def _set_type_filter(self, value: str | None) -> None:
        self._type_filter_value = value
        self._type_filter_menu_value.set(value or "")
        self.load_records()

    def _show_type_filter_menu(self) -> None:
        records = self.data_manager.load_all()
        type_options = self._record_type_options(records)

        self._type_filter_menu.delete(0, "end")
        if type_options:
            for type_name in type_options:
                normalized_value = self._normalized_type_value(type_name)
                self._type_filter_menu.add_radiobutton(
                    label=type_name,
                    value=normalized_value,
                    variable=self._type_filter_menu_value,
                    command=lambda value=normalized_value: self._set_type_filter(value),
                )
        else:
            self._type_filter_menu.add_command(label="No types available", state="disabled")

        self._type_filter_menu.add_separator()
        self._type_filter_menu.add_command(label="Remove type filter", command=lambda: self._set_type_filter(None))

        try:
            self._type_filter_menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())
        except tk.TclError:
            LOGGER.debug("Unable to show type filter menu", exc_info=True)
        finally:
            try:
                self._type_filter_menu.grab_release()
            except tk.TclError:
                LOGGER.debug("Unable to release type filter menu grab", exc_info=True)

    def _filtered_records(self, records: list[Record]) -> list[Record]:
        return filtered_records(self._apply_type_filter(records), self._current_search_query())

    def _record_matches_current_filter(self, record: Record) -> bool:
        query = self._current_search_query()
        filtered_records_for_query = self._apply_type_filter(self.data_manager.load_all())
        if self._type_filter_value and self._normalized_type_value(record.field1) != self._type_filter_value:
            return False
        return record_matches_query(record, query, filtered_records_for_query)

    def _set_gp_highlight_threshold(self, threshold: float | None) -> None:
        self.table.set_gp_highlight_threshold(threshold)
        try:
            self._settings.save_gp_highlight_threshold(threshold)
        except (OSError, TypeError, ValueError) as exc:
            LOGGER.warning("Unable to persist GP highlight threshold", exc_info=True)
            self._warn_settings_save_failure("the GP highlight preference", exc)

    def _prompt_custom_gp_highlight_threshold(self) -> None:
        current_threshold = self.table.get_gp_highlight_threshold()
        initial_value = "" if current_threshold is None else f"{current_threshold:g}"
        response = simpledialog.askstring(
            "Highlight GP rows",
            "Highlight rows with GP smaller than what percentage?\n\nEnter a number like 70 or 70.5.\nLeave blank to clear highlighting.",
            parent=self,
            initialvalue=initial_value,
        )
        if response is None:
            return
        text = response.strip().rstrip("%")
        if not text:
            self._set_gp_highlight_threshold(None)
            return
        try:
            threshold = float(text)
        except ValueError:
            messagebox.showerror("Invalid GP threshold", "Enter a GP percentage like 70 or 70.5.")
            return
        if threshold < 0 or threshold > 100:
            messagebox.showerror("Invalid GP threshold", "GP highlight threshold must be between 0 and 100.")
            return
        self._set_gp_highlight_threshold(threshold)

    def _show_gp_highlight_menu(self) -> None:
        try:
            self._gp_highlight_menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())
        finally:
            try:
                self._gp_highlight_menu.grab_release()
            except tk.TclError:
                LOGGER.debug("Unable to release GP highlight menu grab", exc_info=True)

    def _on_table_heading_click(self, column_name: str) -> None:
        if column_name == "gp":
            self._show_gp_highlight_menu()
            return
        if column_name == "field1":
            self._show_type_filter_menu()

    def _refresh_saved_record(self, record: Record) -> None:
        still_visible = self._record_matches_current_filter(record)
        previous_index = next((index for index, existing in enumerate(self._displayed_records) if existing.id == record.id), None)
        self._displayed_records = [existing for existing in self._displayed_records if existing.id != record.id]

        if still_visible:
            if self.table.exists(record.id):
                if previous_index is not None and previous_index <= len(self._displayed_records):
                    self._displayed_records.insert(previous_index, record)
                else:
                    self._displayed_records.append(record)
                self.table.update_record(record)
            else:
                self.load_records()
                return
            try:
                self.table.selection_set(record.id)
            except tk.TclError:
                LOGGER.debug("Unable to restore table selection for %s", record.id, exc_info=True)
            return

        if self.table.exists(record.id):
            try:
                self.table.delete(record.id)
            except tk.TclError:
                LOGGER.debug("Unable to remove hidden record %s from the table; reloading rows", record.id, exc_info=True)
                self.load_records()

    def load_records(self) -> None:
        try:
            records = self.data_manager.load_all()
        except (OSError, RuntimeError, ValueError) as exc:
            LOGGER.warning("Unable to load records", exc_info=True)
            self._displayed_records = []
            self.table.load([])
            self._update_form_mode_ui()
            self._show_storage_error("Storage unavailable", "load records", self.data_manager.path, exc)
            return
        displayed = self._sort_records_for_display(self._filtered_records(records))
        self._displayed_records = displayed
        self.table.load(displayed)
        self._update_form_mode_ui()

    def on_search(self) -> None:
        self.load_records()

    def on_clear_search(self) -> None:
        self._search_entry.delete(0, "end")
        self.load_records()

    def on_new_item(self) -> None:
        if not self._confirm_discard_form_changes():
            return
        self._reset_to_new_item()

    def _reset_to_new_item(self) -> None:
        self.form.clear()
        clear_table_selection(self.table)
        self._update_form_mode_ui()
        first_field = self.form.entries.get("field1")
        focus_widget(first_field)

    def on_form_submit(self) -> None:
        if self.form.current_record_id:
            self.on_save_changes()
            return
        self.on_add()

    def on_add(self) -> None:
        recalc_form_field6(self.form, "adding a new item")
        data = self.form.get_values()
        rec = self._record_actions.build_record_or_show_error(data)
        if rec is None:
            return

        if not self._confirm_duplicate_record(rec, action_text="add another record"):
            return
        self._record_actions.save_new_record(rec)

    def on_edit(self) -> None:
        record = self._record_actions.record_or_show_missing_error(
            self.table.get_selected_id(),
            selection_message="Please select a record to edit.",
        )
        if record is None:
            return
        self.form.set_values(record.to_dict())
        self._update_form_mode_ui(record)
        first_field = self.form.entries.get("field1")
        focus_widget(first_field)

    def on_save_changes(self) -> None:
        record = self._record_actions.record_or_show_missing_error(
            self.form.current_record_id or self.table.get_selected_id(),
            selection_message="Please select a record to edit.",
        )
        if record is None:
            return
        recalc_form_field6(self.form, "saving changes")
        values = self.form.get_values()
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
        sel_id = self._record_actions.record_id_or_show_selection_error(
            self.table.get_selected_id(),
            "Please select a record to delete.",
        )
        if sel_id is None:
            return
        if self.form.is_dirty() and not self._confirm_discard_form_changes():
            return
        if messagebox.askyesno("Confirm", "Delete selected record?"):
            self._record_actions.delete_record(
                sel_id,
                backup_action="deleting this record",
                error_title="Delete failed",
                error_action="delete the selected record",
            )

    def on_close(self) -> None:
        if not self._confirm_discard_form_changes():
            return
        self.destroy()

    def _csv_preview_geometry(self) -> tuple[int, int]:
        self.update_idletasks()
        return max(self.table.winfo_width(), 900), max(self.table.winfo_height(), 500)

    def _update_open_last_csv_button_state(self) -> None:
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
                command=lambda value=saved_path: self.on_open_recent_csv_preview(value),
            )

    @property
    def _csv_preview_status_var(self) -> tk.StringVar:
        return self._csv_preview_status.message_var

    @property
    def _csv_preview_status_dialog(self) -> tk.Toplevel | None:
        return self._csv_preview_status.dialog

    def _open_csv_preview_path(
        self,
        csv_path: Path,
        *,
        remember: bool,
        has_header_row: bool,
        status_message: str = "Processing CSV...",
    ) -> None:
        self._set_csv_preview_status(status_message)
        width, height = self._csv_preview_geometry()
        try:
            open_csv_preview_dialog(self, csv_path, width=width, height=height, has_header_row=has_header_row)
        except CsvPreviewError as exc:
            messagebox.showerror("CSV preview unavailable", str(exc))
            return
        finally:
            self._clear_csv_preview_status()

        if remember:
            try:
                self._settings.remember_csv_preview_path(str(csv_path))
            except (OSError, TypeError, ValueError) as exc:
                LOGGER.warning("Unable to persist recent CSV preview paths", exc_info=True)
                self._warn_settings_save_failure("the recent CSV preview list", exc)
            self._update_open_last_csv_button_state()

    def _set_csv_preview_status(self, message: str) -> None:
        self._csv_preview_status.show(message)

    def _clear_csv_preview_status(self) -> None:
        self._csv_preview_status.clear()

    def _resolve_csv_preview_has_header_row(self, csv_path: Path, *, prompt: bool) -> bool | None:
        normalized_path = str(csv_path)
        saved_choice = self._settings.load_csv_preview_has_header_row(normalized_path)
        if saved_choice is not None and not prompt:
            return saved_choice

        remembered_text = ""
        if saved_choice is not None:
            remembered_text = "\n\nRemembered choice for this file: first row is {}headers.".format("" if saved_choice else "not ")
        choice = messagebox.askyesnocancel(
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
        path = filedialog.askopenfilename(
            title="Open CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        has_header_row = self._resolve_csv_preview_has_header_row(Path(path), prompt=True)
        if has_header_row is None:
            return
        self._open_csv_preview_path(Path(path), remember=True, has_header_row=has_header_row, status_message="Processing CSV...")

    def on_open_last_csv_preview(self) -> None:
        recent_paths = self._settings.load_csv_preview_recent_paths()
        if not recent_paths:
            self._update_open_last_csv_button_state()
            return
        csv_path = Path(recent_paths[0])
        if not csv_path.exists():
            messagebox.showerror("CSV preview unavailable", "The remembered CSV file could not be found.")
            try:
                self._settings.save_csv_preview_recent_paths([path for path in recent_paths if path != str(csv_path)])
            except (OSError, TypeError, ValueError) as exc:
                LOGGER.warning("Unable to clear missing remembered CSV preview path", exc_info=True)
                self._warn_settings_save_failure("the recent CSV preview list", exc)
            self._update_open_last_csv_button_state()
            return
        has_header_row = self._resolve_csv_preview_has_header_row(csv_path, prompt=False)
        if has_header_row is None:
            return
        self._open_csv_preview_path(csv_path, remember=True, has_header_row=has_header_row, status_message="Processing last CSV...")

    def on_open_recent_csv_preview(self, saved_path: str) -> None:
        csv_path = Path(saved_path)
        if not csv_path.exists():
            messagebox.showerror("CSV preview unavailable", "The selected recent CSV file could not be found.")
            try:
                self._settings.save_csv_preview_recent_paths(
                    [path for path in self._settings.load_csv_preview_recent_paths() if path != saved_path]
                )
            except (OSError, TypeError, ValueError) as exc:
                LOGGER.warning("Unable to clear missing recent CSV preview path", exc_info=True)
                self._warn_settings_save_failure("the recent CSV preview list", exc)
            self._update_open_last_csv_button_state()
            return
        has_header_row = self._resolve_csv_preview_has_header_row(csv_path, prompt=False)
        if has_header_row is None:
            return
        self._open_csv_preview_path(csv_path, remember=True, has_header_row=has_header_row, status_message="Processing recent CSV...")

    def on_export(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        if not path:
            return
        try:
            if self._displayed_records:
                tmp = CSVDataManager(Path(path))
                tmp._write_all(self._displayed_records)
            else:
                self.data_manager.export_csv(Path(path))
            messagebox.showinfo("Export", f"Exported to {path}")
        except (OSError, RuntimeError, ValueError) as exc:
            self._show_storage_error("Export failed", "export records", Path(path), exc)

    def on_manage_backups(self) -> None:
        return open_manage_backups_dialog(self, self.data_manager, on_restored=self.load_records)

    def on_labels_changed(self, labels: Sequence[str]) -> None:
        self.table.update_column_labels(labels)

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

    def _column_label(self, column: str) -> str:
        if column.startswith("field") and column[5:].isdigit():
            idx = int(column[5:]) - 1
            if 0 <= idx < len(self.form.labels):
                return self.form.labels[idx]
        return METRIC_LABELS.get(column, column)

    def on_manage_columns(self) -> None:
        win = tk.Toplevel(self)
        win.title("Columns")
        win.geometry("320x360")

        body = ttk.Frame(win)
        body.pack(fill="both", expand=True, padx=10, pady=10)

        visible = set(self.table.get_visible_columns())
        vars_by_column: dict[str, tk.BooleanVar] = {}
        for row, column in enumerate(self.table.get_column_order()):
            var = tk.BooleanVar(value=column in visible)
            vars_by_column[column] = var
            ttk.Checkbutton(body, text=self._column_label(column), variable=var).grid(row=row, column=0, sticky="w", pady=2)

        def apply_columns() -> None:
            selected = [column for column in self.table.get_column_order() if vars_by_column[column].get()]
            if not selected:
                messagebox.showinfo("Columns", "At least one column must stay visible.")
                return
            self.table.set_visible_columns(selected)
            win.destroy()

        buttons = ttk.Frame(win)
        buttons.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(buttons, text="Apply", command=apply_columns).pack(side="right", padx=4)
        ttk.Button(buttons, text="Cancel", command=win.destroy).pack(side="right", padx=4)

    def _on_table_commit(self, record_id: str, col: str, new_value: str) -> None:
        try:
            record = self._record_actions.record_by_id(record_id)
            if record is None:
                messagebox.showerror("Error", "Record not found")
                return

            data = record.to_dict()
            data[col] = new_value

            if col in ("field3", "field5"):
                data["field6"] = calculate_field6(data.get("field3"), data.get("field5"))

            updated = self._record_actions.build_record_or_show_error(data)
            if updated is None:
                return
            self._record_actions.save_existing_record(
                record,
                updated,
                duplicate_action_text="save this edit",
                backup_action="saving this inline edit",
                error_title="Edit failed",
                error_action="save the inline edit",
                refresh_form_mode=False,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            self._show_storage_error("Edit failed", "save the inline edit", self.data_manager.path, exc)

    def _on_row_right_click(self, event) -> None:
        try:
            row = self.table.identify_row(event.y)
            if row:
                self.table.selection_set(row)
                self._on_table_select()
                self.row_menu.post(event.x_root, event.y_root)
        except tk.TclError:
            LOGGER.debug("Unable to open row context menu", exc_info=True)

    def _copy_selected_id_to_clipboard(self) -> None:
        try:
            self.table.copy_selected_id_to_clipboard()
        except tk.TclError:
            LOGGER.debug("Unable to copy selected id to clipboard", exc_info=True)

    def run(self) -> None:
        self.mainloop()