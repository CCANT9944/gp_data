from decimal import Decimal
from pathlib import Path

from gp_data.ui.csv_preview.analysis import (
    build_aggregated_chart_series,
    build_category_chart_series,
    build_numeric_bar_chart_series,
    build_preview_analysis_snapshot,
    format_value_counts_summary,
)
from gp_data.ui.csv_preview.loader import CsvPreviewData


def _analysis_data(headers: list[str]) -> CsvPreviewData:
    return CsvPreviewData(
        path=Path("analysis.csv"),
        encoding="utf-8",
        headers=headers,
        rows=[],
        row_total=0,
        fully_cached=True,
    )


def test_build_preview_analysis_snapshot_calculates_numeric_summary() -> None:
    data = _analysis_data(["Item", "Quantity", "Category"])
    snapshot = build_preview_analysis_snapshot(
        data,
        [
            ("Aperol", "10", "Spritz"),
            ("Negroni", "20", "Cocktail"),
            ("Campari", "", "Bitters"),
        ],
        [0, 1, 2],
        {1},
        filtering_active=True,
        combine_sessions=False,
    )

    quantity_column = snapshot.column(1)
    assert quantity_column is not None
    assert quantity_column.numeric is True
    assert quantity_column.non_empty_count == 2
    assert quantity_column.distinct_count == 2
    assert quantity_column.numeric_summary is not None
    assert quantity_column.numeric_summary.minimum == Decimal("10")
    assert quantity_column.numeric_summary.maximum == Decimal("20")
    assert quantity_column.numeric_summary.total == Decimal("30")
    assert quantity_column.numeric_summary.average == Decimal("15")


def test_build_preview_analysis_snapshot_treats_missing_cells_as_blank() -> None:
    data = _analysis_data(["Item", "Category", "Quantity"])
    snapshot = build_preview_analysis_snapshot(
        data,
        [
            ("Aperol", "Spritz", "10"),
            ("Negroni", "Cocktail"),
        ],
        [0, 1, 2],
        {2},
        filtering_active=True,
        combine_sessions=False,
    )

    quantity_column = snapshot.column(2)
    assert quantity_column is not None
    assert quantity_column.row_count == 2
    assert quantity_column.non_empty_count == 1
    assert quantity_column.blank_count == 1
    assert quantity_column.distinct_count == 1
    assert quantity_column.numeric_summary is not None
    assert quantity_column.numeric_summary.total == Decimal("10")


def test_build_category_chart_series_groups_other_bucket() -> None:
    data = _analysis_data(["Category"])
    snapshot = build_preview_analysis_snapshot(
        data,
        [(value,) for value in ["Beer", "Beer", "Wine", "Wine", "Spritz", "Gin", "Rum", "Vodka", "Whisky", "Tequila"]],
        [0],
        set(),
        filtering_active=True,
        combine_sessions=False,
    )

    series = build_category_chart_series(snapshot, 0, limit=5)

    assert series is not None
    assert series.labels[-1] == "Other"
    assert sum(series.values) == 10
    assert len(series.labels) == 5


def test_build_category_chart_series_disambiguates_existing_other_label() -> None:
    data = _analysis_data(["Category"])
    snapshot = build_preview_analysis_snapshot(
        data,
        [(value,) for value in ["Other", "Other", "Other", "Wine", "Wine", "Beer", "Beer", "Gin", "Rum"]],
        [0],
        set(),
        filtering_active=True,
        combine_sessions=False,
    )

    series = build_category_chart_series(snapshot, 0, limit=4)

    assert series is not None
    assert series.labels.count("Other") == 1
    assert any(label.startswith("Other (grouped") for label in series.labels)


def test_build_numeric_bar_chart_series_uses_description_and_quantity_high_to_low() -> None:
    data = _analysis_data(["Description1", "Quantity1", "ClassName1"])
    snapshot = build_preview_analysis_snapshot(
        data,
        [
            ("Peroni", "4", "Beer"),
            ("Negroni", "9", "Cocktails"),
            ("Spritz", "6", "Spritz"),
            ("Negroni", "1", "Cocktails"),
        ],
        [0, 1, 2],
        {1},
        filtering_active=True,
        combine_sessions=False,
    )

    series = build_numeric_bar_chart_series(snapshot, 1, limit=3)

    assert series is not None
    assert series.label_column_label == "1: Description1"
    assert series.value_column_label == "2: Quantity1"
    assert series.labels == ["Negroni", "Spritz", "Peroni"]
    assert series.values == [Decimal("10"), Decimal("6"), Decimal("4")]


def test_build_aggregated_chart_series_uses_selected_label_and_value_columns() -> None:
    data = _analysis_data(["Description1", "ClassName1", "Quantity1"])
    snapshot = build_preview_analysis_snapshot(
        data,
        [
            ("Spritzer", "Spritz", "12"),
            ("Negroni", "Cocktails", "10"),
            ("Spritzer", "Spritz", "3"),
            ("Peroni", "Beer", "4"),
        ],
        [0, 1, 2],
        {2},
        filtering_active=True,
        combine_sessions=False,
    )

    series = build_aggregated_chart_series(snapshot, 0, value_column_index=2, limit=4)

    assert series is not None
    assert series.label_column_label == "1: Description1"
    assert series.value_column_label == "3: Quantity1"
    assert series.labels == ["Spritzer", "Negroni", "Peroni"]
    assert series.values == [Decimal("15"), Decimal("10"), Decimal("4")]


def test_build_aggregated_chart_series_with_no_limit_keeps_all_labels() -> None:
    data = _analysis_data(["Description1", "Quantity1"])
    snapshot = build_preview_analysis_snapshot(
        data,
        [(f"Cocktail {index}", str(index)) for index in range(1, 15)],
        [0, 1],
        {1},
        filtering_active=True,
        combine_sessions=False,
    )

    series = build_aggregated_chart_series(snapshot, 0, value_column_index=1, limit=None)

    assert series is not None
    assert len(series.labels) == 14
    assert "Other" not in series.labels


def test_build_aggregated_chart_series_disambiguates_existing_other_label() -> None:
    data = _analysis_data(["Description1", "Quantity1"])
    snapshot = build_preview_analysis_snapshot(
        data,
        [
            ("Other", "8"),
            ("Wine", "6"),
            ("Beer", "4"),
            ("Gin", "2"),
            ("Rum", "1"),
        ],
        [0, 1],
        {1},
        filtering_active=True,
        combine_sessions=False,
    )

    series = build_aggregated_chart_series(snapshot, 0, value_column_index=1, limit=4)

    assert series is not None
    assert series.labels.count("Other") == 1
    assert any(label.startswith("Other (grouped") for label in series.labels)


def test_format_value_counts_summary_limits_entries() -> None:
    data = _analysis_data(["Category"])
    snapshot = build_preview_analysis_snapshot(
        data,
        [(value,) for value in ["Beer", "Beer", "Wine", "Spritz"]],
        [0],
        set(),
        filtering_active=False,
        combine_sessions=False,
    )

    category_column = snapshot.column(0)
    assert category_column is not None

    assert format_value_counts_summary(category_column.value_counts, limit=2) == "Beer (2), Spritz (1)"