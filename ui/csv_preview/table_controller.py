from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk

from .helpers import _sort_direction_label
from .loader import CsvPreviewData
from .pipeline import _FilteredCountUpdate, _FilteredErrorUpdate, _FilteredPreviewUpdate, _PreviewFilterState
from .popup_controller import _PreviewPopupExportControllerBase
from .refresh_controller import _PreviewRefreshControllerBase
from ..view_helpers import ProcessingDialogHandle


class _PreviewPopupExportController(_PreviewPopupExportControllerBase):
    def __init__(
        self,
        controller,
        *,
        popup_width: int,
        popup_height: int,
        popup_list_height: int,
        prepare_export_directory,
        default_export_path,
        paths_match,
        write_export,
        filter_label,
        compact_filter_popup_label,
        widget_descends_from,
    ) -> None:
        super().__init__(controller)
        self._configured_popup_width = popup_width
        self._configured_popup_height = popup_height
        self._configured_popup_list_height = popup_list_height
        self._prepare_export_directory_impl = prepare_export_directory
        self._default_export_path_impl = default_export_path
        self._paths_match_impl = paths_match
        self._write_export_impl = write_export
        self._filter_label_impl = filter_label
        self._compact_filter_popup_label_impl = compact_filter_popup_label
        self._widget_descends_from_impl = widget_descends_from

    def _popup_width(self) -> int:
        return self._configured_popup_width

    def _popup_height(self) -> int:
        return self._configured_popup_height

    def _popup_list_height(self) -> int:
        return self._configured_popup_list_height

    def _prepare_export_directory(self, source_path: Path) -> Path:
        return self._prepare_export_directory_impl(source_path)

    def _default_export_path(self, source_path: Path) -> Path:
        return self._default_export_path_impl(source_path)

    def _paths_match(self, first: Path, second: Path) -> bool:
        return self._paths_match_impl(first, second)

    def _write_export(self, dest_path: Path, headers: list[str], rows) -> None:
        self._write_export_impl(dest_path, headers, rows)

    def _filter_label(self, header: str, index: int) -> str:
        return self._filter_label_impl(header, index)

    def _compact_filter_popup_label(self, value: str) -> str:
        return self._compact_filter_popup_label_impl(value)

    def _widget_descends_from(self, widget: tk.Misc | None, ancestor: tk.Misc | None) -> bool:
        return self._widget_descends_from_impl(widget, ancestor)


class _PreviewTableController(_PreviewRefreshControllerBase):
    def __init__(
        self,
        win: tk.Toplevel,
        tree: ttk.Treeview,
        data: CsvPreviewData,
        summary_var: tk.StringVar,
        query_var: tk.StringVar,
        combine_sessions_var: tk.BooleanVar,
        all_column_ids: list[str],
        initial_visible_column_indices: list[int] | None = None,
        initial_sort_column_index: int | None = None,
        initial_sort_descending: bool = False,
        on_visible_columns_changed=None,
        on_sort_changed=None,
        *,
        view_state_factory,
        normalize_visible_column_indices,
        pipeline_factory,
        popup_export_controller_factory,
        column_manager_factory,
        row_renderer_factory,
        analysis_launcher_factory,
        processing_dialog_factory,
        rendered_row_limit,
    ) -> None:
        self._win = win
        self._tree = tree
        self._summary_var = summary_var
        self._query_var = query_var
        self._combine_sessions_var = combine_sessions_var
        self._all_column_ids = all_column_ids
        self._pipeline = pipeline_factory(data)
        self._rendered_row_limit_for_columns = rendered_row_limit
        self._view_state = view_state_factory(
            visible_column_indices=normalize_visible_column_indices(
                len(all_column_ids),
                initial_visible_column_indices,
            ),
            sort_column_index=initial_sort_column_index,
            sort_descending=bool(initial_sort_descending) if initial_sort_column_index is not None else False,
        )
        self._on_visible_columns_changed = on_visible_columns_changed
        self._on_sort_changed = on_sort_changed
        self._popup_export_controller = popup_export_controller_factory(self)
        self._column_manager = column_manager_factory(
            win,
            tree,
            self._all_column_ids,
            self._view_state,
            lambda: self._data,
            self._popup_export_controller,
            on_visible_columns_changed=on_visible_columns_changed,
            on_sort_changed=on_sort_changed,
        )
        self._row_renderer = row_renderer_factory(
            win,
            tree,
            self._view_state,
            self._update_summary_label,
        )
        self._analysis_launcher = analysis_launcher_factory(
            win,
            lambda: self._data,
            self._current_filter_state,
            lambda: self._view_state.visible_column_indices,
            self._pipeline.is_numeric_sort_column,
        )
        self._processing_status = processing_dialog_factory(win)
        self._processing_status_load_token: int | None = None
        self._initialize_refresh_state()

    @property
    def _header_filter_popup(self) -> tk.Toplevel | None:
        return self._popup_export_controller.popup

    @property
    def _data(self) -> CsvPreviewData:
        return self._pipeline.data

    @property
    def _processing_status_var(self) -> tk.StringVar:
        return self._processing_status.message_var

    @property
    def _processing_status_dialog(self) -> tk.Toplevel | None:
        return self._processing_status.dialog

    @property
    def _analysis_status_var(self) -> tk.StringVar:
        return self._analysis_launcher.status_var

    @property
    def _analysis_status_dialog(self) -> tk.Toplevel | None:
        return self._analysis_launcher.status_dialog

    def _rendered_row_limit(self) -> int:
        return self._rendered_row_limit_for_columns(self._data.column_count)

    def _current_filter_state(self) -> _PreviewFilterState:
        return self._view_state.filter_state(
            query=self._query_var.get().strip(),
            combine_sessions=self._combine_sessions_var.get(),
        )

    def _update_summary_label(self) -> None:
        self._summary_var.set(
            self._view_state.summary.render_text(
                self._data,
                sort_description=self._active_sort_description(),
            )
        )

    def _active_sort_description(self) -> str | None:
        column_index = self._view_state.sort_column_index
        if column_index is None or column_index >= len(self._data.headers):
            return None
        header = self._data.headers[column_index].strip() or f"Column {column_index + 1}"
        numeric = self._pipeline.is_numeric_sort_column(column_index)
        direction = _sort_direction_label(descending=self._view_state.sort_descending, numeric=numeric)
        return f"Sorted by {header} ({direction})"

    def _notify_sort_changed(self) -> None:
        self._column_manager.notify_sort_changed()

    def set_header_filter(self, column_index: int | None, value: str | None) -> None:
        self._view_state.set_header_filter(column_index, value)
        self._popup_export_controller._header_filter_popup_value.set(value or "")
        self.refresh()

    def clear_header_filter(self) -> None:
        self.set_header_filter(None, None)
        self._popup_export_controller.destroy_header_filter_popup()

    def set_sort(self, column_index: int, *, descending: bool) -> None:
        self._view_state.set_sort(column_index, descending=descending)
        self._notify_sort_changed()
        self._popup_export_controller.destroy_header_filter_popup()
        self.refresh()

    def clear_sort(self) -> None:
        self._view_state.set_sort(None)
        self._notify_sort_changed()
        self._popup_export_controller.destroy_header_filter_popup()
        self.refresh()

    def on_query_changed(self, *_args) -> None:
        self._cancel_pending_analysis_request()
        self._clear_processing_status()
        super().on_query_changed(*_args)

    def on_combine_sessions_changed(self, *_args) -> None:
        self._set_processing_status("Processing sessions...")
        self._processing_status_load_token = self._load_token + 1
        self.refresh()

    def refresh(self, *_args) -> None:
        self._cancel_pending_analysis_request()
        next_load_token = self._load_token + 1
        if self._processing_status_load_token is not None and self._processing_status_load_token != next_load_token:
            self._clear_processing_status()
        super().refresh(*_args)

    def _analysis_request_state(self) -> tuple[_PreviewFilterState, list[int], set[int]]:
        return self._analysis_launcher.request_state()

    def export_current_view_as_csv(self) -> None:
        self._popup_export_controller.export_current_view_as_csv()

    def open_analysis_dialog(self) -> None:
        self._analysis_launcher.open_dialog()

    def show_header_filter_popup(self, column_index: int, x_root: int, y_root: int) -> None:
        self._popup_export_controller.show_header_filter_popup(column_index, x_root, y_root)

    def _apply_selected_header_filter_option(self) -> None:
        self._popup_export_controller._apply_selected_header_filter_option()

    def on_tree_click(self, event) -> None:
        if self._tree.identify_region(event.x, event.y) != "heading":
            return
        column_index = self._column_index_from_event_column(self._tree.identify_column(event.x))
        if column_index is None:
            return
        self._popup_export_controller.show_header_filter_popup(column_index, event.x_root, event.y_root)

    def _column_index_from_event_column(self, tree_column: str) -> int | None:
        if not tree_column.startswith("#"):
            return None
        try:
            visible_index = int(tree_column[1:]) - 1
        except ValueError:
            return None
        displaycolumns = list(self._tree.cget("displaycolumns")) or self._all_column_ids
        if visible_index < 0 or visible_index >= len(displaycolumns):
            return None
        column_id = displaycolumns[visible_index]
        if not str(column_id).startswith("col_"):
            return None
        try:
            return int(str(column_id).split("_", 1)[1])
        except ValueError:
            return None

    def _update_tree_headings(self) -> None:
        self._column_manager.update_tree_headings()

    def _rebuild_tree_columns(self, previous_column_count: int) -> None:
        self._column_manager.rebuild_tree_columns(previous_column_count)

    def open_column_dialog(self) -> None:
        self._column_manager.open_column_dialog(self._apply_visible_columns)

    def _apply_visible_columns(self, visible_indices: list[int]) -> None:
        self._column_manager.apply_visible_columns(
            visible_indices,
            clear_header_filter=self.clear_header_filter,
            refresh=self.refresh,
        )

    def _on_filtered_refresh_message(self, message) -> None:
        if self._processing_status_load_token != message.load_token:
            return
        if self._processing_status_should_clear(message):
            self._clear_processing_status()

    def _processing_status_should_clear(self, message) -> bool:
        if isinstance(message, (_FilteredErrorUpdate, _FilteredCountUpdate)):
            return True
        return isinstance(message, _FilteredPreviewUpdate) and message.total_rows is not None

    def _set_processing_status(self, message: str) -> None:
        self._processing_status.show(message)

    def _clear_processing_status(self) -> None:
        self._processing_status_load_token = None
        self._processing_status.clear()

    def _cancel_pending_analysis_request(self) -> None:
        self._analysis_launcher.cancel()

    def _populate_rows_in_chunks(
        self,
        load_token: int,
        render_token: int,
        displayed_rows: list[tuple[str, ...]],
        filtered: bool,
        total_visible_rows: int | None,
        start_index: int,
        render_started_at: float,
    ) -> None:
        self._row_renderer.populate_rows_in_chunks(
            load_token,
            render_token,
            displayed_rows,
            filtered,
            total_visible_rows,
            start_index,
            render_started_at,
            current_load_token=self._load_token,
            current_render_token=self._render_token,
            schedule_next=self._populate_rows_in_chunks,
        )