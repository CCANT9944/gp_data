from __future__ import annotations

import csv
import logging
import queue
import threading
import tkinter as tk
from collections import OrderedDict
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from tkinter import filedialog, messagebox, ttk

from gp_data.settings import SettingsStore
from .analysis import PreviewAnalysisSnapshot, build_preview_analysis_snapshot
from .analysis_dialog import open_csv_preview_analysis_dialog_from_snapshot
from .helpers import (
    HEADER_FILTER_POPUP_LABEL_MAX_LENGTH,
    _column_identity_keys,
    _column_index_from_identity_key,
    _combined_sessions,
    _compact_filter_popup_label,
    _detect_numeric_columns,
    _detect_quantity_column,
    _detect_session_column,
    _filter_label,
    _format_decimal,
    _header_suggests_numeric,
    _is_identifier_column,
    _loading_summary_text,
    _normalized_header,
    _normalized_visible_column_indices,
    _parse_decimal,
    _row_matches_normalized_query,
    _row_matches_query,
    _row_search_text,
    _sort_direction_label,
    _sorted_distinct_column_values,
    _sorted_distinct_values,
    _sort_rows,
    _summary_text,
    _visible_column_indices_from_keys,
    _visible_column_keys,
)
from .loader import CsvPreviewData, iter_csv_preview_rows, load_csv_preview, resolve_csv_preview_metadata
from .pipeline import (
    MAX_INDEXED_SOURCE_MEMORY_BYTES as _PIPELINE_MAX_INDEXED_SOURCE_MEMORY_BYTES,
    _FilteredCountUpdate,
    _FilteredErrorUpdate,
    _FilteredPreviewUpdate,
    _PreviewDataPipelineBase,
    _PreviewFilterState,
)
from .popup_controller import _PreviewPopupExportControllerBase
from .refresh_controller import (
    CSV_PREVIEW_LOADING_ROW_TEXT,
    PREWARM_VISIBLE_HEADER_FILTER_COLUMNS,
    _MetadataErrorUpdate,
    _MetadataRefreshMessage,
    _MetadataResolvedUpdate,
    _PreviewRefreshControllerBase,
)
from ..view_helpers import ProcessingDialogHandle


LOGGER = logging.getLogger(__name__)


MIN_PREVIEW_WIDTH = 800
MIN_PREVIEW_HEIGHT = 420
DEFAULT_COLUMN_WIDTH = 140
MAX_COLUMN_WIDTH = 320
MIN_COLUMN_WIDTH = 80
ROW_INSERT_CHUNK_SIZE = 250
COMBINED_SESSION_SEPARATOR = " + "
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


@dataclass
class _PreviewSummaryState:
    filtered: bool = False
    loading: bool = False
    visible_rows: int | None = None
    displayed_rows: int = 0
    loaded_rows: int | None = None

    def set_loading(self, *, filtered: bool) -> None:
        self.filtered = filtered
        self.loading = True
        self.visible_rows = None
        self.displayed_rows = 0
        self.loaded_rows = 0

    def set_ready(self, *, filtered: bool, visible_rows: int | None, displayed_rows: int) -> None:
        self.filtered = filtered
        self.loading = False
        self.visible_rows = visible_rows
        self.displayed_rows = displayed_rows
        self.loaded_rows = 0 if displayed_rows else None

    def apply_loaded_chunk(
        self,
        *,
        filtered: bool,
        total_visible_rows: int | None,
        displayed_rows: int,
        loaded_rows: int,
    ) -> None:
        self.filtered = filtered
        if self.visible_rows is None:
            self.visible_rows = total_visible_rows
        self.displayed_rows = displayed_rows
        self.loaded_rows = loaded_rows

    def render_text(self, data: CsvPreviewData, *, sort_description: str | None = None) -> str:
        if self.loading:
            return _loading_summary_text(data, filtered=self.filtered, sort_description=sort_description)
        return _summary_text(
            data,
            visible_rows=self.visible_rows,
            displayed_rows=self.displayed_rows,
            loaded_rows=self.loaded_rows,
            filtered=self.filtered,
            sort_description=sort_description,
        )


@dataclass
class _PreviewViewState:
    visible_column_indices: list[int]
    header_filter_column_index: int | None = None
    header_filter_value: str | None = None
    sort_column_index: int | None = None
    sort_descending: bool = False
    summary: _PreviewSummaryState = field(default_factory=_PreviewSummaryState)

    def filter_state(self, *, query: str, combine_sessions: bool) -> _PreviewFilterState:
        return _PreviewFilterState(
            query=query,
            combine_sessions=combine_sessions,
            header_filter_column_index=self.header_filter_column_index,
            header_filter_value=self.header_filter_value,
            sort_column_index=self.sort_column_index,
            sort_descending=self.sort_descending,
        )

    def visible_column_ids(self, all_column_ids: list[str]) -> list[str]:
        return [all_column_ids[index] for index in self.visible_column_indices]

    def set_header_filter(self, column_index: int | None, value: str | None) -> None:
        self.header_filter_column_index = column_index
        self.header_filter_value = value

    def set_sort(self, column_index: int | None, *, descending: bool = False) -> None:
        self.sort_column_index = column_index
        self.sort_descending = bool(descending) if column_index is not None else False

    def apply_visible_columns(self, all_column_ids: list[str], visible_indices: list[int]) -> tuple[bool, bool]:
        self.visible_column_indices = _normalized_visible_column_indices(len(all_column_ids), visible_indices)
        header_filter_cleared = False
        sort_cleared = False
        if self.header_filter_column_index is not None and self.header_filter_column_index not in self.visible_column_indices:
            self.header_filter_column_index = None
            self.header_filter_value = None
            header_filter_cleared = True
        if self.sort_column_index is not None and self.sort_column_index not in self.visible_column_indices:
            self.sort_column_index = None
            self.sort_descending = False
            sort_cleared = True
        return header_filter_cleared, sort_cleared


@dataclass(frozen=True)
class _AnalysisSnapshotReady:
    request_token: int
    snapshot: PreviewAnalysisSnapshot


@dataclass(frozen=True)
class _AnalysisSnapshotError:
    request_token: int
    error: Exception


_AnalysisMessage = _AnalysisSnapshotReady | _AnalysisSnapshotError


class _AnalysisSnapshotCoordinator:
    def __init__(self, win: tk.Toplevel) -> None:
        self._win = win
        self._status = ProcessingDialogHandle(
            win,
            title="Preparing Analysis",
            eyebrow_text="ANALYSIS",
            detail_text="Collecting filtered rows and preparing chart summaries.",
        )
        self._request_token = 0
        self._queue: queue.Queue[_AnalysisMessage] = queue.Queue()
        self._pending_tokens: set[int] = set()
        self._polling = False

    @property
    def status_var(self) -> tk.StringVar:
        return self._status.message_var

    @property
    def status_dialog(self) -> tk.Toplevel | None:
        return self._status.dialog

    def request(
        self,
        data: CsvPreviewData,
        filter_state: _PreviewFilterState,
        visible_column_indices: list[int],
        numeric_column_indices: set[int],
    ) -> None:
        self.cancel()
        self._request_token += 1
        request_token = self._request_token
        self._pending_tokens.add(request_token)
        self._status.show("Preparing analysis...")
        worker = threading.Thread(
            target=self._build_snapshot,
            args=(request_token, data, filter_state, visible_column_indices, numeric_column_indices),
            daemon=True,
        )
        worker.start()
        if not self._polling:
            self._polling = True
            self._win.after(25, self._poll)

    def cancel(self) -> None:
        if self._pending_tokens:
            self._request_token += 1
            self._pending_tokens.clear()
        self._status.clear()

    def _build_snapshot(
        self,
        request_token: int,
        data: CsvPreviewData,
        filter_state: _PreviewFilterState,
        visible_column_indices: list[int],
        numeric_column_indices: set[int],
    ) -> None:
        try:
            analysis_pipeline = _PreviewDataPipeline(data)
            filtered_rows = analysis_pipeline.filtered_rows_snapshot(filter_state)
            snapshot = build_preview_analysis_snapshot(
                data,
                filtered_rows,
                visible_column_indices,
                numeric_column_indices,
                filtering_active=filter_state.filtering_active,
                combine_sessions=filter_state.combine_sessions,
            )
            self._queue.put(_AnalysisSnapshotReady(request_token=request_token, snapshot=snapshot))
        except Exception as exc:
            self._queue.put(_AnalysisSnapshotError(request_token=request_token, error=exc))

    def _poll(self) -> None:
        if not self._win.winfo_exists():
            return

        while True:
            try:
                message = self._queue.get_nowait()
            except queue.Empty:
                break

            self._pending_tokens.discard(message.request_token)
            if message.request_token != self._request_token:
                continue

            self._status.clear()
            if isinstance(message, _AnalysisSnapshotError):
                messagebox.showerror("CSV analysis unavailable", str(message.error))
                continue
            open_csv_preview_analysis_dialog_from_snapshot(self._win, message.snapshot)

        if self._pending_tokens:
            self._win.after(25, self._poll)
            return
        self._polling = False


def _column_width(header: str) -> int:
    estimated = max(MIN_COLUMN_WIDTH, min(MAX_COLUMN_WIDTH, (len(header) * 10) + 24))
    return max(DEFAULT_COLUMN_WIDTH, estimated)


def _column_ids(data: CsvPreviewData) -> list[str]:
    return [f"col_{index}" for index in range(data.column_count)]


def _rendered_preview_row_limit(column_count: int) -> int:
    safe_column_count = max(1, column_count)
    adaptive_limit = MAX_RENDERED_PREVIEW_CELLS // safe_column_count
    return max(MIN_RENDERED_PREVIEW_ROWS, min(MAX_RENDERED_PREVIEW_ROWS, adaptive_limit))


def _normalized_visible_column_indices(column_count: int, visible_indices: list[int] | None) -> list[int]:
    if not visible_indices:
        return list(range(column_count))

    normalized: list[int] = []
    seen: set[int] = set()
    for raw_index in visible_indices:
        try:
            index = int(raw_index)
        except (TypeError, ValueError):
            continue
        if index < 0 or index >= column_count or index in seen:
            continue
        normalized.append(index)
        seen.add(index)
    return normalized or list(range(column_count))


def _build_tree(parent: tk.Misc, data: CsvPreviewData) -> ttk.Treeview:
    column_ids = _column_ids(data)
    tree = ttk.Treeview(parent, columns=column_ids, show="headings")
    for column_id, header in zip(column_ids, data.headers):
        tree.heading(column_id, text=header)
        tree.column(column_id, width=_column_width(header), minwidth=MIN_COLUMN_WIDTH, stretch=False, anchor="w")
    return tree


def _default_csv_preview_export_path(source_path: Path) -> Path:
    return source_path.with_name(f"{source_path.stem}.preview.csv")


def _default_csv_preview_export_directory(source_path: Path) -> Path:
    favorites_dir = Path.home() / "Favorites"
    if favorites_dir.name.casefold() == "favorites":
        return favorites_dir / "csv_exports"
    return source_path.parent / "csv_exports"


def _prepare_csv_preview_export_directory(source_path: Path) -> Path:
    export_dir = _default_csv_preview_export_directory(source_path)
    try:
        export_dir.mkdir(parents=True, exist_ok=True)
        return export_dir
    except OSError:
        return source_path.parent


def _paths_match(first: Path, second: Path) -> bool:
    return str(first.resolve(strict=False)).casefold() == str(second.resolve(strict=False)).casefold()


def _write_csv_preview_export(dest_path: Path, headers: list[str], rows) -> None:
    with dest_path.open("w", encoding=CSV_PREVIEW_EXPORT_ENCODING, newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def _widget_descends_from(widget: tk.Misc | None, ancestor: tk.Misc | None) -> bool:
    current = widget
    while current is not None:
        if current == ancestor:
            return True
        parent_name = current.winfo_parent()
        if not parent_name:
            return False
        try:
            current = current.nametowidget(parent_name)
        except KeyError:
            return False
    return False


def _iter_combined_rows(data: CsvPreviewData, enabled: bool):
    if not enabled:
        yield from iter_csv_preview_rows(data)
        return

    session_index = _detect_session_column(data.headers)
    quantity_index = _detect_quantity_column(data.headers)
    if session_index is None or quantity_index is None or session_index == quantity_index:
        yield from iter_csv_preview_rows(data)
        return

    numeric_detection_rows = data.rows if data.fully_cached else iter_csv_preview_rows(data)
    numeric_indices = _detect_numeric_columns(data, {session_index}, rows=numeric_detection_rows)
    grouping_exclusions = {session_index, *numeric_indices}

    grouped: OrderedDict[tuple[str, ...], dict[str, object]] = OrderedDict()
    for row in iter_csv_preview_rows(data):
        key = tuple(value for index, value in enumerate(row) if index not in grouping_exclusions)
        group = grouped.get(key)
        if group is None:
            group = {
                "row": list(row),
                "sessions": [row[session_index]],
                "numeric_totals": {index: _parse_decimal(row[index]) for index in numeric_indices},
            }
            grouped[key] = group
            continue

        group["sessions"].append(row[session_index])
        for index in numeric_indices:
            row_total = _parse_decimal(row[index])
            if row_total is None:
                continue
            if group["numeric_totals"][index] is None:
                group["numeric_totals"][index] = row_total
            else:
                group["numeric_totals"][index] += row_total

    for group in grouped.values():
        combined_row = list(group["row"])
        combined_row[session_index] = _combined_sessions(group["sessions"])
        for index in numeric_indices:
            combined_row[index] = _format_decimal(group["numeric_totals"][index])
        yield tuple(combined_row)


def _iter_rows_before_header_filter(
    data: CsvPreviewData,
    query: str,
    combine_sessions: bool,
    combined_rows: list[tuple[str, ...]] | None = None,
):
    normalized_query = query.strip().casefold()
    source_rows = combined_rows if combine_sessions and combined_rows is not None else _iter_combined_rows(data, combine_sessions)
    for row in source_rows:
        if _row_matches_normalized_query(row, normalized_query):
            yield row


class _PreviewDataPipeline(_PreviewDataPipelineBase):
    def _can_index_uncombined_source_rows(self) -> bool:
        if self._data.fully_cached:
            return True

        estimated_bytes = self._estimated_uncombined_source_index_bytes()
        return estimated_bytes is not None and estimated_bytes <= MAX_INDEXED_SOURCE_MEMORY_BYTES

    def _log_performance(self, operation: str, started_at: float, **fields: object) -> None:
        _log_preview_performance(operation, started_at, **fields)

    def _row_search_text(self, row: tuple[str, ...]) -> str:
        return _row_search_text(row)

    def _iter_csv_preview_rows(self):
        return iter_csv_preview_rows(self._data)

    def _iter_rows_before_header_filter(
        self,
        query: str,
        combine_sessions: bool,
        combined_rows: list[tuple[str, ...]] | None = None,
    ):
        return _iter_rows_before_header_filter(
            self._data,
            query,
            combine_sessions,
            combined_rows=combined_rows,
        )

    def _sort_rows(
        self,
        rows: list[tuple[str, ...]],
        column_index: int,
        *,
        descending: bool,
        numeric: bool,
    ) -> list[tuple[str, ...]]:
        return _sort_rows(rows, column_index, descending=descending, numeric=numeric)

    def _sorted_distinct_values(self, rows, column_index: int) -> list[str]:
        return _sorted_distinct_values(rows, column_index)

    def _header_suggests_numeric(self, header: str) -> bool:
        return _header_suggests_numeric(header)

    def _is_identifier_column(self, header: str) -> bool:
        return _is_identifier_column(header)

    def _parse_decimal(self, value: str) -> Decimal | None:
        return _parse_decimal(value)

    def resolve_metadata_refresh_message(self) -> _MetadataRefreshMessage:
        try:
            return _MetadataResolvedUpdate(resolved_data=resolve_csv_preview_metadata(self._data))
        except Exception as exc:
            return _MetadataErrorUpdate(error=exc)

    def _combined_rows(self, combine_sessions: bool) -> list[tuple[str, ...]] | None:
        if not combine_sessions:
            return None
        if self._combined_rows_cache is None:
            started_at = perf_counter()
            self._combined_rows_cache = list(_iter_combined_rows(self._data, True))
            _log_preview_performance("combine session rows", started_at, rows=len(self._combined_rows_cache))
        return self._combined_rows_cache


def _open_column_visibility_dialog(parent: tk.Misc, headers: list[str], selected_indices: list[int], on_apply) -> tk.Toplevel:
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
        ttk.Checkbutton(container, text=_filter_label(header, index), variable=variable).pack(anchor="w")

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


class _PreviewPopupExportController(_PreviewPopupExportControllerBase):
    def _popup_width(self) -> int:
        return HEADER_FILTER_POPUP_WIDTH

    def _popup_height(self) -> int:
        return HEADER_FILTER_POPUP_HEIGHT

    def _popup_list_height(self) -> int:
        return HEADER_FILTER_POPUP_LIST_HEIGHT

    def _prepare_export_directory(self, source_path: Path) -> Path:
        return _prepare_csv_preview_export_directory(source_path)

    def _default_export_path(self, source_path: Path) -> Path:
        return _default_csv_preview_export_path(source_path)

    def _paths_match(self, first: Path, second: Path) -> bool:
        return _paths_match(first, second)

    def _write_export(self, dest_path: Path, headers: list[str], rows) -> None:
        _write_csv_preview_export(dest_path, headers, rows)

    def _filter_label(self, header: str, index: int) -> str:
        return _filter_label(header, index)

    def _compact_filter_popup_label(self, value: str) -> str:
        return _compact_filter_popup_label(value)

    def _widget_descends_from(self, widget: tk.Misc | None, ancestor: tk.Misc | None) -> bool:
        return _widget_descends_from(widget, ancestor)


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
    ) -> None:
        self._win = win
        self._tree = tree
        self._summary_var = summary_var
        self._query_var = query_var
        self._combine_sessions_var = combine_sessions_var
        self._all_column_ids = all_column_ids
        self._pipeline = _PreviewDataPipeline(data)
        self._view_state = _PreviewViewState(
            visible_column_indices=_normalized_visible_column_indices(
                len(all_column_ids),
                initial_visible_column_indices,
            ),
            sort_column_index=initial_sort_column_index,
            sort_descending=bool(initial_sort_descending) if initial_sort_column_index is not None else False,
        )
        self._on_visible_columns_changed = on_visible_columns_changed
        self._on_sort_changed = on_sort_changed
        self._popup_export_controller = _PreviewPopupExportController(self)
        self._processing_status = ProcessingDialogHandle(
            win,
            title="Processing CSV",
            eyebrow_text="SESSION MERGE",
            detail_text="Combining sessions and rebuilding the visible preview rows.",
        )
        self._processing_status_load_token: int | None = None
        self._analysis_coordinator = _AnalysisSnapshotCoordinator(win)
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
        return self._analysis_coordinator.status_var

    @property
    def _analysis_status_dialog(self) -> tk.Toplevel | None:
        return self._analysis_coordinator.status_dialog

    def _rendered_row_limit(self) -> int:
        return _rendered_preview_row_limit(self._data.column_count)

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
        if not callable(self._on_sort_changed):
            return
        self._on_sort_changed(list(self._data.headers), self._view_state.sort_column_index, self._view_state.sort_descending)

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
        filter_state = self._current_filter_state()
        visible_column_indices = list(self._view_state.visible_column_indices)
        numeric_column_indices = {
            index
            for index in visible_column_indices
            if self._pipeline.is_numeric_sort_column(index)
        }
        return filter_state, visible_column_indices, numeric_column_indices

    def export_current_view_as_csv(self) -> None:
        self._popup_export_controller.export_current_view_as_csv()

    def open_analysis_dialog(self) -> None:
        self._cancel_pending_analysis_request()
        filter_state, visible_column_indices, numeric_column_indices = self._analysis_request_state()
        self._analysis_coordinator.request(
            self._data,
            filter_state,
            visible_column_indices,
            numeric_column_indices,
        )

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
        for index, column_id in enumerate(self._all_column_ids):
            header = self._data.headers[index]
            if self._view_state.sort_column_index == index:
                indicator = " ▼" if self._view_state.sort_descending else " ▲"
            else:
                indicator = ""
            self._tree.heading(column_id, text=f"{header}{indicator}")

    def _rebuild_tree_columns(self, previous_column_count: int) -> None:
        previous_all_visible = self._view_state.visible_column_indices == list(range(previous_column_count))
        self._all_column_ids = _column_ids(self._data)
        self._tree.configure(columns=self._all_column_ids)
        for column_id, header in zip(self._all_column_ids, self._data.headers):
            self._tree.heading(column_id, text=header)
            self._tree.column(column_id, width=_column_width(header), minwidth=MIN_COLUMN_WIDTH, stretch=False, anchor="w")

        if previous_all_visible:
            self._view_state.visible_column_indices = list(range(self._data.column_count))
        else:
            self._view_state.visible_column_indices = _normalized_visible_column_indices(
                self._data.column_count,
                self._view_state.visible_column_indices,
            )
        if self._view_state.sort_column_index is not None and self._view_state.sort_column_index >= self._data.column_count:
            self._view_state.set_sort(None)
            self._notify_sort_changed()
        self._update_tree_headings()

    def open_column_dialog(self) -> None:
        _open_column_visibility_dialog(self._win, self._data.headers, self._view_state.visible_column_indices, self._apply_visible_columns)

    def _apply_visible_columns(self, visible_indices: list[int]) -> None:
        header_filter_cleared, sort_cleared = self._view_state.apply_visible_columns(self._all_column_ids, visible_indices)
        if sort_cleared:
            self._notify_sort_changed()
        if header_filter_cleared:
            self.clear_header_filter()
        elif sort_cleared:
            self._popup_export_controller.destroy_header_filter_popup()
            self.refresh()
        if callable(self._on_visible_columns_changed):
            self._on_visible_columns_changed(list(self._data.headers), list(self._view_state.visible_column_indices))
        if not header_filter_cleared and not sort_cleared:
            self.refresh()

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
        self._analysis_coordinator.cancel()

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
        if load_token != self._load_token:
            return
        if render_token != self._render_token:
            return
        if not self._win.winfo_exists() or not self._tree.winfo_exists():
            return

        end_index = min(start_index + ROW_INSERT_CHUNK_SIZE, len(displayed_rows))
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
                self._populate_rows_in_chunks,
                load_token,
                render_token,
                displayed_rows,
                filtered,
                total_visible_rows,
                end_index,
                render_started_at,
            )
            return

        _log_preview_performance(
            "render rows",
            render_started_at,
            rows=len(displayed_rows),
            filtered=filtered,
            visible_columns=len(self._view_state.visible_column_indices),
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
    win = tk.Toplevel(parent)
    win.title(f"CSV Preview - {data.path.name}")
    win.geometry(f"{max(width, MIN_PREVIEW_WIDTH)}x{max(height, MIN_PREVIEW_HEIGHT)}")

    container = ttk.Frame(win)
    container.pack(fill="both", expand=True, padx=8, pady=8)
    container.columnconfigure(0, weight=1)
    container.rowconfigure(2, weight=1)

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
    summary.grid(row=0, column=0, sticky="ew", pady=(0, 6))

    filter_row = ttk.Frame(container)
    filter_row.grid(row=1, column=0, sticky="ew", pady=(0, 6))
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
    table_frame.grid(row=2, column=0, sticky="nsew")
    table_frame.columnconfigure(0, weight=1)
    table_frame.rowconfigure(0, weight=1)

    tree = _build_tree(table_frame, data)
    y_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
    x_scroll = ttk.Scrollbar(table_frame, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

    tree.grid(row=0, column=0, sticky="nsew")
    y_scroll.grid(row=0, column=1, sticky="ns")
    x_scroll.grid(row=1, column=0, sticky="ew")

    controller = _PreviewTableController(
        win,
        tree,
        data,
        summary_var,
        query_var,
        combine_sessions_var,
        _column_ids(data),
        initial_visible_column_indices=initial_visible_column_indices,
        initial_sort_column_index=initial_sort_column_index,
        initial_sort_descending=initial_sort_descending,
        on_visible_columns_changed=on_visible_columns_changed,
        on_sort_changed=on_sort_changed,
    )
    win._csv_preview_controller = controller  # type: ignore[attr-defined]

    def _clear_filters() -> None:
        query_var.set("")
        combine_sessions_var.set(False)
        controller.clear_sort()
        controller.clear_header_filter()

    ttk.Button(filter_row, text="Columns", command=controller.open_column_dialog).pack(side="left", padx=(0, 12))
    ttk.Button(filter_row, text="Save As CSV", command=controller.export_current_view_as_csv).pack(side="left", padx=(0, 12))
    ttk.Button(filter_row, text="Analyze", command=controller.open_analysis_dialog).pack(side="left", padx=(0, 12))
    ttk.Button(filter_row, text="Clear filters", command=_clear_filters).pack(side="left")

    button_row = ttk.Frame(container)
    button_row.grid(row=3, column=0, sticky="ew", pady=(8, 0))
    ttk.Button(button_row, text="Close", command=win.destroy).pack(side="right")

    query_var.trace_add("write", controller.on_query_changed)
    combine_sessions_var.trace_add("write", controller.on_combine_sessions_changed)
    query_entry.bind("<Return>", controller.trigger_refresh_now, add="+")
    tree.bind("<ButtonRelease-1>", controller.on_tree_click, add="+")
    controller.refresh()
    query_entry.focus_set()

    return win


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
    normalized_path = str(data.path)
    saved_state = settings_store.load_csv_preview_state(normalized_path)
    saved_visible_column_keys = saved_state.visible_column_keys if saved_state is not None else settings_store.load_csv_preview_visible_column_keys(normalized_path)
    initial_visible_column_indices = _visible_column_indices_from_keys(
        data.headers,
        saved_visible_column_keys,
    )
    if initial_visible_column_indices is None:
        initial_visible_column_indices = (
            saved_state.visible_columns if saved_state is not None and saved_state.visible_columns else settings_store.load_csv_preview_visible_columns(normalized_path)
        )

    saved_sort = (
        {"column_key": saved_state.sort_column_key, "descending": saved_state.sort_descending}
        if saved_state is not None and saved_state.sort_column_key
        else settings_store.load_csv_preview_sort(normalized_path)
    )
    initial_sort_column_index = None
    initial_sort_descending = False
    if saved_sort is not None:
        initial_sort_column_index = _column_index_from_identity_key(data.headers, saved_sort.get("column_key"))
        initial_sort_descending = bool(saved_sort.get("descending", False)) if initial_sort_column_index is not None else False

    def _save_visible_columns(headers: list[str], visible_indices: list[int]) -> None:
        try:
            settings_store.save_csv_preview_visible_column_keys(
                normalized_path,
                _visible_column_keys(headers, visible_indices),
            )
        except (OSError, TypeError, ValueError) as exc:
            messagebox.showerror("CSV preview settings unavailable", f"Could not save CSV preview columns.\n\nReason: {exc}")

    def _save_sort(headers: list[str], column_index: int | None, descending: bool) -> None:
        column_key = None
        if column_index is not None and 0 <= column_index < len(headers):
            column_key = _column_identity_keys(headers)[column_index]
        try:
            settings_store.save_csv_preview_sort(normalized_path, column_key, descending=descending)
        except (OSError, TypeError, ValueError) as exc:
            messagebox.showerror("CSV preview settings unavailable", f"Could not save CSV preview sort.\n\nReason: {exc}")

    return create_csv_preview_dialog(
        parent,
        data,
        width=width,
        height=height,
        initial_visible_column_indices=initial_visible_column_indices,
        initial_sort_column_index=initial_sort_column_index,
        initial_sort_descending=initial_sort_descending,
        on_visible_columns_changed=_save_visible_columns,
        on_sort_changed=_save_sort,
    )
