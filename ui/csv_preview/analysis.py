from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from math import ceil
from typing import Sequence

from .helpers import _filter_label, _format_decimal, _is_identifier_column, _normalized_header, _parse_decimal
from .loader import CsvPreviewData


DEFAULT_CHART_CATEGORY_LIMIT = 8
DEFAULT_SUMMARY_TOP_VALUE_LIMIT = 3
DEFAULT_HISTOGRAM_BIN_COUNT = 8


@dataclass(frozen=True)
class PreviewAnalysisValueCount:
    value: str
    count: int


@dataclass(frozen=True)
class PreviewNumericSummary:
    minimum: Decimal | None
    maximum: Decimal | None
    total: Decimal | None
    average: Decimal | None


@dataclass(frozen=True)
class PreviewAnalysisColumn:
    index: int
    header: str
    label: str
    numeric: bool
    row_count: int
    non_empty_count: int
    blank_count: int
    distinct_count: int
    value_counts: list[PreviewAnalysisValueCount]
    numeric_summary: PreviewNumericSummary | None = None


@dataclass(frozen=True)
class PreviewCategoryChartSeries:
    column_index: int
    column_label: str
    labels: list[str]
    values: list[int]


@dataclass(frozen=True)
class PreviewNumericBarChartSeries:
    value_column_index: int
    value_column_label: str
    label_column_index: int
    label_column_label: str
    labels: list[str]
    values: list[Decimal]


@dataclass(frozen=True)
class PreviewAggregatedChartSeries:
    label_column_index: int
    label_column_label: str
    value_column_index: int | None
    value_column_label: str
    labels: list[str]
    values: list[Decimal]


@dataclass(frozen=True)
class PreviewHistogramSeries:
    value_column_index: int
    value_column_label: str
    labels: list[str]
    counts: list[int]
    minimum: Decimal
    maximum: Decimal
    bin_count: int
    auto_bin_count: bool
    outlier_bin_indices: frozenset[int]


@dataclass(frozen=True)
class PreviewAnalysisSnapshot:
    source_name: str
    row_count: int
    visible_column_count: int
    filtering_active: bool
    combine_sessions: bool
    columns: list[PreviewAnalysisColumn]
    rows: Sequence[tuple[str, ...]]

    def column(self, column_index: int) -> PreviewAnalysisColumn | None:
        for column in self.columns:
            if column.index == column_index:
                return column
        return None


def _format_histogram_boundary(value: Decimal) -> str:
    rounded = value.quantize(Decimal("0.01"))
    return _format_decimal(rounded)


def _interpolated_quantile(sorted_values: Sequence[Decimal], numerator: int, denominator: int) -> Decimal:
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (Decimal(len(sorted_values) - 1) * Decimal(numerator)) / Decimal(denominator)
    lower_index = int(position.to_integral_value(rounding=ROUND_FLOOR))
    upper_index = int(position.to_integral_value(rounding=ROUND_CEILING))
    if lower_index == upper_index:
        return sorted_values[lower_index]
    fraction = position - Decimal(lower_index)
    lower_value = sorted_values[lower_index]
    upper_value = sorted_values[upper_index]
    return lower_value + ((upper_value - lower_value) * fraction)


def _auto_histogram_bin_count(numeric_values: Sequence[Decimal]) -> int:
    value_count = len(numeric_values)
    if value_count <= 1:
        return value_count

    minimum = min(numeric_values)
    maximum = max(numeric_values)
    if minimum == maximum:
        return 1

    sorted_values = sorted(numeric_values)
    q1 = _interpolated_quantile(sorted_values, 1, 4)
    q3 = _interpolated_quantile(sorted_values, 3, 4)
    iqr = q3 - q1
    suggested_bin_count: int | None = None

    if iqr > 0:
        bucket_width = float(Decimal("2") * iqr) / (value_count ** (1 / 3))
        if bucket_width > 0:
            suggested_bin_count = ceil(float(maximum - minimum) / bucket_width)

    if suggested_bin_count is None or suggested_bin_count < 1:
        suggested_bin_count = ceil(value_count ** 0.5)

    return max(2, min(suggested_bin_count, min(20, value_count)))


def _histogram_outlier_fences(numeric_values: Sequence[Decimal]) -> tuple[Decimal, Decimal] | None:
    if len(numeric_values) < 4:
        return None
    sorted_values = sorted(numeric_values)
    q1 = _interpolated_quantile(sorted_values, 1, 4)
    q3 = _interpolated_quantile(sorted_values, 3, 4)
    iqr = q3 - q1
    if iqr <= 0:
        return None
    margin = Decimal("1.5") * iqr
    return q1 - margin, q3 + margin


def _sorted_value_counts(counter: Counter[str]) -> list[PreviewAnalysisValueCount]:
    items = sorted(counter.items(), key=lambda item: (-item[1], item[0].casefold()))
    return [PreviewAnalysisValueCount(value=value, count=count) for value, count in items]


def _grouped_other_label(existing_labels: set[str]) -> str:
    label = "Other"
    if label not in existing_labels:
        return label
    suffix = 1
    while True:
        candidate = f"Other (grouped {suffix})"
        if candidate not in existing_labels:
            return candidate
        suffix += 1


def build_preview_analysis_snapshot(
    data: CsvPreviewData,
    filtered_rows: list[tuple[str, ...]],
    visible_column_indices: list[int],
    numeric_column_indices: set[int],
    *,
    filtering_active: bool,
    combine_sessions: bool,
) -> PreviewAnalysisSnapshot:
    analyzed_columns: list[PreviewAnalysisColumn] = []
    row_count = len(filtered_rows)

    for column_index in visible_column_indices:
        if column_index < 0 or column_index >= data.column_count:
            continue
        header = data.headers[column_index]
        values = [row[column_index] if column_index < len(row) else "" for row in filtered_rows]
        non_empty_values = [value for value in values if value.strip()]
        value_counts = _sorted_value_counts(Counter(non_empty_values))
        numeric_summary = None
        if column_index in numeric_column_indices:
            numeric_values = [value for value in (_parse_decimal(raw_value) for raw_value in non_empty_values) if value is not None]
            if numeric_values:
                total = sum(numeric_values, Decimal("0"))
                numeric_summary = PreviewNumericSummary(
                    minimum=min(numeric_values),
                    maximum=max(numeric_values),
                    total=total,
                    average=total / Decimal(len(numeric_values)),
                )
        analyzed_columns.append(
            PreviewAnalysisColumn(
                index=column_index,
                header=header,
                label=_filter_label(header, column_index),
                numeric=column_index in numeric_column_indices,
                row_count=row_count,
                non_empty_count=len(non_empty_values),
                blank_count=row_count - len(non_empty_values),
                distinct_count=len(value_counts),
                value_counts=value_counts,
                numeric_summary=numeric_summary,
            )
        )

    return PreviewAnalysisSnapshot(
        source_name=data.path.name,
        row_count=row_count,
        visible_column_count=len(analyzed_columns),
        filtering_active=filtering_active,
        combine_sessions=combine_sessions,
        columns=analyzed_columns,
        rows=filtered_rows,
    )


def _label_column_priority(column: PreviewAnalysisColumn) -> tuple[int, int]:
    normalized = _normalized_header(column.header)
    if any(token in normalized for token in ("description", "name", "item", "product")):
        return (0, column.index)
    if "class" in normalized:
        return (1, column.index)
    if _is_identifier_column(column.header):
        return (4, column.index)
    if "session" in normalized:
        return (3, column.index)
    return (2, column.index)


def _preferred_label_column(
    snapshot: PreviewAnalysisSnapshot,
    *,
    exclude_index: int,
) -> PreviewAnalysisColumn | None:
    candidates = [column for column in snapshot.columns if not column.numeric and column.index != exclude_index]
    if not candidates:
        return None
    return min(candidates, key=_label_column_priority)


def preferred_chart_label_column(snapshot: PreviewAnalysisSnapshot) -> PreviewAnalysisColumn | None:
    non_numeric_candidates = [column for column in snapshot.columns if not column.numeric]
    if non_numeric_candidates:
        return min(non_numeric_candidates, key=_label_column_priority)
    return snapshot.columns[0] if snapshot.columns else None


def preferred_chart_value_column(snapshot: PreviewAnalysisSnapshot) -> PreviewAnalysisColumn | None:
    numeric_candidates = [column for column in snapshot.columns if column.numeric]
    if not numeric_candidates:
        return None

    def _value_priority(column: PreviewAnalysisColumn) -> tuple[int, int]:
        normalized = _normalized_header(column.header)
        if "quantity" in normalized or normalized == "qty":
            return (0, column.index)
        if any(token in normalized for token in ("sales", "revenue", "amount", "total", "value", "price", "cost")):
            return (1, column.index)
        return (2, column.index)

    return min(numeric_candidates, key=_value_priority)


def build_category_chart_series(
    snapshot: PreviewAnalysisSnapshot,
    column_index: int,
    *,
    limit: int = DEFAULT_CHART_CATEGORY_LIMIT,
) -> PreviewCategoryChartSeries | None:
    column = snapshot.column(column_index)
    if column is None or not column.value_counts:
        return None

    safe_limit = max(2, limit)
    value_counts = list(column.value_counts)
    if len(value_counts) > safe_limit:
        other_label = _grouped_other_label({entry.value for entry in value_counts})
        retained = value_counts[: safe_limit - 1]
        other_count = sum(value.count for value in value_counts[safe_limit - 1 :])
        value_counts = retained + [PreviewAnalysisValueCount(value=other_label, count=other_count)]

    return PreviewCategoryChartSeries(
        column_index=column.index,
        column_label=column.label,
        labels=[entry.value or "(blank)" for entry in value_counts],
        values=[entry.count for entry in value_counts],
    )


def build_aggregated_chart_series(
    snapshot: PreviewAnalysisSnapshot,
    label_column_index: int,
    *,
    value_column_index: int | None = None,
    limit: int | None = DEFAULT_CHART_CATEGORY_LIMIT,
) -> PreviewAggregatedChartSeries | None:
    label_column = snapshot.column(label_column_index)
    if label_column is None:
        return None

    value_column = None if value_column_index is None else snapshot.column(value_column_index)
    if value_column_index is not None and (value_column is None or not value_column.numeric):
        return None

    totals_by_label: dict[str, Decimal] = {}
    for row in snapshot.rows:
        if label_column.index >= len(row):
            continue
        label = row[label_column.index].strip() or "(blank)"
        if value_column is None:
            totals_by_label[label] = totals_by_label.get(label, Decimal("0")) + Decimal("1")
            continue
        if value_column.index >= len(row):
            continue
        numeric_value = _parse_decimal(row[value_column.index])
        if numeric_value is None:
            continue
        totals_by_label[label] = totals_by_label.get(label, Decimal("0")) + numeric_value

    if not totals_by_label:
        return None

    sorted_items = sorted(totals_by_label.items(), key=lambda item: (-item[1], item[0].casefold()))
    if limit is not None:
        safe_limit = max(2, limit)
        if len(sorted_items) > safe_limit:
            other_label = _grouped_other_label({label for label, _ in sorted_items})
            retained = sorted_items[: safe_limit - 1]
            other_value = sum((value for _, value in sorted_items[safe_limit - 1 :]), Decimal("0"))
            sorted_items = retained + [(other_label, other_value)]

    value_column_label = value_column.label if value_column is not None else "Count rows"
    return PreviewAggregatedChartSeries(
        label_column_index=label_column.index,
        label_column_label=label_column.label,
        value_column_index=None if value_column is None else value_column.index,
        value_column_label=value_column_label,
        labels=[label for label, _ in sorted_items],
        values=[value for _, value in sorted_items],
    )


def build_histogram_series(
    snapshot: PreviewAnalysisSnapshot,
    value_column_index: int,
    *,
    bin_count: int | None = None,
) -> PreviewHistogramSeries | None:
    value_column = snapshot.column(value_column_index)
    if value_column is None or not value_column.numeric:
        return None

    numeric_values: list[Decimal] = []
    for row in snapshot.rows:
        if value_column.index >= len(row):
            continue
        numeric_value = _parse_decimal(row[value_column.index])
        if numeric_value is None:
            continue
        numeric_values.append(numeric_value)

    if not numeric_values:
        return None

    minimum = min(numeric_values)
    maximum = max(numeric_values)
    auto_bin_count = bin_count is None
    requested_bin_count = _auto_histogram_bin_count(numeric_values) if auto_bin_count else max(1, min(bin_count, len(numeric_values)))
    safe_bin_count = requested_bin_count

    if minimum == maximum:
        return PreviewHistogramSeries(
            value_column_index=value_column.index,
            value_column_label=value_column.label,
            labels=[_format_decimal(minimum)],
            counts=[len(numeric_values)],
            minimum=minimum,
            maximum=maximum,
            bin_count=1,
            auto_bin_count=auto_bin_count,
            outlier_bin_indices=frozenset(),
        )

    bucket_width = (maximum - minimum) / Decimal(safe_bin_count)
    counts = [0] * safe_bin_count
    outlier_bin_indices: set[int] = set()
    outlier_fences = _histogram_outlier_fences(numeric_values)
    for numeric_value in numeric_values:
        if numeric_value == maximum:
            bucket_index = safe_bin_count - 1
        else:
            bucket_index = int((numeric_value - minimum) / bucket_width)
        safe_bucket_index = max(0, min(bucket_index, safe_bin_count - 1))
        counts[safe_bucket_index] += 1
        if outlier_fences is not None:
            lower_fence, upper_fence = outlier_fences
            if numeric_value < lower_fence or numeric_value > upper_fence:
                outlier_bin_indices.add(safe_bucket_index)

    labels: list[str] = []
    for bucket_index in range(safe_bin_count):
        start_value = minimum + (bucket_width * Decimal(bucket_index))
        if bucket_index == safe_bin_count - 1:
            end_value = maximum
        else:
            end_value = minimum + (bucket_width * Decimal(bucket_index + 1))
        labels.append(f"{_format_histogram_boundary(start_value)} - {_format_histogram_boundary(end_value)}")

    return PreviewHistogramSeries(
        value_column_index=value_column.index,
        value_column_label=value_column.label,
        labels=labels,
        counts=counts,
        minimum=minimum,
        maximum=maximum,
        bin_count=safe_bin_count,
        auto_bin_count=auto_bin_count,
        outlier_bin_indices=frozenset(outlier_bin_indices),
    )


def build_numeric_bar_chart_series(
    snapshot: PreviewAnalysisSnapshot,
    value_column_index: int,
    *,
    label_column_index: int | None = None,
    limit: int = DEFAULT_CHART_CATEGORY_LIMIT,
) -> PreviewNumericBarChartSeries | None:
    value_column = snapshot.column(value_column_index)
    if value_column is None or not value_column.numeric:
        return None

    if label_column_index is None:
        label_column = _preferred_label_column(snapshot, exclude_index=value_column_index)
    else:
        label_column = snapshot.column(label_column_index)
        if label_column is None or label_column.index == value_column_index:
            return None

    aggregated_series = build_aggregated_chart_series(
        snapshot,
        label_column.index,
        value_column_index=value_column_index,
        limit=limit,
    )
    if aggregated_series is None:
        return None
    return PreviewNumericBarChartSeries(
        value_column_index=value_column.index,
        value_column_label=value_column.label,
        label_column_index=aggregated_series.label_column_index,
        label_column_label=aggregated_series.label_column_label,
        labels=aggregated_series.labels,
        values=aggregated_series.values,
    )


def format_value_counts_summary(
    value_counts: list[PreviewAnalysisValueCount],
    *,
    limit: int = DEFAULT_SUMMARY_TOP_VALUE_LIMIT,
) -> str:
    if not value_counts:
        return ""
    limited_values = value_counts[: max(1, limit)]
    return ", ".join(f"{entry.value or '(blank)'} ({entry.count})" for entry in limited_values)


def format_decimal_summary(value: Decimal | None) -> str:
    return _format_decimal(value)