from __future__ import annotations

import logging
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog
from typing import Sequence

from ..data_manager import DataManager
from ..models import Record
from ..settings import SettingsStore
from .app_layout import build_app_layout
from .app_csv_preview_controller import _CsvPreviewLaunchController
from .app_form_mode_controller import _FormModeController
from .app_record_controllers import _RecordFormActionsController, _RecordListController
from .app_storage_controller import _AppStorageActionsController
from .app_table_display_controller import _TableDisplayController
from .backup_dialog import open_manage_backups_dialog
from .csv_preview import CsvPreviewError, open_csv_preview_dialog
from .record_actions import RecordActions
from .storage_feedback import describe_backup_failure, describe_startup_storage_issue, describe_storage_error
from .view_helpers import focus_record_in_table


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
        layout = build_app_layout(
            self,
            labels=labels,
            column_order=column_order,
            column_widths=column_widths,
            visible_columns=visible_columns,
            gp_highlight_presets=GP_HIGHLIGHT_PRESETS,
            save_labels_callback=self._settings.save_labels,
            on_labels_changed=self.on_labels_changed,
            on_form_submit=self.on_form_submit,
            on_table_commit=self._on_table_commit,
            on_column_order_changed=self.on_column_order_changed,
            on_column_widths_changed=self.on_column_widths_changed,
            on_visible_columns_changed=self.on_visible_columns_changed,
            on_heading_click=self._on_table_heading_click,
            on_new_item=self.on_new_item,
            on_save_changes=self.on_save_changes,
            on_delete=self.on_delete,
            on_manage_columns=self.on_manage_columns,
            on_open_csv_preview=self.on_open_csv_preview,
            on_open_last_csv_preview=self.on_open_last_csv_preview,
            on_manage_backups=self.on_manage_backups,
            on_export=self.on_export,
            on_clear_search=self.on_clear_search,
            on_search=self.on_search,
            on_edit=self.on_edit,
            on_copy_selected_id_to_clipboard=self._copy_selected_id_to_clipboard,
            on_set_gp_highlight_threshold=self._set_gp_highlight_threshold,
            on_prompt_custom_gp_highlight_threshold=self._prompt_custom_gp_highlight_threshold,
        )
        self._apply_layout(layout)
        self._build_runtime_controllers()
        self._bind_runtime_events()
        self._run_startup_sequence(gp_highlight_threshold)

    def _apply_layout(self, layout) -> None:
        self.form = layout.form
        self.table = layout.table
        self._form_mode_var = layout.form_mode_var
        self._form_mode_label = layout.form_mode_label
        self._save_changes_button = layout.save_changes_button
        self._delete_selected_button = layout.delete_selected_button
        self._open_last_csv_button = layout.open_last_csv_button
        self._open_recent_csv_button = layout.open_recent_csv_button
        self._recent_csv_menu = layout.recent_csv_menu
        self._search_entry = layout.search_entry
        self._csv_preview_status = layout.csv_preview_status
        self.row_menu = layout.row_menu
        self._gp_highlight_menu = layout.gp_highlight_menu
        self._type_filter_menu = layout.type_filter_menu

    def _build_runtime_controllers(self) -> None:
        self._csv_preview_launch = _CsvPreviewLaunchController(
            self,
            self._settings,
            self._open_last_csv_button,
            self._open_recent_csv_button,
            self._recent_csv_menu,
            self._warn_settings_save_failure,
            self._csv_preview_geometry,
            self._set_csv_preview_status,
            self._clear_csv_preview_status,
            lambda: filedialog.askopenfilename(
                title="Open CSV",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            ),
            lambda title, message: messagebox.askyesnocancel(title, message),
            lambda title, message: messagebox.showerror(title, message),
            lambda csv_path, width, height, has_header_row: open_csv_preview_dialog(
                self,
                csv_path,
                width=width,
                height=height,
                has_header_row=has_header_row,
            ),
            CsvPreviewError,
            self.on_open_recent_csv_preview,
        )
        self._storage_actions = _AppStorageActionsController(
            self,
            self.data_manager,
            self._show_storage_error,
            self.load_records,
            lambda: filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")]),
            lambda title, message: messagebox.showinfo(title, message),
            lambda: open_manage_backups_dialog(self, self.data_manager, on_restored=self.load_records),
        )
        self._form_mode = _FormModeController(
            self.form,
            self.table,
            self._form_mode_var,
            self._form_mode_label,
            self._save_changes_button,
            self._delete_selected_button,
            self._record_actions.record_by_id,
            NEW_MODE_BANNER_BG,
            NEW_MODE_BANNER_FG,
            EDIT_MODE_BANNER_BG,
            EDIT_MODE_BANNER_FG,
            DIRTY_MODE_BANNER_BG,
            DIRTY_MODE_BANNER_FG,
        )
        self.form.on_dirty_change = self._on_form_dirty_change
        self._table_display = _TableDisplayController(
            self,
            self._settings,
            self.data_manager,
            self.form,
            self.table,
            self._gp_highlight_menu,
            self._type_filter_menu,
            self._type_filter_menu_value,
            self._warn_settings_save_failure,
            self.load_records,
            self._current_search_query,
            lambda *args, **kwargs: simpledialog.askstring(*args, **kwargs),
            lambda title, message: messagebox.askyesno(title, message),
            lambda title, message: messagebox.showerror(title, message),
            lambda title, message: messagebox.showinfo(title, message),
            self._record_actions.bulk_rename_type,
        )
        self._record_list = _RecordListController(
            self.data_manager,
            self.form,
            self.table,
            self._search_entry,
            self._record_actions,
            self._show_storage_error,
            self._update_form_mode_ui,
            self._confirm_discard_form_changes,
            self._sort_records_for_display,
            self._filtered_records,
            self._record_matches_current_filter,
        )
        self._record_form_actions = _RecordFormActionsController(
            self.form,
            self.table,
            self._record_actions,
            self._confirm_discard_form_changes,
            self._confirm_duplicate_record,
            self._update_form_mode_ui,
            lambda title, message: messagebox.askyesno(title, message),
        )

    def _bind_runtime_events(self) -> None:
        self.table.bind("<<TreeviewSelect>>", self._on_table_select)
        self.table.bind("<Button-3>", self._on_row_right_click)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _run_startup_sequence(self, gp_highlight_threshold: float | None) -> None:
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
        self._record_list.on_table_select(event)

    def _confirm_discard_form_changes(self) -> bool:
        if not self.form.is_dirty():
            return True
        return messagebox.askyesno(
            "Discard changes",
            "You have unsaved changes in the form.\n\nDiscard them?",
        )

    def _on_form_dirty_change(self, is_dirty: bool) -> None:
        self._form_mode.on_form_dirty_change(is_dirty)

    def _update_form_mode_ui(self, record: Record | None = None) -> None:
        self._form_mode.update(record)

    def _set_form_mode_banner(self, text: str, bg: str, fg: str) -> None:
        self._form_mode_var.set(text)
        self._form_mode_label.config(bg=bg, fg=fg)

    def _current_search_query(self) -> str:
        return self._search_entry.get().strip().lower()

    def _normalized_type_value(self, value: str | None) -> str:
        return self._table_display.normalized_type_value(value)

    def _record_type_options(self, records: list[Record]) -> list[str]:
        return self._table_display.record_type_options(records)

    def _apply_type_filter(self, records: list[Record]) -> list[Record]:
        return self._table_display.apply_type_filter(records)

    def _sort_records_for_display(self, records: list[Record]) -> list[Record]:
        return sorted(
            records,
            key=lambda record: record.created_at.timestamp() if record.created_at is not None else 0.0,
            reverse=True,
        )

    def _set_type_filter(self, value: str | None) -> None:
        self._table_display.set_type_filter(value)

    def _show_type_filter_menu(self) -> None:
        self._table_display.show_type_filter_menu()

    def _filtered_records(self, records: list[Record]) -> list[Record]:
        return self._table_display.filtered_records(records)

    def _record_matches_current_filter(self, record: Record) -> bool:
        return self._table_display.record_matches_current_filter(record)

    def _set_gp_highlight_threshold(self, threshold: float | None) -> None:
        self._table_display.set_gp_highlight_threshold(threshold)

    def _prompt_custom_gp_highlight_threshold(self) -> None:
        self._table_display.prompt_custom_gp_highlight_threshold()

    def _show_gp_highlight_menu(self) -> None:
        self._table_display.show_gp_highlight_menu()

    def _on_table_heading_click(self, column_name: str) -> None:
        if column_name == "gp":
            self._show_gp_highlight_menu()
            return
        if column_name == "field1":
            self._show_type_filter_menu()

    def _refresh_saved_record(self, record: Record) -> None:
        self._record_list.refresh_saved_record(record)

    def load_records(self) -> None:
        self._record_list.load_records()

    def on_search(self) -> None:
        self._record_list.on_search()

    def on_clear_search(self) -> None:
        self._record_list.on_clear_search()

    def on_new_item(self) -> None:
        self._record_form_actions.on_new_item()

    def _reset_to_new_item(self) -> None:
        self._record_form_actions.reset_to_new_item()

    def on_form_submit(self) -> None:
        self._record_form_actions.on_form_submit()

    def on_add(self) -> None:
        self._record_form_actions.on_add()

    def on_edit(self) -> None:
        self._record_form_actions.on_edit()

    def on_save_changes(self) -> None:
        self._record_form_actions.on_save_changes()

    def on_delete(self) -> None:
        self._record_form_actions.on_delete()

    def on_close(self) -> None:
        if not self._confirm_discard_form_changes():
            return
        self.destroy()

    def _csv_preview_geometry(self) -> tuple[int, int]:
        self.update_idletasks()
        return max(self.table.winfo_width(), 900), max(self.table.winfo_height(), 500)

    def _update_open_last_csv_button_state(self) -> None:
        self._csv_preview_launch.update_open_last_csv_button_state()

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
        self._csv_preview_launch.open_csv_preview_path(
            csv_path,
            remember=remember,
            has_header_row=has_header_row,
            status_message=status_message,
        )

    def _set_csv_preview_status(self, message: str) -> None:
        self._csv_preview_status.show(message)

    def _clear_csv_preview_status(self) -> None:
        self._csv_preview_status.clear()

    def _resolve_csv_preview_has_header_row(self, csv_path: Path, *, prompt: bool) -> bool | None:
        return self._csv_preview_launch.resolve_csv_preview_has_header_row(csv_path, prompt=prompt)

    def on_open_csv_preview(self) -> None:
        self._csv_preview_launch.on_open_csv_preview()

    def on_open_last_csv_preview(self) -> None:
        self._csv_preview_launch.on_open_last_csv_preview()

    def on_open_recent_csv_preview(self, saved_path: str) -> None:
        self._csv_preview_launch.on_open_recent_csv_preview(saved_path)

    def on_export(self) -> None:
        self._storage_actions.on_export(self._record_list.displayed_records)

    def on_manage_backups(self) -> None:
        return self._storage_actions.on_manage_backups()

    def on_labels_changed(self, labels: Sequence[str]) -> None:
        self._table_display.on_labels_changed(labels)

    def on_column_order_changed(self, columns: Sequence[str]) -> None:
        self._table_display.on_column_order_changed(columns)

    def on_column_widths_changed(self, column_widths: dict[str, int]) -> None:
        self._table_display.on_column_widths_changed(column_widths)

    def on_visible_columns_changed(self, visible_columns: Sequence[str]) -> None:
        self._table_display.on_visible_columns_changed(visible_columns)

    def _column_label(self, column: str) -> str:
        return self._table_display.column_label(column)

    def on_manage_columns(self) -> None:
        self._table_display.on_manage_columns()

    def _on_table_commit(self, record_id: str, col: str, new_value: str) -> None:
        self._record_actions.save_inline_edit(record_id, col, new_value)

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