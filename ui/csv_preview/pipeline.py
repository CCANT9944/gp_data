from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from decimal import Decimal
from time import perf_counter

from .loader import CsvPreviewData, load_cached_csv_row_cache


MAX_INDEXED_SOURCE_MEMORY_BYTES = 192 * 1024 * 1024
SOURCE_INDEX_FILE_SIZE_MULTIPLIER = 6
SOURCE_INDEX_ROW_OVERHEAD_BYTES = 64
NUMERIC_SORT_DETECTION_SAMPLE_SIZE = 2000
FILTERED_PREVIEW_PROGRESS_THRESHOLDS = (1, 10, 25, 100, 250)


@dataclass(frozen=True)
class _PreviewFilterState:
    query: str
    combine_sessions: bool
    header_filter_column_index: int | None
    header_filter_value: str | None
    sort_column_index: int | None = None
    sort_descending: bool = False

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
    replace_rows: bool = True


@dataclass(frozen=True)
class _FilteredCountUpdate:
    load_token: int
    total_rows: int


@dataclass(frozen=True)
class _FilteredErrorUpdate:
    load_token: int
    error: Exception


_FilteredRefreshMessage = _FilteredPreviewUpdate | _FilteredCountUpdate | _FilteredErrorUpdate


class _PreviewDataPipelineBase:
    def __init__(self, data: CsvPreviewData) -> None:
        self._data = data
        self._combined_rows_cache: list[tuple[str, ...]] | None = None
        self._source_rows_cache: dict[bool, list[tuple[str, ...]]] = {}
        self._source_search_text_cache: dict[bool, list[str]] = {}
        self._header_filter_options_cache: dict[tuple[int, str, bool], list[str]] = {}
        self._numeric_sort_columns_cache: dict[int, bool] = {}
        self._rows_before_header_filter_cache: OrderedDict[tuple[str, bool], list[tuple[str, ...]]] = OrderedDict()
        self._filtered_rows_cache: OrderedDict[
            tuple[str, bool, int | None, str | None],
            list[tuple[str, ...]],
        ] = OrderedDict()
        self._sorted_rows_cache: OrderedDict[
            tuple[str, bool, int | None, str | None, int, bool],
            list[tuple[str, ...]],
        ] = OrderedDict()

    @property
    def data(self) -> CsvPreviewData:
        return self._data

    def update_data(self, data: CsvPreviewData) -> None:
        self._data = data
        self._combined_rows_cache = None
        self._source_rows_cache.clear()
        self._source_search_text_cache.clear()
        self._header_filter_options_cache.clear()
        self._numeric_sort_columns_cache.clear()
        self._rows_before_header_filter_cache.clear()
        self._filtered_rows_cache.clear()
        self._sorted_rows_cache.clear()

    def _log_performance(self, operation: str, started_at: float, **fields: object) -> None:
        raise NotImplementedError

    def _row_search_text(self, row: tuple[str, ...]) -> str:
        raise NotImplementedError

    def _iter_csv_preview_rows(self):
        raise NotImplementedError

    def _iter_rows_before_header_filter(
        self,
        query: str,
        combine_sessions: bool,
        combined_rows: list[tuple[str, ...]] | None = None,
    ):
        raise NotImplementedError

    def _sort_rows(
        self,
        rows: list[tuple[str, ...]],
        column_index: int,
        *,
        descending: bool,
        numeric: bool,
    ) -> list[tuple[str, ...]]:
        raise NotImplementedError

    def _sorted_distinct_values(self, rows, column_index: int) -> list[str]:
        raise NotImplementedError

    def _header_suggests_numeric(self, header: str) -> bool:
        raise NotImplementedError

    def _is_identifier_column(self, header: str) -> bool:
        raise NotImplementedError

    def _parse_decimal(self, value: str) -> Decimal | None:
        raise NotImplementedError

    def _combined_rows(self, combine_sessions: bool) -> list[tuple[str, ...]] | None:
        raise NotImplementedError

    def _remember_cached_rows(self, cache: OrderedDict, cache_key, rows, *, max_entries: int) -> list[tuple[str, ...]]:
        cached_rows = list(rows)
        cache[cache_key] = cached_rows
        cache.move_to_end(cache_key)
        while len(cache) > max_entries:
            cache.popitem(last=False)
        return cached_rows

    def _rows_before_header_filter_cache_key(self, filter_state: _PreviewFilterState) -> tuple[str, bool]:
        return (filter_state.query.casefold(), filter_state.combine_sessions)

    def _estimated_uncombined_source_index_bytes(self) -> int | None:
        if self._data.fully_cached:
            return 0

        row_count = self._data.row_count
        if row_count is None or row_count <= 0:
            return None

        try:
            file_size = self._data.path.stat().st_size
        except OSError:
            return None

        estimated_bytes = (file_size * SOURCE_INDEX_FILE_SIZE_MULTIPLIER) + (row_count * SOURCE_INDEX_ROW_OVERHEAD_BYTES)
        sample_rows = self._data.rows[: min(len(self._data.rows), 250)]
        if sample_rows:
            average_search_text_length = sum(len(self._row_search_text(row)) for row in sample_rows) / len(sample_rows)
            estimated_bytes += int(row_count * max(16.0, average_search_text_length * 2.0))
        return estimated_bytes

    def _can_index_uncombined_source_rows(self) -> bool:
        if self._data.fully_cached:
            return True

        estimated_bytes = self._estimated_uncombined_source_index_bytes()
        return estimated_bytes is not None and estimated_bytes <= MAX_INDEXED_SOURCE_MEMORY_BYTES

    def _source_rows_snapshot(self, combine_sessions: bool) -> list[tuple[str, ...]] | None:
        cached_rows = self._source_rows_cache.get(combine_sessions)
        if cached_rows is not None:
            return cached_rows

        if combine_sessions:
            combined_rows = self._combined_rows(True)
            if combined_rows is not None:
                self._source_rows_cache[True] = combined_rows
            return combined_rows

        if self._data.fully_cached:
            self._source_rows_cache[False] = self._data.rows
            return self._data.rows

        if not self._can_index_uncombined_source_rows():
            return None

        started_at = perf_counter()
        persisted_rows = load_cached_csv_row_cache(self._data)
        if persisted_rows is not None:
            self._source_rows_cache[False] = persisted_rows
            self._log_performance("load persisted source rows", started_at, rows=len(persisted_rows), combined=False)
            return persisted_rows

        started_at = perf_counter()
        rows = list(self._iter_csv_preview_rows())
        self._source_rows_cache[False] = rows
        self._log_performance(
            "index source rows",
            started_at,
            rows=len(rows),
            combined=False,
            estimated_bytes=self._estimated_uncombined_source_index_bytes(),
        )
        return rows

    def _source_search_text_snapshot(self, combine_sessions: bool, source_rows: list[tuple[str, ...]]) -> list[str]:
        cached_search_texts = self._source_search_text_cache.get(combine_sessions)
        if cached_search_texts is not None:
            return cached_search_texts

        started_at = perf_counter()
        search_texts = [self._row_search_text(row) for row in source_rows]
        self._source_search_text_cache[combine_sessions] = search_texts
        self._log_performance("index search text", started_at, rows=len(source_rows), combined=combine_sessions)
        return search_texts

    def _filtered_rows_cache_key(self, filter_state: _PreviewFilterState) -> tuple[str, bool, int | None, str | None]:
        normalized_value = filter_state.header_filter_value.casefold() if filter_state.header_filter_value is not None else None
        return (
            filter_state.query.casefold(),
            filter_state.combine_sessions,
            filter_state.header_filter_column_index,
            normalized_value,
        )

    def _sorted_rows_cache_key(self, filter_state: _PreviewFilterState) -> tuple[str, bool, int | None, str | None, int, bool] | None:
        if filter_state.sort_column_index is None:
            return None
        return (*self._filtered_rows_cache_key(filter_state), filter_state.sort_column_index, filter_state.sort_descending)

    def rows_before_header_filter(self, filter_state: _PreviewFilterState):
        cache_key = self._rows_before_header_filter_cache_key(filter_state)
        cached_rows = self._rows_before_header_filter_cache.get(cache_key)
        if cached_rows is not None:
            self._rows_before_header_filter_cache.move_to_end(cache_key)
            yield from cached_rows
            return

        source_rows = self._source_rows_snapshot(filter_state.combine_sessions)
        if source_rows is not None:
            yield from self.rows_before_header_filter_snapshot(filter_state)
            return

        yield from self._iter_rows_before_header_filter(
            filter_state.query,
            filter_state.combine_sessions,
            combined_rows=self._combined_rows(filter_state.combine_sessions),
        )

    def rows_before_header_filter_snapshot(self, filter_state: _PreviewFilterState) -> list[tuple[str, ...]]:
        cache_key = self._rows_before_header_filter_cache_key(filter_state)
        cached_rows = self._rows_before_header_filter_cache.get(cache_key)
        if cached_rows is not None:
            self._rows_before_header_filter_cache.move_to_end(cache_key)
            return cached_rows

        normalized_query = filter_state.query.strip().casefold()
        if normalized_query:
            incremental_source = self._rows_before_header_filter_cache.get((normalized_query[:-1], filter_state.combine_sessions))
            if incremental_source is not None:
                started_at = perf_counter()
                rows = [row for row in incremental_source if normalized_query in self._row_search_text(row)]
                self._log_performance(
                    "collect query rows",
                    started_at,
                    rows=len(rows),
                    combined=filter_state.combine_sessions,
                    query_length=len(normalized_query),
                    incremental=True,
                )
                return self._remember_cached_rows(self._rows_before_header_filter_cache, cache_key, rows, max_entries=4)

        source_rows = self._source_rows_snapshot(filter_state.combine_sessions)
        if source_rows is not None:
            started_at = perf_counter()
            if not normalized_query:
                rows = list(source_rows)
            else:
                search_texts = self._source_search_text_snapshot(filter_state.combine_sessions, source_rows)
                rows = [
                    row
                    for row, search_text in zip(source_rows, search_texts)
                    if normalized_query in search_text
                ]
            self._log_performance(
                "collect query rows",
                started_at,
                rows=len(rows),
                combined=filter_state.combine_sessions,
                query_length=len(normalized_query),
            )
            return self._remember_cached_rows(self._rows_before_header_filter_cache, cache_key, rows, max_entries=4)

        started_at = perf_counter()
        rows = list(
            self._iter_rows_before_header_filter(
                filter_state.query,
                filter_state.combine_sessions,
                combined_rows=self._combined_rows(filter_state.combine_sessions),
            )
        )
        self._log_performance(
            "collect query rows",
            started_at,
            rows=len(rows),
            combined=filter_state.combine_sessions,
            query_length=len(normalized_query),
        )
        return self._remember_cached_rows(self._rows_before_header_filter_cache, cache_key, rows, max_entries=4)

    def header_filter_options(self, filter_state: _PreviewFilterState, column_index: int) -> list[str]:
        cache_key = filter_state.header_filter_cache_key(column_index)
        options = self._header_filter_options_cache.get(cache_key)
        if options is None:
            options = self.resolve_header_filter_options(filter_state, column_index)
        return options

    def cached_header_filter_options(self, filter_state: _PreviewFilterState, column_index: int) -> list[str] | None:
        cache_key = filter_state.header_filter_cache_key(column_index)
        options = self._header_filter_options_cache.get(cache_key)
        if options is None:
            return None
        return list(options)

    def resolve_header_filter_options(self, filter_state: _PreviewFilterState, column_index: int, *, should_cancel=None) -> list[str]:
        cache_key = filter_state.header_filter_cache_key(column_index)
        options = self._header_filter_options_cache.get(cache_key)
        if options is not None:
            return list(options)

        started_at = perf_counter()
        if not filter_state.query.strip() and not filter_state.combine_sessions:
            source_rows = self._source_rows_snapshot(False)
            row_source = source_rows if source_rows is not None else (self._data.rows if self._data.fully_cached else self._iter_csv_preview_rows())
            distinct_values: set[str] = set()
            for row in row_source:
                if should_cancel is not None and should_cancel():
                    return []
                distinct_values.add(row[column_index])
            options = sorted(distinct_values, key=lambda value: value.casefold())
        else:
            started_at = perf_counter()
            options = self._sorted_distinct_values(self.rows_before_header_filter_snapshot(filter_state), column_index)
        self._header_filter_options_cache[cache_key] = options
        self._log_performance(
            "collect distinct values",
            started_at,
            column_index=column_index,
            values=len(options),
            query_length=len(filter_state.query.strip()),
            combined=filter_state.combine_sessions,
        )
        return list(options)

    def prewarm_header_filter_columns(self, filter_state: _PreviewFilterState, column_indices: list[int], *, should_cancel=None) -> None:
        started_at = perf_counter()
        source_rows = self._source_rows_snapshot(filter_state.combine_sessions)
        if source_rows is None:
            return

        unique_indices: list[int] = []
        seen_indices: set[int] = set()
        for raw_index in column_indices:
            try:
                column_index = int(raw_index)
            except (TypeError, ValueError):
                continue
            if column_index < 0 or column_index >= self._data.column_count or column_index in seen_indices:
                continue
            unique_indices.append(column_index)
            seen_indices.add(column_index)

        for column_index in unique_indices:
            if should_cancel is not None and should_cancel():
                return
            self.resolve_header_filter_options(filter_state, column_index, should_cancel=should_cancel)
            if should_cancel is not None and should_cancel():
                return
            self.is_numeric_sort_column(column_index, should_cancel=should_cancel)

        self._log_performance(
            "prewarm header filters",
            started_at,
            columns=len(unique_indices),
            query_length=len(filter_state.query.strip()),
            combined=filter_state.combine_sessions,
        )

    def iter_rows(self, filter_state: _PreviewFilterState):
        if filter_state.sort_column_index is None:
            yield from self.iter_filtered_rows(filter_state)
            return
        yield from self.iter_sorted_rows(filter_state)

    def iter_filtered_rows(self, filter_state: _PreviewFilterState):
        yield from self._iter_rows_after_header_filter(filter_state)

    def iter_sorted_rows(self, filter_state: _PreviewFilterState):
        yield from self.sorted_rows_snapshot(filter_state)

    def filtered_rows_snapshot(self, filter_state: _PreviewFilterState) -> list[tuple[str, ...]]:
        cache_key = self._filtered_rows_cache_key(filter_state)
        cached_rows = self._filtered_rows_cache.get(cache_key)
        if cached_rows is not None:
            self._filtered_rows_cache.move_to_end(cache_key)
            return cached_rows

        started_at = perf_counter()
        rows = list(self._iter_rows_after_header_filter(filter_state))
        self._log_performance(
            "collect filtered rows",
            started_at,
            rows=len(rows),
            query_length=len(filter_state.query.strip()),
            header_filter=filter_state.header_filter_column_index is not None,
        )
        return self._remember_cached_rows(self._filtered_rows_cache, cache_key, rows, max_entries=4)

    def sorted_rows_snapshot(self, filter_state: _PreviewFilterState) -> list[tuple[str, ...]]:
        if filter_state.sort_column_index is None:
            return self.filtered_rows_snapshot(filter_state)

        cache_key = self._sorted_rows_cache_key(filter_state)
        if cache_key is not None:
            cached_rows = self._sorted_rows_cache.get(cache_key)
            if cached_rows is not None:
                self._sorted_rows_cache.move_to_end(cache_key)
                return cached_rows

        started_at = perf_counter()
        sorted_rows = self._sort_rows(
            list(self.filtered_rows_snapshot(filter_state)),
            filter_state.sort_column_index,
            descending=filter_state.sort_descending,
            numeric=self.is_numeric_sort_column(filter_state.sort_column_index),
        )
        self._log_performance(
            "sort rows",
            started_at,
            rows=len(sorted_rows),
            column_index=filter_state.sort_column_index,
            descending=filter_state.sort_descending,
        )
        if cache_key is None:
            return sorted_rows
        return self._remember_cached_rows(self._sorted_rows_cache, cache_key, sorted_rows, max_entries=4)

    def is_numeric_sort_column(self, column_index: int, *, should_cancel=None) -> bool:
        cached_value = self._numeric_sort_columns_cache.get(column_index)
        if cached_value is not None:
            return cached_value

        if column_index < 0 or column_index >= self._data.column_count:
            return False

        started_at = perf_counter()
        header = self._data.headers[column_index]
        if self._is_identifier_column(header):
            result = False
        elif self._header_suggests_numeric(header):
            result = True
        else:
            non_empty_values = 0
            numeric_values = 0
            source_rows = self._source_rows_snapshot(False)
            row_source = source_rows if source_rows is not None else (self._data.rows if self._data.fully_cached else self._iter_csv_preview_rows())
            for row in row_source:
                if should_cancel is not None and should_cancel():
                    return False
                value = row[column_index].strip()
                if not value:
                    continue
                non_empty_values += 1
                if self._parse_decimal(value) is not None:
                    numeric_values += 1
                if non_empty_values >= NUMERIC_SORT_DETECTION_SAMPLE_SIZE:
                    break

            mostly_numeric = non_empty_values and (numeric_values / non_empty_values) >= 0.98
            small_sample_with_single_outlier = non_empty_values <= 5 and numeric_values >= max(2, non_empty_values - 1)
            result = bool(mostly_numeric or small_sample_with_single_outlier)

        self._numeric_sort_columns_cache[column_index] = result
        self._log_performance(
            "detect numeric sort column",
            started_at,
            column_index=column_index,
            result=result,
        )
        return result

    def _iter_rows_after_header_filter(self, filter_state: _PreviewFilterState):
        normalized_value = filter_state.header_filter_value.casefold() if filter_state.header_filter_value is not None else None
        if filter_state.header_filter_column_index is None or normalized_value is None:
            yield from self.rows_before_header_filter(filter_state)
            return

        column_index = filter_state.header_filter_column_index
        casefold_cache: dict[str, str] = {}
        for row in self.rows_before_header_filter(filter_state):
            raw_value = row[column_index]
            folded_value = casefold_cache.get(raw_value)
            if folded_value is None:
                folded_value = raw_value.casefold()
                casefold_cache[raw_value] = folded_value
            if folded_value == normalized_value:
                yield row

    def iter_filtered_refresh_messages(self, load_token: int, filter_state: _PreviewFilterState, *, rendered_row_limit: int, should_cancel=None):
        if filter_state.sort_column_index is not None:
            yield from self._iter_sorted_refresh_messages(
                load_token,
                filter_state,
                rendered_row_limit=rendered_row_limit,
                should_cancel=should_cancel,
            )
            return

        displayed_rows: list[tuple[str, ...]] = []
        matched_rows = 0
        preview_sent = False
        emitted_preview_sizes: set[int] = set()

        for row in self.iter_filtered_rows(filter_state):
            if should_cancel is not None and should_cancel():
                return
            matched_rows += 1
            if len(displayed_rows) < rendered_row_limit:
                displayed_rows.append(row)
                if len(displayed_rows) in FILTERED_PREVIEW_PROGRESS_THRESHOLDS and len(displayed_rows) not in emitted_preview_sizes:
                    yield _FilteredPreviewUpdate(load_token=load_token, displayed_rows=list(displayed_rows), total_rows=None)
                    emitted_preview_sizes.add(len(displayed_rows))
                continue
            if not preview_sent:
                yield _FilteredPreviewUpdate(load_token=load_token, displayed_rows=list(displayed_rows), total_rows=None)
                preview_sent = True

        if preview_sent:
            yield _FilteredCountUpdate(load_token=load_token, total_rows=matched_rows)
            return

        if matched_rows and matched_rows in emitted_preview_sizes:
            yield _FilteredCountUpdate(load_token=load_token, total_rows=matched_rows)
            return

        yield _FilteredPreviewUpdate(load_token=load_token, displayed_rows=displayed_rows, total_rows=matched_rows)

    def _iter_sorted_refresh_messages(self, load_token: int, filter_state: _PreviewFilterState, *, rendered_row_limit: int, should_cancel=None):
        if filter_state.sort_column_index is None:
            yield _FilteredPreviewUpdate(load_token=load_token, displayed_rows=[], total_rows=0)
            return

        cache_key = self._sorted_rows_cache_key(filter_state)
        if cache_key is not None:
            cached_sorted_rows = self._sorted_rows_cache.get(cache_key)
            if cached_sorted_rows is not None:
                self._sorted_rows_cache.move_to_end(cache_key)
                yield _FilteredPreviewUpdate(
                    load_token=load_token,
                    displayed_rows=cached_sorted_rows[:rendered_row_limit],
                    total_rows=len(cached_sorted_rows),
                )
                return

        numeric_sort = self.is_numeric_sort_column(filter_state.sort_column_index, should_cancel=should_cancel)
        if should_cancel is not None and should_cancel():
            return
        filtered_cache_key = self._filtered_rows_cache_key(filter_state)
        cached_filtered_rows = self._filtered_rows_cache.get(filtered_cache_key)
        if cached_filtered_rows is not None:
            self._filtered_rows_cache.move_to_end(filtered_cache_key)
            if len(cached_filtered_rows) > rendered_row_limit:
                preview_started_at = perf_counter()
                yield _FilteredPreviewUpdate(
                    load_token=load_token,
                    displayed_rows=self._sort_rows(
                        list(cached_filtered_rows[:rendered_row_limit]),
                        filter_state.sort_column_index,
                        descending=filter_state.sort_descending,
                        numeric=numeric_sort,
                    ),
                    total_rows=None,
                )
                self._log_performance(
                    "sort preview rows",
                    preview_started_at,
                    rows=rendered_row_limit,
                    cached=True,
                    column_index=filter_state.sort_column_index,
                )
            sort_started_at = perf_counter()
            sorted_rows = self._sort_rows(
                list(cached_filtered_rows),
                filter_state.sort_column_index,
                descending=filter_state.sort_descending,
                numeric=numeric_sort,
            )
            self._log_performance(
                "sort rows",
                sort_started_at,
                rows=len(sorted_rows),
                column_index=filter_state.sort_column_index,
                descending=filter_state.sort_descending,
                cached=True,
            )
            if cache_key is not None:
                self._remember_cached_rows(self._sorted_rows_cache, cache_key, sorted_rows, max_entries=4)
            yield _FilteredPreviewUpdate(
                load_token=load_token,
                displayed_rows=sorted_rows[:rendered_row_limit],
                total_rows=len(sorted_rows),
            )
            return

        preview_rows: list[tuple[str, ...]] = []
        filtered_rows: list[tuple[str, ...]] = []
        preview_sent = False
        collect_started_at = perf_counter()
        for row in self.iter_filtered_rows(filter_state):
            if should_cancel is not None and should_cancel():
                return
            filtered_rows.append(row)
            if len(preview_rows) < rendered_row_limit:
                preview_rows.append(row)
                continue
            if not preview_sent:
                preview_started_at = perf_counter()
                yield _FilteredPreviewUpdate(
                    load_token=load_token,
                    displayed_rows=self._sort_rows(
                        list(preview_rows),
                        filter_state.sort_column_index,
                        descending=filter_state.sort_descending,
                        numeric=numeric_sort,
                    ),
                    total_rows=None,
                )
                self._log_performance(
                    "sort preview rows",
                    preview_started_at,
                    rows=len(preview_rows),
                    cached=False,
                    column_index=filter_state.sort_column_index,
                )
                preview_sent = True
        self._log_performance(
            "collect filtered rows",
            collect_started_at,
            rows=len(filtered_rows),
            query_length=len(filter_state.query.strip()),
            header_filter=filter_state.header_filter_column_index is not None,
        )

        cached_filtered_rows = self._remember_cached_rows(
            self._filtered_rows_cache,
            filtered_cache_key,
            filtered_rows,
            max_entries=4,
        )
        sort_started_at = perf_counter()
        sorted_rows = self._sort_rows(
            list(cached_filtered_rows),
            filter_state.sort_column_index,
            descending=filter_state.sort_descending,
            numeric=numeric_sort,
        )
        self._log_performance(
            "sort rows",
            sort_started_at,
            rows=len(sorted_rows),
            column_index=filter_state.sort_column_index,
            descending=filter_state.sort_descending,
            cached=False,
        )
        if cache_key is not None:
            self._remember_cached_rows(self._sorted_rows_cache, cache_key, sorted_rows, max_entries=4)
        yield _FilteredPreviewUpdate(
            load_token=load_token,
            displayed_rows=sorted_rows[:rendered_row_limit],
            total_rows=len(sorted_rows),
        )