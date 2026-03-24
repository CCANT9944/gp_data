from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk
from typing import Sequence

from .form import InputForm
from .table import RecordTable
from .view_helpers import ProcessingDialogHandle


@dataclass(frozen=True)
class _AppLayout:
    form: InputForm
    table: RecordTable
    formula_panel: ttk.LabelFrame
    formula_panel_text: tk.Text
    form_mode_var: tk.StringVar
    form_mode_label: tk.Label
    manage_formula_settings_button: ttk.Button
    save_changes_button: ttk.Button
    delete_selected_button: ttk.Button
    open_last_csv_button: ttk.Button
    open_recent_csv_button: ttk.Menubutton
    recent_csv_menu: tk.Menu
    search_entry: ttk.Entry
    csv_preview_status: ProcessingDialogHandle
    row_menu: tk.Menu
    gp_highlight_menu: tk.Menu
    type_filter_menu: tk.Menu


def build_app_layout(
    owner: tk.Tk,
    *,
    labels: Sequence[str],
    column_order: Sequence[str],
    column_widths: dict[str, int],
    visible_columns: Sequence[str],
    gp_highlight_presets: Sequence[float],
    save_labels_callback,
    on_labels_changed,
    on_form_submit,
    on_table_commit,
    on_column_order_changed,
    on_column_widths_changed,
    on_visible_columns_changed,
    on_heading_click,
    on_new_item,
    on_save_changes,
    on_delete,
    on_manage_columns,
    on_manage_formula_settings,
    on_open_csv_preview,
    on_open_last_csv_preview,
    on_manage_backups,
    on_export,
    on_clear_search,
    on_search,
    on_edit,
    on_copy_selected_id_to_clipboard,
    on_set_gp_highlight_threshold,
    on_prompt_custom_gp_highlight_threshold,
) -> _AppLayout:
    container = ttk.Frame(owner)
    container.pack(fill="both", expand=True, padx=8, pady=8)

    left = ttk.Frame(container)
    left.pack(side="left", fill="y", padx=(0, 8))
    form = InputForm(
        left,
        labels=labels,
        on_rename=on_labels_changed,
        on_submit=on_form_submit,
        save_labels_callback=save_labels_callback,
        on_dirty_change=lambda _is_dirty: None,
    )
    form.pack(fill="y", expand=False)

    form_mode_var = tk.StringVar(value="NEW ITEM MODE")
    form_mode_label = tk.Label(
        left,
        textvariable=form_mode_var,
        anchor="w",
        padx=8,
        pady=6,
        justify="left",
        relief="solid",
        borderwidth=1,
        font=("TkDefaultFont", 9, "bold"),
    )
    form_mode_label.pack(fill="x", pady=(6, 0))
    left.update_idletasks()
    left_width = max(form.winfo_reqwidth(), form_mode_label.winfo_reqwidth())
    left.configure(width=left_width)
    left.pack_propagate(False)
    form_mode_label.configure(wraplength=max(left_width - 16, 1))

    right = ttk.Frame(container)
    right.pack(side="left", fill="both", expand=True)
    table = RecordTable(
        right,
        columns=column_order,
        labels=labels,
        on_commit=on_table_commit,
        on_column_order_changed=on_column_order_changed,
        column_widths=column_widths,
        on_column_widths_changed=on_column_widths_changed,
        visible_columns=visible_columns,
        on_visible_columns_changed=on_visible_columns_changed,
        on_heading_click=on_heading_click,
    )
    table.pack(fill="both", expand=True)

    formula_panel = ttk.LabelFrame(right, text="Calculation details")
    formula_panel_text = tk.Text(formula_panel, height=11, wrap="word")
    formula_panel_text.pack(fill="both", expand=True, padx=8, pady=8)
    formula_panel_text.configure(state="disabled")

    controls = ttk.Frame(owner)
    controls.pack(fill="x", padx=8, pady=6)
    ttk.Button(controls, text="New item", command=on_new_item).pack(side="left", padx=4)
    save_changes_button = ttk.Button(controls, text="Save changes", command=on_save_changes)
    save_changes_button.pack(side="left", padx=4)
    delete_selected_button = ttk.Button(controls, text="Delete selected", command=on_delete)
    delete_selected_button.pack(side="left", padx=4)
    ttk.Button(controls, text="Columns", command=on_manage_columns).pack(side="left", padx=4)
    manage_formula_settings_button = ttk.Button(controls, text="Formula settings", command=on_manage_formula_settings)
    manage_formula_settings_button.pack(side="left", padx=4)
    ttk.Button(controls, text="Rename fields", command=form.rename_fields).pack(side="left", padx=4)
    ttk.Button(controls, text="Open CSV", command=on_open_csv_preview).pack(side="left", padx=4)
    open_last_csv_button = ttk.Button(controls, text="Last CSV", command=on_open_last_csv_preview)
    open_last_csv_button.pack(side="left", padx=4)
    recent_csv_menu = tk.Menu(owner, tearoff=0)
    open_recent_csv_button = ttk.Menubutton(controls, text="Recent CSVs", direction="below")
    open_recent_csv_button.configure(menu=recent_csv_menu)
    open_recent_csv_button.pack(side="left", padx=4)

    ttk.Button(controls, text="Manage backups", command=on_manage_backups).pack(side="right", padx=4)
    ttk.Button(controls, text="Export CSV", command=on_export).pack(side="right", padx=4)

    search_entry = ttk.Entry(controls, width=20)
    search_entry.bind("<KeyRelease>", lambda _event: on_search())
    ttk.Button(controls, text="Clear", command=on_clear_search).pack(side="right", padx=4)
    search_entry.pack(side="right", padx=4)
    ttk.Label(controls, text="Search").pack(side="right", padx=(4, 0))

    csv_preview_status = ProcessingDialogHandle(
        owner,
        title="Processing CSV",
        eyebrow_text="CSV PREVIEW",
        detail_text="Loading the preview, checking metadata, and preparing visible rows.",
    )

    row_menu = tk.Menu(owner, tearoff=0)
    row_menu.add_command(label="Load into form", command=on_edit)
    row_menu.add_command(label="Delete", command=on_delete)
    row_menu.add_separator()
    row_menu.add_command(label="Copy ID", command=on_copy_selected_id_to_clipboard)

    gp_highlight_menu = tk.Menu(owner, tearoff=0)
    for threshold in gp_highlight_presets:
        label = f"Highlight below {threshold:g}%"
        gp_highlight_menu.add_command(label=label, command=lambda value=threshold: on_set_gp_highlight_threshold(value))
    gp_highlight_menu.add_separator()
    gp_highlight_menu.add_command(label="Custom...", command=on_prompt_custom_gp_highlight_threshold)
    gp_highlight_menu.add_command(label="Clear GP highlight", command=lambda: on_set_gp_highlight_threshold(None))

    type_filter_menu = tk.Menu(owner, tearoff=0)

    return _AppLayout(
        form=form,
        table=table,
        formula_panel=formula_panel,
        formula_panel_text=formula_panel_text,
        form_mode_var=form_mode_var,
        form_mode_label=form_mode_label,
        manage_formula_settings_button=manage_formula_settings_button,
        save_changes_button=save_changes_button,
        delete_selected_button=delete_selected_button,
        open_last_csv_button=open_last_csv_button,
        open_recent_csv_button=open_recent_csv_button,
        recent_csv_menu=recent_csv_menu,
        search_entry=search_entry,
        csv_preview_status=csv_preview_status,
        row_menu=row_menu,
        gp_highlight_menu=gp_highlight_menu,
        type_filter_menu=type_filter_menu,
    )