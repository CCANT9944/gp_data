from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..models import Record
from .form import InputForm
from .table import RecordTable


class _FormModeController:
    def __init__(
        self,
        form: InputForm,
        table: RecordTable,
        form_mode_var: tk.StringVar,
        form_mode_label: tk.Label,
        save_changes_button: ttk.Button,
        delete_selected_button: ttk.Button,
        record_by_id,
        new_mode_banner_bg: str,
        new_mode_banner_fg: str,
        edit_mode_banner_bg: str,
        edit_mode_banner_fg: str,
        dirty_mode_banner_bg: str,
        dirty_mode_banner_fg: str,
    ) -> None:
        self._form = form
        self._table = table
        self._form_mode_var = form_mode_var
        self._form_mode_label = form_mode_label
        self._save_changes_button = save_changes_button
        self._delete_selected_button = delete_selected_button
        self._record_by_id = record_by_id
        self._new_mode_banner_bg = new_mode_banner_bg
        self._new_mode_banner_fg = new_mode_banner_fg
        self._edit_mode_banner_bg = edit_mode_banner_bg
        self._edit_mode_banner_fg = edit_mode_banner_fg
        self._dirty_mode_banner_bg = dirty_mode_banner_bg
        self._dirty_mode_banner_fg = dirty_mode_banner_fg

    def on_form_dirty_change(self, _is_dirty: bool) -> None:
        self.update()

    def update(self, record: Record | None = None) -> None:
        current_record_id = self._form.current_record_id
        selected_record_id = self._table.get_selected_id()
        dirty = self._form.is_dirty()
        self._delete_selected_button.config(state="normal" if selected_record_id else "disabled")
        if current_record_id is None:
            self._save_changes_button.config(state="disabled")
            text = "NEW ITEM MODE"
            bg = self._new_mode_banner_bg
            fg = self._new_mode_banner_fg
            if dirty:
                text = "NEW ITEM MODE (UNSAVED CHANGES)"
                bg = self._dirty_mode_banner_bg
                fg = self._dirty_mode_banner_fg
            self._set_banner(text, bg, fg)
            return
        if record is None or record.id != current_record_id:
            record = self._record_by_id(current_record_id)
        self._save_changes_button.config(state="normal")
        if record is None:
            text = "EDITING SELECTED ITEM"
            bg = self._edit_mode_banner_bg
            fg = self._edit_mode_banner_fg
            if dirty:
                text = f"{text} (UNSAVED CHANGES)"
                bg = self._dirty_mode_banner_bg
                fg = self._dirty_mode_banner_fg
            self._set_banner(text, bg, fg)
            return
        left = (record.field1 or "").strip() or "(blank)"
        right = (record.field2 or "").strip() or "(blank)"
        text = f"EDITING: {left} / {right}"
        bg = self._edit_mode_banner_bg
        fg = self._edit_mode_banner_fg
        if dirty:
            text = f"{text} (UNSAVED CHANGES)"
            bg = self._dirty_mode_banner_bg
            fg = self._dirty_mode_banner_fg
        self._set_banner(text, bg, fg)

    def _set_banner(self, text: str, bg: str, fg: str) -> None:
        self._form_mode_var.set(text)
        self._form_mode_label.config(bg=bg, fg=fg)