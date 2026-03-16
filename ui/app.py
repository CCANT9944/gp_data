from __future__ import annotations

import re
import sqlite3
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Sequence

from ..data_manager import CSVDataManager, DataManager
from ..models import Record, calculate_field6
from ..settings import load_settings, save_column_order, save_column_widths, save_visible_columns
from .form import InputForm
from .table import METRIC_LABELS, RecordTable


def _format_backup_label(path: Path) -> str:
    name = path.name
    if not name.endswith(".bak"):
        return name
    stem = name[:-4]
    base, sep, stamp = stem.rpartition(".")
    if not sep:
        return name
    try:
        dt = datetime.strptime(stamp, "%Y%m%dT%H%M%S%fZ")
    except ValueError:
        return name
    return f"{dt.strftime('%Y-%m-%d %H:%M:%S.%f')} UTC - {base}"


def _is_sqlite_backup(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(16) == b"SQLite format 3\x00"
    except OSError:
        return False


def _preview_metadata(path: Path) -> list[str]:
    stat = path.stat()
    modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    return [
        f"Name: {path.name}",
        f"Saved: {modified}",
        f"Size: {stat.st_size:,} bytes",
    ]


def _build_sqlite_backup_preview(path: Path) -> str:
    lines = _preview_metadata(path)
    lines.append("Type: SQLite backup")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row[0] for row in cur.fetchall()]
        lines.append(f"Tables: {', '.join(tables) if tables else '(none)'}")
        if "records" not in tables:
            return "\n".join(lines + ["", "No records table found in this backup."])

        cur.execute("SELECT COUNT(*) FROM records")
        count = cur.fetchone()[0]
        lines.append(f"Records: {count}")
        lines.append("")
        lines.append("Recent entries:")
        cur.execute(
            "SELECT field1, field2, created_at FROM records ORDER BY created_at DESC LIMIT 5"
        )
        rows = cur.fetchall()
        if not rows:
            lines.append("- No rows in records")
        else:
            for field1, field2, created_at in rows:
                left = field1 or "(blank)"
                right = field2 or "(blank)"
                stamp = created_at or "(no timestamp)"
                lines.append(f"- {left} | {right} | {stamp}")
        return "\n".join(lines)
    finally:
        conn.close()


def _build_backup_preview(path: Path) -> str:
    if _is_sqlite_backup(path):
        try:
            return _build_sqlite_backup_preview(path)
        except Exception as exc:
            lines = _preview_metadata(path)
            lines.append("Type: SQLite backup")
            lines.append("")
            lines.append(f"Unable to inspect database contents: {exc}")
            return "\n".join(lines)

    lines = _preview_metadata(path)
    lines.append("Type: Text backup")
    lines.append("")
    try:
        text = path.read_text(encoding="utf-8")
        lines.append(text[:2000])
    except Exception as exc:
        lines.append(f"Unable to preview text contents: {exc}")
    return "\n".join(lines)


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

        container = ttk.Frame(self)
        container.pack(fill="both", expand=True, padx=8, pady=8)

        left = ttk.Frame(container)
        left.pack(side="left", fill="y", padx=(0, 8))
        self.form = InputForm(left, labels=labels, on_rename=self.on_labels_changed, on_submit=self.on_form_submit)
        self.form.pack(fill="y", expand=False)
        self._form_mode_var = tk.StringVar(value="Mode: New item")
        self._form_mode_label = ttk.Label(left, textvariable=self._form_mode_var)
        self._form_mode_label.pack(fill="x", pady=(6, 0))

        right = ttk.Frame(container)
        right.pack(side="left", fill="both", expand=True)
        self.table = RecordTable(right, columns=column_order, labels=labels, on_commit=self._on_table_commit, on_column_order_changed=self.on_column_order_changed, column_widths=column_widths, on_column_widths_changed=self.on_column_widths_changed, visible_columns=visible_columns, on_visible_columns_changed=self.on_visible_columns_changed)
        self.table.pack(fill="both", expand=True)

        controls = ttk.Frame(self)
        controls.pack(fill="x", padx=8, pady=6)
        ttk.Button(controls, text="New item", command=self.on_new_item).pack(side="left", padx=4)
        self._save_changes_button = ttk.Button(controls, text="Save changes", command=self.on_save_changes)
        self._save_changes_button.pack(side="left", padx=4)
        ttk.Button(controls, text="Delete selected", command=self.on_delete).pack(side="left", padx=4)
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
        self.table.bind("<<TreeviewSelect>>", self._on_table_select)
        self.table.bind("<Button-3>", self._on_row_right_click)

        self._update_form_mode_ui()
        self.load_records()

    def _record_by_id(self, record_id: str) -> Record | None:
        records = self.data_manager.load_all()
        return next((record for record in records if record.id == record_id), None)

    def _duplicate_identity(self, record: Record) -> tuple[str, str] | None:
        field1 = (record.field1 or "").strip().lower()
        field2 = (record.field2 or "").strip().lower()
        if not field1 or not field2:
            return None
        return field1, field2

    def _find_duplicate_record(self, record: Record, exclude_id: str | None = None) -> Record | None:
        duplicate_identity = self._duplicate_identity(record)
        if duplicate_identity is None:
            return None
        for existing in self.data_manager.load_all():
            if exclude_id is not None and existing.id == exclude_id:
                continue
            if self._duplicate_identity(existing) == duplicate_identity:
                return existing
        return None

    def _confirm_duplicate_record(self, record: Record, exclude_id: str | None = None, action_text: str = "save") -> bool:
        duplicate = self._find_duplicate_record(record, exclude_id=exclude_id)
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
        except Exception:
            pass

    def _on_table_select(self, event=None) -> None:
        sel_id = self.table.get_selected_id()
        if not sel_id:
            return
        record = self._record_by_id(sel_id)
        if record is None:
            return
        self.form.set_values(record.to_dict())
        self._update_form_mode_ui(record)

    def _update_form_mode_ui(self, record: Record | None = None) -> None:
        current_record_id = self.form.current_record_id
        if current_record_id is None:
            self._save_changes_button.config(state="disabled")
            self._form_mode_var.set("Mode: New item")
            return
        if record is None or record.id != current_record_id:
            record = self._record_by_id(current_record_id)
        self._save_changes_button.config(state="normal")
        if record is None:
            self._form_mode_var.set("Mode: Editing selected item")
            return
        left = (record.field1 or "").strip() or "(blank)"
        right = (record.field2 or "").strip() or "(blank)"
        self._form_mode_var.set(f"Mode: Editing {left} / {right}")

    def _current_search_query(self) -> str:
        return self._search_entry.get().strip().lower()

    def _sort_records_for_display(self, records: list[Record]) -> list[Record]:
        return sorted(
            records,
            key=lambda record: record.created_at.timestamp() if record.created_at is not None else 0.0,
            reverse=True,
        )

    def _search_words(self, text: str) -> set[str]:
        return set(re.findall(r"[a-z0-9]+", (text or "").lower()))

    def _record_matches_substring_query(self, record: Record, query: str) -> bool:
        return query in (record.field1 or "").lower() or query in (record.field2 or "").lower()

    def _record_matches_exact_word_query(self, record: Record, query: str) -> bool:
        return query in self._search_words(record.field1 or "") or query in self._search_words(record.field2 or "")

    def _filtered_records(self, records: list[Record]) -> list[Record]:
        query = self._current_search_query()
        if not query:
            return records

        exact_matches = [record for record in records if self._record_matches_exact_word_query(record, query)]
        if exact_matches:
            return exact_matches

        return [record for record in records if self._record_matches_substring_query(record, query)]

    def _record_matches_current_filter(self, record: Record) -> bool:
        query = self._current_search_query()
        if not query:
            return True

        records = self.data_manager.load_all()
        if any(self._record_matches_exact_word_query(existing, query) for existing in records):
            return self._record_matches_exact_word_query(record, query)

        return self._record_matches_substring_query(record, query)

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
            except Exception:
                pass
            return

        if self.table.exists(record.id):
            try:
                self.table.delete(record.id)
            except Exception:
                self.load_records()

    def load_records(self) -> None:
        records = self.data_manager.load_all()
        displayed = self._sort_records_for_display(self._filtered_records(records))
        self._displayed_records = displayed
        self.table.load(displayed)

    def on_search(self) -> None:
        self.load_records()

    def on_clear_search(self) -> None:
        self._search_entry.delete(0, "end")
        self.load_records()

    def on_new_item(self) -> None:
        self.form.clear()
        try:
            self.table.selection_remove(*self.table.selection())
        except Exception:
            pass
        self._update_form_mode_ui()
        first_field = self.form.entries.get("field1")
        if first_field is not None:
            try:
                first_field.focus_set()
                first_field.focus_force()
            except Exception:
                try:
                    first_field.focus_set()
                except Exception:
                    pass

    def on_form_submit(self) -> None:
        if self.form.current_record_id:
            self.on_save_changes()
            return
        self.on_add()

    def on_add(self) -> None:
        try:
            self.form.recalc_field6()
        except Exception:
            pass
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
        except Exception:
            pass
        self.data_manager.save(rec)
        self.load_records()
        self.on_new_item()

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
        if first_field is not None:
            try:
                first_field.focus_set()
                first_field.focus_force()
            except Exception:
                try:
                    first_field.focus_set()
                except Exception:
                    pass

    def on_save_changes(self) -> None:
        record_id = self.form.current_record_id or self.table.get_selected_id()
        if not record_id:
            messagebox.showinfo("Select", "Please select a record to edit.")
            return
        record = self._record_by_id(record_id)
        if not record:
            messagebox.showerror("Error", "Record not found")
            return
        try:
            self.form.recalc_field6()
        except Exception:
            pass
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
            self.on_new_item()

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
        win = tk.Toplevel(self)
        win.title("Manage Backups")
        win.geometry("720x360")

        btn_frame = ttk.Frame(win)
        btn_frame.pack(side="bottom", fill="x", padx=8, pady=6)
        btn_restore = ttk.Button(btn_frame, text="Restore", state="disabled")
        btn_delete = ttk.Button(btn_frame, text="Delete", state="disabled")
        btn_close = ttk.Button(btn_frame, text="Close", command=win.destroy)
        btn_delete.pack(side="right", padx=4)
        btn_restore.pack(side="right", padx=4)
        btn_close.pack(side="right", padx=4)

        content = ttk.Frame(win)
        content.pack(fill="both", expand=True)

        left = ttk.Frame(content)
        left.pack(side="left", fill="y", padx=8, pady=8)
        lb = tk.Listbox(left, width=48, height=18)
        lb.pack(side="top", fill="y", expand=True)

        info = ttk.Label(left, text="Select a backup to preview or restore")
        info.pack(side="top", pady=(6, 0))

        right = ttk.Frame(content)
        right.pack(side="left", fill="both", expand=True, padx=8, pady=8)
        preview = tk.Text(right, wrap="none", height=20)
        preview.pack(fill="both", expand=True)

        backup_paths: list[Path] = []

        def _selected_backup_path() -> Path | None:
            sel = lb.curselection()
            if not sel:
                return None
            idx = sel[0]
            if idx >= len(backup_paths):
                return None
            return backup_paths[idx]

        def _refresh_list():
            nonlocal backup_paths
            backup_paths = list(self.data_manager.list_backups())
            lb.delete(0, "end")
            for path in backup_paths:
                lb.insert("end", _format_backup_label(path))
            preview.delete("1.0", "end")
            btn_restore.config(state="disabled")
            btn_delete.config(state="disabled")

        _refresh_list()

        def _on_select(evt=None):
            path = _selected_backup_path()
            if path is None:
                preview.delete("1.0", "end")
                btn_restore.config(state="disabled")
                btn_delete.config(state="disabled")
                return
            preview.delete("1.0", "end")
            preview.insert("1.0", _build_backup_preview(path))
            btn_restore.config(state="normal")
            btn_delete.config(state="normal")

        def _do_restore():
            path = _selected_backup_path()
            if path is None:
                return
            label = _format_backup_label(path)
            if not messagebox.askyesno("Restore", f"Restore from {label}?"):
                return
            try:
                pre = self.data_manager.restore_from_backup(path)
                self.load_records()
                messagebox.showinfo("Restored", f"Restored {label}; pre-restore at {pre}")
                _refresh_list()
            except Exception as exc:
                messagebox.showerror("Restore failed", str(exc))

        def _do_delete():
            path = _selected_backup_path()
            if path is None:
                return
            label = _format_backup_label(path)
            if not messagebox.askyesno("Delete", f"Delete backup {label}?"):
                return
            try:
                self.data_manager.delete_backup(path)
                _refresh_list()
            except Exception as exc:
                messagebox.showerror("Delete failed", str(exc))

        lb.bind("<<ListboxSelect>>", _on_select)
        btn_restore.config(command=_do_restore)
        btn_delete.config(command=_do_delete)
        try:
            win.transient(self)
            win.grab_set()
        except Exception:
            pass
        return win

    def on_labels_changed(self, labels: Sequence[str]) -> None:
        try:
            self.table.update_column_labels(labels)
        except Exception:
            pass

    def on_column_order_changed(self, columns: Sequence[str]) -> None:
        try:
            save_column_order(list(columns))
        except Exception:
            pass

    def on_column_widths_changed(self, column_widths: dict[str, int]) -> None:
        try:
            save_column_widths(column_widths)
        except Exception:
            pass

    def on_visible_columns_changed(self, visible_columns: Sequence[str]) -> None:
        try:
            save_visible_columns(list(visible_columns))
        except Exception:
            pass

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
            except Exception:
                pass

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
        except Exception:
            pass

    def _copy_selected_id_to_clipboard(self) -> None:
        try:
            self.table.copy_selected_id_to_clipboard()
        except Exception:
            pass

    def run(self) -> None:
        self.mainloop()