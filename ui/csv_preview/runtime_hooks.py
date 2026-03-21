from __future__ import annotations

from .preview_pipeline import _PreviewDataPipeline
from .preview_state import _PreviewSummaryState, _PreviewViewState


def configure_preview_runtime(
    *,
    max_indexed_source_memory_bytes,
    log_preview_performance,
    row_search_text,
    iter_csv_preview_rows,
    iter_rows_before_header_filter,
    sort_rows,
    sorted_distinct_values,
    header_suggests_numeric,
    is_identifier_column,
    parse_decimal,
    resolve_metadata,
    metadata_resolved_update_factory,
    metadata_error_update_factory,
    iter_combined_rows,
    perf_counter_impl,
    loading_summary_text,
    summary_text,
    normalize_visible_column_indices,
) -> None:
    _PreviewSummaryState.loading_summary_text_impl = staticmethod(
        lambda data, *, filtered, sort_description=None: loading_summary_text(
            data,
            filtered=filtered,
            sort_description=sort_description,
        )
    )
    _PreviewSummaryState.summary_text_impl = staticmethod(
        lambda data, *, visible_rows, displayed_rows, loaded_rows, filtered=False, sort_description=None: summary_text(
            data,
            visible_rows=visible_rows,
            displayed_rows=displayed_rows,
            loaded_rows=loaded_rows,
            filtered=filtered,
            sort_description=sort_description,
        )
    )
    _PreviewViewState.normalize_visible_column_indices_impl = staticmethod(normalize_visible_column_indices)
    _PreviewDataPipeline.max_indexed_source_memory_bytes_impl = staticmethod(max_indexed_source_memory_bytes)
    _PreviewDataPipeline.log_performance_impl = staticmethod(log_preview_performance)
    _PreviewDataPipeline.row_search_text_impl = staticmethod(row_search_text)
    _PreviewDataPipeline.iter_csv_preview_rows_impl = staticmethod(iter_csv_preview_rows)
    _PreviewDataPipeline.iter_rows_before_header_filter_impl = staticmethod(iter_rows_before_header_filter)
    _PreviewDataPipeline.sort_rows_impl = staticmethod(sort_rows)
    _PreviewDataPipeline.sorted_distinct_values_impl = staticmethod(sorted_distinct_values)
    _PreviewDataPipeline.header_suggests_numeric_impl = staticmethod(header_suggests_numeric)
    _PreviewDataPipeline.is_identifier_column_impl = staticmethod(is_identifier_column)
    _PreviewDataPipeline.parse_decimal_impl = staticmethod(parse_decimal)
    _PreviewDataPipeline.resolve_metadata_impl = staticmethod(resolve_metadata)
    _PreviewDataPipeline.metadata_resolved_update_factory = staticmethod(metadata_resolved_update_factory)
    _PreviewDataPipeline.metadata_error_update_factory = staticmethod(metadata_error_update_factory)
    _PreviewDataPipeline.iter_combined_rows_impl = staticmethod(iter_combined_rows)
    _PreviewDataPipeline.perf_counter_impl = staticmethod(perf_counter_impl)