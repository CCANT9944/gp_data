from __future__ import annotations

import logging
import tkinter as tk


LOGGER = logging.getLogger(__name__)


def focus_widget(widget: tk.Misc | None) -> None:
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


def recalc_form_field6(form, context: str) -> None:
    try:
        form.recalc_field6()
    except tk.TclError:
        LOGGER.debug("Unable to recalculate field6 while %s", context, exc_info=True)


def clear_table_selection(table) -> None:
    try:
        selection = table.selection()
        if selection:
            table.selection_remove(*selection)
    except tk.TclError:
        LOGGER.debug("Unable to clear table selection", exc_info=True)


def restore_table_selection(table, record_id: str | None) -> None:
    try:
        selection = table.selection()
        if selection:
            table.selection_remove(*selection)
        if record_id:
            table.selection_set(record_id)
            table.see(record_id)
    except tk.TclError:
        LOGGER.debug("Unable to restore table selection", exc_info=True)


def focus_record_in_table(table, record_id: str, reload_records) -> None:
    if not table.exists(record_id):
        reload_records()
    if not table.exists(record_id):
        return
    try:
        table.selection_set(record_id)
        table.see(record_id)
    except tk.TclError:
        LOGGER.debug("Unable to focus record %s in the table", record_id, exc_info=True)