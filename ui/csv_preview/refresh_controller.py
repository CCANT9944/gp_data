from __future__ import annotations

import queue
import threading
import tkinter as tk
from dataclasses import dataclass
from time import perf_counter

from .loader import CsvPreviewData
from .pipeline import (
    _FilteredCountUpdate,
    _FilteredErrorUpdate,
    _FilteredPreviewUpdate,
    _FilteredRefreshMessage,
    _PreviewFilterState,
)


BACKGROUND_REFRESH_POLL_MS = 25
METADATA_REFRESH_POLL_MS = 50
PREWARM_VISIBLE_HEADER_FILTER_COLUMNS = 6
CSV_PREVIEW_LOADING_ROW_TEXT = "Loading..."


@dataclass(frozen=True)
class _MetadataResolvedUpdate:
    resolved_data: CsvPreviewData


@dataclass(frozen=True)
class _MetadataErrorUpdate:
    error: Exception


_MetadataRefreshMessage = _MetadataResolvedUpdate | _MetadataErrorUpdate


class _PreviewRefreshControllerBase:
    def _initialize_refresh_state(self) -> None:
        self._load_token = 0
        self._render_token = 0
        self._scheduled_refresh_id: str | None = None
        self._metadata_refresh_active = False
        self._metadata_refresh_queue: queue.Queue[_MetadataRefreshMessage] = queue.Queue()
        self._filtered_refresh_queue: queue.Queue[_FilteredRefreshMessage] = queue.Queue()
        self._pending_filtered_refresh_tokens: set[int] = set()
        self._pending_filtered_refresh_filtered_state: dict[int, bool] = {}
        self._filtered_refresh_polling = False
        self._header_filter_prewarm_request_token = 0
        self._header_filter_prewarm_key: tuple[object, ...] | None = None
        self._view_state.summary.visible_rows = self._data.row_count
        self._start_metadata_refresh_if_needed()

    def _rendered_row_limit(self) -> int:
        raise NotImplementedError

    def _current_filter_state(self) -> _PreviewFilterState:
        raise NotImplementedError

    def _update_tree_headings(self) -> None:
        raise NotImplementedError

    def _apply_displaycolumns(self) -> None:
        raise NotImplementedError

    def _update_summary_label(self) -> None:
        raise NotImplementedError

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
        raise NotImplementedError

    def _rebuild_tree_columns(self, previous_column_count: int) -> None:
        raise NotImplementedError

    def _on_filtered_refresh_message(self, message: _FilteredRefreshMessage) -> None:
        return

    def on_query_changed(self, *_args) -> None:
        if self._scheduled_refresh_id is not None:
            self._win.after_cancel(self._scheduled_refresh_id)
            self._scheduled_refresh_id = None

        self._load_token += 1
        self._render_token += 1
        self._header_filter_prewarm_request_token += 1

    def schedule_refresh(self, *_args) -> None:
        self.on_query_changed(*_args)

    def trigger_refresh_now(self, _event=None) -> str:
        if self._scheduled_refresh_id is not None:
            self._win.after_cancel(self._scheduled_refresh_id)
            self._scheduled_refresh_id = None
        self.refresh()
        return "break"

    def _loading_placeholder_row(self) -> tuple[str, ...]:
        values = [""] * self._data.column_count
        target_index = self._view_state.visible_column_indices[0] if self._view_state.visible_column_indices else 0
        if 0 <= target_index < len(values):
            values[target_index] = CSV_PREVIEW_LOADING_ROW_TEXT
        return tuple(values)

    def _show_loading_placeholder(self) -> None:
        if not self._tree.winfo_exists():
            return
        self._apply_displaycolumns()
        self._update_tree_headings()
        children = self._tree.get_children()
        placeholder_row = self._loading_placeholder_row()
        if children:
            self._tree.item(children[0], values=placeholder_row)
            if len(children) > 1:
                self._tree.delete(*children[1:])
            return
        self._tree.insert("", "end", values=placeholder_row)

    def refresh(self, *_args) -> None:
        self._scheduled_refresh_id = None
        self._load_token += 1
        self._render_token += 1
        load_token = self._load_token
        rendered_row_limit = self._rendered_row_limit()
        self._apply_displaycolumns()
        self._update_tree_headings()

        filter_state = self._current_filter_state()
        requires_full_refresh = filter_state.filtering_active or filter_state.sort_column_index is not None

        if not requires_full_refresh:
            displayed_rows = self._data.rows[:rendered_row_limit]
            total_rows = self._data.row_count
        else:
            self._view_state.summary.set_loading(filtered=filter_state.filtering_active)
            self._update_summary_label()
            if filter_state.query:
                self._show_loading_placeholder()
            self._start_filtered_refresh(
                load_token,
                filter_state,
                rendered_row_limit=rendered_row_limit,
            )
            return

        self._view_state.summary.set_ready(
            filtered=filter_state.filtering_active,
            visible_rows=total_rows,
            displayed_rows=len(displayed_rows),
        )
        self._update_summary_label()
        if displayed_rows:
            self._win.after_idle(
                self._populate_rows_in_chunks,
                self._load_token,
                self._render_token,
                displayed_rows,
                filter_state.filtering_active,
                total_rows,
                0,
                perf_counter(),
            )
            self._maybe_start_header_filter_prewarm(filter_state)
        else:
            children = self._tree.get_children()
            if children:
                self._tree.delete(*children)

    def _header_filter_prewarm_columns(self) -> list[int]:
        return list(self._view_state.visible_column_indices[:PREWARM_VISIBLE_HEADER_FILTER_COLUMNS])

    def _maybe_start_header_filter_prewarm(self, filter_state: _PreviewFilterState) -> None:
        if filter_state.filtering_active or filter_state.sort_column_index is not None:
            return

        column_indices = self._header_filter_prewarm_columns()
        if not column_indices:
            return

        prewarm_key = (
            str(self._data.path),
            self._data.column_count,
            self._data.row_count,
            tuple(column_indices),
        )
        if prewarm_key == self._header_filter_prewarm_key:
            return

        self._header_filter_prewarm_key = prewarm_key
        self._header_filter_prewarm_request_token += 1
        request_token = self._header_filter_prewarm_request_token
        worker = threading.Thread(
            target=self._prewarm_header_filter_columns_in_background,
            args=(request_token, filter_state, column_indices),
            daemon=True,
        )
        worker.start()

    def _prewarm_header_filter_columns_in_background(
        self,
        request_token: int,
        filter_state: _PreviewFilterState,
        column_indices: list[int],
    ) -> None:
        should_cancel = lambda: request_token != self._header_filter_prewarm_request_token
        if should_cancel():
            return
        self._pipeline.prewarm_header_filter_columns(filter_state, column_indices, should_cancel=should_cancel)

    def _start_filtered_refresh(
        self,
        load_token: int,
        filter_state: _PreviewFilterState,
        *,
        rendered_row_limit: int,
    ) -> None:
        self._pending_filtered_refresh_tokens.add(load_token)
        self._pending_filtered_refresh_filtered_state[load_token] = filter_state.filtering_active
        worker = threading.Thread(
            target=self._load_filtered_rows_in_background,
            args=(load_token, filter_state, rendered_row_limit),
            daemon=True,
        )
        worker.start()
        if not self._filtered_refresh_polling:
            self._filtered_refresh_polling = True
            self._win.after(BACKGROUND_REFRESH_POLL_MS, self._poll_filtered_refresh)

    def _load_filtered_rows_in_background(
        self,
        load_token: int,
        filter_state: _PreviewFilterState,
        rendered_row_limit: int,
    ) -> None:
        try:
            should_cancel = lambda: load_token != self._load_token
            for message in self._pipeline.iter_filtered_refresh_messages(
                load_token,
                filter_state,
                rendered_row_limit=rendered_row_limit,
                should_cancel=should_cancel,
            ):
                if should_cancel():
                    return
                self._filtered_refresh_queue.put(message)
        except Exception as exc:
            self._filtered_refresh_queue.put(_FilteredErrorUpdate(load_token=load_token, error=exc))

    def _poll_filtered_refresh(self) -> None:
        if not self._win.winfo_exists():
            return

        while True:
            try:
                message = self._filtered_refresh_queue.get_nowait()
            except queue.Empty:
                break

            self._on_filtered_refresh_message(message)

            if isinstance(message, _FilteredPreviewUpdate):
                filtered_state = self._pending_filtered_refresh_filtered_state.get(message.load_token, False)
                if message.total_rows is not None:
                    self._pending_filtered_refresh_tokens.discard(message.load_token)
                    self._pending_filtered_refresh_filtered_state.pop(message.load_token, None)
                if message.load_token != self._load_token:
                    continue
                self._render_token += 1
                render_token = self._render_token
                self._view_state.summary.set_ready(
                    filtered=filtered_state,
                    visible_rows=message.total_rows,
                    displayed_rows=len(message.displayed_rows),
                )
                self._update_summary_label()
                if message.displayed_rows:
                    self._win.after_idle(
                        self._populate_rows_in_chunks,
                        message.load_token,
                        render_token,
                        message.displayed_rows,
                        filtered_state,
                        message.total_rows,
                        0,
                        perf_counter(),
                    )
                elif message.replace_rows:
                    children = self._tree.get_children()
                    if children:
                        self._tree.delete(*children)
                continue

            self._pending_filtered_refresh_tokens.discard(message.load_token)
            filtered_state = self._pending_filtered_refresh_filtered_state.pop(message.load_token, False)
            if message.load_token != self._load_token or isinstance(message, _FilteredErrorUpdate):
                continue
            self._view_state.summary.loading = False
            if isinstance(message, _FilteredCountUpdate):
                self._view_state.summary.visible_rows = message.total_rows
                self._view_state.summary.filtered = filtered_state
                self._update_summary_label()

        if self._pending_filtered_refresh_tokens:
            self._win.after(BACKGROUND_REFRESH_POLL_MS, self._poll_filtered_refresh)
            return
        self._filtered_refresh_polling = False

    def _start_metadata_refresh_if_needed(self) -> None:
        if self._data.row_count is not None or self._metadata_refresh_active:
            return
        self._metadata_refresh_active = True
        worker = threading.Thread(target=self._load_metadata_in_background, daemon=True)
        worker.start()
        self._poll_metadata_refresh()

    def _load_metadata_in_background(self) -> None:
        self._metadata_refresh_queue.put(self._pipeline.resolve_metadata_refresh_message())

    def _poll_metadata_refresh(self) -> None:
        if not self._win.winfo_exists():
            return
        try:
            message = self._metadata_refresh_queue.get_nowait()
        except queue.Empty:
            if self._metadata_refresh_active:
                self._win.after(METADATA_REFRESH_POLL_MS, self._poll_metadata_refresh)
            return

        self._metadata_refresh_active = False
        if isinstance(message, _MetadataErrorUpdate):
            return
        self._apply_resolved_metadata(message.resolved_data)

    def _apply_resolved_metadata(self, resolved_data: CsvPreviewData) -> None:
        previous_column_count = self._data.column_count
        previous_headers = list(self._data.headers)
        self._pipeline.update_data(resolved_data)
        if resolved_data.column_count != previous_column_count or resolved_data.headers != previous_headers:
            self._rebuild_tree_columns(previous_column_count)
        self.refresh()