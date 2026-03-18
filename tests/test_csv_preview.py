import tkinter as tk
import time
from tkinter import ttk

import pytest

from gp_data import settings
import gp_data.ui.csv_preview.dialog as dialog_module
import gp_data.ui.csv_preview.loader as loader_module
from gp_data.ui.csv_preview import CsvPreviewError, load_csv_preview, open_csv_preview_dialog
from gp_data.ui.csv_preview.dialog import (
    HEADER_FILTER_POPUP_LABEL_MAX_LENGTH,
    HEADER_FILTER_POPUP_LIST_HEIGHT,
    MAX_RENDERED_PREVIEW_ROWS,
    _compact_filter_popup_label,
    _detect_numeric_columns,
    _detect_session_column,
)
from gp_data.ui.csv_preview.loader import PREVIEW_ROW_SAMPLE_SIZE, resolve_csv_preview_metadata


def _find_descendant(root: tk.Misc, cls):
    for widget in root.winfo_children():
        if isinstance(widget, cls):
            return widget
        found = _find_descendant(widget, cls)
        if found is not None:
            return found
    return None


def _find_button(root: tk.Misc, text: str):
    for widget in root.winfo_children():
        if isinstance(widget, ttk.Button) and str(widget.cget("text")) == text:
            return widget
        found = _find_button(widget, text)
        if found is not None:
            return found
    return None


def _find_widgets(root: tk.Misc, cls):
    found = []
    for widget in root.winfo_children():
        if isinstance(widget, cls):
            found.append(widget)
        found.extend(_find_widgets(widget, cls))
    return found


def _listbox_values(listbox: tk.Listbox) -> list[str]:
    return [str(listbox.get(index)) for index in range(listbox.size())]


def _find_label_with_text(root: tk.Misc, expected_text: str):
    for widget in root.winfo_children():
        if isinstance(widget, ttk.Label):
            try:
                if expected_text in str(widget.cget("text")):
                    return widget
            except tk.TclError:
                pass
        found = _find_label_with_text(widget, expected_text)
        if found is not None:
            return found
    return None


def _wait_for_rows(window: tk.Misc, tree: ttk.Treeview, expected_count: int) -> None:
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        window.update()
        if len(tree.get_children()) == expected_count:
            return
        time.sleep(0.02)
    assert len(tree.get_children()) == expected_count


def _wait_for_columns(window: tk.Misc, tree: ttk.Treeview, expected_count: int) -> None:
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        window.update()
        if len(tree.cget("columns")) == expected_count:
            return
        time.sleep(0.02)
    assert len(tree.cget("columns")) == expected_count


def test_load_csv_preview_preserves_all_columns_and_rows(tmp_path):
    csv_path = tmp_path / "wide.csv"
    headers = [f"Col {index}" for index in range(1, 21)]
    rows = [
        [f"r1c{index}" for index in range(1, 21)],
        [f"r2c{index}" for index in range(1, 21)],
        [f"r3c{index}" for index in range(1, 21)],
    ]
    csv_path.write_text(
        "\n".join([",".join(headers)] + [",".join(row) for row in rows]) + "\n",
        encoding="utf-8",
    )

    data = load_csv_preview(csv_path)

    assert data.headers == headers
    assert data.column_count == 20
    assert data.row_count == 3
    assert data.rows[0][0] == "r1c1"
    assert data.rows[-1][-1] == "r3c20"


def test_load_csv_preview_rejects_empty_file(tmp_path):
    csv_path = tmp_path / "empty.csv"
    csv_path.write_text("", encoding="utf-8")

    with pytest.raises(CsvPreviewError, match="empty"):
        load_csv_preview(csv_path)


def test_open_csv_preview_dialog_shows_all_columns_and_rows(tk_root, tmp_path):
    csv_path = tmp_path / "wide.csv"
    headers = [f"Col {index}" for index in range(1, 21)]
    rows = [
        [f"row{row_index}_col{column_index}" for column_index in range(1, 21)]
        for row_index in range(1, 4)
    ]
    csv_path.write_text(
        "\n".join([",".join(headers)] + [",".join(row) for row in rows]) + "\n",
        encoding="utf-8",
    )

    dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    tree = _find_descendant(dialog, ttk.Treeview)

    assert tree is not None
    assert len(tree.cget("columns")) == 20
    assert [tree.heading(column_id)["text"] for column_id in tree.cget("columns")] == headers
    _wait_for_rows(dialog, tree, 3)
    assert len(tree.get_children()) == 3
    assert tree.item(tree.get_children()[0])["values"][0] == "row1_col1"
    assert tree.item(tree.get_children()[-1])["values"][-1] == "row3_col20"

    dialog.destroy()


def test_load_csv_preview_reuses_cached_data_for_unchanged_file(tmp_path):
    csv_path = tmp_path / "wide.csv"
    csv_path.write_text("A,B\n1,2\n", encoding="utf-8")

    first = load_csv_preview(csv_path)
    second = load_csv_preview(csv_path)

    assert first is second


def test_load_large_csv_preview_keeps_only_preview_rows_in_memory(tmp_path):
    csv_path = tmp_path / "large.csv"
    rows = [f"Item {index},Lunch,{index}" for index in range(1, PREVIEW_ROW_SAMPLE_SIZE + 1501)]
    csv_path.write_text(
        "Description1,Sessionname1,Quantity1\n" + "\n".join(rows) + "\n",
        encoding="utf-8",
    )

    data = load_csv_preview(csv_path)

    assert data.row_count is None
    assert len(data.rows) == PREVIEW_ROW_SAMPLE_SIZE
    assert data.fully_cached is False


def test_resolve_csv_preview_metadata_expands_late_wide_rows(tmp_path):
    csv_path = tmp_path / "late_wide.csv"
    rows = ["A,B"]
    rows.extend("x,y" for _ in range(PREVIEW_ROW_SAMPLE_SIZE))
    rows.append("late,wide,extra")
    csv_path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    data = load_csv_preview(csv_path)
    resolved = resolve_csv_preview_metadata(data)

    assert data.column_count == 2
    assert resolved.column_count == 3
    assert resolved.row_count == PREVIEW_ROW_SAMPLE_SIZE + 1
    assert resolved.headers == ["A", "B", "Column 3"]


def test_load_large_csv_preview_reuses_sidecar_metadata_on_reopen(tmp_path):
    csv_path = tmp_path / "late_wide.csv"
    rows = ["A,B"]
    rows.extend("x,y" for _ in range(PREVIEW_ROW_SAMPLE_SIZE))
    rows.append("late,wide,extra")
    csv_path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    data = load_csv_preview(csv_path)
    resolved = resolve_csv_preview_metadata(data)

    loader_module._PREVIEW_CACHE.clear()
    reopened = load_csv_preview(csv_path)

    assert loader_module._metadata_sidecar_path(csv_path).exists()
    assert reopened is not resolved
    assert reopened.column_count == 3
    assert reopened.headers == ["A", "B", "Column 3"]
    assert reopened.row_count == PREVIEW_ROW_SAMPLE_SIZE + 1
    assert len(reopened.rows) == PREVIEW_ROW_SAMPLE_SIZE
    assert reopened.fully_cached is False


def test_load_large_csv_preview_ignores_stale_sidecar_metadata_after_file_change(tmp_path):
    csv_path = tmp_path / "late_wide.csv"
    original_rows = ["A,B"]
    original_rows.extend("x,y" for _ in range(PREVIEW_ROW_SAMPLE_SIZE))
    original_rows.append("late,wide,extra")
    csv_path.write_text("\n".join(original_rows) + "\n", encoding="utf-8")

    data = load_csv_preview(csv_path)
    resolve_csv_preview_metadata(data)
    loader_module._PREVIEW_CACHE.clear()

    updated_rows = ["A,B"]
    updated_rows.extend("x,y" for _ in range(PREVIEW_ROW_SAMPLE_SIZE + 10))
    csv_path.write_text("\n".join(updated_rows) + "\n", encoding="utf-8")

    reopened = load_csv_preview(csv_path)

    assert reopened.column_count == 2
    assert reopened.headers == ["A", "B"]
    assert reopened.row_count is None
    assert reopened.fully_cached is False


def test_detect_numeric_columns_tolerates_single_summary_outlier_in_large_sample(tmp_path):
    csv_path = tmp_path / "numeric_textboxes.csv"
    rows = [f"Item {index},Lunch,{index},6,{index * 10}.25" for index in range(1, 121)]
    rows.append("Summary row,Dinner,1,7,TOTAL SALES??")
    csv_path.write_text(
        "Description1,Sessionname1,Quantity1,Textbox73,Textbox79\n" + "\n".join(rows) + "\n",
        encoding="utf-8",
    )

    data = load_csv_preview(csv_path)
    numeric_columns = _detect_numeric_columns(data, {_detect_session_column(data.headers)})

    assert numeric_columns == {2, 3, 4}


def test_open_csv_preview_dialog_combines_sessions_when_numeric_export_values_appear_after_preview_sample(tk_root, tmp_path):
    csv_path = tmp_path / "late_numeric.csv"
    rows = ["Description1,Sessionname1,Quantity1,Textbox73"]
    rows.extend(f"Item {index},Lunch,{index}," for index in range(PREVIEW_ROW_SAMPLE_SIZE))
    rows.append("Target,Lunch,2,5")
    rows.append("Target,Dinner,3,7")
    csv_path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    tree = _find_descendant(dialog, ttk.Treeview)
    combine_toggle = _find_descendant(dialog, ttk.Checkbutton)
    query_entry = _find_descendant(dialog, ttk.Entry)

    assert tree is not None
    assert combine_toggle is not None
    assert query_entry is not None

    query_entry.insert(0, "target")
    _wait_for_rows(dialog, tree, 2)
    combine_toggle.invoke()
    _wait_for_rows(dialog, tree, 1)

    first_row = tree.get_children()[0]
    assert tree.item(first_row)["values"] == ["Target", "Lunch + Dinner", 5, 12]

    dialog.destroy()


def test_open_csv_preview_dialog_filters_rows_by_search_text(tk_root, tmp_path):
    csv_path = tmp_path / "searchable.csv"
    csv_path.write_text(
        "Name,Category,Origin\nBerry Gin,Spirit,UK\nLemon Soda,Mixer,US\nDark Rum,Spirit,Jamaica\n",
        encoding="utf-8",
    )

    dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    tree = _find_descendant(dialog, ttk.Treeview)
    query_entry = _find_descendant(dialog, ttk.Entry)

    assert tree is not None
    assert query_entry is not None

    _wait_for_rows(dialog, tree, 3)
    query_entry.insert(0, "mixer")
    _wait_for_rows(dialog, tree, 1)

    first_row = tree.get_children()[0]
    assert tree.item(first_row)["values"] == ["Lemon Soda", "Mixer", "US"]

    dialog.destroy()


def test_open_csv_preview_dialog_can_combine_sessions_for_same_product(tk_root, tmp_path):
    csv_path = tmp_path / "sessions.csv"
    csv_path.write_text(
        "Description1,PluCode,Sessionname1,Revenue1,Quantity1\nCuban,101,Lunch,12.5,2\nCuban,101,Dinner,18.5,3\nFrench 75,202,Lunch,20,4\n",
        encoding="utf-8",
    )

    dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    tree = _find_descendant(dialog, ttk.Treeview)
    combine_toggle = _find_descendant(dialog, ttk.Checkbutton)

    assert tree is not None
    assert combine_toggle is not None

    _wait_for_rows(dialog, tree, 3)
    combine_toggle.invoke()
    _wait_for_rows(dialog, tree, 2)

    first_row = tree.get_children()[0]
    assert tree.item(first_row)["values"] == ["Cuban", 101, "Lunch + Dinner", 31, 5]

    dialog.destroy()


def test_open_csv_preview_dialog_reuses_cached_combined_rows_for_follow_up_filters(tk_root, tmp_path, monkeypatch):
    csv_path = tmp_path / "combined_cache.csv"
    csv_path.write_text(
        "Description1,Sessionname1,Quantity1\nTarget,Lunch,2\nTarget,Dinner,3\n",
        encoding="utf-8",
    )

    dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    tree = _find_descendant(dialog, ttk.Treeview)
    combine_toggle = _find_descendant(dialog, ttk.Checkbutton)
    query_entry = _find_descendant(dialog, ttk.Entry)
    controller = getattr(dialog, "_csv_preview_controller", None)

    assert tree is not None
    assert combine_toggle is not None
    assert query_entry is not None
    assert controller is not None

    original_iter_combined_rows = dialog_module._iter_combined_rows
    combined_calls = 0

    def counting_iter_combined_rows(data, enabled):
        nonlocal combined_calls
        combined_calls += 1
        yield from original_iter_combined_rows(data, enabled)

    monkeypatch.setattr(dialog_module, "_iter_combined_rows", counting_iter_combined_rows)

    combine_toggle.invoke()
    _wait_for_rows(dialog, tree, 1)
    assert combined_calls == 1

    query_entry.insert(0, "target")
    controller.refresh()
    _wait_for_rows(dialog, tree, 1)
    assert combined_calls == 1

    controller.set_header_filter(0, "Target")
    _wait_for_rows(dialog, tree, 1)
    assert combined_calls == 1

    dialog.destroy()


def test_open_csv_preview_dialog_runs_search_refresh_off_ui_thread(tk_root, tmp_path, monkeypatch):
    csv_path = tmp_path / "search_async.csv"
    csv_path.write_text(
        "Name,Category\nPeroni,Beer\nNegroni,Cocktails\n",
        encoding="utf-8",
    )

    dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    tree = _find_descendant(dialog, ttk.Treeview)
    controller = getattr(dialog, "_csv_preview_controller", None)

    assert tree is not None
    assert controller is not None

    original_iter_rows_before_header_filter = dialog_module._iter_rows_before_header_filter

    def slow_iter_rows_before_header_filter(*args, **kwargs):
        time.sleep(0.35)
        yield from original_iter_rows_before_header_filter(*args, **kwargs)

    monkeypatch.setattr(dialog_module, "_iter_rows_before_header_filter", slow_iter_rows_before_header_filter)

    controller._query_var.set("beer")
    if controller._scheduled_refresh_id is not None:
        dialog.after_cancel(controller._scheduled_refresh_id)
        controller._scheduled_refresh_id = None

    started = time.monotonic()
    controller.refresh()
    elapsed = time.monotonic() - started

    assert elapsed < 0.2
    assert controller._summary_var.get().startswith("search_async.csv | Loading matching rows")

    _wait_for_rows(dialog, tree, 1)
    assert tree.item(tree.get_children()[0])["values"] == ["Peroni", "Beer"]

    dialog.destroy()


def test_open_csv_preview_dialog_combines_sessions_with_numeric_textbox_columns(tk_root, tmp_path):
    csv_path = tmp_path / "sessions_with_textboxes.csv"
    csv_path.write_text(
        "Description1,Sessionname1,Quantity1,Textbox73,Textbox79\n"
        "Pornstar Martini,Lunch,302,6,\n"
        "Pornstar Martini,Dinner,947,6,56.25\n",
        encoding="utf-8",
    )

    dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    tree = _find_descendant(dialog, ttk.Treeview)
    combine_toggle = _find_descendant(dialog, ttk.Checkbutton)

    assert tree is not None
    assert combine_toggle is not None

    _wait_for_rows(dialog, tree, 2)
    combine_toggle.invoke()
    _wait_for_rows(dialog, tree, 1)

    first_row = tree.get_children()[0]
    assert tree.item(first_row)["values"] == ["Pornstar Martini", "Lunch + Dinner", 1249, 12, "56.25"]

    dialog.destroy()


def test_open_csv_preview_dialog_runs_combine_refresh_off_ui_thread(tk_root, tmp_path, monkeypatch):
    csv_path = tmp_path / "combine_async.csv"
    csv_path.write_text(
        "Description1,Sessionname1,Quantity1\nTarget,Lunch,2\nTarget,Dinner,3\n",
        encoding="utf-8",
    )

    dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    tree = _find_descendant(dialog, ttk.Treeview)
    combine_toggle = _find_descendant(dialog, ttk.Checkbutton)
    controller = getattr(dialog, "_csv_preview_controller", None)

    assert tree is not None
    assert combine_toggle is not None
    assert controller is not None

    original_iter_combined_rows = dialog_module._iter_combined_rows

    def slow_iter_combined_rows(*args, **kwargs):
        time.sleep(0.35)
        yield from original_iter_combined_rows(*args, **kwargs)

    monkeypatch.setattr(dialog_module, "_iter_combined_rows", slow_iter_combined_rows)

    started = time.monotonic()
    combine_toggle.invoke()
    elapsed = time.monotonic() - started

    assert elapsed < 0.2
    assert controller._summary_var.get().startswith("combine_async.csv | Loading matching rows")

    _wait_for_rows(dialog, tree, 1)
    assert tree.item(tree.get_children()[0])["values"] == ["Target", "Lunch + Dinner", 5]

    dialog.destroy()


def test_open_csv_preview_dialog_limits_rendered_rows_for_large_files(tk_root, tmp_path):
    csv_path = tmp_path / "large.csv"
    rows = [f"Item {index},Lunch,{index}" for index in range(1, MAX_RENDERED_PREVIEW_ROWS + 1501)]
    csv_path.write_text(
        "Description1,Sessionname1,Quantity1\n" + "\n".join(rows) + "\n",
        encoding="utf-8",
    )

    dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    tree = _find_descendant(dialog, ttk.Treeview)

    assert tree is not None

    _wait_for_rows(dialog, tree, MAX_RENDERED_PREVIEW_ROWS)
    assert len(tree.get_children()) == MAX_RENDERED_PREVIEW_ROWS
    summary = _find_label_with_text(dialog, "preview rows") or _find_label_with_text(dialog, "Showing first")
    assert summary is not None

    dialog.destroy()


def test_open_csv_preview_dialog_expands_columns_when_late_wider_rows_are_found(tk_root, tmp_path):
    csv_path = tmp_path / "late_wide.csv"
    rows = ["A,B"]
    rows.extend("x,y" for _ in range(PREVIEW_ROW_SAMPLE_SIZE))
    rows.append("late,wide,extra")
    csv_path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    tree = _find_descendant(dialog, ttk.Treeview)

    assert tree is not None

    _wait_for_columns(dialog, tree, 3)
    assert [tree.heading(column_id)["text"] for column_id in tree.cget("columns")] == ["A", "B", "Column 3"]

    dialog.destroy()


def test_open_csv_preview_dialog_can_hide_unselected_columns(tk_root, tmp_path):
    csv_path = tmp_path / "columns.csv"
    csv_path.write_text(
        "Name,Session,Quantity\nPeroni,Lunch,2\nPeroni,Dinner,3\n",
        encoding="utf-8",
    )

    dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    columns_button = _find_button(dialog, "Columns")

    assert columns_button is not None

    columns_button.invoke()
    dialog.update()
    chooser = dialog.winfo_children()[-1]
    checkbuttons = _find_widgets(chooser, ttk.Checkbutton)
    apply_button = _find_button(chooser, "Apply")
    tree = _find_descendant(dialog, ttk.Treeview)

    assert len(checkbuttons) == 3
    assert apply_button is not None
    assert tree is not None

    checkbuttons[1].invoke()
    apply_button.invoke()
    dialog.update()

    assert list(tree.cget("displaycolumns")) == ["col_0", "col_2"]

    dialog.destroy()


def test_open_csv_preview_dialog_restores_saved_visible_columns_on_reopen(tk_root, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DEFAULT_PATH", tmp_path / "settings.json")
    csv_path = tmp_path / "columns.csv"
    csv_path.write_text(
        "Name,Session,Quantity\nPeroni,Lunch,2\nPeroni,Dinner,3\n",
        encoding="utf-8",
    )

    first_dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    first_columns_button = _find_button(first_dialog, "Columns")

    assert first_columns_button is not None

    first_columns_button.invoke()
    first_dialog.update()
    chooser = first_dialog.winfo_children()[-1]
    checkbuttons = _find_widgets(chooser, ttk.Checkbutton)
    apply_button = _find_button(chooser, "Apply")

    assert apply_button is not None

    checkbuttons[1].invoke()
    apply_button.invoke()
    first_dialog.update()
    first_dialog.destroy()

    second_dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    tree = _find_descendant(second_dialog, ttk.Treeview)

    assert tree is not None
    assert list(tree.cget("displaycolumns")) == ["col_0", "col_2"]

    second_dialog.destroy()


def test_open_csv_preview_dialog_restores_visible_columns_by_header_when_same_path_is_reordered(tk_root, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DEFAULT_PATH", tmp_path / "settings.json")
    csv_path = tmp_path / "columns.csv"
    csv_path.write_text(
        "Name,Session,Quantity\nPeroni,Lunch,2\nPeroni,Dinner,3\n",
        encoding="utf-8",
    )

    first_dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    first_columns_button = _find_button(first_dialog, "Columns")

    assert first_columns_button is not None

    first_columns_button.invoke()
    first_dialog.update()
    chooser = first_dialog.winfo_children()[-1]
    checkbuttons = _find_widgets(chooser, ttk.Checkbutton)
    apply_button = _find_button(chooser, "Apply")

    assert apply_button is not None

    checkbuttons[0].invoke()
    apply_button.invoke()
    first_dialog.update()
    first_dialog.destroy()

    csv_path.write_text(
        "Quantity,Session,Name\n2,Lunch,Peroni\n3,Dinner,Peroni\n",
        encoding="utf-8",
    )

    second_dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    tree = _find_descendant(second_dialog, ttk.Treeview)

    assert tree is not None
    assert list(tree.cget("displaycolumns")) == ["col_0", "col_1"]

    second_dialog.destroy()


def test_open_csv_preview_dialog_restores_visible_duplicate_headers_by_occurrence(tk_root, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DEFAULT_PATH", tmp_path / "settings.json")
    csv_path = tmp_path / "duplicate_columns.csv"
    csv_path.write_text(
        "Name,Value,Value\nPeroni,10,20\n",
        encoding="utf-8",
    )

    first_dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    first_columns_button = _find_button(first_dialog, "Columns")

    assert first_columns_button is not None

    first_columns_button.invoke()
    first_dialog.update()
    chooser = first_dialog.winfo_children()[-1]
    checkbuttons = _find_widgets(chooser, ttk.Checkbutton)
    apply_button = _find_button(chooser, "Apply")

    assert apply_button is not None

    checkbuttons[1].invoke()
    apply_button.invoke()
    first_dialog.update()
    first_dialog.destroy()

    csv_path.write_text(
        "Name,Value,Extra,Value\nPeroni,10,X,20\n",
        encoding="utf-8",
    )

    second_dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    tree = _find_descendant(second_dialog, ttk.Treeview)

    assert tree is not None
    assert list(tree.cget("displaycolumns")) == ["col_0", "col_3"]

    second_dialog.destroy()


def test_open_csv_preview_dialog_restores_legacy_visible_column_indices_when_no_keys_are_saved(tk_root, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DEFAULT_PATH", tmp_path / "settings.json")
    csv_path = tmp_path / "columns.csv"
    csv_path.write_text(
        "Name,Session,Quantity\nPeroni,Lunch,2\nPeroni,Dinner,3\n",
        encoding="utf-8",
    )
    settings.save_csv_preview_visible_columns(str(csv_path), [0, 2], tmp_path / "settings.json")

    dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    tree = _find_descendant(dialog, ttk.Treeview)

    assert tree is not None
    assert list(tree.cget("displaycolumns")) == ["col_0", "col_2"]

    dialog.destroy()


def test_open_csv_preview_dialog_can_filter_by_clicked_column_value(tk_root, tmp_path):
    csv_path = tmp_path / "classname.csv"
    csv_path.write_text(
        "SiteName1,ClassName1,Description1\nWaterfront,Cocktails,Espresso Martini\nWaterfront,Beer,Peroni\nWaterfront,Cocktails,Negroni\n",
        encoding="utf-8",
    )

    dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    tree = _find_descendant(dialog, ttk.Treeview)
    controller = getattr(dialog, "_csv_preview_controller", None)

    assert tree is not None
    assert controller is not None

    _wait_for_rows(dialog, tree, 3)
    controller.set_header_filter(1, "Cocktails")
    _wait_for_rows(dialog, tree, 2)

    values = [tree.item(item_id)["values"] for item_id in tree.get_children()]
    assert values == [
        ["Waterfront", "Cocktails", "Espresso Martini"],
        ["Waterfront", "Cocktails", "Negroni"],
    ]

    controller.set_header_filter(None, None)
    _wait_for_rows(dialog, tree, 3)

    dialog.destroy()


def test_open_csv_preview_dialog_reuses_cached_header_filter_values(tk_root, tmp_path, monkeypatch):
    csv_path = tmp_path / "classname.csv"
    csv_path.write_text(
        "SiteName1,ClassName1,Description1\nWaterfront,Cocktails,Espresso Martini\nWaterfront,Beer,Peroni\nWaterfront,Cocktails,Negroni\n",
        encoding="utf-8",
    )

    dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    controller = getattr(dialog, "_csv_preview_controller", None)

    assert controller is not None

    original_sorted_distinct_values = dialog_module._sorted_distinct_values
    distinct_calls = 0

    def counting_sorted_distinct_values(rows, column_index):
        nonlocal distinct_calls
        distinct_calls += 1
        return original_sorted_distinct_values(rows, column_index)

    monkeypatch.setattr(dialog_module, "_sorted_distinct_values", counting_sorted_distinct_values)

    controller.show_header_filter_popup(1, 0, 0)
    controller.show_header_filter_popup(1, 0, 0)

    assert distinct_calls == 1

    dialog.destroy()


def test_compact_filter_popup_label_truncates_long_values():
    value = "This is a very long filter option value that should be truncated"

    compact = _compact_filter_popup_label(value)

    assert compact.endswith("...")
    assert len(compact) == HEADER_FILTER_POPUP_LABEL_MAX_LENGTH


def test_open_csv_preview_dialog_uses_searchable_scrollable_header_filter_popup(tk_root, tmp_path):
    long_value = "This is a very long filter option value that should be truncated"
    csv_path = tmp_path / "long_filter.csv"
    csv_path.write_text(
        f"ClassName1,Description1\n{long_value},Peroni\nShort,Negroni\nShortlist,Martini\n",
        encoding="utf-8",
    )

    dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    controller = getattr(dialog, "_csv_preview_controller", None)

    assert controller is not None

    controller.show_header_filter_popup(0, 0, 0)
    dialog.update()

    popup = controller._header_filter_popup
    assert popup is not None

    search_entry = _find_descendant(popup, ttk.Entry)
    listbox = _find_descendant(popup, tk.Listbox)
    scrollbar = _find_descendant(popup, ttk.Scrollbar)
    clear_button = _find_button(popup, "Clear filter")
    tree = _find_descendant(dialog, ttk.Treeview)

    assert search_entry is not None
    assert listbox is not None
    assert scrollbar is not None
    assert clear_button is not None
    assert tree is not None
    assert search_entry.winfo_rooty() < listbox.winfo_rooty()
    assert int(listbox.cget("height")) == HEADER_FILTER_POPUP_LIST_HEIGHT
    assert _compact_filter_popup_label(long_value) in _listbox_values(listbox)

    search_entry.insert(0, "short")
    dialog.update()

    assert _listbox_values(listbox) == ["Short", "Shortlist"]

    search_entry.delete(0, "end")
    search_entry.insert(0, "long filter option")
    dialog.update()
    listbox.selection_set(0)
    controller._apply_selected_header_filter_option()
    _wait_for_rows(dialog, tree, 1)

    values = [tree.item(item_id)["values"] for item_id in tree.get_children()]
    assert values == [[long_value, "Peroni"]]

    dialog.destroy()


def test_open_csv_preview_dialog_clear_filters_closes_open_header_filter_popup(tk_root, tmp_path):
    csv_path = tmp_path / "classname.csv"
    csv_path.write_text(
        "SiteName1,ClassName1,Description1\nWaterfront,Cocktails,Espresso Martini\nWaterfront,Beer,Peroni\n",
        encoding="utf-8",
    )

    dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    controller = getattr(dialog, "_csv_preview_controller", None)
    clear_filters_button = _find_button(dialog, "Clear filters")

    assert controller is not None
    assert clear_filters_button is not None

    controller.show_header_filter_popup(1, 0, 0)
    dialog.update()

    popup = controller._header_filter_popup
    assert popup is not None

    clear_filters_button.invoke()
    dialog.update()

    assert controller._header_filter_popup is None

    dialog.destroy()


def test_open_csv_preview_dialog_hiding_filtered_column_clears_filter_and_popup(tk_root, tmp_path):
    csv_path = tmp_path / "columns.csv"
    csv_path.write_text(
        "Name,Session,Quantity\nPeroni,Lunch,2\nPeroni,Dinner,3\nGuinness,Lunch,1\n",
        encoding="utf-8",
    )

    dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    controller = getattr(dialog, "_csv_preview_controller", None)
    tree = _find_descendant(dialog, ttk.Treeview)
    columns_button = _find_button(dialog, "Columns")

    assert controller is not None
    assert tree is not None
    assert columns_button is not None

    controller.set_header_filter(1, "Lunch")
    _wait_for_rows(dialog, tree, 2)
    controller.show_header_filter_popup(1, 0, 0)
    dialog.update()

    assert controller._header_filter_popup is not None

    columns_button.invoke()
    dialog.update()
    chooser = dialog.winfo_children()[-1]
    checkbuttons = _find_widgets(chooser, ttk.Checkbutton)
    apply_button = _find_button(chooser, "Apply")

    assert apply_button is not None
    assert len(checkbuttons) == 3

    checkbuttons[1].invoke()
    apply_button.invoke()
    dialog.update()
    _wait_for_rows(dialog, tree, 3)

    assert controller._header_filter_popup is None
    assert list(tree.cget("displaycolumns")) == ["col_0", "col_2"]

    dialog.destroy()
