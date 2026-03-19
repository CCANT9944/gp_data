from __future__ import annotations

from decimal import Decimal
import tkinter as tk
from tkinter import ttk

from .analysis import (
    DEFAULT_CHART_CATEGORY_LIMIT,
    PreviewAggregatedChartSeries,
    PreviewAnalysisSnapshot,
    build_aggregated_chart_series,
    build_preview_analysis_snapshot,
    format_decimal_summary,
    format_value_counts_summary,
    preferred_chart_label_column,
    preferred_chart_value_column,
)
from .helpers import _compact_filter_popup_label
from .loader import CsvPreviewData


ANALYSIS_WINDOW_WIDTH = 980
ANALYSIS_WINDOW_HEIGHT = 680
VIEW_SUMMARY = "Summary"
VIEW_BAR = "Bar chart"
VIEW_PIE = "Pie chart"
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
    canvas.create_text(
        width / 2,
        height / 2,
        text=message,
        fill="#6b7280",
        width=max(width - 80, 240),
        justify="center",
        font=("Segoe UI", 11),
    )


def _draw_bar_chart(canvas: tk.Canvas, series: PreviewAggregatedChartSeries) -> None:
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


def open_csv_preview_analysis_dialog_from_snapshot(
    parent: tk.Misc,
    snapshot: PreviewAnalysisSnapshot,
) -> tk.Toplevel:
    win = tk.Toplevel(parent)
    win.title(f"CSV Analysis - {snapshot.source_name}")
    win.geometry(f"{ANALYSIS_WINDOW_WIDTH}x{ANALYSIS_WINDOW_HEIGHT}")

    container = ttk.Frame(win, padding=8)
    container.pack(fill="both", expand=True)
    container.columnconfigure(0, weight=1)
    container.rowconfigure(2, weight=1)

    subtitle_var = tk.StringVar(value=_analysis_subtitle(snapshot))
    ttk.Label(container, textvariable=subtitle_var, anchor="w").grid(row=0, column=0, sticky="ew", pady=(0, 8))

    control_row = ttk.Frame(container)
    control_row.grid(row=1, column=0, sticky="ew", pady=(0, 8))

    output_var = tk.StringVar(value=VIEW_SUMMARY)
    ttk.Label(control_row, text="View").pack(side="left")
    output_box = ttk.Combobox(control_row, textvariable=output_var, state="readonly", width=16)
    output_box["values"] = (VIEW_SUMMARY, VIEW_BAR, VIEW_PIE)
    output_box.pack(side="left", padx=(6, 12))

    label_var = tk.StringVar()
    ttk.Label(control_row, text="Label").pack(side="left")
    label_box = ttk.Combobox(control_row, textvariable=label_var, state="readonly", width=28)
    label_options = [column.label for column in snapshot.columns]
    label_box["values"] = label_options
    if label_options:
        preferred_label = preferred_chart_label_column(snapshot)
        label_var.set(preferred_label.label if preferred_label is not None else label_options[0])
    label_box.pack(side="left", padx=(6, 12))

    value_var = tk.StringVar()
    ttk.Label(control_row, text="Value").pack(side="left")
    value_box = ttk.Combobox(control_row, textvariable=value_var, state="readonly", width=22)
    numeric_value_options = [column.label for column in snapshot.columns if column.numeric]
    value_options = [COUNT_ROWS_LABEL] + numeric_value_options
    value_box["values"] = value_options
    preferred_value = preferred_chart_value_column(snapshot)
    value_var.set(preferred_value.label if preferred_value is not None else COUNT_ROWS_LABEL)
    value_box.pack(side="left", padx=(6, 0))

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
    ttk.Label(chart_frame, textvariable=chart_message_var, anchor="w", justify="left").grid(
        row=0, column=0, sticky="ew", pady=(0, 8)
    )
    chart_x_scroll = ttk.Scrollbar(chart_frame, orient="horizontal")
    chart_canvas = tk.Canvas(chart_frame, background="white", highlightthickness=0)
    chart_canvas.configure(xscrollcommand=chart_x_scroll.set)
    chart_x_scroll.configure(command=chart_canvas.xview)
    chart_canvas.grid(row=1, column=0, sticky="nsew")
    chart_x_scroll.grid(row=2, column=0, sticky="ew")

    column_label_to_index = {column.label: column.index for column in snapshot.columns}

    def _selected_label_column_index() -> int | None:
        return column_label_to_index.get(label_var.get())

    def _selected_value_column_index() -> int | None:
        selected_label = value_var.get()
        if not selected_label or selected_label == COUNT_ROWS_LABEL:
            return None
        return column_label_to_index.get(selected_label)

    def _set_chart_x_scrollbar(enabled: bool) -> None:
        if enabled:
            chart_x_scroll.grid()
        else:
            chart_x_scroll.grid_remove()
            chart_canvas.xview_moveto(0)

    def _render_chart() -> None:
        label_column_index = _selected_label_column_index()
        if label_column_index is None:
            _set_chart_x_scrollbar(False)
            chart_message_var.set("Choose a visible label column to render a chart.")
            _draw_empty_chart(chart_canvas, "Choose a visible label column to render a chart.")
            return

        selected_view = output_var.get()
        value_column_index = _selected_value_column_index()
        series = build_aggregated_chart_series(
            snapshot,
            label_column_index,
            value_column_index=value_column_index,
            limit=None if selected_view == VIEW_BAR else DEFAULT_CHART_CATEGORY_LIMIT,
        )
        if series is None:
            _set_chart_x_scrollbar(False)
            chart_message_var.set("No chartable values are available for the selected columns.")
            _draw_empty_chart(chart_canvas, "No chartable values are available for the selected columns.")
            return

        if selected_view == VIEW_BAR:
            _set_chart_x_scrollbar(True)
            chart_message_var.set(f"{series.value_column_label} by {series.label_column_label} (highest to lowest)")
            _draw_bar_chart(chart_canvas, series)
            return

        _set_chart_x_scrollbar(False)
        chart_message_var.set(f"{series.value_column_label} by {series.label_column_label}")
        if selected_view == VIEW_PIE:
            _draw_aggregated_pie_chart(chart_canvas, series)
            return
        _draw_bar_chart(chart_canvas, series)

    def _update_view(*_args) -> None:
        selected_output = output_var.get()
        if selected_output == VIEW_SUMMARY:
            _set_chart_x_scrollbar(False)
            label_box.configure(state="disabled")
            value_box.configure(state="disabled")
            chart_frame.grid_forget()
            summary_frame.grid(row=0, column=0, sticky="nsew")
            return

        label_box.configure(state="readonly")
        value_box.configure(state="readonly")
        summary_frame.grid_forget()
        chart_frame.grid(row=0, column=0, sticky="nsew")
        _render_chart()

    def _on_chart_resize(_event) -> None:
        if output_var.get() != "Summary":
            _render_chart()

    output_box.bind("<<ComboboxSelected>>", _update_view, add="+")
    label_box.bind("<<ComboboxSelected>>", _update_view, add="+")
    value_box.bind("<<ComboboxSelected>>", _update_view, add="+")
    chart_canvas.bind("<Configure>", _on_chart_resize, add="+")
    _update_view()

    button_row = ttk.Frame(container)
    button_row.grid(row=3, column=0, sticky="ew", pady=(8, 0))
    ttk.Button(button_row, text="Close", command=win.destroy).pack(side="right")

    return win