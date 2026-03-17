from __future__ import annotations

import logging
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Sequence

from ..models import Record


TABLE_STYLE = "GPData.Treeview"
TABLE_HEADING_STYLE = "GPData.Treeview.Heading"
SEPARATOR_PREFIX = "__sep_"
SEPARATOR_GLYPH = "|"
METRIC_LABELS = {
    "gp": "GP",
    "cash_margin": "CASH MARGIN",
    "gp70": "WITH 70% GP",
}
ROW_TAG_ODD = "row-odd"
ROW_TAG_EVEN = "row-even"
ROW_TAG_GP_LOW_ODD = "row-gp-low-odd"
ROW_TAG_GP_LOW_EVEN = "row-gp-low-even"
ROW_ODD_BACKGROUND = "#ffffff"
ROW_EVEN_BACKGROUND = "#e7edf5"
ROW_GP_LOW_ODD_BACKGROUND = "#ffe4d8"
ROW_GP_LOW_EVEN_BACKGROUND = "#ffd7c5"
LOGGER = logging.getLogger(__name__)


def _is_separator_column(name: str) -> bool:
    return name.startswith(SEPARATOR_PREFIX)


def _build_display_columns(columns: Sequence[str]) -> list[str]:
    display_columns: list[str] = []
    for index, column in enumerate(columns):
        display_columns.append(column)
        if index < len(columns) - 1:
            display_columns.append(f"{SEPARATOR_PREFIX}{index}")
    return display_columns


def _configure_table_style(widget: ttk.Treeview) -> None:
    style = ttk.Style(widget)
    style.configure(
        TABLE_STYLE,
        rowheight=30,
        borderwidth=2,
        relief="solid",
        background="#ffffff",
        fieldbackground="#dfe6ef",
    )
    style.map(
        TABLE_STYLE,
        background=[("selected", "#9fc2f7")],
        foreground=[("selected", "#111111")],
    )
    style.configure(
        TABLE_HEADING_STYLE,
        relief="solid",
        borderwidth=2,
        padding=(8, 7),
        background="#d8e0ea",
        foreground="#1c2530",
    )


class RecordTable(ttk.Treeview):
    """Table-like display using ttk.Treeview."""

    def __init__(self, parent, columns: Sequence[str] | None = None, labels: Sequence[str] | None = None, on_commit: Callable[[str, str, str], None] | None = None, on_column_order_changed: Callable[[list[str]], None] | None = None, column_widths: dict[str, int] | None = None, on_column_widths_changed: Callable[[dict[str, int]], None] | None = None, visible_columns: Sequence[str] | None = None, on_visible_columns_changed: Callable[[list[str]], None] | None = None, on_heading_click: Callable[[str], None] | None = None, **kwargs):
        cols = list(columns or ["field1", "field2", "field3", "field4", "field5", "field6", "field7", "gp", "cash_margin", "gp70"])
        self._data_cols = ["id"] + cols
        self._cols = cols
        self._display_cols = _build_display_columns(self._cols)

        default_field_labels = ["Field 1", "Field 2", "Field 3", "Field 4", "Field 5", "Field 6", "Field 7"]
        heading_labels = list(labels or default_field_labels)
        if len(heading_labels) < len(default_field_labels):
            heading_labels = heading_labels + default_field_labels[len(heading_labels):]
        self._labels = heading_labels[:len(default_field_labels)]
        self._on_commit = on_commit
        self._on_column_order_changed = on_column_order_changed
        self._column_widths = dict(column_widths or {})
        self._on_column_widths_changed = on_column_widths_changed
        self._visible_cols = [col for col in self._cols if visible_columns is None or col in visible_columns] or list(self._cols)
        self._on_visible_columns_changed = on_visible_columns_changed
        self._on_heading_click = on_heading_click
        self._records: list[Record] = []
        self._drag_column: str | None = None
        self._heading_press_column: str | None = None
        self._heading_press_xy = (0, 0)
        self._gp_highlight_threshold: float | None = None
        self._last_known_widths = dict(self._column_widths)
        _configure_table_style(parent)

        super().__init__(parent, columns=self._display_cols, show="headings", style=TABLE_STYLE, **kwargs)
        self._apply_column_layout()

        self.bind("<Double-1>", self._on_double_click)
        self.bind("<ButtonPress-1>", self._on_button_press, add="+")
        self.bind("<ButtonRelease-1>", self._on_button_release, add="+")

    def update_column_labels(self, labels: Sequence[str]) -> None:
        updated = list(labels)
        if len(updated) < len(self._labels):
            updated = updated + self._labels[len(updated):]
        self._labels = updated[:len(self._labels)]
        self._apply_column_layout(reload_rows=False)

    def get_column_order(self) -> list[str]:
        return list(self._cols)

    def get_visible_columns(self) -> list[str]:
        return [col for col in self._cols if col in self._visible_cols]

    def get_gp_highlight_threshold(self) -> float | None:
        return self._gp_highlight_threshold

    def _show_error_dialog(self, title: str, message: str, *, log_context: str) -> None:
        try:
            messagebox.showerror(title, message, parent=self.winfo_toplevel())
        except tk.TclError:
            LOGGER.debug(log_context, exc_info=True)

    def _show_callback_error(self, title: str, message: str) -> None:
        self._show_error_dialog(title, message, log_context="Unable to show callback failure dialog")

    def _copy_text_to_clipboard_safely(self, text: str) -> None:
        try:
            top = self.winfo_toplevel()
            top.clipboard_clear()
            top.clipboard_append(text)
        except tk.TclError:
            LOGGER.debug("Unable to copy record id to clipboard", exc_info=True)

    def _focus_editor_safely(self, editor: ttk.Entry, *, context: str, select_text: bool = False) -> None:
        try:
            editor.focus_set()
            if select_text:
                editor.select_range(0, "end")
        except tk.TclError:
            LOGGER.debug("Unable to %s", context, exc_info=True)

    def _destroy_editor_safely(self, *, context: str) -> None:
        editor = getattr(self, "_editor", None)
        if editor is None:
            return
        try:
            editor.destroy()
        except tk.TclError:
            LOGGER.debug("Unable to destroy inline editor while %s", context, exc_info=True)

    def _clear_editor_state(self) -> None:
        self._editor = None
        self._editing = None

    def _editable_cell_from_event(self, event) -> tuple[str, str] | None:
        try:
            row = self.identify_row(event.y)
            col_id = self.identify_column(event.x)
            if not row or not col_id:
                return None
            col_index = int(col_id.lstrip("#")) - 1
            visible_display_cols = self._visible_display_columns()
            if col_index < 0 or col_index >= len(visible_display_cols):
                return None
            col_name = visible_display_cols[col_index]
        except (tk.TclError, ValueError):
            LOGGER.debug("Unable to start inline cell edit from double click", exc_info=True)
            return None

        if _is_separator_column(col_name) or col_name == "field6":
            return None
        return row, col_name

    def _normalized_editor_value(self, col: str, value):
        if col not in ("field3", "field6", "field7") or not isinstance(value, str):
            return value
        stripped = value.replace("£", "").replace(",", "").strip()
        try:
            return str(float(stripped))
        except (TypeError, ValueError):
            LOGGER.debug("Unable to normalize editor value for %s", col, exc_info=True)
            return value

    def _apply_inline_edit_locally(self, iid: str, col: str, new_value: str) -> None:
        try:
            cur_vals = list(self.item(iid)["values"])
            idx = self._display_cols.index(col)
            cur_vals[idx] = new_value
            self.item(iid, values=cur_vals)
        except (tk.TclError, ValueError):
            LOGGER.debug("Unable to apply inline edit locally", exc_info=True)

    def set_gp_highlight_threshold(self, threshold_percent: float | None) -> None:
        self._gp_highlight_threshold = threshold_percent
        self._refresh_row_tags()

    def set_visible_columns(self, columns: Sequence[str]) -> None:
        visible = [col for col in self._cols if col in columns]
        if not visible:
            visible = [self._cols[0]]
        if visible == self.get_visible_columns():
            return
        original_visible = list(self._visible_cols)
        self._visible_cols = visible
        self._apply_column_layout(reload_rows=False)
        if callable(self._on_visible_columns_changed):
            try:
                self._on_visible_columns_changed(self.get_visible_columns())
            except Exception as exc:
                LOGGER.exception("Visible-columns callback failed")
                self._visible_cols = original_visible
                self._apply_column_layout(reload_rows=False)
                self._show_callback_error("Columns not updated", f"Could not apply the visible column change.\n\nReason: {exc}")

    def set_column_order(self, columns: Sequence[str]) -> None:
        new_order = [column for column in columns if column in self._cols]
        for column in self._cols:
            if column not in new_order:
                new_order.append(column)
        if new_order == self._cols:
            return
        self._cols = new_order
        self._display_cols = _build_display_columns(self._cols)
        self._apply_column_layout(reload_rows=True)

    def _heading_text_for(self, col: str) -> str:
        if col.startswith("field") and col[5:].isdigit():
            idx = int(col[5:]) - 1
            if 0 <= idx < len(self._labels):
                return self._labels[idx]
        return METRIC_LABELS.get(col, col)

    def _column_presentation(self, col: str) -> tuple[int, str]:
        width = self._column_widths.get(col)
        if width is None:
            if col in ("field3", "field4", "field5", "field6", "field7", "gp", "cash_margin", "gp70"):
                width = 80
            elif col in ("field1", "field2"):
                width = 140
            else:
                width = 120
        if col in ("field3", "field4", "field5", "field6", "field7", "gp", "cash_margin", "gp70"):
            return width, "e"
        if col in ("field1", "field2"):
            return width, "w"
        return width, "w"

    def get_column_widths(self) -> dict[str, int]:
        widths: dict[str, int] = {}
        for col in self._cols:
            try:
                widths[col] = int(self.column(col, "width"))
            except (tk.TclError, ValueError):
                width, _anchor = self._column_presentation(col)
                widths[col] = width
        return widths

    def set_column_widths(self, column_widths: dict[str, int]) -> None:
        self._column_widths = dict(column_widths)
        self._last_known_widths = dict(column_widths)
        self._apply_column_layout(reload_rows=False)

    def _notify_if_widths_changed(self) -> None:
        widths = self.get_column_widths()
        if widths == self._last_known_widths:
            return
        original_widths = dict(self._last_known_widths)
        self._last_known_widths = dict(widths)
        self._column_widths = dict(widths)
        if callable(self._on_column_widths_changed):
            try:
                self._on_column_widths_changed(widths)
            except Exception as exc:
                LOGGER.exception("Column-width callback failed")
                self._column_widths = dict(original_widths)
                self._last_known_widths = dict(original_widths)
                self._apply_column_layout(reload_rows=False)
                self._show_callback_error("Column widths not updated", f"Could not apply the column width change.\n\nReason: {exc}")

    def _apply_column_layout(self, reload_rows: bool = False) -> None:
        records = list(self._records)
        visible_display_cols = self._visible_display_columns()
        self.configure(columns=self._display_cols, displaycolumns=visible_display_cols)
        for col in self._display_cols:
            if _is_separator_column(col):
                self.heading(col, text=SEPARATOR_GLYPH, anchor="center")
                self.column(col, width=18, minwidth=18, stretch=False, anchor="center")
                continue

            heading_text = self._heading_text_for(col)
            col_width, col_anchor = self._column_presentation(col)
            self.heading(col, text=heading_text, anchor=col_anchor)
            self.column(col, width=col_width, anchor=col_anchor)

        self.tag_configure(ROW_TAG_ODD, background=ROW_ODD_BACKGROUND)
        self.tag_configure(ROW_TAG_EVEN, background=ROW_EVEN_BACKGROUND)
        self.tag_configure(ROW_TAG_GP_LOW_ODD, background=ROW_GP_LOW_ODD_BACKGROUND)
        self.tag_configure(ROW_TAG_GP_LOW_EVEN, background=ROW_GP_LOW_EVEN_BACKGROUND)
        self._last_known_widths = self.get_column_widths()
        if reload_rows:
            self.load(records)

    def _visible_display_columns(self) -> list[str]:
        return _build_display_columns(self.get_visible_columns())

    def _column_name_from_event(self, event) -> str | None:
        if self.identify_region(event.x, event.y) != "heading":
            return None
        col_id = self.identify_column(event.x)
        if not col_id:
            return None
        col_index = int(col_id.lstrip("#")) - 1
        visible_display_cols = self._visible_display_columns()
        if col_index < 0 or col_index >= len(visible_display_cols):
            return None
        return visible_display_cols[col_index]

    def _display_column_bounds(self, column_name: str) -> tuple[int, int]:
        left = 0
        for name in self._visible_display_columns():
            width = int(self.column(name, "width"))
            right = left + width
            if name == column_name:
                return left, right
            left = right
        return 0, 0

    def _move_data_column(self, dragged: str, target: str, after: bool = False) -> bool:
        if dragged == target or dragged not in self._cols or target not in self._cols:
            return False
        new_order = [column for column in self._cols if column != dragged]
        target_index = new_order.index(target)
        if after:
            target_index += 1
        new_order.insert(target_index, dragged)
        if new_order == self._cols:
            return False
        original_order = list(self._cols)
        original_visible = list(self._visible_cols)
        self.set_column_order(new_order)
        self._visible_cols = [column for column in self._cols if column in self._visible_cols]
        if callable(self._on_column_order_changed):
            try:
                self._on_column_order_changed(self.get_column_order())
            except Exception as exc:
                LOGGER.exception("Column-order callback failed")
                self._cols = list(original_order)
                self._display_cols = _build_display_columns(self._cols)
                self._visible_cols = list(original_visible)
                self._apply_column_layout(reload_rows=True)
                self._show_callback_error("Column order not updated", f"Could not apply the column order change.\n\nReason: {exc}")
                return False
        return True

    def _row_tag_for_record(self, record: Record, row_index: int) -> str:
        if self._gp_highlight_threshold is not None and record.gp is not None and (record.gp * 100.0) < self._gp_highlight_threshold:
            return ROW_TAG_GP_LOW_EVEN if row_index % 2 else ROW_TAG_GP_LOW_ODD
        return ROW_TAG_EVEN if row_index % 2 else ROW_TAG_ODD

    def _refresh_row_tags(self) -> None:
        for row_index, record in enumerate(self._records):
            if self.exists(record.id):
                self.item(record.id, tags=(self._row_tag_for_record(record, row_index),))

    def _on_button_press(self, event) -> None:
        column_name = self._column_name_from_event(event)
        if column_name is None or _is_separator_column(column_name):
            self._drag_column = None
            self._heading_press_column = None
            return
        self._drag_column = column_name
        self._heading_press_column = column_name
        self._heading_press_xy = (event.x, event.y)

    def _on_button_release(self, event) -> None:
        self.after_idle(self._notify_if_widths_changed)
        if not self._drag_column:
            return
        dragged = self._drag_column
        self._drag_column = None
        pressed = self._heading_press_column
        press_x, press_y = self._heading_press_xy
        self._heading_press_column = None
        target = self._column_name_from_event(event)
        is_click = target == pressed and abs(event.x - press_x) <= 4 and abs(event.y - press_y) <= 4
        if is_click and callable(self._on_heading_click):
            try:
                self._on_heading_click(target)
            except Exception as exc:
                LOGGER.exception("Heading-click callback failed")
                self._show_callback_error("Header action failed", f"Could not open the header action.\n\nReason: {exc}")
            return
        if target is None or _is_separator_column(target) or target == dragged:
            return
        left, right = self._display_column_bounds(target)
        midpoint = left + ((right - left) / 2)
        self._move_data_column(dragged, target, after=event.x > midpoint)

    def copy_selected_id_to_clipboard(self) -> None:
        sel = self.get_selected_id()
        if not sel:
            return
        self._copy_text_to_clipboard_safely(sel)

    def _on_double_click(self, event) -> None:
        cell = self._editable_cell_from_event(event)
        if cell is None:
            return
        row, col_name = cell
        self.start_cell_edit(row, col_name)

    def start_cell_edit(self, iid: str, col: str) -> None:
        self._destroy_editor_safely(context="starting a new inline edit")
        self._clear_editor_state()

        if col == "field6":
            return

        try:
            col_index = self._display_cols.index(col)
        except ValueError:
            return
        bbox = self.bbox(iid, column=col)
        if not bbox:
            x, y, w, h = 2, 2, 120, 20
        else:
            x, y, w, h = bbox
        cur = self.item(iid)["values"][col_index]
        cur = self._normalized_editor_value(col, cur)

        editor = ttk.Entry(self)
        try:
            editor.place(x=x, y=y, width=w, height=h)
        except tk.TclError:
            editor.pack()
        editor.insert(0, cur)
        self._focus_editor_safely(editor, context="focus the inline editor", select_text=True)
        editor.bind("<Return>", lambda e: self._commit_edit())
        editor.bind("<Escape>", lambda e: self._cancel_edit())
        editor.bind("<FocusOut>", lambda e: self._cancel_edit())
        self._editor = editor
        self._editing = (iid, col)

    def _commit_edit(self, event=None) -> None:
        if not getattr(self, "_editor", None) or not getattr(self, "_editing", None):
            return
        iid, col = self._editing
        editor = self._editor
        new_val = editor.get()
        if callable(self._on_commit):
            try:
                self._on_commit(iid, col, new_val)
            except Exception as exc:
                LOGGER.exception("Inline edit commit callback failed")
                self._focus_editor_safely(editor, context="refocus inline editor after commit failure", select_text=True)
                self._show_error_dialog(
                    "Edit failed",
                    f"Could not save the inline edit.\n\nReason: {exc}",
                    log_context="Unable to show inline edit failure dialog",
                )
                return
            self._destroy_editor_safely(context="committing an inline edit")
            self._clear_editor_state()
            return
        self._destroy_editor_safely(context="committing an inline edit")
        self._clear_editor_state()
        self._apply_inline_edit_locally(iid, col, new_val)

    def _cancel_edit(self, event=None) -> None:
        self._destroy_editor_safely(context="canceling an inline edit")
        self._clear_editor_state()

    def load(self, records: Sequence[Record]) -> None:
        self._records = list(records)
        self.delete(*self.get_children())
        for record in records:
            self.insert_record(record)

    def update_record(self, record: Record) -> None:
        values = self._values_for_record(record)
        row_index = next((index for index, existing in enumerate(self._records) if existing.id == record.id), None)
        if row_index is None:
            self._records.append(record)
            row_index = len(self._records) - 1
        else:
            self._records[row_index] = record
        if self.exists(record.id):
            self.item(record.id, values=values, tags=(self._row_tag_for_record(record, row_index),))
        else:
            self.insert_record(record)

    def _format_display_value(self, col: str, val) -> str:
        if val is None:
            return ""
        if col == "gp":
            try:
                return f"{float(val) * 100:.2f}%"
            except (TypeError, ValueError):
                return str(val)
        if col in ("field3", "field6", "field7", "cash_margin", "gp70"):
            try:
                return f"\u00A3{float(val):.2f}"
            except (TypeError, ValueError):
                return str(val)
        if isinstance(val, float):
            return ("{:.6f}".format(val)).rstrip("0").rstrip(".")
        return str(val)

    def _values_for_record(self, record: Record) -> list[str]:
        values: list[str] = []
        for index, col in enumerate(self._cols):
            values.append(self._format_display_value(col, getattr(record, col)))
            if index < len(self._cols) - 1:
                values.append(SEPARATOR_GLYPH)
        return values

    def insert_record(self, record: Record):
        values = self._values_for_record(record)
        row_index = len(self.get_children())
        tag = self._row_tag_for_record(record, row_index)
        return self.insert("", "end", iid=record.id, values=values, tags=(tag,))

    def get_selected_id(self) -> str | None:
        sel = self.selection()
        if not sel:
            return None
        return sel[0]

    def delete_selected(self) -> None:
        for iid in self.selection():
            self.delete(iid)