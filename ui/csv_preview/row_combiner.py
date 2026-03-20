from __future__ import annotations

from collections import OrderedDict

from .helpers import (
    _combined_sessions,
    _detect_numeric_columns,
    _detect_quantity_column,
    _detect_session_column,
    _format_decimal,
    _parse_decimal,
    _row_matches_normalized_query,
)
from .loader import CsvPreviewData, iter_csv_preview_rows


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