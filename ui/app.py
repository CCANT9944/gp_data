from __future__ import annotations

import logging
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Sequence

from ..data_manager import CSVDataManager, DataManager
from ..models import Record, calculate_field6
from ..settings import load_settings, save_column_order, save_column_widths, save_gp_highlight_threshold, save_visible_columns
from .backup_dialog import open_manage_backups_dialog
from .form import InputForm
from .record_logic import filtered_records, record_matches_query
from .table import METRIC_LABELS, RecordTable


NEW_MODE_BANNER_BG = "#e7f1ff"
NEW_MODE_BANNER_FG = "#0b4f8a"
EDIT_MODE_BANNER_BG = "#fff1c9"
EDIT_MODE_BANNER_FG = "#7a4b00"
GP_HIGHLIGHT_PRESETS = (50.0, 60.0, 70.0, 80.0)
LOGGER = logging.getLogger(__name__)


class GPDataApp(tk.Tk):
    def __init__(self, storage_path: Path | None = None):
        super().__init__()
        self.title("GP Data Manager")
        self.geometry("1200x520")

        self.data_manager = DataManager(storage_path)
        self._displayed_records: list[Record] = []
        app_settings = load_settings()
        labels = app_settings["labels"]
        column_order = app_settings["column_order"]
        column_widths = app_settings["column_widths"]
        visible_columns = app_settings["visible_columns"]
        gp_highlight_threshold = app_settings["gp_highlight_threshold"]

        container = ttk.Frame(self)
        container.pack(fill="both", expand=True, padx=8, pady=8)

        left = ttk.Frame(container)
        left.pack(side="left", fill="y", padx=(0, 8))
        self.form = InputForm(left, labels=labels, on_rename=self.on_labels_changed, on_submit=self.on_form_submit)
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

        ttk.Button(controls, text="Manage backups", command=self.on_manage_backups).pack(side="right", padx=4)
        ttk.Button(controls, text="Export CSV", command=self.on_export).pack(side="right", padx=4)

        self._search_entry = ttk.Entry(controls, width=20)
        self._search_entry.bind("<KeyRelease>", lambda e: self.on_search())
        ttk.Button(controls, text="Clear", command=self.on_clear_search).pack(side="right", padx=4)
        self._search_entry.pack(side="right", padx=4)
        ttk.Label(controls, text="Search").pack(side="right", padx=(4, 0))

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
        self.table.bind("<<TreeviewSelect>>", self._on_table_select)
        self.table.bind("<Button-3>", self._on_row_right_click)

        self._suspend_table_select = False
        self.table.set_gp_highlight_threshold(gp_highlight_threshold)
        self._update_form_mode_ui()
        self.load_records()

    def _record_by_id(self, record_id: str) -> Record | None:
        records = self.data_manager.load_all()
        return next((record for record in records if record.id == record_id), None)

    def _confirm_duplicate_record(self, record: Record, exclude_id: str | None = None, action_text: str = "save") -> bool:
        duplicate = self.data_manager.find_duplicate_record(record, exclude_id=exclude_id)
        if duplicate is None:
            return True
        should_continue = messagebox.askyesno(
            "Duplicate item",
            f"{record.field1} / {record.field2} already exists.\n\n{action_text.capitalize()} anyway?",
        )
        if not should_continue:
            self._focus_record(duplicate.id)
            return False
        return True

    def _focus_record(self, record_id: str) -> None:
        if not self.table.exists(record_id):
            self.load_records()
        if not self.table.exists(record_id):
            return
        try:
            self.table.selection_set(record_id)
            self.table.see(record_id)
        except tk.TclError:
            LOGGER.debug("Unable to focus record %s in the table", record_id, exc_info=True)

    def _focus_widget(self, widget: tk.Misc | None) -> None:
        if widget is None:
            return
        try:
            widget.focus_set()
            widget.focus_force()
        except tk.TclError:
            try:
                widget.focus_set()
            except tk.TclError:
                LOGGER.debug("Unable to focus widget", exc_info=True)

    def _recalc_form_field6(self, context: str) -> None:
        try:
            self.form.recalc_field6()
        except tk.TclError:
            LOGGER.debug("Unable to recalculate field6 while %s", context, exc_info=True)

    def _on_table_select(self, event=None) -> None:
        if self._suspend_table_select:
            return
        sel_id = self.table.get_selected_id()
        if not sel_id:
            return
        current_record_id = self.form.current_record_id
        if sel_id != current_record_id and self.form.is_dirty():
            if not self._confirm_discard_form_changes():
                self._restore_table_selection(current_record_id)
                return
        record = self._record_by_id(sel_id)
        if record is None:
            return
        self.form.set_values(record.to_dict())
        self._update_form_mode_ui(record)

    def _restore_table_selection(self, record_id: str | None) -> None:
        self._suspend_table_select = True
        try:
            selection = self.table.selection()
            if selection:
                self.table.selection_remove(*selection)
            if record_id:
                self.table.selection_set(record_id)
                self.table.see(record_id)
        finally:
            self._suspend_table_select = False

    def _confirm_discard_form_changes(self) -> bool:
        if not self.form.is_dirty():
            return True
        return messagebox.askyesno(
            "Discard changes",
            "You have unsaved changes in the form.\n\nDiscard them?",
        )

    def _update_form_mode_ui(self, record: Record | None = None) -> None:
        current_record_id = self.form.current_record_id
        selected_record_id = self.table.get_selected_id()
        self._delete_selected_button.config(state="normal" if selected_record_id else "disabled")
        if current_record_id is None:
            self._save_changes_button.config(state="disabled")
            self._set_form_mode_banner("NEW ITEM MODE", NEW_MODE_BANNER_BG, NEW_MODE_BANNER_FG)
            return
        if record is None or record.id != current_record_id:
            record = self._record_by_id(current_record_id)
        self._save_changes_button.config(state="normal")
        if record is None:
            self._set_form_mode_banner("EDITING SELECTED ITEM", EDIT_MODE_BANNER_BG, EDIT_MODE_BANNER_FG)
            return
        left = (record.field1 or "").strip() or "(blank)"
        right = (record.field2 or "").strip() or "(blank)"
        self._set_form_mode_banner(f"EDITING: {left} / {right}", EDIT_MODE_BANNER_BG, EDIT_MODE_BANNER_FG)

    def _set_form_mode_banner(self, text: str, bg: str, fg: str) -> None:
        self._form_mode_var.set(text)
        self._form_mode_label.config(bg=bg, fg=fg)

    def _current_search_query(self) -> str:
        return self._search_entry.get().strip().lower()

    def _sort_records_for_display(self, records: list[Record]) -> list[Record]:
        return sorted(
            records,
            key=lambda record: record.created_at.timestamp() if record.created_at is not None else 0.0,
            reverse=True,
        )

    def _filtered_records(self, records: list[Record]) -> list[Record]:
        return filtered_records(records, self._current_search_query())

    def _record_matches_current_filter(self, record: Record) -> bool:
        query = self._current_search_query()
        return record_matches_query(record, query, self.data_manager.load_all())

    def _set_gp_highlight_threshold(self, threshold: float | None) -> None:
        self.table.set_gp_highlight_threshold(threshold)
        try:
            save_gp_highlight_threshold(threshold)
        except (OSError, TypeError, ValueError):
            LOGGER.warning("Unable to persist GP highlight threshold", exc_info=True)

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
        if column_name != "gp":
            return
        self._show_gp_highlight_menu()

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
        records = self.data_manager.load_all()
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
        try:
            self.table.selection_remove(*self.table.selection())
        except tk.TclError:
            LOGGER.debug("Unable to clear table selection", exc_info=True)
        self._update_form_mode_ui()
        first_field = self.form.entries.get("field1")
        self._focus_widget(first_field)

    def on_form_submit(self) -> None:
        if self.form.current_record_id:
            self.on_save_changes()
            return
        self.on_add()

    def on_add(self) -> None:
        self._recalc_form_field6("adding a new item")
        data = self.form.get_values()
        try:
            rec = Record(**data)
        except Exception as exc:
            messagebox.showerror("Validation error", str(exc))
            return

        if not self._confirm_duplicate_record(rec, action_text="add another record"):
            return

        try:
            self.data_manager.create_timestamped_backup()
        except OSError:
            LOGGER.warning("Unable to create a backup before adding a record", exc_info=True)
        self.data_manager.save(rec)
        self.load_records()
        self._reset_to_new_item()

    def on_edit(self) -> None:
        sel_id = self.table.get_selected_id()
        if not sel_id:
            messagebox.showinfo("Select", "Please select a record to edit.")
            return
        record = self._record_by_id(sel_id)
        if not record:
            messagebox.showerror("Error", "Record not found")
            return
        self.form.set_values(record.to_dict())
        self._update_form_mode_ui(record)
        first_field = self.form.entries.get("field1")
        self._focus_widget(first_field)

    def on_save_changes(self) -> None:
        record_id = self.form.current_record_id or self.table.get_selected_id()
        if not record_id:
            messagebox.showinfo("Select", "Please select a record to edit.")
            return
        record = self._record_by_id(record_id)
        if not record:
            messagebox.showerror("Error", "Record not found")
            return
        self._recalc_form_field6("saving changes")
        values = self.form.get_values()
        try:
            updated = Record(id=record.id, created_at=record.created_at, **values)
        except Exception as exc:
            messagebox.showerror("Validation error", str(exc))
            return
        if not self._confirm_duplicate_record(updated, exclude_id=record.id, action_text="save this edit"):
            return
        saved = self.data_manager.update(record.id, updated)
        self.form.set_values(saved.to_dict())
        self._update_form_mode_ui(saved)
        self._refresh_saved_record(saved)

    def on_delete(self) -> None:
        sel_id = self.table.get_selected_id()
        if not sel_id:
            messagebox.showinfo("Select", "Please select a record to delete.")
            return
        if messagebox.askyesno("Confirm", "Delete selected record?"):
            self.data_manager.delete(sel_id)
            self.load_records()
            self._reset_to_new_item()

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
        except Exception as exc:
            messagebox.showerror("Export failed", str(exc))

    def on_manage_backups(self) -> None:
        return open_manage_backups_dialog(self, self.data_manager, on_restored=self.load_records)

    def on_labels_changed(self, labels: Sequence[str]) -> None:
        try:
            self.table.update_column_labels(labels)
        except tk.TclError:
            LOGGER.debug("Unable to update table column labels", exc_info=True)

    def on_column_order_changed(self, columns: Sequence[str]) -> None:
        try:
            save_column_order(list(columns))
        except (OSError, TypeError, ValueError):
            LOGGER.warning("Unable to persist column order", exc_info=True)

    def on_column_widths_changed(self, column_widths: dict[str, int]) -> None:
        try:
            save_column_widths(column_widths)
        except (OSError, TypeError, ValueError):
            LOGGER.warning("Unable to persist column widths", exc_info=True)

    def on_visible_columns_changed(self, visible_columns: Sequence[str]) -> None:
        try:
            save_visible_columns(list(visible_columns))
        except (OSError, TypeError, ValueError):
            LOGGER.warning("Unable to persist visible columns", exc_info=True)

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
            records = self.data_manager.load_all()
            record = next((r for r in records if r.id == record_id), None)
            if record is None:
                messagebox.showerror("Error", "Record not found")
                return

            data = record.to_dict()
            data[col] = new_value

            if col in ("field3", "field5"):
                data["field6"] = calculate_field6(data.get("field3"), data.get("field5"))

            try:
                updated = Record(**data)
            except Exception as exc:
                messagebox.showerror("Validation error", str(exc))
                return
            if not self._confirm_duplicate_record(updated, exclude_id=record_id, action_text="save this edit"):
                return

            try:
                self.data_manager.create_timestamped_backup()
            except OSError:
                LOGGER.warning("Unable to create a backup before inline edit commit", exc_info=True)

            saved = self.data_manager.update(record_id, updated)
            self.form.set_values(saved.to_dict())
            self._refresh_saved_record(saved)
        except Exception as exc:
            messagebox.showerror("Error", str(exc))

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