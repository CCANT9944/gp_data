from __future__ import annotations

import queue
import threading
import tkinter as tk
from collections import OrderedDict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from tkinter import messagebox, ttk

from gp_data.settings import SettingsStore
from .loader import CsvPreviewData, iter_csv_preview_rows, load_csv_preview, resolve_csv_preview_metadata


MIN_PREVIEW_WIDTH = 800
MIN_PREVIEW_HEIGHT = 420
DEFAULT_COLUMN_WIDTH = 140
MAX_COLUMN_WIDTH = 320
MIN_COLUMN_WIDTH = 80
ROW_INSERT_CHUNK_SIZE = 250
COMBINED_SESSION_SEPARATOR = " + "
MAX_RENDERED_PREVIEW_ROWS = 5000
QUERY_REFRESH_DEBOUNCE_MS = 250
HEADER_FILTER_POPUP_LABEL_MAX_LENGTH = 36
HEADER_FILTER_POPUP_WIDTH = 320
HEADER_FILTER_POPUP_HEIGHT = 300
HEADER_FILTER_POPUP_LIST_HEIGHT = 10


@dataclass(frozen=True)
class _PreviewFilterState:
    query: str
    combine_sessions: bool
    header_filter_column_index: int | None
    header_filter_value: str | None

    @property
    def filtering_active(self) -> bool:
        return bool(self.query or self.combine_sessions or self.header_filter_column_index is not None)

    def header_filter_cache_key(self, column_index: int) -> tuple[int, str, bool]:
        return (column_index, self.query.casefold(), self.combine_sessions)


@dataclass(frozen=True)
class _FilteredPreviewUpdate:
    load_token: int
    displayed_rows: list[tuple[str, ...]]
    total_rows: int | None


@dataclass(frozen=True)
class _FilteredCountUpdate:
    load_token: int
    total_rows: int


@dataclass(frozen=True)
class _FilteredErrorUpdate:
    load_token: int
    error: Exception


_FilteredRefreshMessage = _FilteredPreviewUpdate | _FilteredCountUpdate | _FilteredErrorUpdate


@dataclass(frozen=True)
class _MetadataResolvedUpdate:
    resolved_data: CsvPreviewData


@dataclass(frozen=True)
class _MetadataErrorUpdate:
    error: Exception


_MetadataRefreshMessage = _MetadataResolvedUpdate | _MetadataErrorUpdate


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

    def render_text(self, data: CsvPreviewData) -> str:
        if self.loading:
            return _loading_summary_text(data, filtered=self.filtered)
        return _summary_text(
            data,
            visible_rows=self.visible_rows,
            displayed_rows=self.displayed_rows,
            loaded_rows=self.loaded_rows,
            filtered=self.filtered,
        )


@dataclass
class _PreviewViewState:
    visible_column_indices: list[int]
    header_filter_column_index: int | None = None
    header_filter_value: str | None = None
    summary: _PreviewSummaryState = field(default_factory=_PreviewSummaryState)

    def filter_state(self, *, query: str, combine_sessions: bool) -> _PreviewFilterState:
        return _PreviewFilterState(
            query=query,
            combine_sessions=combine_sessions,
            header_filter_column_index=self.header_filter_column_index,
            header_filter_value=self.header_filter_value,
        )

    def visible_column_ids(self, all_column_ids: list[str]) -> list[str]:
        return [all_column_ids[index] for index in self.visible_column_indices]

    def set_header_filter(self, column_index: int | None, value: str | None) -> None:
        self.header_filter_column_index = column_index
        self.header_filter_value = value

    def apply_visible_columns(self, all_column_ids: list[str], visible_indices: list[int]) -> bool:
        self.visible_column_indices = _normalized_visible_column_indices(len(all_column_ids), visible_indices)
        if self.header_filter_column_index is None:
            return False
        if self.header_filter_column_index in self.visible_column_indices:
            return False
        self.header_filter_column_index = None
        self.header_filter_value = None
        return True


def _column_width(header: str) -> int:
    estimated = max(MIN_COLUMN_WIDTH, min(MAX_COLUMN_WIDTH, (len(header) * 10) + 24))
    return max(DEFAULT_COLUMN_WIDTH, estimated)


def _column_ids(data: CsvPreviewData) -> list[str]:
    return [f"col_{index}" for index in range(data.column_count)]


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


def _filter_label(header: str, index: int) -> str:
    display = header.strip() or f"Column {index + 1}"
    return f"{index + 1}: {display}"


def _compact_filter_popup_label(value: str, *, max_length: int = HEADER_FILTER_POPUP_LABEL_MAX_LENGTH) -> str:
    if len(value) <= max_length:
        return value
    if max_length <= 3:
        return value[:max_length]
    return f"{value[: max_length - 3].rstrip()}..."


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


def _column_identity_keys(headers: list[str]) -> list[str]:
    seen_counts: dict[str, int] = {}
    keys: list[str] = []
    for index, header in enumerate(headers):
        display = header.strip() or f"Column {index + 1}"
        normalized_display = display.casefold()
        occurrence = seen_counts.get(normalized_display, 0) + 1
        seen_counts[normalized_display] = occurrence
        keys.append(f"{normalized_display}#{occurrence}")
    return keys


def _visible_column_keys(headers: list[str], visible_indices: list[int] | None) -> list[str]:
    normalized_indices = _normalized_visible_column_indices(len(headers), visible_indices)
    identity_keys = _column_identity_keys(headers)
    return [identity_keys[index] for index in normalized_indices]


def _visible_column_indices_from_keys(headers: list[str], visible_keys: list[str] | None) -> list[int] | None:
    if not visible_keys:
        return None

    identity_keys = _column_identity_keys(headers)
    index_by_key = {key: index for index, key in enumerate(identity_keys)}
    resolved_indices: list[int] = []
    seen_indices: set[int] = set()
    for raw_key in visible_keys:
        key = str(raw_key).strip().casefold()
        index = index_by_key.get(key)
        if index is None or index in seen_indices:
            continue
        resolved_indices.append(index)
        seen_indices.add(index)

    return sorted(resolved_indices) or None


def _normalized_header(header: str) -> str:
    return "".join(ch for ch in header.casefold() if ch.isalnum())


def _detect_session_column(headers: list[str]) -> int | None:
    for index, header in enumerate(headers):
        if "session" in _normalized_header(header):
            return index
    return None


def _detect_quantity_column(headers: list[str]) -> int | None:
    for index, header in enumerate(headers):
        normalized = _normalized_header(header)
        if "quantity" in normalized or normalized == "qty":
            return index
    return None


def _is_identifier_column(header: str) -> bool:
    normalized = _normalized_header(header)
    identifier_tokens = ("plu", "code", "sku", "barcode", "upc", "ean", "itemid", "productid")
    return any(token in normalized for token in identifier_tokens)


def _parse_decimal(value: str) -> Decimal | None:
    normalized = value.strip().replace(",", "")
    if not normalized:
        return None
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def _format_decimal(value: Decimal | None) -> str:
    if value is None:
        return ""
    normalized = value.normalize()
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _combined_sessions(values: list[str]) -> str:
    ordered = OrderedDict.fromkeys(value.strip() for value in values if value.strip())
    return COMBINED_SESSION_SEPARATOR.join(ordered)


def _detect_numeric_columns(data: CsvPreviewData, excluded_indices: set[int], rows=None) -> set[int]:
    numeric_columns: set[int] = set()
    numeric_tokens = ("qty", "quantity", "revenue", "sales", "amount", "total", "price", "cost", "value", "units")
    candidate_indices: list[int] = []
    for index, header in enumerate(data.headers):
        normalized = _normalized_header(header)
        if index in excluded_indices or _is_identifier_column(header):
            continue
        if any(token in normalized for token in numeric_tokens):
            numeric_columns.add(index)
        else:
            candidate_indices.append(index)

    # Fall back to sampled row values so unnamed numeric export columns such as
    # Textbox73/Textbox79 still combine correctly across sessions.
    inspected_rows = data.rows if rows is None else rows
    column_counts = {index: [0, 0] for index in candidate_indices}
    for row in inspected_rows:
        for index in candidate_indices:
            value = row[index].strip()
            if not value:
                continue
            column_counts[index][0] += 1
            if _parse_decimal(value) is not None:
                column_counts[index][1] += 1

    for index, (non_empty_values, numeric_values) in column_counts.items():
        mostly_numeric = non_empty_values and (numeric_values / non_empty_values) >= 0.98
        small_sample_with_single_outlier = non_empty_values <= 5 and numeric_values >= max(2, non_empty_values - 1)
        if mostly_numeric or small_sample_with_single_outlier:
            numeric_columns.add(index)
    return numeric_columns


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


def _row_matches_query(row: tuple[str, ...], query: str) -> bool:
    normalized_query = query.strip().casefold()
    if not normalized_query:
        return True
    return any(normalized_query in value.casefold() for value in row)


def _sorted_distinct_values(rows, column_index: int) -> list[str]:
    values = {row[column_index] for row in rows}
    return sorted(values, key=lambda value: value.casefold())


def _iter_rows_before_header_filter(
    data: CsvPreviewData,
    query: str,
    combine_sessions: bool,
    combined_rows: list[tuple[str, ...]] | None = None,
):
    source_rows = combined_rows if combine_sessions and combined_rows is not None else _iter_combined_rows(data, combine_sessions)
    for row in source_rows:
        if _row_matches_query(row, query):
            yield row


def _summary_text(
    data: CsvPreviewData,
    *,
    visible_rows: int | None = None,
    displayed_rows: int | None = None,
    loaded_rows: int | None = None,
    filtered: bool = False,
) -> str:
    known_total_rows = data.row_count
    matched_rows = known_total_rows if visible_rows is None else visible_rows
    if displayed_rows is not None:
        shown_rows = displayed_rows
    elif matched_rows is not None:
        shown_rows = matched_rows
    else:
        shown_rows = len(data.rows)

    if filtered:
        if visible_rows is None:
            row_text = f"Showing first {shown_rows} matching rows"
        elif shown_rows >= matched_rows:
            row_text = f"{matched_rows} matching rows"
        else:
            row_text = f"Showing first {shown_rows}/{matched_rows} matching rows"
    elif visible_rows is None:
        if known_total_rows is None:
            row_text = f"Showing first {shown_rows} preview rows"
        elif shown_rows >= known_total_rows:
            row_text = f"{known_total_rows} rows"
        else:
            row_text = f"Showing first {shown_rows}/{known_total_rows} rows"
    elif known_total_rows is not None and matched_rows == known_total_rows:
        if shown_rows >= matched_rows:
            row_text = f"{matched_rows} rows"
        else:
            row_text = f"Showing first {shown_rows}/{matched_rows} rows"
    elif shown_rows >= matched_rows:
        row_text = f"{matched_rows} matching rows"
    else:
        row_text = f"Showing first {shown_rows}/{matched_rows} matching rows"
    if loaded_rows is None or loaded_rows >= shown_rows:
        return f"{data.path.name} | {row_text} | {data.column_count} columns | {data.encoding}"
    return f"{data.path.name} | Loading {loaded_rows}/{shown_rows} shown rows | {data.column_count} columns | {data.encoding}"


def _loading_summary_text(data: CsvPreviewData, *, filtered: bool) -> str:
    row_text = "Loading matching rows" if filtered else "Loading rows"
    return f"{data.path.name} | {row_text} | {data.column_count} columns | {data.encoding}"


class _PreviewDataPipeline:
    def __init__(self, data: CsvPreviewData) -> None:
        self._data = data
        self._combined_rows_cache: list[tuple[str, ...]] | None = None
        self._header_filter_options_cache: dict[tuple[int, str, bool], list[str]] = {}

    @property
    def data(self) -> CsvPreviewData:
        return self._data

    def update_data(self, data: CsvPreviewData) -> None:
        self._data = data
        self._combined_rows_cache = None
        self._header_filter_options_cache.clear()

    def rows_before_header_filter(self, filter_state: _PreviewFilterState):
        yield from _iter_rows_before_header_filter(
            self._data,
            filter_state.query,
            filter_state.combine_sessions,
            combined_rows=self._combined_rows(filter_state.combine_sessions),
        )

    def header_filter_options(self, filter_state: _PreviewFilterState, column_index: int) -> list[str]:
        cache_key = filter_state.header_filter_cache_key(column_index)
        options = self._header_filter_options_cache.get(cache_key)
        if options is None:
            options = _sorted_distinct_values(self.rows_before_header_filter(filter_state), column_index)
            self._header_filter_options_cache[cache_key] = options
        return options

    def iter_filtered_refresh_messages(self, load_token: int, filter_state: _PreviewFilterState):
        displayed_rows: list[tuple[str, ...]] = []
        matched_rows = 0
        normalized_value = filter_state.header_filter_value.casefold() if filter_state.header_filter_value is not None else None
        preview_sent = False

        for row in self.rows_before_header_filter(filter_state):
            if (
                filter_state.header_filter_column_index is not None
                and normalized_value is not None
                and row[filter_state.header_filter_column_index].casefold() != normalized_value
            ):
                continue
            matched_rows += 1
            if len(displayed_rows) < MAX_RENDERED_PREVIEW_ROWS:
                displayed_rows.append(row)
                continue
            if not preview_sent:
                yield _FilteredPreviewUpdate(load_token=load_token, displayed_rows=list(displayed_rows), total_rows=None)
                preview_sent = True

        if preview_sent:
            yield _FilteredCountUpdate(load_token=load_token, total_rows=matched_rows)
            return

        yield _FilteredPreviewUpdate(load_token=load_token, displayed_rows=displayed_rows, total_rows=matched_rows)

    def resolve_metadata_refresh_message(self) -> _MetadataRefreshMessage:
        try:
            return _MetadataResolvedUpdate(resolved_data=resolve_csv_preview_metadata(self._data))
        except Exception as exc:
            return _MetadataErrorUpdate(error=exc)

    def _combined_rows(self, combine_sessions: bool) -> list[tuple[str, ...]] | None:
        if not combine_sessions:
            return None
        if self._combined_rows_cache is None:
            self._combined_rows_cache = list(_iter_combined_rows(self._data, True))
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


class _PreviewTableController:
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
        on_visible_columns_changed=None,
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
        )
        self._on_visible_columns_changed = on_visible_columns_changed
        self._load_token = 0
        self._scheduled_refresh_id: str | None = None
        self._header_filter_popup_value = tk.StringVar(value="")
        self._header_filter_popup: tk.Toplevel | None = None
        self._header_filter_popup_column_index: int | None = None
        self._header_filter_popup_search_var: tk.StringVar | None = None
        self._header_filter_popup_listbox: tk.Listbox | None = None
        self._header_filter_popup_empty_var: tk.StringVar | None = None
        self._header_filter_popup_options: list[str] = []
        self._header_filter_popup_filtered_options: list[str] = []
        self._metadata_refresh_active = False
        self._metadata_refresh_queue: queue.Queue[_MetadataRefreshMessage] = queue.Queue()
        self._filtered_refresh_queue: queue.Queue[_FilteredRefreshMessage] = queue.Queue()
        self._pending_filtered_refresh_tokens: set[int] = set()
        self._filtered_refresh_polling = False
        self._view_state.summary.visible_rows = self._data.row_count
        self._start_metadata_refresh_if_needed()

    @property
    def _data(self) -> CsvPreviewData:
        return self._pipeline.data

    def schedule_refresh(self, *_args) -> None:
        if self._scheduled_refresh_id is not None:
            self._win.after_cancel(self._scheduled_refresh_id)
        self._scheduled_refresh_id = self._win.after(QUERY_REFRESH_DEBOUNCE_MS, self.refresh)

    def refresh(self, *_args) -> None:
        self._scheduled_refresh_id = None
        self._load_token += 1
        load_token = self._load_token
        children = self._tree.get_children()
        if children:
            self._tree.delete(*children)
        self._tree.configure(displaycolumns=self._view_state.visible_column_ids(self._all_column_ids))

        filter_state = self._current_filter_state()

        if not filter_state.filtering_active:
            displayed_rows = self._data.rows[:MAX_RENDERED_PREVIEW_ROWS]
            total_rows = self._data.row_count
        else:
            self._view_state.summary.set_loading(filtered=True)
            self._update_summary_label()
            self._start_filtered_refresh(
                load_token,
                filter_state,
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
                displayed_rows,
                filter_state.filtering_active,
                total_rows,
                0,
            )

    def _current_filter_state(self) -> _PreviewFilterState:
        return self._view_state.filter_state(
            query=self._query_var.get().strip(),
            combine_sessions=self._combine_sessions_var.get(),
        )

    def _update_summary_label(self) -> None:
        self._summary_var.set(self._view_state.summary.render_text(self._data))

    def _start_filtered_refresh(
        self,
        load_token: int,
        filter_state: _PreviewFilterState,
    ) -> None:
        self._pending_filtered_refresh_tokens.add(load_token)
        worker = threading.Thread(
            target=self._load_filtered_rows_in_background,
            args=(load_token, filter_state),
            daemon=True,
        )
        worker.start()
        if not self._filtered_refresh_polling:
            self._filtered_refresh_polling = True
            self._win.after(50, self._poll_filtered_refresh)

    def _load_filtered_rows_in_background(
        self,
        load_token: int,
        filter_state: _PreviewFilterState,
    ) -> None:
        try:
            for message in self._pipeline.iter_filtered_refresh_messages(load_token, filter_state):
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

            if isinstance(message, _FilteredPreviewUpdate):
                if message.total_rows is not None:
                    self._pending_filtered_refresh_tokens.discard(message.load_token)
                if message.load_token != self._load_token:
                    continue
                self._view_state.summary.set_ready(
                    filtered=True,
                    visible_rows=message.total_rows,
                    displayed_rows=len(message.displayed_rows),
                )
                self._update_summary_label()
                if message.displayed_rows:
                    self._win.after_idle(
                        self._populate_rows_in_chunks,
                        message.load_token,
                        message.displayed_rows,
                        True,
                        message.total_rows,
                        0,
                    )
                continue

            self._pending_filtered_refresh_tokens.discard(message.load_token)
            if message.load_token != self._load_token or isinstance(message, _FilteredErrorUpdate):
                continue
            self._view_state.summary.loading = False
            if isinstance(message, _FilteredCountUpdate):
                self._view_state.summary.visible_rows = message.total_rows
                self._update_summary_label()

        if self._pending_filtered_refresh_tokens:
            self._win.after(50, self._poll_filtered_refresh)
            return
        self._filtered_refresh_polling = False

    def set_header_filter(self, column_index: int | None, value: str | None) -> None:
        self._view_state.set_header_filter(column_index, value)
        self._header_filter_popup_value.set(value or "")
        self.refresh()

    def clear_header_filter(self) -> None:
        self.set_header_filter(None, None)
        self._destroy_header_filter_popup()

    def show_header_filter_popup(self, column_index: int, x_root: int, y_root: int) -> None:
        options = self._pipeline.header_filter_options(self._current_filter_state(), column_index)
        self._destroy_header_filter_popup()

        popup = tk.Toplevel(self._win)
        popup.title(_filter_label(self._data.headers[column_index], column_index))
        popup.transient(self._win)
        popup.resizable(False, False)

        screen_width = popup.winfo_screenwidth()
        screen_height = popup.winfo_screenheight()
        left = max(0, min(x_root, screen_width - HEADER_FILTER_POPUP_WIDTH))
        top = max(0, min(y_root, screen_height - HEADER_FILTER_POPUP_HEIGHT))
        popup.geometry(f"{HEADER_FILTER_POPUP_WIDTH}x{HEADER_FILTER_POPUP_HEIGHT}+{left}+{top}")

        self._header_filter_popup = popup
        self._header_filter_popup_column_index = column_index
        self._header_filter_popup_options = list(options)
        self._header_filter_popup_filtered_options = []
        self._header_filter_popup_search_var = tk.StringVar(value="")
        self._header_filter_popup_empty_var = tk.StringVar(value="")

        container = ttk.Frame(popup, padding=8)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(2, weight=1)

        ttk.Label(container, text="Search").grid(row=0, column=0, sticky="w")
        search_entry = ttk.Entry(container, textvariable=self._header_filter_popup_search_var, width=28)
        search_entry.grid(row=1, column=0, sticky="ew", pady=(4, 8))

        list_frame = ttk.Frame(container)
        list_frame.grid(row=2, column=0, sticky="nsew")
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        listbox = tk.Listbox(list_frame, exportselection=False, height=HEADER_FILTER_POPUP_LIST_HEIGHT)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=listbox.yview)
        listbox.configure(yscrollcommand=scrollbar.set)
        listbox.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        self._header_filter_popup_listbox = listbox

        empty_label = ttk.Label(container, textvariable=self._header_filter_popup_empty_var, anchor="w")
        empty_label.grid(row=3, column=0, sticky="ew", pady=(6, 0))

        button_row = ttk.Frame(container)
        button_row.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(button_row, text="Clear filter", command=self._clear_header_filter_popup_filter).pack(side="right")
        ttk.Button(button_row, text="Apply", command=self._apply_selected_header_filter_option).pack(side="right", padx=(0, 6))

        if self._view_state.header_filter_column_index != column_index:
            self._header_filter_popup_value.set("")

        popup.bind("<Destroy>", self._on_header_filter_popup_destroy, add="+")
        popup.bind("<Escape>", lambda _event: self._destroy_header_filter_popup(), add="+")
        for widget in (popup, container, search_entry, listbox, empty_label, button_row):
            widget.bind("<FocusOut>", self._schedule_header_filter_popup_focus_check, add="+")

        listbox.bind("<Double-Button-1>", self._on_header_filter_popup_listbox_activate, add="+")
        listbox.bind("<Return>", self._on_header_filter_popup_listbox_activate, add="+")
        search_entry.bind("<Return>", self._on_header_filter_popup_search_submit, add="+")

        self._header_filter_popup_search_var.trace_add("write", self._refresh_header_filter_popup_options)
        self._refresh_header_filter_popup_options()
        search_entry.focus_set()

    def _refresh_header_filter_popup_options(self, *_args) -> None:
        listbox = self._header_filter_popup_listbox
        search_var = self._header_filter_popup_search_var
        empty_var = self._header_filter_popup_empty_var
        if listbox is None or search_var is None or empty_var is None:
            return

        query = search_var.get().strip().casefold()
        if query:
            filtered_options = [option for option in self._header_filter_popup_options if query in option.casefold()]
        else:
            filtered_options = list(self._header_filter_popup_options)

        self._header_filter_popup_filtered_options = filtered_options
        listbox.delete(0, "end")
        for option in filtered_options:
            listbox.insert("end", "(blank)" if not option else _compact_filter_popup_label(option))

        selected_value = self._header_filter_popup_value.get()
        if selected_value and selected_value in filtered_options:
            selected_index = filtered_options.index(selected_value)
            listbox.selection_set(selected_index)
            listbox.see(selected_index)

        if filtered_options:
            empty_var.set("")
        else:
            empty_var.set("No matching values" if query else "No values available")

    def _apply_selected_header_filter_option(self) -> None:
        column_index = self._header_filter_popup_column_index
        listbox = self._header_filter_popup_listbox
        if column_index is None or listbox is None:
            return
        selection = listbox.curselection()
        if not selection:
            return
        selected_index = selection[0]
        if selected_index < 0 or selected_index >= len(self._header_filter_popup_filtered_options):
            return
        self.set_header_filter(column_index, self._header_filter_popup_filtered_options[selected_index])
        self._destroy_header_filter_popup()

    def _clear_header_filter_popup_filter(self) -> None:
        self.clear_header_filter()

    def _on_header_filter_popup_listbox_activate(self, _event) -> str:
        self._apply_selected_header_filter_option()
        return "break"

    def _on_header_filter_popup_search_submit(self, _event) -> str:
        listbox = self._header_filter_popup_listbox
        if listbox is None:
            return "break"
        if not listbox.curselection() and self._header_filter_popup_filtered_options:
            listbox.selection_set(0)
            listbox.see(0)
        self._apply_selected_header_filter_option()
        return "break"

    def _schedule_header_filter_popup_focus_check(self, _event=None) -> None:
        if self._header_filter_popup is None:
            return
        self._win.after_idle(self._close_header_filter_popup_if_focus_lost)

    def _close_header_filter_popup_if_focus_lost(self) -> None:
        popup = self._header_filter_popup
        if popup is None or not popup.winfo_exists():
            return
        focused_widget = popup.focus_get()
        if _widget_descends_from(focused_widget, popup):
            return
        self._destroy_header_filter_popup()

    def _on_header_filter_popup_destroy(self, event) -> None:
        if event.widget != self._header_filter_popup:
            return
        self._header_filter_popup = None
        self._header_filter_popup_column_index = None
        self._header_filter_popup_search_var = None
        self._header_filter_popup_listbox = None
        self._header_filter_popup_empty_var = None
        self._header_filter_popup_options = []
        self._header_filter_popup_filtered_options = []

    def _destroy_header_filter_popup(self) -> None:
        popup = self._header_filter_popup
        if popup is None or not popup.winfo_exists():
            return
        popup.destroy()

    def on_tree_click(self, event) -> None:
        if self._tree.identify_region(event.x, event.y) != "heading":
            return
        column_index = self._column_index_from_event_column(self._tree.identify_column(event.x))
        if column_index is None:
            return
        self.show_header_filter_popup(column_index, event.x_root, event.y_root)

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
                self._win.after(50, self._poll_metadata_refresh)
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

    def open_column_dialog(self) -> None:
        _open_column_visibility_dialog(self._win, self._data.headers, self._view_state.visible_column_indices, self._apply_visible_columns)

    def _apply_visible_columns(self, visible_indices: list[int]) -> None:
        header_filter_cleared = self._view_state.apply_visible_columns(self._all_column_ids, visible_indices)
        if header_filter_cleared:
            self.clear_header_filter()
        if callable(self._on_visible_columns_changed):
            self._on_visible_columns_changed(list(self._data.headers), list(self._view_state.visible_column_indices))
        self.refresh()

    def _populate_rows_in_chunks(
        self,
        load_token: int,
        displayed_rows: list[tuple[str, ...]],
        filtered: bool,
        total_visible_rows: int | None,
        start_index: int,
    ) -> None:
        if load_token != self._load_token:
            return
        if not self._win.winfo_exists() or not self._tree.winfo_exists():
            return

        end_index = min(start_index + ROW_INSERT_CHUNK_SIZE, len(displayed_rows))
        for row in displayed_rows[start_index:end_index]:
            self._tree.insert("", "end", values=row)

        self._view_state.summary.apply_loaded_chunk(
            filtered=filtered,
            total_visible_rows=total_visible_rows,
            displayed_rows=len(displayed_rows),
            loaded_rows=end_index,
        )
        self._update_summary_label()
        if end_index < len(displayed_rows):
            self._win.after_idle(self._populate_rows_in_chunks, load_token, displayed_rows, filtered, total_visible_rows, end_index)


def create_csv_preview_dialog(
    parent: tk.Misc,
    data: CsvPreviewData,
    *,
    width: int,
    height: int,
    initial_visible_column_indices: list[int] | None = None,
    on_visible_columns_changed=None,
) -> tk.Toplevel:
    win = tk.Toplevel(parent)
    win.title(f"CSV Preview - {data.path.name}")
    win.geometry(f"{max(width, MIN_PREVIEW_WIDTH)}x{max(height, MIN_PREVIEW_HEIGHT)}")

    container = ttk.Frame(win)
    container.pack(fill="both", expand=True, padx=8, pady=8)
    container.columnconfigure(0, weight=1)
    container.rowconfigure(2, weight=1)

    initial_displayed_rows = min(data.row_count or len(data.rows), MAX_RENDERED_PREVIEW_ROWS)
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
        on_visible_columns_changed=on_visible_columns_changed,
    )
    win._csv_preview_controller = controller  # type: ignore[attr-defined]

    def _clear_filters() -> None:
        query_var.set("")
        combine_sessions_var.set(False)
        controller.clear_header_filter()

    ttk.Button(filter_row, text="Columns", command=controller.open_column_dialog).pack(side="left", padx=(0, 12))
    ttk.Button(filter_row, text="Clear filters", command=_clear_filters).pack(side="left")

    button_row = ttk.Frame(container)
    button_row.grid(row=3, column=0, sticky="ew", pady=(8, 0))
    ttk.Button(button_row, text="Close", command=win.destroy).pack(side="right")

    query_var.trace_add("write", controller.schedule_refresh)
    combine_sessions_var.trace_add("write", controller.refresh)
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
) -> tk.Toplevel:
    data = load_csv_preview(csv_path)
    settings_store = SettingsStore()
    normalized_path = str(data.path)
    initial_visible_column_indices = _visible_column_indices_from_keys(
        data.headers,
        settings_store.load_csv_preview_visible_column_keys(normalized_path),
    )
    if initial_visible_column_indices is None:
        initial_visible_column_indices = settings_store.load_csv_preview_visible_columns(normalized_path)

    def _save_visible_columns(headers: list[str], visible_indices: list[int]) -> None:
        try:
            settings_store.save_csv_preview_visible_column_keys(
                normalized_path,
                _visible_column_keys(headers, visible_indices),
            )
        except (OSError, TypeError, ValueError) as exc:
            messagebox.showerror("CSV preview settings unavailable", f"Could not save CSV preview columns.\n\nReason: {exc}")

    return create_csv_preview_dialog(
        parent,
        data,
        width=width,
        height=height,
        initial_visible_column_indices=initial_visible_column_indices,
        on_visible_columns_changed=_save_visible_columns,
    )
