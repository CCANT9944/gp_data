from __future__ import annotations

import tkinter as tk
from tkinter import ttk


def _open_column_visibility_dialog(parent: tk.Misc, headers: list[str], selected_indices: list[int], on_apply, *, filter_label) -> tk.Toplevel:
    dialog = tk.Toplevel(parent)
    dialog.title("Choose columns")
    dialog.transient(parent.winfo_toplevel())

    container = ttk.Frame(dialog)
    container.pack(fill="both", expand=True, padx=10, pady=10)
    ttk.Label(container, text="Visible columns").pack(anchor="w", pady=(0, 6))

    selected_set = set(selected_indices)
    variables: list[tk.BooleanVar] = []
    for index, header in enumerate(headers):
        variable = tk.BooleanVar(value=index in selected_set)
        variables.append(variable)
        ttk.Checkbutton(container, text=filter_label(header, index), variable=variable).pack(anchor="w")

    button_row = ttk.Frame(container)
    button_row.pack(fill="x", pady=(10, 0))

    def _apply() -> None:
        chosen_indices = [index for index, variable in enumerate(variables) if variable.get()]
        if not chosen_indices:
            chosen_indices = [0]
        on_apply(chosen_indices)
        dialog.destroy()

    ttk.Button(button_row, text="Cancel", command=dialog.destroy).pack(side="right")
    ttk.Button(button_row, text="Apply", command=_apply).pack(side="right", padx=(0, 6))
    return dialog


class _PreviewColumnManager:
    def __init__(
        self,
        win: tk.Toplevel,
        tree: ttk.Treeview,
        all_column_ids: list[str],
        view_state,
        get_data,
        popup_export_controller,
        on_visible_columns_changed=None,
        on_sort_changed=None,
        *,
        column_ids_for_data,
        column_width_for_header,
        min_column_width: int,
        normalize_visible_column_indices,
        filter_label,
    ) -> None:
        self._win = win
        self._tree = tree
        self._all_column_ids = all_column_ids
        self._view_state = view_state
        self._get_data = get_data
        self._popup_export_controller = popup_export_controller
        self._on_visible_columns_changed = on_visible_columns_changed
        self._on_sort_changed = on_sort_changed
        self._column_ids_for_data = column_ids_for_data
        self._column_width_for_header = column_width_for_header
        self._min_column_width = min_column_width
        self._normalize_visible_column_indices = normalize_visible_column_indices
        self._filter_label = filter_label
        initial_data = self._get_data()
        self._displaycolumns_cache = list(self._all_column_ids)
        self._heading_text_cache = {
            column_id: initial_data.headers[index]
            for index, column_id in enumerate(self._all_column_ids)
            if index < len(initial_data.headers)
        }

    def apply_displaycolumns(self) -> None:
        desired_displaycolumns = list(self._view_state.visible_column_ids(self._all_column_ids))
        if desired_displaycolumns == self._displaycolumns_cache:
            return
        self._tree.configure(displaycolumns=desired_displaycolumns)
        self._displaycolumns_cache = desired_displaycolumns

    def notify_sort_changed(self) -> None:
        if not callable(self._on_sort_changed):
            return
        data = self._get_data()
        self._on_sort_changed(list(data.headers), self._view_state.sort_column_index, self._view_state.sort_descending)

    def update_tree_headings(self) -> None:
        data = self._get_data()
        for index, column_id in enumerate(self._all_column_ids):
            header = data.headers[index]
            if self._view_state.sort_column_index == index:
                indicator = " ▼" if self._view_state.sort_descending else " ▲"
            else:
                indicator = ""
            heading_text = f"{header}{indicator}"
            if self._heading_text_cache.get(column_id) == heading_text:
                continue
            self._tree.heading(column_id, text=heading_text)
            self._heading_text_cache[column_id] = heading_text

    def rebuild_tree_columns(self, previous_column_count: int) -> None:
        data = self._get_data()
        previous_all_visible = self._view_state.visible_column_indices == list(range(previous_column_count))
        self._all_column_ids[:] = self._column_ids_for_data(data)
        self._tree.configure(columns=self._all_column_ids)
        self._displaycolumns_cache = None
        self._heading_text_cache = {}
        for column_id, header in zip(self._all_column_ids, data.headers):
            self._tree.heading(column_id, text=header)
            self._tree.column(
                column_id,
                width=self._column_width_for_header(header),
                minwidth=self._min_column_width,
                stretch=False,
                anchor="w",
            )
            self._heading_text_cache[column_id] = header

        if previous_all_visible:
            self._view_state.visible_column_indices = list(range(data.column_count))
        else:
            self._view_state.visible_column_indices = self._normalize_visible_column_indices(
                data.column_count,
                self._view_state.visible_column_indices,
            )
        if self._view_state.sort_column_index is not None and self._view_state.sort_column_index >= data.column_count:
            self._view_state.set_sort(None)
            self.notify_sort_changed()
        self.update_tree_headings()

    def open_column_dialog(self, on_apply) -> None:
        data = self._get_data()
        _open_column_visibility_dialog(
            self._win,
            data.headers,
            self._view_state.visible_column_indices,
            on_apply,
            filter_label=self._filter_label,
        )

    def apply_visible_columns(self, visible_indices: list[int], *, clear_header_filter, refresh) -> None:
        data = self._get_data()
        header_filter_cleared, sort_cleared = self._view_state.apply_visible_columns(self._all_column_ids, visible_indices)
        if sort_cleared:
            self.notify_sort_changed()
        if header_filter_cleared:
            clear_header_filter()
        elif sort_cleared:
            self._popup_export_controller.destroy_header_filter_popup()
            refresh()
        if callable(self._on_visible_columns_changed):
            self._on_visible_columns_changed(list(data.headers), list(self._view_state.visible_column_indices))
        if not header_filter_cleared and not sort_cleared:
            refresh()


class _PreviewRowRenderer:
    def __init__(
        self,
        win: tk.Toplevel,
        tree: ttk.Treeview,
        view_state,
        update_summary_label,
        *,
        row_insert_chunk_size: int,
        log_preview_performance,
    ) -> None:
        self._win = win
        self._tree = tree
        self._view_state = view_state
        self._update_summary_label = update_summary_label
        self._row_insert_chunk_size = row_insert_chunk_size
        self._log_preview_performance = log_preview_performance

    def populate_rows_in_chunks(
        self,
        load_token: int,
        render_token: int,
        displayed_rows: list[tuple[str, ...]],
        filtered: bool,
        total_visible_rows: int | None,
        start_index: int,
        render_started_at: float,
        *,
        current_load_token: int,
        current_render_token: int,
        schedule_next,
    ) -> None:
        if load_token != current_load_token:
            return
        if render_token != current_render_token:
            return
        if not self._win.winfo_exists() or not self._tree.winfo_exists():
            return

        end_index = min(start_index + self._row_insert_chunk_size, len(displayed_rows))
        children = list(self._tree.get_children())
        for row_index, row in enumerate(displayed_rows[start_index:end_index], start=start_index):
            if row_index < len(children):
                self._tree.item(children[row_index], values=row)
                continue
            self._tree.insert("", "end", values=row)

        if end_index >= len(displayed_rows) and len(children) > len(displayed_rows):
            self._tree.delete(*children[len(displayed_rows):])

        self._view_state.summary.apply_loaded_chunk(
            filtered=filtered,
            total_visible_rows=total_visible_rows,
            displayed_rows=len(displayed_rows),
            loaded_rows=end_index,
        )
        self._update_summary_label()
        if end_index < len(displayed_rows):
            self._win.after_idle(
                schedule_next,
                load_token,
                render_token,
                displayed_rows,
                filtered,
                total_visible_rows,
                end_index,
                render_started_at,
            )
            return

        self._log_preview_performance(
            "render rows",
            render_started_at,
            rows=len(displayed_rows),
            filtered=filtered,
            visible_columns=len(self._view_state.visible_column_indices),
        )