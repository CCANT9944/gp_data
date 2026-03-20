from __future__ import annotations

from decimal import Decimal

from .pipeline import _PreviewDataPipelineBase


class _PreviewDataPipeline(_PreviewDataPipelineBase):
    max_indexed_source_memory_bytes_impl = staticmethod(lambda: 0)
    log_performance_impl = staticmethod(lambda operation, started_at, **fields: None)
    row_search_text_impl = staticmethod(lambda row: "")
    iter_csv_preview_rows_impl = staticmethod(lambda data: ())
    iter_rows_before_header_filter_impl = staticmethod(
        lambda data, query, combine_sessions, combined_rows=None: ()
    )
    sort_rows_impl = staticmethod(lambda rows, column_index, *, descending, numeric: rows)
    sorted_distinct_values_impl = staticmethod(lambda rows, column_index: [])
    header_suggests_numeric_impl = staticmethod(lambda header: False)
    is_identifier_column_impl = staticmethod(lambda header: False)
    parse_decimal_impl = staticmethod(lambda value: None)
    resolve_metadata_impl = staticmethod(lambda data: data)
    metadata_resolved_update_factory = staticmethod(lambda resolved_data: resolved_data)
    metadata_error_update_factory = staticmethod(lambda error: error)
    iter_combined_rows_impl = staticmethod(lambda data, enabled: ())
    perf_counter_impl = staticmethod(lambda: 0.0)

    def _can_index_uncombined_source_rows(self) -> bool:
        if self._data.fully_cached:
            return True

        estimated_bytes = self._estimated_uncombined_source_index_bytes()
        return estimated_bytes is not None and estimated_bytes <= self.max_indexed_source_memory_bytes_impl()

    def _log_performance(self, operation: str, started_at: float, **fields: object) -> None:
        self.log_performance_impl(operation, started_at, **fields)

    def _row_search_text(self, row: tuple[str, ...]) -> str:
        return self.row_search_text_impl(row)

    def _iter_csv_preview_rows(self):
        return self.iter_csv_preview_rows_impl(self._data)

    def _iter_rows_before_header_filter(
        self,
        query: str,
        combine_sessions: bool,
        combined_rows: list[tuple[str, ...]] | None = None,
    ):
        return self.iter_rows_before_header_filter_impl(
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
        return self.sort_rows_impl(rows, column_index, descending=descending, numeric=numeric)

    def _sorted_distinct_values(self, rows, column_index: int) -> list[str]:
        return self.sorted_distinct_values_impl(rows, column_index)

    def _header_suggests_numeric(self, header: str) -> bool:
        return self.header_suggests_numeric_impl(header)

    def _is_identifier_column(self, header: str) -> bool:
        return self.is_identifier_column_impl(header)

    def _parse_decimal(self, value: str) -> Decimal | None:
        return self.parse_decimal_impl(value)

    def resolve_metadata_refresh_message(self):
        try:
            return self.metadata_resolved_update_factory(self.resolve_metadata_impl(self._data))
        except Exception as exc:
            return self.metadata_error_update_factory(exc)

    def _combined_rows(self, combine_sessions: bool) -> list[tuple[str, ...]] | None:
        if not combine_sessions:
            return None
        if self._combined_rows_cache is None:
            started_at = self.perf_counter_impl()
            self._combined_rows_cache = list(self.iter_combined_rows_impl(self._data, True))
            self.log_performance_impl("combine session rows", started_at, rows=len(self._combined_rows_cache))
        return self._combined_rows_cache