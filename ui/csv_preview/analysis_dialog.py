from __future__ import annotations

from decimal import Decimal
import tkinter as tk
from tkinter import ttk

from .analysis import (
    DEFAULT_CHART_CATEGORY_LIMIT,
    DEFAULT_HISTOGRAM_BIN_COUNT,
    PreviewAggregatedChartSeries,
    PreviewHistogramSeries,
    PreviewAnalysisSnapshot,
    build_aggregated_chart_series,
    build_histogram_series,
    build_preview_analysis_snapshot,
    format_decimal_summary,
    format_value_counts_summary,
    preferred_chart_label_column,
    preferred_chart_value_column,
)
from .helpers import _compact_filter_popup_label
from .histogram_help import open_histogram_help_dialog
from .loader import CsvPreviewData


ANALYSIS_WINDOW_WIDTH = 980
ANALYSIS_WINDOW_HEIGHT = 680
VIEW_SUMMARY = "Summary"
VIEW_BAR = "Bar chart"
VIEW_PIE = "Pie chart"
VIEW_HISTOGRAM = "Histogram"
BAR_ORIENTATION_VERTICAL = "Vertical"
BAR_ORIENTATION_HORIZONTAL = "Horizontal"
BAR_ORIENTATION_OPTIONS = (
    BAR_ORIENTATION_VERTICAL,
    BAR_ORIENTATION_HORIZONTAL,
)
BAR_RANGE_ALL = "All"
BAR_RANGE_FIRST_5 = "First 5"
BAR_RANGE_FIRST_10 = "First 10"
BAR_RANGE_FIRST_20 = "First 20"
BAR_RANGE_LAST_5 = "Last 5"
BAR_RANGE_LAST_10 = "Last 10"
BAR_RANGE_LAST_20 = "Last 20"
BAR_RANGE_OPTIONS = (
    BAR_RANGE_ALL,
    BAR_RANGE_FIRST_5,
    BAR_RANGE_FIRST_10,
    BAR_RANGE_FIRST_20,
    BAR_RANGE_LAST_5,
    BAR_RANGE_LAST_10,
    BAR_RANGE_LAST_20,
)
SUMMARY_COLUMNS = (
    "column",
    "type",
    "rows",
    "non_empty",
    "distinct",
    "min",
    "max",
    "average",
    "sum",
    "top_values",
)
CHART_COLORS = (
    "#4e79a7",
    "#f28e2b",
    "#e15759",
    "#76b7b2",
    "#59a14f",
    "#edc948",
    "#b07aa1",
    "#ff9da7",
)
COUNT_ROWS_LABEL = "Count rows"
HISTOGRAM_BIN_AUTO = "Auto"
HISTOGRAM_BIN_OPTIONS = (HISTOGRAM_BIN_AUTO, "5", "8", "10", "12", "15", "20")
HISTOGRAM_OUTLIER_FILL = "#d1495b"
HISTOGRAM_OUTLIER_OUTLINE = "#7f1d1d"
BAR_VISIBILITY_POPUP_WIDTH = 360
BAR_VISIBILITY_POPUP_HEIGHT = 420
BAR_VISIBILITY_POPUP_LIST_HEIGHT = 260


def _slice_bar_chart_series(series: PreviewAggregatedChartSeries, selection: str) -> PreviewAggregatedChartSeries:
    if selection == BAR_RANGE_FIRST_5:
        limit = 5
        labels = series.labels[:limit]
        values = series.values[:limit]
    elif selection == BAR_RANGE_FIRST_10:
        limit = 10
        labels = series.labels[:limit]
        values = series.values[:limit]
    elif selection == BAR_RANGE_FIRST_20:
        limit = 20
        labels = series.labels[:limit]
        values = series.values[:limit]
    elif selection == BAR_RANGE_LAST_5:
        limit = 5
        labels = series.labels[-limit:]
        values = series.values[-limit:]
    elif selection == BAR_RANGE_LAST_10:
        limit = 10
        labels = series.labels[-limit:]
        values = series.values[-limit:]
    elif selection == BAR_RANGE_LAST_20:
        limit = 20
        labels = series.labels[-limit:]
        values = series.values[-limit:]
    else:
        labels = list(series.labels)
        values = list(series.values)

    return PreviewAggregatedChartSeries(
        label_column_index=series.label_column_index,
        label_column_label=series.label_column_label,
        value_column_index=series.value_column_index,
        value_column_label=series.value_column_label,
        labels=labels,
        values=values,
    )


def _bar_chart_range_description(selection: str) -> str:
    if selection == BAR_RANGE_FIRST_5:
        return "first 5"
    if selection == BAR_RANGE_FIRST_10:
        return "first 10"
    if selection == BAR_RANGE_FIRST_20:
        return "first 20"
    if selection == BAR_RANGE_LAST_5:
        return "last 5"
    if selection == BAR_RANGE_LAST_10:
        return "last 10"
    if selection == BAR_RANGE_LAST_20:
        return "last 20"
    return "all items"


def _bar_chart_message(series: PreviewAggregatedChartSeries, selection: str) -> str:
    if selection == BAR_RANGE_ALL:
        return f"{series.value_column_label} by {series.label_column_label} (highest to lowest)"
    return f"{series.value_column_label} by {series.label_column_label} ({_bar_chart_range_description(selection)}, highest to lowest)"


def _filter_bar_chart_series(
    series: PreviewAggregatedChartSeries,
    hidden_labels: set[str],
) -> PreviewAggregatedChartSeries:
    if not hidden_labels:
        return series

    labels: list[str] = []
    values: list[Decimal] = []
    for label, value in zip(series.labels, series.values, strict=False):
        if label in hidden_labels:
            continue
        labels.append(label)
        values.append(value)

    return PreviewAggregatedChartSeries(
        label_column_index=series.label_column_index,
        label_column_label=series.label_column_label,
        value_column_index=series.value_column_index,
        value_column_label=series.value_column_label,
        labels=labels,
        values=values,
    )


def _analysis_subtitle(snapshot: PreviewAnalysisSnapshot) -> str:
    row_label = "filtered rows" if snapshot.filtering_active else "preview rows"
    combine_label = "Combine sessions on" if snapshot.combine_sessions else "Combine sessions off"
    return f"{snapshot.row_count} {row_label} | {snapshot.visible_column_count} visible columns | {combine_label}"


def _populate_summary_tree(tree: ttk.Treeview, snapshot: PreviewAnalysisSnapshot) -> None:
    for existing_row in tree.get_children():
        tree.delete(existing_row)

    for column in snapshot.columns:
        minimum = maximum = average = total = ""
        if column.numeric_summary is not None:
            minimum = format_decimal_summary(column.numeric_summary.minimum)
            maximum = format_decimal_summary(column.numeric_summary.maximum)
            average = format_decimal_summary(column.numeric_summary.average)
            total = format_decimal_summary(column.numeric_summary.total)
        tree.insert(
            "",
            "end",
            values=(
                column.label,
                "Numeric" if column.numeric else "Category",
                column.row_count,
                column.non_empty_count,
                column.distinct_count,
                minimum,
                maximum,
                average,
                total,
                format_value_counts_summary(column.value_counts),
            ),
        )


def _chart_canvas_size(canvas: tk.Canvas) -> tuple[int, int]:
    return max(canvas.winfo_width(), 720), max(canvas.winfo_height(), 420)


def _clear_chart(canvas: tk.Canvas) -> None:
    canvas.delete("all")


def _draw_empty_chart(canvas: tk.Canvas, message: str) -> None:
    _clear_chart(canvas)
    width, height = _chart_canvas_size(canvas)
    canvas.configure(scrollregion=(0, 0, width, height))
    canvas.xview_moveto(0)
    canvas.yview_moveto(0)
    canvas.create_text(
        width / 2,
        height / 2,
        text=message,
        fill="#6b7280",
        width=max(width - 80, 240),
        justify="center",
        font=("Segoe UI", 11),
    )


def _draw_vertical_bar_chart(canvas: tk.Canvas, series: PreviewAggregatedChartSeries) -> None:
    _clear_chart(canvas)
    viewport_width, height = _chart_canvas_size(canvas)
    label_texts = [_compact_filter_popup_label(label, max_length=20) for label in series.labels]
    max_label_length = max((len(label) for label in label_texts), default=0)
    label_padding = 10
    left = 72
    right = 28
    top = 36
    bottom = max(208, min(288, 112 + (max_label_length * 5)))
    chart_bottom = height - bottom
    chart_top = top
    chart_height = max(chart_bottom - chart_top, 80)
    max_value = max(series.values, default=None)
    min_value = min(series.values, default=None)
    if max_value is None or min_value is None:
        _draw_empty_chart(canvas, "No chartable values are available for the selected columns.")
        return
    chart_min = min(min_value, Decimal("0"))
    chart_max = max(max_value, Decimal("0"))
    if chart_min == chart_max:
        _draw_empty_chart(canvas, "No chartable values are available for the selected columns.")
        return
    chart_range_float = float(chart_max - chart_min)

    def _y_for(value: Decimal) -> float:
        return chart_top + ((float(chart_max - value) / chart_range_float) * chart_height)

    baseline_y = _y_for(Decimal("0"))

    count = len(series.values)
    gap = 10
    bar_width = 16
    content_width = left + right + gap + count * (bar_width + gap)
    if content_width < viewport_width:
        gap = max(gap, (viewport_width - left - right - (count * bar_width)) // max(count + 1, 1))
        content_width = viewport_width
    canvas.configure(scrollregion=(0, 0, content_width, height))
    canvas.xview_moveto(0)

    canvas.create_line(left, chart_top, left, chart_bottom, fill="#9ca3af")
    canvas.create_line(left, baseline_y, content_width - right, baseline_y, fill="#9ca3af")

    tick_count = 4
    for tick in range(tick_count + 1):
        value = chart_min + ((chart_max - chart_min) * Decimal(tick) / Decimal(tick_count))
        y = _y_for(value)
        grid_color = "#9ca3af" if value == 0 else "#eef2f7"
        canvas.create_line(left, y, content_width - right, y, fill=grid_color)
        canvas.create_text(
            left - 10,
            y,
            text=format_decimal_summary(value),
            anchor="e",
            fill="#6b7280",
            font=("Segoe UI", 9),
        )
    start_x = left + gap

    for index, (label, value) in enumerate(zip(label_texts, series.values, strict=False)):
        x0 = start_x + index * (bar_width + gap)
        x1 = x0 + bar_width
        value_y = _y_for(value)
        y0 = min(value_y, baseline_y)
        y1 = max(value_y, baseline_y)
        color = CHART_COLORS[index % len(CHART_COLORS)]
        canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline="")
        value_text_y = y0 - 10 if value >= 0 else y1 + 10
        value_anchor = "s" if value >= 0 else "n"
        canvas.create_text(
            (x0 + x1) / 2,
            value_text_y,
            text=format_decimal_summary(value),
            anchor=value_anchor,
            fill="#374151",
            font=("Segoe UI", 8, "bold"),
        )
        label_id = canvas.create_text(
            (x0 + x1) / 2,
            chart_bottom + 44,
            text=label,
            anchor="center",
            angle=90,
            fill="#374151",
            font=("Segoe UI", 9),
        )
        label_box = canvas.bbox(label_id)
        if label_box is not None and label_box[1] < chart_bottom + label_padding:
            canvas.move(label_id, 0, (chart_bottom + label_padding) - label_box[1])


def _draw_horizontal_bar_chart(canvas: tk.Canvas, series: PreviewAggregatedChartSeries) -> None:
    _clear_chart(canvas)
    width, viewport_height = _chart_canvas_size(canvas)
    label_texts = [_compact_filter_popup_label(label, max_length=24) for label in series.labels]
    max_label_length = max((len(label) for label in label_texts), default=0)
    left = max(164, min(320, 88 + (max_label_length * 6)))
    right = 96
    top = 36
    bottom = 28
    count = len(series.values)
    gap = 12
    bar_height = 16
    content_height = top + bottom + gap + count * (bar_height + gap)
    if content_height < viewport_height:
        gap = max(gap, (viewport_height - top - bottom - (count * bar_height)) // max(count + 1, 1))
        content_height = viewport_height

    chart_left = left
    chart_right = width - right
    chart_width = max(chart_right - chart_left, 120)
    max_value = max(series.values, default=None)
    min_value = min(series.values, default=None)
    if max_value is None or min_value is None:
        _draw_empty_chart(canvas, "No chartable values are available for the selected columns.")
        return
    chart_min = min(min_value, Decimal("0"))
    chart_max = max(max_value, Decimal("0"))
    if chart_min == chart_max:
        _draw_empty_chart(canvas, "No chartable values are available for the selected columns.")
        return
    chart_range_float = float(chart_max - chart_min)

    def _x_for(value: Decimal) -> float:
        return chart_left + ((float(value - chart_min) / chart_range_float) * chart_width)

    baseline_x = _x_for(Decimal("0"))
    canvas.configure(scrollregion=(0, 0, width, content_height))
    canvas.xview_moveto(0)
    canvas.yview_moveto(0)

    canvas.create_line(chart_left, top, chart_left, content_height - bottom, fill="#9ca3af")
    canvas.create_line(baseline_x, top, baseline_x, content_height - bottom, fill="#9ca3af")

    tick_count = 4
    for tick in range(tick_count + 1):
        value = chart_min + ((chart_max - chart_min) * Decimal(tick) / Decimal(tick_count))
        x = _x_for(value)
        grid_color = "#9ca3af" if value == 0 else "#eef2f7"
        canvas.create_line(x, top, x, content_height - bottom, fill=grid_color)
        canvas.create_text(
            x,
            top - 12,
            text=format_decimal_summary(value),
            anchor="s",
            fill="#6b7280",
            font=("Segoe UI", 9),
        )

    start_y = top + gap
    for index, (label, value) in enumerate(zip(label_texts, series.values, strict=False)):
        y0 = start_y + index * (bar_height + gap)
        y1 = y0 + bar_height
        value_x = _x_for(value)
        x0 = min(value_x, baseline_x)
        x1 = max(value_x, baseline_x)
        color = CHART_COLORS[index % len(CHART_COLORS)]
        canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline="")
        value_text_x = x1 + 8 if value >= 0 else x0 - 8
        value_anchor = "w" if value >= 0 else "e"
        canvas.create_text(
            value_text_x,
            (y0 + y1) / 2,
            text=format_decimal_summary(value),
            anchor=value_anchor,
            fill="#374151",
            font=("Segoe UI", 8, "bold"),
        )
        canvas.create_text(
            chart_left - 10,
            (y0 + y1) / 2,
            text=label,
            anchor="e",
            fill="#374151",
            font=("Segoe UI", 9),
        )


def _draw_bar_chart(canvas: tk.Canvas, series: PreviewAggregatedChartSeries, orientation: str) -> None:
    if orientation == BAR_ORIENTATION_HORIZONTAL:
        _draw_horizontal_bar_chart(canvas, series)
        return
    _draw_vertical_bar_chart(canvas, series)


def _draw_aggregated_pie_chart(canvas: tk.Canvas, series: PreviewAggregatedChartSeries) -> None:
    _clear_chart(canvas)
    width, height = _chart_canvas_size(canvas)
    canvas.xview_moveto(0)
    if any(value < 0 for value in series.values):
        _draw_empty_chart(canvas, "Pie charts require positive values only.")
        return

    positive_items = [(label, value) for label, value in zip(series.labels, series.values, strict=False) if value > 0]
    total = sum((value for _, value in positive_items), Decimal("0"))
    if total <= 0:
        _draw_empty_chart(canvas, "No chartable values are available for the selected columns.")
        return

    legend_width = min(320, max(width // 3, 230))
    diameter = min(width - legend_width - 72, height - 80)
    diameter = max(diameter, 180)
    left = 28
    top = 36
    bbox = (left, top, left + diameter, top + diameter)
    legend_x = left + diameter + 28
    legend_y = top + 12
    legend_row_height = 24
    canvas.configure(scrollregion=(0, 0, width, height))

    start_angle = 0.0
    total_float = float(total)
    for index, (label, value) in enumerate(positive_items):
        value_float = float(value)
        extent = 360.0 * value_float / total_float
        color = CHART_COLORS[index % len(CHART_COLORS)]
        canvas.create_arc(bbox, start=start_angle, extent=extent, fill=color, outline="white", width=2)
        start_angle += extent

        item_y = legend_y + index * legend_row_height
        percentage = (value_float / total_float) * 100.0
        canvas.create_rectangle(legend_x, item_y, legend_x + 14, item_y + 14, fill=color, outline="")
        canvas.create_text(
            legend_x + 22,
            item_y + 7,
            text=f"{_compact_filter_popup_label(label, max_length=24)} ({format_decimal_summary(value)}, {percentage:.0f}%)",
            anchor="w",
            width=max(width - legend_x - 32, 180),
            justify="left",
            fill="#374151",
            font=("Segoe UI", 8),
        )

    canvas.create_oval(
        left + diameter * 0.32,
        top + diameter * 0.32,
        left + diameter * 0.68,
        top + diameter * 0.68,
        fill="white",
        outline="white",
    )
    canvas.create_text(
        left + diameter / 2,
        top + diameter / 2,
        text=f"{format_decimal_summary(total)}\n{series.value_column_label}",
        justify="center",
        fill="#374151",
        font=("Segoe UI", 11, "bold"),
    )


def _histogram_message(series: PreviewHistogramSeries) -> str:
    return (
        f"Distribution of {series.value_column_label} across {series.bin_count} bins "
        f"({format_decimal_summary(series.minimum)} to {format_decimal_summary(series.maximum)})"
    )


def _histogram_helper_text(series: PreviewHistogramSeries) -> str:
    parts = []
    if series.auto_bin_count:
        parts.append(f"Auto chose {series.bin_count} bins from the data spread.")
    parts.append("Bins group nearby values together: fewer bins show broader groups, more bins show finer detail.")
    parts.append("Histogram counts rows in value ranges; it does not sum values by item.")
    parts.append("Blue bins show the main distribution.")
    if series.outlier_bin_indices:
        parts.append("Red bins include outlier values.")
    return " ".join(parts)


def _draw_histogram_chart(canvas: tk.Canvas, series: PreviewHistogramSeries) -> None:
    _clear_chart(canvas)
    width, height = _chart_canvas_size(canvas)
    left = 72
    right = 28
    top = 36
    bottom = 220
    chart_bottom = height - bottom
    chart_top = top
    chart_height = max(chart_bottom - chart_top, 80)
    label_padding = 10
    max_count = max(series.counts, default=0)
    if max_count <= 0:
        _draw_empty_chart(canvas, "No chartable values are available for the selected columns.")
        return

    canvas.configure(scrollregion=(0, 0, width, height))
    canvas.xview_moveto(0)
    canvas.yview_moveto(0)

    canvas.create_line(left, chart_top, left, chart_bottom, fill="#9ca3af")
    canvas.create_line(left, chart_bottom, width - right, chart_bottom, fill="#9ca3af")

    tick_count = min(4, max_count)
    for tick in range(tick_count + 1):
        value = int(round((max_count * tick) / max(tick_count, 1)))
        y = chart_bottom - ((value / max_count) * chart_height)
        canvas.create_line(left, y, width - right, y, fill="#eef2f7")
        canvas.create_text(
            left - 10,
            y,
            text=str(value),
            anchor="e",
            fill="#6b7280",
            font=("Segoe UI", 9),
        )

    bucket_count = len(series.counts)
    gap = 12
    available_width = max(width - left - right - ((bucket_count + 1) * gap), bucket_count * 24)
    bar_width = max(24, available_width / max(bucket_count, 1))
    start_x = left + gap
    label_texts = [_compact_filter_popup_label(label, max_length=14) for label in series.labels]

    for index, (label, count) in enumerate(zip(label_texts, series.counts, strict=False)):
        x0 = start_x + index * (bar_width + gap)
        x1 = x0 + bar_width
        y1 = chart_bottom
        y0 = chart_bottom - ((count / max_count) * chart_height)
        is_outlier_bin = index in series.outlier_bin_indices
        canvas.create_rectangle(
            x0,
            y0,
            x1,
            y1,
            fill=HISTOGRAM_OUTLIER_FILL if is_outlier_bin else CHART_COLORS[index % len(CHART_COLORS)],
            outline=HISTOGRAM_OUTLIER_OUTLINE if is_outlier_bin else "",
            width=1 if is_outlier_bin else 0,
        )
        canvas.create_text(
            (x0 + x1) / 2,
            y0 - 10,
            text=str(count),
            anchor="s",
            fill="#374151",
            font=("Segoe UI", 8, "bold"),
        )
        label_id = canvas.create_text(
            (x0 + x1) / 2,
            chart_bottom + 46,
            text=label,
            anchor="center",
            angle=90,
            fill="#374151",
            font=("Segoe UI", 9),
        )
        label_box = canvas.bbox(label_id)
        if label_box is not None and label_box[1] < chart_bottom + label_padding:
            canvas.move(label_id, 0, (chart_bottom + label_padding) - label_box[1])


def open_csv_preview_analysis_dialog(
    parent: tk.Misc,
    data: CsvPreviewData,
    filtered_rows: list[tuple[str, ...]],
    visible_column_indices: list[int],
    numeric_column_indices: set[int],
    *,
    filtering_active: bool,
    combine_sessions: bool,
) -> tk.Toplevel:
    snapshot = build_preview_analysis_snapshot(
        data,
        filtered_rows,
        visible_column_indices,
        numeric_column_indices,
        filtering_active=filtering_active,
        combine_sessions=combine_sessions,
    )
    return open_csv_preview_analysis_dialog_from_snapshot(parent, snapshot)


def build_csv_preview_analysis_view(
    parent: tk.Misc,
    snapshot: PreviewAnalysisSnapshot,
    *,
    close_command=None,
    close_button_text: str = "Close",
    popup_parent: tk.Misc | None = None,
    chart_message_wraplength: int = ANALYSIS_WINDOW_WIDTH - 120,
) -> ttk.Frame:
    popup_owner = (popup_parent if popup_parent is not None else parent.winfo_toplevel())
    container = ttk.Frame(parent, padding=8)
    container.columnconfigure(0, weight=1)
    container.rowconfigure(2, weight=1)

    subtitle_var = tk.StringVar(value=_analysis_subtitle(snapshot))
    ttk.Label(container, textvariable=subtitle_var, anchor="w").grid(row=0, column=0, sticky="ew", pady=(0, 8))

    control_row = ttk.Frame(container)
    control_row.grid(row=1, column=0, sticky="ew", pady=(0, 8))
    control_row.columnconfigure(1, weight=1)
    control_row.columnconfigure(3, weight=1)
    control_row.columnconfigure(5, weight=1)

    output_var = tk.StringVar(value=VIEW_SUMMARY)
    ttk.Label(control_row, text="View").grid(row=0, column=0, sticky="w")
    output_box = ttk.Combobox(control_row, textvariable=output_var, state="readonly", width=16)
    output_box["values"] = (VIEW_SUMMARY, VIEW_BAR, VIEW_PIE, VIEW_HISTOGRAM)
    output_box.grid(row=0, column=1, sticky="ew", padx=(6, 12))

    label_var = tk.StringVar()
    ttk.Label(control_row, text="Label").grid(row=0, column=2, sticky="w")
    label_box = ttk.Combobox(control_row, textvariable=label_var, state="readonly", width=28)
    label_options = [column.label for column in snapshot.columns]
    label_box["values"] = label_options
    if label_options:
        preferred_label = preferred_chart_label_column(snapshot)
        label_var.set(preferred_label.label if preferred_label is not None else label_options[0])
    label_box.grid(row=0, column=3, sticky="ew", padx=(6, 12))

    value_var = tk.StringVar()
    ttk.Label(control_row, text="Value").grid(row=0, column=4, sticky="w")
    value_box = ttk.Combobox(control_row, textvariable=value_var, state="readonly", width=22)
    numeric_value_options = [column.label for column in snapshot.columns if column.numeric]
    value_options = [COUNT_ROWS_LABEL] + numeric_value_options
    value_box["values"] = value_options
    preferred_value = preferred_chart_value_column(snapshot)
    value_var.set(preferred_value.label if preferred_value is not None else COUNT_ROWS_LABEL)
    value_box.grid(row=0, column=5, sticky="ew", padx=(6, 0))

    bar_range_var = tk.StringVar(value=BAR_RANGE_ALL)
    ttk.Label(control_row, text="Bar range").grid(row=1, column=0, sticky="w", pady=(8, 0))
    bar_range_box = ttk.Combobox(control_row, textvariable=bar_range_var, state="disabled", width=12)
    bar_range_box["values"] = BAR_RANGE_OPTIONS
    bar_range_box.grid(row=1, column=1, sticky="w", padx=(6, 12), pady=(8, 0))

    bar_orientation_var = tk.StringVar(value=BAR_ORIENTATION_VERTICAL)
    ttk.Label(control_row, text="Orientation").grid(row=1, column=2, sticky="w", pady=(8, 0))
    bar_orientation_box = ttk.Combobox(control_row, textvariable=bar_orientation_var, state="disabled", width=12)
    bar_orientation_box["values"] = BAR_ORIENTATION_OPTIONS
    bar_orientation_box.grid(row=1, column=3, sticky="w", padx=(6, 12), pady=(8, 0))

    histogram_bins_var = tk.StringVar(value=HISTOGRAM_BIN_AUTO)
    ttk.Label(control_row, text="Bins").grid(row=1, column=4, sticky="w", pady=(8, 0))
    histogram_bins_box = ttk.Combobox(control_row, textvariable=histogram_bins_var, state="disabled", width=8)
    histogram_bins_box["values"] = HISTOGRAM_BIN_OPTIONS
    histogram_bins_box.grid(row=1, column=5, sticky="w", padx=(6, 0), pady=(8, 0))

    bar_visibility_button = ttk.Button(control_row, text="Hide bars")
    bar_visibility_button.grid(row=1, column=6, sticky="w", padx=(12, 0), pady=(8, 0))
    bar_visibility_button.grid_remove()

    histogram_help_button = ttk.Button(control_row, text="Explain histogram")
    histogram_help_button.grid(row=1, column=7, sticky="w", padx=(12, 0), pady=(8, 0))
    histogram_help_button.grid_remove()

    content_frame = ttk.Frame(container)
    content_frame.grid(row=2, column=0, sticky="nsew")
    content_frame.columnconfigure(0, weight=1)
    content_frame.rowconfigure(0, weight=1)

    summary_frame = ttk.Frame(content_frame)
    summary_frame.columnconfigure(0, weight=1)
    summary_frame.rowconfigure(0, weight=1)
    summary_tree = ttk.Treeview(summary_frame, columns=SUMMARY_COLUMNS, show="headings")
    summary_headers = {
        "column": "Column",
        "type": "Type",
        "rows": "Rows",
        "non_empty": "Non-empty",
        "distinct": "Distinct",
        "min": "Min",
        "max": "Max",
        "average": "Average",
        "sum": "Sum",
        "top_values": "Top values",
    }
    summary_widths = {
        "column": 180,
        "type": 90,
        "rows": 70,
        "non_empty": 90,
        "distinct": 80,
        "min": 90,
        "max": 90,
        "average": 90,
        "sum": 90,
        "top_values": 260,
    }
    for column_id in SUMMARY_COLUMNS:
        summary_tree.heading(column_id, text=summary_headers[column_id])
        summary_tree.column(column_id, width=summary_widths[column_id], stretch=column_id in {"column", "top_values"})
    summary_y_scroll = ttk.Scrollbar(summary_frame, orient="vertical", command=summary_tree.yview)
    summary_x_scroll = ttk.Scrollbar(summary_frame, orient="horizontal", command=summary_tree.xview)
    summary_tree.configure(yscrollcommand=summary_y_scroll.set, xscrollcommand=summary_x_scroll.set)
    summary_tree.grid(row=0, column=0, sticky="nsew")
    summary_y_scroll.grid(row=0, column=1, sticky="ns")
    summary_x_scroll.grid(row=1, column=0, sticky="ew")
    _populate_summary_tree(summary_tree, snapshot)

    chart_frame = ttk.Frame(content_frame)
    chart_frame.columnconfigure(0, weight=1)
    chart_frame.rowconfigure(1, weight=1)
    chart_message_var = tk.StringVar(value="")
    ttk.Label(
        chart_frame,
        textvariable=chart_message_var,
        anchor="w",
        justify="left",
        wraplength=chart_message_wraplength,
    ).grid(
        row=0, column=0, sticky="ew", pady=(0, 8)
    )
    chart_x_scroll = ttk.Scrollbar(chart_frame, orient="horizontal")
    chart_y_scroll = ttk.Scrollbar(chart_frame, orient="vertical")
    chart_canvas = tk.Canvas(chart_frame, background="white", highlightthickness=0)
    chart_canvas.configure(xscrollcommand=chart_x_scroll.set, yscrollcommand=chart_y_scroll.set)
    chart_x_scroll.configure(command=chart_canvas.xview)
    chart_y_scroll.configure(command=chart_canvas.yview)
    chart_canvas.grid(row=1, column=0, sticky="nsew")
    chart_y_scroll.grid(row=1, column=1, sticky="ns")
    chart_x_scroll.grid(row=2, column=0, sticky="ew")

    column_label_to_index = {column.label: column.index for column in snapshot.columns}
    bar_hidden_labels: set[str] = set()
    bar_hidden_context: tuple[int | None, int | None] | None = None
    bar_visibility_popup: tk.Toplevel | None = None

    def _selected_label_column_index() -> int | None:
        return column_label_to_index.get(label_var.get())

    def _selected_value_column_index() -> int | None:
        selected_label = value_var.get()
        if not selected_label or selected_label == COUNT_ROWS_LABEL:
            return None
        return column_label_to_index.get(selected_label)

    def _selected_histogram_bin_count() -> int | None:
        if histogram_bins_var.get() == HISTOGRAM_BIN_AUTO:
            return None
        try:
            return max(1, int(histogram_bins_var.get()))
        except (TypeError, ValueError):
            return None

    def _selected_histogram_bin_label() -> str:
        selected_label = histogram_bins_var.get().strip()
        return selected_label or HISTOGRAM_BIN_AUTO

    def _destroy_bar_visibility_popup() -> None:
        nonlocal bar_visibility_popup
        popup = bar_visibility_popup
        bar_visibility_popup = None
        if popup is not None and popup.winfo_exists():
            popup.destroy()

    def _current_bar_chart_series() -> PreviewAggregatedChartSeries | None:
        label_column_index = _selected_label_column_index()
        if label_column_index is None:
            return None
        value_column_index = _selected_value_column_index()
        series = build_aggregated_chart_series(
            snapshot,
            label_column_index,
            value_column_index=value_column_index,
            limit=None,
        )
        if series is None:
            return None
        return _slice_bar_chart_series(series, bar_range_var.get())

    def _open_bar_visibility_popup() -> None:
        nonlocal bar_visibility_popup
        _destroy_bar_visibility_popup()

        popup = tk.Toplevel(popup_owner)
        popup.title("Bar visibility")
        popup.geometry(f"{BAR_VISIBILITY_POPUP_WIDTH}x{BAR_VISIBILITY_POPUP_HEIGHT}")
        popup.transient(popup_owner)
        popup.minsize(320, 260)
        popup.resizable(True, True)
        bar_visibility_popup = popup

        def _clear_popup_reference(_event=None) -> None:
            nonlocal bar_visibility_popup
            if bar_visibility_popup is popup:
                bar_visibility_popup = None

        popup.bind("<Destroy>", _clear_popup_reference, add="+")
        popup.protocol("WM_DELETE_WINDOW", _destroy_bar_visibility_popup)

        container = ttk.Frame(popup, padding=8)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(1, weight=1)

        ttk.Label(
            container,
            text="Untick items to hide them from the current bar chart.",
            justify="left",
            wraplength=BAR_VISIBILITY_POPUP_WIDTH - 32,
        ).grid(row=0, column=0, sticky="ew", pady=(0, 8))

        series = _current_bar_chart_series()
        if series is None or not series.labels:
            ttk.Label(
                container,
                text="No bars are available for the current chart settings.",
                justify="left",
                wraplength=BAR_VISIBILITY_POPUP_WIDTH - 32,
            ).grid(row=1, column=0, sticky="nw")
            button_row = ttk.Frame(container)
            button_row.grid(row=2, column=0, sticky="e", pady=(8, 0))
            ttk.Button(button_row, text="Close", command=_destroy_bar_visibility_popup).pack(side="right")
            return

        list_frame = ttk.Frame(container)
        list_frame.grid(row=1, column=0, sticky="nsew")
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        list_canvas = tk.Canvas(list_frame, highlightthickness=0, height=BAR_VISIBILITY_POPUP_LIST_HEIGHT)
        list_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=list_canvas.yview)
        list_canvas.configure(yscrollcommand=list_scroll.set)
        list_canvas.grid(row=0, column=0, sticky="nsew")
        list_scroll.grid(row=0, column=1, sticky="ns")

        checklist_frame = ttk.Frame(list_canvas)
        checklist_window = list_canvas.create_window((0, 0), window=checklist_frame, anchor="nw")

        def _sync_scroll_region(_event=None) -> None:
            bbox = list_canvas.bbox("all")
            if bbox is not None:
                list_canvas.configure(scrollregion=bbox)

        def _sync_checklist_width(event) -> None:
            list_canvas.itemconfigure(checklist_window, width=event.width)

        checklist_frame.bind("<Configure>", _sync_scroll_region, add="+")
        list_canvas.bind("<Configure>", _sync_checklist_width, add="+")

        visibility_vars: dict[str, tk.BooleanVar] = {}
        visibility_buttons: list[tk.Checkbutton] = []

        def _update_visibility_button_wraplength(_event=None) -> None:
            wraplength = max(checklist_frame.winfo_width() - 36, 120)
            for button in visibility_buttons:
                button.configure(wraplength=wraplength)

        def _set_bar_visibility(label: str) -> None:
            if visibility_vars[label].get():
                bar_hidden_labels.discard(label)
            else:
                bar_hidden_labels.add(label)
            _render_chart()

        for label in series.labels:
            visibility_var = tk.BooleanVar(value=label not in bar_hidden_labels)
            visibility_vars[label] = visibility_var
            visibility_button = tk.Checkbutton(
                checklist_frame,
                text=label,
                variable=visibility_var,
                anchor="w",
                justify="left",
                relief="flat",
                borderwidth=0,
                highlightthickness=0,
                command=lambda selected_label=label: _set_bar_visibility(selected_label),
            )
            visibility_button.pack(anchor="w", fill="x")
            visibility_buttons.append(visibility_button)

        checklist_frame.bind("<Configure>", _update_visibility_button_wraplength, add="+")
        list_canvas.bind("<Configure>", _update_visibility_button_wraplength, add="+")

        button_row = ttk.Frame(container)
        button_row.grid(row=2, column=0, sticky="ew", pady=(8, 0))

        def _show_all_bars() -> None:
            bar_hidden_labels.clear()
            for visibility_var in visibility_vars.values():
                visibility_var.set(True)
            _render_chart()

        ttk.Button(button_row, text="Show all", command=_show_all_bars).pack(side="left")
        ttk.Button(button_row, text="Close", command=_destroy_bar_visibility_popup).pack(side="right")

    def _open_histogram_help() -> None:
        selected_value_label = value_var.get().strip() or COUNT_ROWS_LABEL
        open_histogram_help_dialog(
            popup_owner,
            value_column_label=selected_value_label,
            bin_label=_selected_histogram_bin_label(),
            row_count=snapshot.row_count,
            filtering_active=snapshot.filtering_active,
            combine_sessions=snapshot.combine_sessions,
        )

    def _set_chart_x_scrollbar(enabled: bool) -> None:
        if enabled:
            chart_x_scroll.grid()
        else:
            chart_x_scroll.grid_remove()
            chart_canvas.xview_moveto(0)

    def _set_chart_y_scrollbar(enabled: bool) -> None:
        if enabled:
            chart_y_scroll.grid()
        else:
            chart_y_scroll.grid_remove()
            chart_canvas.yview_moveto(0)

    def _render_chart() -> None:
        nonlocal bar_hidden_context
        label_column_index = _selected_label_column_index()
        if label_column_index is None:
            _set_chart_x_scrollbar(False)
            _set_chart_y_scrollbar(False)
            chart_message_var.set("Choose a visible label column to render a chart.")
            _draw_empty_chart(chart_canvas, "Choose a visible label column to render a chart.")
            return

        selected_view = output_var.get()
        value_column_index = _selected_value_column_index()
        if selected_view == VIEW_HISTOGRAM:
            if value_column_index is None:
                _set_chart_x_scrollbar(False)
                _set_chart_y_scrollbar(False)
                chart_message_var.set("Choose a numeric value column to render a histogram.")
                _draw_empty_chart(chart_canvas, "Choose a numeric value column to render a histogram.")
                return

            histogram_series = build_histogram_series(
                snapshot,
                value_column_index,
                bin_count=_selected_histogram_bin_count(),
            )
            if histogram_series is None:
                _set_chart_x_scrollbar(False)
                _set_chart_y_scrollbar(False)
                chart_message_var.set("No chartable numeric values are available for the selected column.")
                _draw_empty_chart(chart_canvas, "No chartable numeric values are available for the selected column.")
                return

            _set_chart_x_scrollbar(False)
            _set_chart_y_scrollbar(False)
            chart_message_var.set(f"{_histogram_message(histogram_series)}\n{_histogram_helper_text(histogram_series)}")
            _draw_histogram_chart(chart_canvas, histogram_series)
            return

        current_bar_context = (label_column_index, value_column_index)
        if bar_hidden_context != current_bar_context:
            bar_hidden_context = current_bar_context
            bar_hidden_labels.clear()
            _destroy_bar_visibility_popup()

        series = build_aggregated_chart_series(
            snapshot,
            label_column_index,
            value_column_index=value_column_index,
            limit=None if selected_view == VIEW_BAR else DEFAULT_CHART_CATEGORY_LIMIT,
        )
        if series is None:
            _set_chart_x_scrollbar(False)
            _set_chart_y_scrollbar(False)
            chart_message_var.set("No chartable values are available for the selected columns.")
            _draw_empty_chart(chart_canvas, "No chartable values are available for the selected columns.")
            return

        if selected_view == VIEW_BAR:
            series = _slice_bar_chart_series(series, bar_range_var.get())
            hidden_bar_count = sum(1 for label in series.labels if label in bar_hidden_labels)
            visible_series = _filter_bar_chart_series(series, bar_hidden_labels)
            if not visible_series.labels:
                _set_chart_x_scrollbar(False)
                _set_chart_y_scrollbar(False)
                chart_message_var.set("All bars are hidden. Use Hide bars and choose Show all to restore them.")
                _draw_empty_chart(chart_canvas, "All bars are hidden. Use Hide bars and choose Show all to restore them.")
                return
            if bar_orientation_var.get() == BAR_ORIENTATION_HORIZONTAL:
                _set_chart_x_scrollbar(False)
                _set_chart_y_scrollbar(True)
            else:
                _set_chart_x_scrollbar(True)
                _set_chart_y_scrollbar(False)
            chart_message = _bar_chart_message(visible_series, bar_range_var.get())
            if hidden_bar_count:
                chart_message = f"{chart_message}\n{hidden_bar_count} hidden bar(s)."
            chart_message_var.set(chart_message)
            _draw_bar_chart(chart_canvas, visible_series, bar_orientation_var.get())
            return

        _set_chart_x_scrollbar(False)
        _set_chart_y_scrollbar(False)
        chart_message_var.set(f"{series.value_column_label} by {series.label_column_label}")
        if selected_view == VIEW_PIE:
            _draw_aggregated_pie_chart(chart_canvas, series)
            return
        _draw_bar_chart(chart_canvas, series, BAR_ORIENTATION_VERTICAL)

    def _update_view(*_args) -> None:
        _destroy_bar_visibility_popup()
        selected_output = output_var.get()
        if selected_output == VIEW_SUMMARY:
            _set_chart_x_scrollbar(False)
            _set_chart_y_scrollbar(False)
            label_box.configure(state="disabled")
            value_box.configure(state="disabled")
            bar_range_box.configure(state="disabled")
            bar_orientation_box.configure(state="disabled")
            histogram_bins_box.configure(state="disabled")
            bar_visibility_button.grid_remove()
            histogram_help_button.grid_remove()
            chart_frame.grid_forget()
            summary_frame.grid(row=0, column=0, sticky="nsew")
            return

        value_box.configure(state="readonly")
        if selected_output == VIEW_BAR:
            label_box.configure(state="readonly")
            bar_range_box.configure(state="readonly")
            bar_orientation_box.configure(state="readonly")
            histogram_bins_box.configure(state="disabled")
            bar_visibility_button.grid()
            histogram_help_button.grid_remove()
        elif selected_output == VIEW_HISTOGRAM:
            label_box.configure(state="disabled")
            bar_range_box.configure(state="disabled")
            bar_orientation_box.configure(state="disabled")
            histogram_bins_box.configure(state="readonly")
            bar_visibility_button.grid_remove()
            histogram_help_button.grid()
            if value_var.get() == COUNT_ROWS_LABEL and numeric_value_options:
                value_var.set(numeric_value_options[0])
        else:
            label_box.configure(state="readonly")
            bar_range_box.configure(state="disabled")
            bar_orientation_box.configure(state="disabled")
            histogram_bins_box.configure(state="disabled")
            bar_visibility_button.grid_remove()
            histogram_help_button.grid_remove()
        summary_frame.grid_forget()
        chart_frame.grid(row=0, column=0, sticky="nsew")
        _render_chart()

    def _on_chart_resize(_event) -> None:
        if output_var.get() != "Summary":
            _render_chart()

    output_box.bind("<<ComboboxSelected>>", _update_view, add="+")
    label_box.bind("<<ComboboxSelected>>", _update_view, add="+")
    value_box.bind("<<ComboboxSelected>>", _update_view, add="+")
    bar_range_box.bind("<<ComboboxSelected>>", _update_view, add="+")
    bar_orientation_box.bind("<<ComboboxSelected>>", _update_view, add="+")
    histogram_bins_box.bind("<<ComboboxSelected>>", _update_view, add="+")
    bar_visibility_button.configure(command=_open_bar_visibility_popup)
    histogram_help_button.configure(command=_open_histogram_help)
    chart_canvas.bind("<Configure>", _on_chart_resize, add="+")
    container.bind("<Destroy>", lambda _event: _destroy_bar_visibility_popup(), add="+")
    _update_view()

    if close_command is not None:
        button_row = ttk.Frame(container)
        button_row.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(button_row, text=close_button_text, command=close_command).pack(side="right")

    return container


def open_csv_preview_analysis_dialog_from_snapshot(
    parent: tk.Misc,
    snapshot: PreviewAnalysisSnapshot,
) -> tk.Toplevel:
    win = tk.Toplevel(parent)
    win.title(f"CSV Analysis - {snapshot.source_name}")
    win.geometry(f"{ANALYSIS_WINDOW_WIDTH}x{ANALYSIS_WINDOW_HEIGHT}")

    container = build_csv_preview_analysis_view(
        win,
        snapshot,
        close_command=win.destroy,
        close_button_text="Close",
        popup_parent=win,
    )
    container.pack(fill="both", expand=True)

    return win