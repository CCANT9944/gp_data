from __future__ import annotations

import queue
import threading
import tkinter as tk
from dataclasses import dataclass

from .analysis import PreviewAnalysisSnapshot
from .loader import CsvPreviewData
from .pipeline import _PreviewFilterState


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
    def __init__(
        self,
        win: tk.Toplevel,
        *,
        processing_dialog_factory,
        pipeline_factory,
        build_snapshot,
        show_error,
        open_analysis_dialog_from_snapshot,
    ) -> None:
        self._win = win
        self._status = processing_dialog_factory(win)
        self._pipeline_factory = pipeline_factory
        self._build_snapshot_impl = build_snapshot
        self._show_error = show_error
        self._open_analysis_dialog_from_snapshot = open_analysis_dialog_from_snapshot
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
            analysis_pipeline = self._pipeline_factory(data)
            filtered_rows = analysis_pipeline.filtered_rows_snapshot(filter_state)
            snapshot = self._build_snapshot_impl(
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
                self._show_error("CSV analysis unavailable", str(message.error))
                continue
            self._open_analysis_dialog_from_snapshot(self._win, message.snapshot)

        if self._pending_tokens:
            self._win.after(25, self._poll)
            return
        self._polling = False


class _PreviewAnalysisLauncher:
    def __init__(
        self,
        win: tk.Toplevel,
        get_data,
        get_filter_state,
        get_visible_column_indices,
        is_numeric_column,
        *,
        coordinator_factory,
    ) -> None:
        self._get_data = get_data
        self._get_filter_state = get_filter_state
        self._get_visible_column_indices = get_visible_column_indices
        self._is_numeric_column = is_numeric_column
        self._coordinator = coordinator_factory(win)

    @property
    def status_var(self) -> tk.StringVar:
        return self._coordinator.status_var

    @property
    def status_dialog(self) -> tk.Toplevel | None:
        return self._coordinator.status_dialog

    def cancel(self) -> None:
        self._coordinator.cancel()

    def request_state(self) -> tuple[_PreviewFilterState, list[int], set[int]]:
        filter_state = self._get_filter_state()
        visible_column_indices = list(self._get_visible_column_indices())
        numeric_column_indices = {
            index
            for index in visible_column_indices
            if self._is_numeric_column(index)
        }
        return filter_state, visible_column_indices, numeric_column_indices

    def open_dialog(self) -> None:
        self.cancel()
        filter_state, visible_column_indices, numeric_column_indices = self.request_state()
        self._coordinator.request(
            self._get_data(),
            filter_state,
            visible_column_indices,
            numeric_column_indices,
        )