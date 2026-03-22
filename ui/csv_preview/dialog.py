from __future__ import annotations

import logging
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from tkinter import filedialog, messagebox, ttk

from gp_data.settings import SettingsStore
from .analysis import PreviewAnalysisSnapshot, build_preview_analysis_snapshot
from .analysis_dialog import build_csv_preview_analysis_view, open_csv_preview_analysis_dialog_from_snapshot
from .analysis_launcher import _AnalysisSnapshotCoordinator, _PreviewAnalysisLauncher
from .dialog_support import (
    _build_tree as _build_tree_impl,
    _column_ids as _column_ids_impl,
    _column_width as _column_width_impl,
    _default_csv_preview_export_directory as _default_csv_preview_export_directory_impl,
    _default_csv_preview_export_path as _default_csv_preview_export_path_impl,
    _normalized_visible_column_indices as _normalized_visible_column_indices_impl,
    _paths_match as _paths_match_impl,
    _prepare_csv_preview_export_directory as _prepare_csv_preview_export_directory_impl,
    _rendered_preview_row_limit as _rendered_preview_row_limit_impl,
    _widget_descends_from as _widget_descends_from_impl,
    _write_csv_preview_export as _write_csv_preview_export_impl,
)
from .helpers import (
    HEADER_FILTER_POPUP_LABEL_MAX_LENGTH,
    _compact_filter_popup_label,
    _detect_numeric_columns,
    _detect_quantity_column,
    _detect_session_column,
    _filter_label,
    _header_suggests_numeric,
    _is_identifier_column,
    _loading_summary_text,
    _parse_decimal,
    _row_search_text,
    _sorted_distinct_values,
    _sort_rows,
    _summary_text,
)
from .loader import CsvPreviewData, iter_csv_preview_rows, load_csv_preview, resolve_csv_preview_metadata
from .pipeline import (
    MAX_INDEXED_SOURCE_MEMORY_BYTES as _PIPELINE_MAX_INDEXED_SOURCE_MEMORY_BYTES,
    _FilteredCountUpdate,
    _FilteredPreviewUpdate,
    _PreviewFilterState,
)
from .preview_pipeline import _PreviewDataPipeline
from .runtime_hooks import configure_preview_runtime
from .preview_settings import build_preview_dialog_settings_bindings
from .preview_state import _PreviewViewState
from .refresh_controller import (
    CSV_PREVIEW_LOADING_ROW_TEXT,
    _MetadataErrorUpdate,
    _MetadataResolvedUpdate,
    _PreviewRefreshControllerBase,
)
from .row_combiner import (
    _iter_combined_rows as _iter_combined_rows_impl,
    _iter_rows_before_header_filter as _iter_rows_before_header_filter_impl,
)
from .table_helpers import _PreviewColumnManager, _PreviewRowRenderer
from .table_controller import _PreviewPopupExportController, _PreviewTableController
from ..view_helpers import ProcessingDialogHandle


LOGGER = logging.getLogger(__name__)


MIN_PREVIEW_WIDTH = 800
MIN_PREVIEW_HEIGHT = 420
DEFAULT_COLUMN_WIDTH = 140
MAX_COLUMN_WIDTH = 320
MIN_COLUMN_WIDTH = 80
ROW_INSERT_CHUNK_SIZE = 250
MAX_RENDERED_PREVIEW_ROWS = 5000
MIN_RENDERED_PREVIEW_ROWS = 750
MAX_RENDERED_PREVIEW_CELLS = 60000
HEADER_FILTER_POPUP_WIDTH = 320
HEADER_FILTER_POPUP_HEIGHT = 300
HEADER_FILTER_POPUP_LIST_HEIGHT = 10
CSV_PREVIEW_EXPORT_ENCODING = "utf-8-sig"
MAX_INDEXED_SOURCE_MEMORY_BYTES = _PIPELINE_MAX_INDEXED_SOURCE_MEMORY_BYTES


def _log_preview_performance(operation: str, started_at: float, **fields: object) -> None:
    if not LOGGER.isEnabledFor(logging.DEBUG):
        return
    duration_ms = (perf_counter() - started_at) * 1000.0
    details = ", ".join(f"{key}={value}" for key, value in fields.items())
    if details:
        LOGGER.debug("CSV preview %s took %.1fms (%s)", operation, duration_ms, details)
        return
    LOGGER.debug("CSV preview %s took %.1fms", operation, duration_ms)


def _header_mode_text(has_header_row: bool) -> str:
    if has_header_row:
        return "Headers: Row 1"
    return "Headers: Generated"


@dataclass(frozen=True)
class _PreviewDialogWidgets:
    win: tk.Toplevel
    container: ttk.Frame
    workspace_row: ttk.Frame
    summary: ttk.Label
    filter_row: ttk.Frame
    summary_var: tk.StringVar
    query_var: tk.StringVar
    query_entry: ttk.Entry
    combine_sessions_var: tk.BooleanVar
    table_frame: ttk.Frame
    tree: ttk.Treeview
    button_row: ttk.Frame


def _column_width(header: str) -> int:
    return _column_width_impl(
        header,
        default_width=DEFAULT_COLUMN_WIDTH,
        min_width=MIN_COLUMN_WIDTH,
        max_width=MAX_COLUMN_WIDTH,
    )


def _column_ids(data: CsvPreviewData) -> list[str]:
    return _column_ids_impl(data)


def _rendered_preview_row_limit(column_count: int) -> int:
    return _rendered_preview_row_limit_impl(
        column_count,
        max_rendered_preview_rows=MAX_RENDERED_PREVIEW_ROWS,
        min_rendered_preview_rows=MIN_RENDERED_PREVIEW_ROWS,
        max_rendered_preview_cells=MAX_RENDERED_PREVIEW_CELLS,
    )


def _normalized_visible_column_indices(column_count: int, visible_indices: list[int] | None) -> list[int]:
    return _normalized_visible_column_indices_impl(column_count, visible_indices)


def _build_tree(parent: tk.Misc, data: CsvPreviewData) -> ttk.Treeview:
    column_ids = _column_ids(data)
    return _build_tree_impl(
        parent,
        data,
        column_ids=column_ids,
        column_width_for_header=_column_width,
        min_column_width=MIN_COLUMN_WIDTH,
    )


def _default_csv_preview_export_path(source_path: Path) -> Path:
    return _default_csv_preview_export_path_impl(source_path)


def _default_csv_preview_export_directory(source_path: Path) -> Path:
    return _default_csv_preview_export_directory_impl(source_path)


def _prepare_csv_preview_export_directory(source_path: Path) -> Path:
    return _prepare_csv_preview_export_directory_impl(source_path)


def _paths_match(first: Path, second: Path) -> bool:
    return _paths_match_impl(first, second)


def _write_csv_preview_export(dest_path: Path, headers: list[str], rows) -> None:
    _write_csv_preview_export_impl(dest_path, headers, rows, encoding=CSV_PREVIEW_EXPORT_ENCODING)


def _widget_descends_from(widget: tk.Misc | None, ancestor: tk.Misc | None) -> bool:
    return _widget_descends_from_impl(widget, ancestor)


def _iter_combined_rows(data: CsvPreviewData, enabled: bool):
    yield from _iter_combined_rows_impl(data, enabled)


def _iter_rows_before_header_filter(
    data: CsvPreviewData,
    query: str,
    combine_sessions: bool,
    combined_rows: list[tuple[str, ...]] | None = None,
):
    yield from _iter_rows_before_header_filter_impl(
        data,
        query,
        combine_sessions,
        combined_rows=combined_rows,
    )


configure_preview_runtime(
    max_indexed_source_memory_bytes=lambda: MAX_INDEXED_SOURCE_MEMORY_BYTES,
    log_preview_performance=lambda operation, started_at, **fields: _log_preview_performance(
        operation,
        started_at,
        **fields,
    ),
    row_search_text=lambda row: _row_search_text(row),
    iter_csv_preview_rows=lambda data: iter_csv_preview_rows(data),
    iter_rows_before_header_filter=lambda data, query, combine_sessions, combined_rows=None: _iter_rows_before_header_filter(
        data,
        query,
        combine_sessions,
        combined_rows=combined_rows,
    ),
    sort_rows=lambda rows, column_index, *, descending, numeric: _sort_rows(
        rows,
        column_index,
        descending=descending,
        numeric=numeric,
    ),
    sorted_distinct_values=lambda rows, column_index: _sorted_distinct_values(rows, column_index),
    header_suggests_numeric=lambda header: _header_suggests_numeric(header),
    is_identifier_column=lambda header: _is_identifier_column(header),
    parse_decimal=lambda value: _parse_decimal(value),
    resolve_metadata=lambda data: resolve_csv_preview_metadata(data),
    metadata_resolved_update_factory=lambda resolved_data: _MetadataResolvedUpdate(resolved_data=resolved_data),
    metadata_error_update_factory=lambda error: _MetadataErrorUpdate(error=error),
    iter_combined_rows=lambda data, enabled: _iter_combined_rows(data, enabled),
    perf_counter_impl=lambda: perf_counter(),
    loading_summary_text=lambda data, *, filtered, sort_description=None: _loading_summary_text(
        data,
        filtered=filtered,
        sort_description=sort_description,
    ),
    summary_text=lambda data, *, visible_rows, displayed_rows, loaded_rows, filtered=False, sort_description=None: _summary_text(
        data,
        visible_rows=visible_rows,
        displayed_rows=displayed_rows,
        loaded_rows=loaded_rows,
        filtered=filtered,
        sort_description=sort_description,
    ),
    normalize_visible_column_indices=lambda column_count, visible_indices: _normalized_visible_column_indices(
        column_count,
        visible_indices,
    ),
)


def _build_preview_dialog_widgets(
    parent: tk.Misc,
    data: CsvPreviewData,
    *,
    width: int,
    height: int,
) -> _PreviewDialogWidgets:
    win = tk.Toplevel(parent)
    win.title(f"CSV Preview - {data.path.name}")
    win.geometry(f"{max(width, MIN_PREVIEW_WIDTH)}x{max(height, MIN_PREVIEW_HEIGHT)}")

    container = ttk.Frame(win)
    container.pack(fill="both", expand=True, padx=8, pady=8)
    container.columnconfigure(0, weight=1)
    container.rowconfigure(3, weight=1)

    workspace_row = ttk.Frame(container)
    workspace_row.grid(row=0, column=0, sticky="ew", pady=(0, 6))

    initial_displayed_rows = min(data.row_count or len(data.rows), _rendered_preview_row_limit(data.column_count))
    summary_var = tk.StringVar(
        value=_summary_text(
            data,
            visible_rows=data.row_count,
            displayed_rows=initial_displayed_rows,
            loaded_rows=0 if initial_displayed_rows else None,
        )
    )
    summary = ttk.Label(container, textvariable=summary_var, anchor="w")
    summary.grid(row=1, column=0, sticky="ew", pady=(0, 6))

    filter_row = ttk.Frame(container)
    filter_row.grid(row=2, column=0, sticky="ew", pady=(0, 6))
    ttk.Label(filter_row, text="Search").pack(side="left")

    query_var = tk.StringVar()
    query_entry = ttk.Entry(filter_row, textvariable=query_var, width=24)
    query_entry.pack(side="left", padx=(6, 12))
    ttk.Label(filter_row, text="Press Enter to search").pack(side="left", padx=(0, 12))
    ttk.Label(filter_row, text=_header_mode_text(data.has_header_row), anchor="e").pack(side="right")

    combine_sessions_supported = _detect_session_column(data.headers) is not None and _detect_quantity_column(data.headers) is not None
    combine_sessions_var = tk.BooleanVar(value=False)
    combine_sessions_toggle = ttk.Checkbutton(filter_row, text="Combine sessions", variable=combine_sessions_var)
    combine_sessions_toggle.pack(side="left", padx=(0, 12))
    if not combine_sessions_supported:
        combine_sessions_toggle.configure(state="disabled")

    table_frame = ttk.Frame(container)
    table_frame.grid(row=3, column=0, sticky="nsew")
    table_frame.columnconfigure(0, weight=1)
    table_frame.rowconfigure(0, weight=1)

    tree = _build_tree(table_frame, data)
    y_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
    x_scroll = ttk.Scrollbar(table_frame, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

    tree.grid(row=0, column=0, sticky="nsew")
    y_scroll.grid(row=0, column=1, sticky="ns")
    x_scroll.grid(row=1, column=0, sticky="ew")

    button_row = ttk.Frame(container)
    button_row.grid(row=4, column=0, sticky="ew", pady=(8, 0))

    return _PreviewDialogWidgets(
        win=win,
        container=container,
        workspace_row=workspace_row,
        summary=summary,
        filter_row=filter_row,
        summary_var=summary_var,
        query_var=query_var,
        query_entry=query_entry,
        combine_sessions_var=combine_sessions_var,
        table_frame=table_frame,
        tree=tree,
        button_row=button_row,
    )


def create_csv_preview_dialog(
    parent: tk.Misc,
    data: CsvPreviewData,
    *,
    width: int,
    height: int,
    initial_visible_column_indices: list[int] | None = None,
    initial_sort_column_index: int | None = None,
    initial_sort_descending: bool = False,
    on_visible_columns_changed=None,
    on_sort_changed=None,
) -> tk.Toplevel:
    widgets = _build_preview_dialog_widgets(parent, data, width=width, height=height)
    analysis_frame: ttk.Frame | None = None
    cached_analysis_snapshot: PreviewAnalysisSnapshot | None = None
    cached_analysis_request_state: tuple[_PreviewFilterState, tuple[int, ...], frozenset[int]] | None = None

    def _current_analysis_request_state() -> tuple[_PreviewFilterState, tuple[int, ...], frozenset[int]]:
        filter_state, visible_column_indices, numeric_column_indices = controller._analysis_request_state()
        return filter_state, tuple(visible_column_indices), frozenset(numeric_column_indices)

    def _sync_workspace_buttons() -> None:
        preview_button.configure(state="disabled" if analysis_frame is None else "normal")
        analysis_button.configure(state="normal" if analysis_frame is None else "disabled")

    def _show_preview_workspace() -> None:
        nonlocal analysis_frame
        if analysis_frame is not None and analysis_frame.winfo_exists():
            analysis_frame.destroy()
        analysis_frame = None
        widgets.summary.grid()
        widgets.filter_row.grid()
        widgets.table_frame.grid()
        _sync_workspace_buttons()
        widgets.query_entry.focus_set()

    def _show_analysis_snapshot(snapshot) -> None:
        nonlocal analysis_frame, cached_analysis_request_state, cached_analysis_snapshot
        widgets.summary.grid_remove()
        widgets.filter_row.grid_remove()
        widgets.table_frame.grid_remove()
        if analysis_frame is not None and analysis_frame.winfo_exists():
            analysis_frame.destroy()
        cached_analysis_snapshot = snapshot
        cached_analysis_request_state = _current_analysis_request_state()
        analysis_frame = build_csv_preview_analysis_view(
            widgets.container,
            snapshot,
            close_command=_show_preview_workspace,
            popup_parent=widgets.win,
            chart_message_wraplength=max(widgets.win.winfo_width() - 120, 240),
        )
        analysis_frame.grid(row=1, column=0, rowspan=3, sticky="nsew")
        _sync_workspace_buttons()

    def _open_analysis_workspace() -> None:
        current_request_state = _current_analysis_request_state()
        if cached_analysis_snapshot is not None and current_request_state == cached_analysis_request_state:
            _show_analysis_snapshot(cached_analysis_snapshot)
            return
        controller.open_analysis_dialog()

    controller = _PreviewTableController(
        widgets.win,
        widgets.tree,
        data,
        widgets.summary_var,
        widgets.query_var,
        widgets.combine_sessions_var,
        _column_ids(data),
        initial_visible_column_indices=initial_visible_column_indices,
        initial_sort_column_index=initial_sort_column_index,
        initial_sort_descending=initial_sort_descending,
        on_visible_columns_changed=on_visible_columns_changed,
        on_sort_changed=on_sort_changed,
        view_state_factory=_PreviewViewState,
        normalize_visible_column_indices=_normalized_visible_column_indices,
        pipeline_factory=_PreviewDataPipeline,
        popup_export_controller_factory=lambda owner: _PreviewPopupExportController(
            owner,
            popup_width=HEADER_FILTER_POPUP_WIDTH,
            popup_height=HEADER_FILTER_POPUP_HEIGHT,
            popup_list_height=HEADER_FILTER_POPUP_LIST_HEIGHT,
            prepare_export_directory=_prepare_csv_preview_export_directory,
            default_export_path=_default_csv_preview_export_path,
            paths_match=_paths_match,
            write_export=_write_csv_preview_export,
            filter_label=_filter_label,
            compact_filter_popup_label=_compact_filter_popup_label,
            widget_descends_from=_widget_descends_from,
        ),
        column_manager_factory=lambda *args, **kwargs: _PreviewColumnManager(
            *args,
            **kwargs,
            column_ids_for_data=_column_ids,
            column_width_for_header=_column_width,
            min_column_width=MIN_COLUMN_WIDTH,
            normalize_visible_column_indices=_normalized_visible_column_indices,
            filter_label=_filter_label,
        ),
        row_renderer_factory=lambda *args: _PreviewRowRenderer(
            *args,
            row_insert_chunk_size=ROW_INSERT_CHUNK_SIZE,
            log_preview_performance=_log_preview_performance,
        ),
        analysis_launcher_factory=lambda *args: _PreviewAnalysisLauncher(
            *args,
            coordinator_factory=lambda win: _AnalysisSnapshotCoordinator(
                win,
                processing_dialog_factory=lambda analysis_win: ProcessingDialogHandle(
                    analysis_win,
                    title="Preparing Analysis",
                    eyebrow_text="ANALYSIS",
                    detail_text="Collecting filtered rows and preparing chart summaries.",
                ),
                pipeline_factory=_PreviewDataPipeline,
                build_snapshot=lambda *launcher_args, **launcher_kwargs: build_preview_analysis_snapshot(
                    *launcher_args,
                    **launcher_kwargs,
                ),
                show_error=lambda title, message: messagebox.showerror(title, message),
                open_analysis_dialog_from_snapshot=lambda parent, snapshot: _show_analysis_snapshot(snapshot),
            ),
        ),
        processing_dialog_factory=lambda win: ProcessingDialogHandle(
            win,
            title="Processing CSV",
            eyebrow_text="SESSION MERGE",
            detail_text="Combining sessions and rebuilding the visible preview rows.",
        ),
        rendered_row_limit=_rendered_preview_row_limit,
    )
    widgets.win._csv_preview_controller = controller  # type: ignore[attr-defined]

    def _clear_filters() -> None:
        widgets.query_var.set("")
        widgets.combine_sessions_var.set(False)
        controller.clear_sort()
        controller.clear_header_filter()

    preview_button = ttk.Button(widgets.workspace_row, text="Preview", command=_show_preview_workspace)
    preview_button.pack(side="left")
    analysis_button = ttk.Button(widgets.workspace_row, text="Analysis", command=_open_analysis_workspace)
    analysis_button.pack(side="left", padx=(8, 0))
    _sync_workspace_buttons()

    ttk.Button(widgets.filter_row, text="Columns", command=controller.open_column_dialog).pack(side="left", padx=(0, 12))
    ttk.Button(widgets.filter_row, text="Save As CSV", command=controller.export_current_view_as_csv).pack(side="left", padx=(0, 12))
    ttk.Button(widgets.filter_row, text="Clear filters", command=_clear_filters).pack(side="left")

    ttk.Button(widgets.button_row, text="Close", command=widgets.win.destroy).pack(side="right")

    widgets.query_var.trace_add("write", controller.on_query_changed)
    widgets.combine_sessions_var.trace_add("write", controller.on_combine_sessions_changed)
    widgets.query_entry.bind("<Return>", controller.trigger_refresh_now, add="+")
    widgets.tree.bind("<ButtonRelease-1>", controller.on_tree_click, add="+")
    controller.refresh()
    widgets.query_entry.focus_set()

    return widgets.win


def open_csv_preview_dialog(
    parent: tk.Misc,
    csv_path: str | Path,
    *,
    width: int,
    height: int,
    has_header_row: bool = True,
) -> tk.Toplevel:
    data = load_csv_preview(csv_path, has_header_row=has_header_row)
    settings_store = SettingsStore()
    settings_bindings = build_preview_dialog_settings_bindings(
        data,
        settings_store,
        messagebox.showerror,
    )

    return create_csv_preview_dialog(
        parent,
        data,
        width=width,
        height=height,
        initial_visible_column_indices=settings_bindings.initial_visible_column_indices,
        initial_sort_column_index=settings_bindings.initial_sort_column_index,
        initial_sort_descending=settings_bindings.initial_sort_descending,
        on_visible_columns_changed=settings_bindings.on_visible_columns_changed,
        on_sort_changed=settings_bindings.on_sort_changed,
    )
