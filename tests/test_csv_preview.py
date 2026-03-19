import csv
import tkinter as tk
import time
from tkinter import ttk

import pytest

from gp_data import settings
import gp_data.ui.csv_preview.analysis_dialog as analysis_dialog_module
import gp_data.ui.csv_preview.dialog as dialog_module
import gp_data.ui.csv_preview.loader as loader_module
from gp_data.ui.csv_preview import CsvPreviewError, load_csv_preview, open_csv_preview_dialog
from gp_data.ui.csv_preview.dialog import (
    CSV_PREVIEW_LOADING_ROW_TEXT,
    HEADER_FILTER_POPUP_LABEL_MAX_LENGTH,
    HEADER_FILTER_POPUP_LIST_HEIGHT,
    MAX_RENDERED_PREVIEW_ROWS,
    _rendered_preview_row_limit,
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


def _canvas_texts(canvas: tk.Canvas) -> list[str]:
    texts: list[str] = []
    for item_id in canvas.find_all():
        if canvas.type(item_id) == "text":
            texts.append(str(canvas.itemcget(item_id, "text")))
    return texts


def _wait_for_rows(window: tk.Misc, tree: ttk.Treeview, expected_count: int) -> None:
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        window.update()
        if len(tree.get_children()) == expected_count:
            return
        time.sleep(0.02)
    assert len(tree.get_children()) == expected_count


def _wait_for_first_column_values(window: tk.Misc, tree: ttk.Treeview, expected_values: list[str]) -> None:
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        window.update()
        values = [tree.item(item_id)["values"][0] for item_id in tree.get_children()]
        if values == expected_values:
            return
        time.sleep(0.02)
    assert [tree.item(item_id)["values"][0] for item_id in tree.get_children()] == expected_values


def _wait_for_tree_values(window: tk.Misc, tree: ttk.Treeview, expected_values: list[list[object]]) -> None:
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        window.update()
        values = [list(tree.item(item_id)["values"]) for item_id in tree.get_children()]
        if values == expected_values:
            return
        time.sleep(0.02)
    assert [list(tree.item(item_id)["values"]) for item_id in tree.get_children()] == expected_values


def _wait_for_listbox_values(window: tk.Misc, listbox: tk.Listbox, expected_values: list[str]) -> None:
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        window.update()
        values = _listbox_values(listbox)
        if values == expected_values:
            return
        time.sleep(0.02)
    assert _listbox_values(listbox) == expected_values


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


def test_load_csv_preview_without_headers_generates_default_headers_and_keeps_first_row(tmp_path):
    csv_path = tmp_path / "no_headers.csv"
    csv_path.write_text("1,2,3\n4,5,6\n", encoding="utf-8")

    data = load_csv_preview(csv_path, has_header_row=False)

    assert data.headers == ["Column 1", "Column 2", "Column 3"]
    assert data.row_count == 2
    assert data.rows[0] == ("1", "2", "3")
    assert data.rows[1] == ("4", "5", "6")


def test_load_csv_preview_keeps_header_and_no_header_cache_entries_separate(tmp_path):
    csv_path = tmp_path / "shared.csv"
    csv_path.write_text("1,2,3\n4,5,6\n", encoding="utf-8")

    with_headers = load_csv_preview(csv_path)
    without_headers = load_csv_preview(csv_path, has_header_row=False)

    assert with_headers.headers == ["1", "2", "3"]
    assert with_headers.rows == [("4", "5", "6")]
    assert without_headers.headers == ["Column 1", "Column 2", "Column 3"]
    assert without_headers.rows == [("1", "2", "3"), ("4", "5", "6")]


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


def test_open_csv_preview_dialog_generates_default_headers_when_csv_has_no_header_row(tk_root, tmp_path):
    csv_path = tmp_path / "headerless.csv"
    csv_path.write_text("1,2,3\n4,5,6\n", encoding="utf-8")

    dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520, has_header_row=False)
    tree = _find_descendant(dialog, ttk.Treeview)
    mode_label = _find_label_with_text(dialog, "Headers: Generated")

    assert tree is not None
    assert mode_label is not None
    assert [tree.heading(column_id)["text"] for column_id in tree.cget("columns")] == ["Column 1", "Column 2", "Column 3"]
    _wait_for_rows(dialog, tree, 2)
    assert [str(value) for value in tree.item(tree.get_children()[0])["values"]] == ["1", "2", "3"]
    assert [str(value) for value in tree.item(tree.get_children()[1])["values"]] == ["4", "5", "6"]

    dialog.destroy()


def test_open_csv_preview_dialog_shows_header_mode_label_for_real_headers(tk_root, tmp_path):
    csv_path = tmp_path / "with_headers.csv"
    csv_path.write_text("A,B,C\n1,2,3\n", encoding="utf-8")

    dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    mode_label = _find_label_with_text(dialog, "Headers: Row 1")

    assert mode_label is not None

    dialog.destroy()


def test_open_csv_preview_dialog_opens_analysis_from_current_filtered_rows(tk_root, tmp_path, monkeypatch):
    csv_path = tmp_path / "analysis_filter.csv"
    csv_path.write_text(
        "Name,Category,Quantity\nNegroni,Cocktail,2\nAperol Spritz,Spritz,4\nBeer,Beer,6\n",
        encoding="utf-8",
    )

    seen: dict[str, object] = {}

    def fake_open_analysis_dialog(parent, snapshot):
        seen.update(
            parent=parent,
            snapshot=snapshot,
        )
        return parent

    monkeypatch.setattr(dialog_module, "open_csv_preview_analysis_dialog_from_snapshot", fake_open_analysis_dialog)

    dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    query_entry = _find_descendant(dialog, ttk.Entry)
    analyze_button = _find_button(dialog, "Analyze")
    controller = getattr(dialog, "_csv_preview_controller", None)

    assert query_entry is not None
    assert analyze_button is not None
    assert controller is not None

    query_entry.insert(0, "spritz")
    controller.trigger_refresh_now()
    analyze_button.invoke()

    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and "snapshot" not in seen:
        dialog.update()
        time.sleep(0.02)

    snapshot = seen["snapshot"]
    assert snapshot.filtering_active is True
    assert snapshot.combine_sessions is False
    assert list(snapshot.rows) == [("Aperol Spritz", "Spritz", "4")]
    assert [column.index for column in snapshot.columns] == [0, 1, 2]
    assert {column.index for column in snapshot.columns if column.numeric} == {2}

    dialog.destroy()


def test_open_csv_preview_dialog_analysis_respects_combined_rows_and_visible_columns(tk_root, tmp_path, monkeypatch):
    csv_path = tmp_path / "analysis_combine.csv"
    csv_path.write_text(
        "Description1,Sessionname1,Quantity1,Notes\nTarget,Lunch,2,a\nTarget,Dinner,3,a\n",
        encoding="utf-8",
    )

    seen: dict[str, object] = {}

    def fake_open_analysis_dialog(parent, snapshot):
        seen.update(
            snapshot=snapshot,
        )
        return parent

    monkeypatch.setattr(dialog_module, "open_csv_preview_analysis_dialog_from_snapshot", fake_open_analysis_dialog)

    dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    combine_toggle = _find_descendant(dialog, ttk.Checkbutton)
    analyze_button = _find_button(dialog, "Analyze")
    controller = getattr(dialog, "_csv_preview_controller", None)

    assert combine_toggle is not None
    assert analyze_button is not None
    assert controller is not None

    controller._apply_visible_columns([0, 1, 2])
    combine_toggle.invoke()
    analyze_button.invoke()

    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and "snapshot" not in seen:
        dialog.update()
        time.sleep(0.02)

    snapshot = seen["snapshot"]
    assert snapshot.combine_sessions is True
    assert [column.index for column in snapshot.columns] == [0, 1, 2]
    assert {column.index for column in snapshot.columns if column.numeric} == {2}
    assert list(snapshot.rows) == [("Target", "Lunch + Dinner", "5", "a")]

    dialog.destroy()


def test_open_csv_preview_dialog_shows_processing_popup_while_opening_analysis(tk_root, tmp_path, monkeypatch):
    csv_path = tmp_path / "analysis_popup.csv"
    csv_path.write_text(
        "Name,Category,Quantity\nNegroni,Cocktail,2\nSpritz,Spritz,4\n",
        encoding="utf-8",
    )

    original_build_preview_analysis_snapshot = dialog_module.build_preview_analysis_snapshot
    seen: dict[str, object] = {}

    def slow_build_preview_analysis_snapshot(*args, **kwargs):
        time.sleep(0.15)
        return original_build_preview_analysis_snapshot(*args, **kwargs)

    def fake_open_analysis_dialog(parent, snapshot):
        seen["snapshot"] = snapshot
        return parent

    monkeypatch.setattr(dialog_module, "build_preview_analysis_snapshot", slow_build_preview_analysis_snapshot)
    monkeypatch.setattr(dialog_module, "open_csv_preview_analysis_dialog_from_snapshot", fake_open_analysis_dialog)

    dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    analyze_button = _find_button(dialog, "Analyze")
    controller = getattr(dialog, "_csv_preview_controller", None)

    assert analyze_button is not None
    assert controller is not None

    dialog.update()
    analyze_button.invoke()
    dialog.update()

    status_dialog = controller._analysis_status_dialog
    assert status_dialog is not None
    assert status_dialog.winfo_exists()
    assert status_dialog.title() == "Preparing Analysis"
    assert controller._analysis_status_var.get() == "Preparing analysis..."

    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and "snapshot" not in seen:
        dialog.update()
        time.sleep(0.02)

    assert "snapshot" in seen
    assert controller._analysis_status_dialog is None

    dialog.destroy()


def test_open_csv_preview_dialog_shows_centered_processing_popup_while_combining_sessions(tk_root, tmp_path, monkeypatch):
    csv_path = tmp_path / "combine_popup.csv"
    csv_path.write_text(
        "Description1,Sessionname1,Quantity1\nTarget,Lunch,2\nTarget,Dinner,3\n",
        encoding="utf-8",
    )

    original_iter_filtered_refresh_messages = dialog_module._PreviewDataPipeline.iter_filtered_refresh_messages

    def delayed_iter_filtered_refresh_messages(self, load_token, filter_state, *, rendered_row_limit, should_cancel=None):
        if not filter_state.combine_sessions:
            yield from original_iter_filtered_refresh_messages(
                self,
                load_token,
                filter_state,
                rendered_row_limit=rendered_row_limit,
                should_cancel=should_cancel,
            )
            return

        yield dialog_module._FilteredPreviewUpdate(
            load_token=load_token,
            displayed_rows=[("Target", "Lunch + Dinner", "5")],
            total_rows=None,
        )
        time.sleep(0.15)
        if should_cancel is not None and should_cancel():
            return
        yield dialog_module._FilteredCountUpdate(load_token=load_token, total_rows=1)

    monkeypatch.setattr(
        dialog_module._PreviewDataPipeline,
        "iter_filtered_refresh_messages",
        delayed_iter_filtered_refresh_messages,
    )

    dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    combine_toggle = _find_descendant(dialog, ttk.Checkbutton)
    tree = _find_descendant(dialog, ttk.Treeview)
    controller = getattr(dialog, "_csv_preview_controller", None)

    assert combine_toggle is not None
    assert tree is not None
    assert controller is not None

    dialog.update()
    combine_toggle.invoke()
    dialog.update()

    status_dialog = controller._processing_status_dialog
    assert status_dialog is not None
    assert status_dialog.winfo_exists()
    assert status_dialog.title() == "Processing CSV"
    assert controller._processing_status_var.get() == "Processing sessions..."

    preview_center_x = dialog.winfo_rootx() + (dialog.winfo_width() / 2)
    preview_center_y = dialog.winfo_rooty() + (dialog.winfo_height() / 2)
    status_center_x = status_dialog.winfo_rootx() + (status_dialog.winfo_width() / 2)
    status_center_y = status_dialog.winfo_rooty() + (status_dialog.winfo_height() / 2)
    assert abs(status_center_x - preview_center_x) <= 20
    assert abs(status_center_y - preview_center_y) <= 40

    saw_preview_with_popup = False
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        dialog.update()
        rows = [list(tree.item(item_id)["values"]) for item_id in tree.get_children()]
        if rows and rows[0][:2] == ["Target", "Lunch + Dinner"] and str(rows[0][2]) == "5":
            if controller._processing_status_dialog is not None:
                saw_preview_with_popup = True
                break
        time.sleep(0.02)

    assert saw_preview_with_popup is True

    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        dialog.update()
        if controller._processing_status_dialog is None:
            break
        time.sleep(0.02)

    assert controller._processing_status_dialog is None
    rows = [list(tree.item(item_id)["values"]) for item_id in tree.get_children()]
    assert rows and rows[0][:2] == ["Target", "Lunch + Dinner"]
    assert str(rows[0][2]) == "5"

    dialog.destroy()


def test_open_csv_preview_analysis_dialog_renders_chart_views(tk_root):
    analysis_path = loader_module.Path("analysis.csv")
    dialog = analysis_dialog_module.open_csv_preview_analysis_dialog(
        tk_root,
        loader_module.CsvPreviewData(
            path=analysis_path,
            encoding="utf-8",
            headers=["Name", "Category", "Quantity"],
            rows=[],
            row_total=1,
            fully_cached=True,
        ),
        [("Negroni", "Cocktail", "2")],
        [0, 1, 2],
        {2},
        filtering_active=True,
        combine_sessions=False,
    )

    combo_boxes = _find_widgets(dialog, ttk.Combobox)
    assert combo_boxes

    view_box = combo_boxes[0]
    label_box = combo_boxes[1]
    value_box = combo_boxes[2]
    view_box.set("Bar chart")
    view_box.event_generate("<<ComboboxSelected>>")
    tk_root.update_idletasks()
    tk_root.update()

    label_box.set("1: Name")
    label_box.event_generate("<<ComboboxSelected>>")
    value_box.set("3: Quantity")
    value_box.event_generate("<<ComboboxSelected>>")
    tk_root.update_idletasks()
    tk_root.update()

    canvas = _find_descendant(dialog, tk.Canvas)
    assert canvas is not None
    assert canvas.find_all()
    assert label_box.get() == "1: Name"
    assert value_box.get() == "3: Quantity"
    assert _find_label_with_text(dialog, "3: Quantity by 1: Name (highest to lowest)") is not None

    view_box.set("Pie chart")
    view_box.event_generate("<<ComboboxSelected>>")
    tk_root.update_idletasks()
    tk_root.update()

    assert dialog.title() == "CSV Analysis - analysis.csv"
    assert canvas.find_all()

    dialog.destroy()


def test_open_csv_preview_analysis_dialog_bar_chart_shows_all_items_with_scroll(tk_root):
    analysis_path = loader_module.Path("analysis.csv")
    dialog = analysis_dialog_module.open_csv_preview_analysis_dialog(
        tk_root,
        loader_module.CsvPreviewData(
            path=analysis_path,
            encoding="utf-8",
            headers=["Name", "Quantity"],
            rows=[],
            row_total=50,
            fully_cached=True,
        ),
        [(f"Cocktail {index}", str(index)) for index in range(1, 51)],
        [0, 1],
        {1},
        filtering_active=True,
        combine_sessions=False,
    )

    combo_boxes = _find_widgets(dialog, ttk.Combobox)
    assert combo_boxes

    view_box = combo_boxes[0]
    view_box.set("Bar chart")
    view_box.event_generate("<<ComboboxSelected>>")
    tk_root.update_idletasks()
    tk_root.update()

    canvas = _find_descendant(dialog, tk.Canvas)
    assert canvas is not None
    assert str(canvas.cget("xscrollcommand"))
    assert "Other" not in _canvas_texts(canvas)

    label_angles = [
        str(canvas.itemcget(item_id, "angle"))
        for item_id in canvas.find_all()
        if canvas.type(item_id) == "text" and "Cocktail" in str(canvas.itemcget(item_id, "text"))
    ]
    assert label_angles
    assert all(angle in {"90", "90.0"} for angle in label_angles)

    axis_y = max(
        canvas.coords(item_id)[1]
        for item_id in canvas.find_all()
        if canvas.type(item_id) == "line" and len(canvas.coords(item_id)) == 4 and canvas.coords(item_id)[1] == canvas.coords(item_id)[3]
    )
    label_item_ids = [
        item_id
        for item_id in canvas.find_all()
        if canvas.type(item_id) == "text" and "Cocktail" in str(canvas.itemcget(item_id, "text"))
    ]
    assert label_item_ids
    assert all(canvas.bbox(item_id)[1] >= axis_y + 10 for item_id in label_item_ids if canvas.bbox(item_id) is not None)
    assert all(str(canvas.itemcget(item_id, "anchor")) == "center" for item_id in label_item_ids)

    bar_item_ids = [
        item_id
        for item_id in canvas.find_all()
        if canvas.type(item_id) == "rectangle" and str(canvas.itemcget(item_id, "fill"))
    ]
    bar_centers = sorted((canvas.coords(item_id)[0] + canvas.coords(item_id)[2]) / 2 for item_id in bar_item_ids)
    label_centers = sorted((canvas.bbox(item_id)[0] + canvas.bbox(item_id)[2]) / 2 for item_id in label_item_ids if canvas.bbox(item_id) is not None)
    assert len(bar_centers) == len(label_centers)
    assert all(abs(bar_center - label_center) <= 1.0 for bar_center, label_center in zip(bar_centers, label_centers, strict=False))

    scrollregion = [float(value) for value in str(canvas.cget("scrollregion")).split()]
    assert len(scrollregion) == 4
    assert scrollregion[2] > canvas.winfo_width()

    dialog.destroy()


def test_open_csv_preview_analysis_dialog_pie_chart_groups_smaller_items_into_other(tk_root):
    analysis_path = loader_module.Path("analysis.csv")
    dialog = analysis_dialog_module.open_csv_preview_analysis_dialog(
        tk_root,
        loader_module.CsvPreviewData(
            path=analysis_path,
            encoding="utf-8",
            headers=["Name", "Quantity"],
            rows=[],
            row_total=50,
            fully_cached=True,
        ),
        [(f"Cocktail {index}", str(index)) for index in range(1, 51)],
        [0, 1],
        {1},
        filtering_active=True,
        combine_sessions=False,
    )

    combo_boxes = _find_widgets(dialog, ttk.Combobox)
    assert combo_boxes

    view_box = combo_boxes[0]
    view_box.set("Pie chart")
    view_box.event_generate("<<ComboboxSelected>>")
    tk_root.update_idletasks()
    tk_root.update()

    canvas = _find_descendant(dialog, tk.Canvas)
    assert canvas is not None
    canvas_texts = _canvas_texts(canvas)
    assert any("Other" in text for text in canvas_texts)
    assert any("Cocktail" in text for text in canvas_texts)

    scrollregion = [float(value) for value in str(canvas.cget("scrollregion")).split()]
    assert len(scrollregion) == 4
    assert scrollregion[3] <= canvas.winfo_height()

    dialog.destroy()


def test_open_csv_preview_analysis_dialog_bar_chart_supports_negative_values(tk_root):
    analysis_path = loader_module.Path("analysis.csv")
    dialog = analysis_dialog_module.open_csv_preview_analysis_dialog(
        tk_root,
        loader_module.CsvPreviewData(
            path=analysis_path,
            encoding="utf-8",
            headers=["Name", "Value"],
            rows=[],
            row_total=2,
            fully_cached=True,
        ),
        [("Refund", "-5"), ("Discount", "-2")],
        [0, 1],
        {1},
        filtering_active=True,
        combine_sessions=False,
    )

    combo_boxes = _find_widgets(dialog, ttk.Combobox)
    view_box = combo_boxes[0]
    view_box.set("Bar chart")
    view_box.event_generate("<<ComboboxSelected>>")
    tk_root.update_idletasks()
    tk_root.update()

    canvas = _find_descendant(dialog, tk.Canvas)
    assert canvas is not None
    texts = _canvas_texts(canvas)
    assert "No chartable values are available for the selected columns." not in texts
    assert any(text == "-5" for text in texts)
    assert any(text == "-2" for text in texts)

    dialog.destroy()


def test_open_csv_preview_analysis_dialog_pie_chart_rejects_negative_values(tk_root):
    analysis_path = loader_module.Path("analysis.csv")
    dialog = analysis_dialog_module.open_csv_preview_analysis_dialog(
        tk_root,
        loader_module.CsvPreviewData(
            path=analysis_path,
            encoding="utf-8",
            headers=["Name", "Value"],
            rows=[],
            row_total=2,
            fully_cached=True,
        ),
        [("Sales", "5"), ("Refund", "-2")],
        [0, 1],
        {1},
        filtering_active=True,
        combine_sessions=False,
    )

    combo_boxes = _find_widgets(dialog, ttk.Combobox)
    view_box = combo_boxes[0]
    view_box.set("Pie chart")
    view_box.event_generate("<<ComboboxSelected>>")
    tk_root.update_idletasks()
    tk_root.update()

    canvas = _find_descendant(dialog, tk.Canvas)
    assert canvas is not None
    assert "Pie charts require positive values only." in _canvas_texts(canvas)

    dialog.destroy()


def test_load_csv_preview_reuses_cached_data_for_unchanged_file(tmp_path):
    csv_path = tmp_path / "wide.csv"
    csv_path.write_text("A,B\n1,2\n", encoding="utf-8")

    first = load_csv_preview(csv_path)
    second = load_csv_preview(csv_path)

    assert first is second


def test_load_csv_preview_evicts_least_recently_used_cache_entry_across_paths(tmp_path, monkeypatch):
    first_path = tmp_path / "first.csv"
    second_path = tmp_path / "second.csv"
    third_path = tmp_path / "third.csv"
    for csv_path, value in ((first_path, "1"), (second_path, "2"), (third_path, "3")):
        csv_path.write_text(f"A,B\n{value},{value}\n", encoding="utf-8")

    loader_module._PREVIEW_CACHE.clear()
    monkeypatch.setattr(loader_module, "PREVIEW_CACHE_MAX_ENTRIES", 2)

    first = load_csv_preview(first_path)
    second = load_csv_preview(second_path)
    assert len(loader_module._PREVIEW_CACHE) == 2

    first_again = load_csv_preview(first_path)
    third = load_csv_preview(third_path)

    assert first_again is first
    assert third.path == third_path
    assert len(loader_module._PREVIEW_CACHE) == 2
    cached_paths = [key[0] for key in loader_module._PREVIEW_CACHE]
    assert str(first_path.resolve()) in cached_paths
    assert str(third_path.resolve()) in cached_paths
    assert str(second_path.resolve()) not in cached_paths


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


def test_load_large_csv_preview_reuses_sidecar_metadata_with_blank_headers_on_reopen(tmp_path):
    csv_path = tmp_path / "blank_headers.csv"
    rows = [",Category"]
    rows.extend(f"item{index},value{index}" for index in range(PREVIEW_ROW_SAMPLE_SIZE + 25))
    csv_path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    data = load_csv_preview(csv_path)
    resolved = resolve_csv_preview_metadata(data)

    loader_module._PREVIEW_CACHE.clear()
    reopened = load_csv_preview(csv_path)

    assert loader_module._metadata_sidecar_path(csv_path).exists()
    assert reopened is not resolved
    assert reopened.headers == ["", "Category"]
    assert reopened.row_count == PREVIEW_ROW_SAMPLE_SIZE + 25
    assert len(reopened.rows) == PREVIEW_ROW_SAMPLE_SIZE
    assert reopened.fully_cached is False


def test_load_large_csv_preview_reuses_persisted_preview_rows_without_rereading_csv(tmp_path, monkeypatch):
    csv_path = tmp_path / "reopen_preview_rows.csv"
    rows = ["A,B"]
    rows.extend(f"item{index},value{index}" for index in range(PREVIEW_ROW_SAMPLE_SIZE + 25))
    csv_path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    data = load_csv_preview(csv_path)
    resolve_csv_preview_metadata(data)

    loader_module._PREVIEW_CACHE.clear()

    def fail_iter_csv_file_rows(*args, **kwargs):
        raise AssertionError("CSV file should not be reread when persisted preview rows are available")

    monkeypatch.setattr(loader_module, "_iter_csv_file_rows", fail_iter_csv_file_rows)

    reopened = load_csv_preview(csv_path)

    assert reopened.row_count == PREVIEW_ROW_SAMPLE_SIZE + 25
    assert len(reopened.rows) == PREVIEW_ROW_SAMPLE_SIZE
    assert reopened.rows[0] == ("item0", "value0")
    assert reopened.fully_cached is False


def test_preview_pipeline_uses_persisted_full_row_cache_with_blank_headers_across_restart(tmp_path, monkeypatch):
    csv_path = tmp_path / "blank_header_row_cache.csv"
    total_rows = PREVIEW_ROW_SAMPLE_SIZE + 120
    rows = [",Category"]
    rows.extend(f"Item {index},Beer" for index in range(1, total_rows + 1))
    csv_path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    data = load_csv_preview(csv_path)
    resolve_csv_preview_metadata(data)

    loader_module._PREVIEW_CACHE.clear()
    reopened = load_csv_preview(csv_path)
    pipeline = dialog_module._PreviewDataPipeline(reopened)

    def fail_iter_csv_preview_rows(*args, **kwargs):
        raise AssertionError("Persisted full row cache should avoid rescanning the CSV file")

    monkeypatch.setattr(dialog_module, "iter_csv_preview_rows", fail_iter_csv_preview_rows)

    source_rows = pipeline._source_rows_snapshot(False)

    assert reopened.headers == ["", "Category"]
    assert source_rows is not None
    assert len(source_rows) == total_rows
    assert source_rows[0] == ("Item 1", "Beer")
    assert source_rows[-1] == (f"Item {total_rows}", "Beer")


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
    controller = getattr(dialog, "_csv_preview_controller", None)

    assert tree is not None
    assert combine_toggle is not None
    assert query_entry is not None
    assert controller is not None

    query_entry.insert(0, "target")
    controller.trigger_refresh_now()
    _wait_for_rows(dialog, tree, 2)
    combine_toggle.invoke()
    _wait_for_tree_values(dialog, tree, [["Target", "Lunch + Dinner", 5, 12]])

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
    controller = getattr(dialog, "_csv_preview_controller", None)

    assert tree is not None
    assert query_entry is not None
    assert controller is not None

    _wait_for_rows(dialog, tree, 3)
    query_entry.insert(0, "mixer")
    controller.trigger_refresh_now()
    _wait_for_first_column_values(dialog, tree, ["Lemon Soda"])

    first_row = tree.get_children()[0]
    assert tree.item(first_row)["values"] == ["Lemon Soda", "Mixer", "US"]

    dialog.destroy()


def test_open_csv_preview_dialog_reuses_source_search_index_for_follow_up_queries(tk_root, tmp_path, monkeypatch):
    csv_path = tmp_path / "query_index.csv"
    csv_path.write_text(
        "Name,Category,Origin\nBerry Gin,Spirit,UK\nLemon Soda,Mixer,US\nDark Rum,Spirit,Jamaica\n",
        encoding="utf-8",
    )

    dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    tree = _find_descendant(dialog, ttk.Treeview)
    controller = getattr(dialog, "_csv_preview_controller", None)

    assert tree is not None
    assert controller is not None

    _wait_for_rows(dialog, tree, 3)

    original_iter_rows_before_header_filter = dialog_module._iter_rows_before_header_filter
    row_scan_calls = 0

    def counting_iter_rows_before_header_filter(*args, **kwargs):
        nonlocal row_scan_calls
        row_scan_calls += 1
        yield from original_iter_rows_before_header_filter(*args, **kwargs)

    monkeypatch.setattr(dialog_module, "_iter_rows_before_header_filter", counting_iter_rows_before_header_filter)

    controller._query_var.set("mixer")
    controller.refresh()
    _wait_for_rows(dialog, tree, 1)

    controller._query_var.set("spirit")
    controller.refresh()
    _wait_for_rows(dialog, tree, 2)

    assert row_scan_calls == 0

    dialog.destroy()


def test_rows_before_header_filter_snapshot_reuses_previous_query_subset_for_incremental_typing(tmp_path, monkeypatch):
    csv_path = tmp_path / "incremental_query.csv"
    csv_path.write_text(
        "Name,Category\nBerry Gin,Spirit\nLemon Soda,Mixer\nDark Rum,Spirit\n",
        encoding="utf-8",
    )

    data = load_csv_preview(csv_path)
    pipeline = dialog_module._PreviewDataPipeline(data)
    first_state = dialog_module._PreviewFilterState(
        query="spi",
        combine_sessions=False,
        header_filter_column_index=None,
        header_filter_value=None,
    )
    second_state = dialog_module._PreviewFilterState(
        query="spir",
        combine_sessions=False,
        header_filter_column_index=None,
        header_filter_value=None,
    )

    assert [row[0] for row in pipeline.rows_before_header_filter_snapshot(first_state)] == ["Berry Gin", "Dark Rum"]

    original_source_rows_snapshot = pipeline._source_rows_snapshot
    source_snapshot_calls = 0

    def counting_source_rows_snapshot(*args, **kwargs):
        nonlocal source_snapshot_calls
        source_snapshot_calls += 1
        return original_source_rows_snapshot(*args, **kwargs)

    monkeypatch.setattr(pipeline, "_source_rows_snapshot", counting_source_rows_snapshot)

    assert [row[0] for row in pipeline.rows_before_header_filter_snapshot(second_state)] == ["Berry Gin", "Dark Rum"]
    assert source_snapshot_calls == 0


def test_preview_pipeline_indexes_large_file_when_estimated_memory_fits_budget(tmp_path):
    csv_path = tmp_path / "budgeted_index.csv"
    rows = [f"Item {index},Beer" for index in range(1, PREVIEW_ROW_SAMPLE_SIZE + 25002)]
    csv_path.write_text("Name,Category\n" + "\n".join(rows) + "\n", encoding="utf-8")

    data = resolve_csv_preview_metadata(load_csv_preview(csv_path))
    pipeline = dialog_module._PreviewDataPipeline(data)

    assert data.row_count is not None
    assert data.row_count > PREVIEW_ROW_SAMPLE_SIZE
    assert data.fully_cached is False
    assert pipeline._estimated_uncombined_source_index_bytes() is not None
    assert pipeline._can_index_uncombined_source_rows() is True
    assert pipeline._source_rows_snapshot(False) is not None


def test_preview_pipeline_skips_large_file_index_when_estimated_memory_exceeds_budget(tmp_path, monkeypatch):
    csv_path = tmp_path / "budgeted_skip.csv"
    rows = [f"Item {index},Beer" for index in range(1, PREVIEW_ROW_SAMPLE_SIZE + 25002)]
    csv_path.write_text("Name,Category\n" + "\n".join(rows) + "\n", encoding="utf-8")

    data = resolve_csv_preview_metadata(load_csv_preview(csv_path))
    pipeline = dialog_module._PreviewDataPipeline(data)
    estimated_bytes = pipeline._estimated_uncombined_source_index_bytes()

    assert estimated_bytes is not None

    monkeypatch.setattr(dialog_module, "MAX_INDEXED_SOURCE_MEMORY_BYTES", estimated_bytes - 1)

    assert pipeline._can_index_uncombined_source_rows() is False
    assert pipeline._source_rows_snapshot(False) is None


def test_preview_pipeline_uses_persisted_full_row_cache_across_restart(tmp_path, monkeypatch):
    csv_path = tmp_path / "persisted_row_cache.csv"
    total_rows = PREVIEW_ROW_SAMPLE_SIZE + 120
    rows = [f"Item {index},Beer" for index in range(1, total_rows + 1)]
    csv_path.write_text("Name,Category\n" + "\n".join(rows) + "\n", encoding="utf-8")

    data = load_csv_preview(csv_path)
    resolve_csv_preview_metadata(data)

    loader_module._PREVIEW_CACHE.clear()
    reopened = load_csv_preview(csv_path)
    pipeline = dialog_module._PreviewDataPipeline(reopened)

    def fail_iter_csv_preview_rows(*args, **kwargs):
        raise AssertionError("Persisted full row cache should avoid rescanning the CSV file")

    monkeypatch.setattr(dialog_module, "iter_csv_preview_rows", fail_iter_csv_preview_rows)

    source_rows = pipeline._source_rows_snapshot(False)

    assert source_rows is not None
    assert len(source_rows) == total_rows
    assert source_rows[0] == ("Item 1", "Beer")
    assert source_rows[-1] == (f"Item {total_rows}", "Beer")


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


def test_open_csv_preview_dialog_shows_loading_row_while_search_refresh_is_pending(tk_root, tmp_path, monkeypatch):
    csv_path = tmp_path / "search_loading_row.csv"
    csv_path.write_text(
        "Name,Category\nPeroni,Beer\nNegroni,Cocktails\n",
        encoding="utf-8",
    )

    dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    tree = _find_descendant(dialog, ttk.Treeview)
    controller = getattr(dialog, "_csv_preview_controller", None)

    assert tree is not None
    assert controller is not None

    _wait_for_rows(dialog, tree, 2)

    original_iter_rows_before_header_filter = dialog_module._iter_rows_before_header_filter

    def slow_iter_rows_before_header_filter(*args, **kwargs):
        time.sleep(0.35)
        yield from original_iter_rows_before_header_filter(*args, **kwargs)

    monkeypatch.setattr(dialog_module, "_iter_rows_before_header_filter", slow_iter_rows_before_header_filter)

    controller._query_var.set("beer")
    dialog.update()

    visible_values_before_refresh = [tree.item(item_id)["values"][0] for item_id in tree.get_children()]
    assert visible_values_before_refresh == ["Peroni", "Negroni"]
    assert controller._summary_var.get().startswith("search_loading_row.csv | 2 rows")
    assert controller._scheduled_refresh_id is None

    controller.trigger_refresh_now()
    dialog.update()

    placeholder_values = [tree.item(item_id)["values"][0] for item_id in tree.get_children()]
    assert placeholder_values == [CSV_PREVIEW_LOADING_ROW_TEXT]
    assert controller._summary_var.get().startswith("search_loading_row.csv | Loading matching rows")

    _wait_for_first_column_values(dialog, tree, ["Peroni"])
    assert tree.item(tree.get_children()[0])["values"] == ["Peroni", "Beer"]

    dialog.destroy()


def test_open_csv_preview_dialog_keeps_existing_rows_visible_until_search_is_submitted(tk_root, tmp_path, monkeypatch):
    csv_path = tmp_path / "search_deferred_scan.csv"
    csv_path.write_text(
        "Name,Category\nPeroni,Beer\nNegroni,Cocktails\n",
        encoding="utf-8",
    )

    dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    tree = _find_descendant(dialog, ttk.Treeview)
    controller = getattr(dialog, "_csv_preview_controller", None)

    assert tree is not None
    assert controller is not None

    _wait_for_rows(dialog, tree, 2)

    controller._query_var.set("beer")
    dialog.update()

    assert controller._scheduled_refresh_id is None
    assert [tree.item(item_id)["values"][0] for item_id in tree.get_children()] == ["Peroni", "Negroni"]
    assert controller._summary_var.get().startswith("search_deferred_scan.csv | 2 rows")

    dialog.destroy()


def test_open_csv_preview_dialog_runs_search_immediately_on_enter(tk_root, tmp_path, monkeypatch):
    csv_path = tmp_path / "search_enter_trigger.csv"
    csv_path.write_text(
        "Name,Category\nPeroni,Beer\nNegroni,Cocktails\n",
        encoding="utf-8",
    )

    dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    tree = _find_descendant(dialog, ttk.Treeview)
    controller = getattr(dialog, "_csv_preview_controller", None)

    assert tree is not None
    assert controller is not None

    _wait_for_rows(dialog, tree, 2)

    original_iter_rows_before_header_filter = dialog_module._iter_rows_before_header_filter

    def slow_iter_rows_before_header_filter(*args, **kwargs):
        time.sleep(0.35)
        yield from original_iter_rows_before_header_filter(*args, **kwargs)

    monkeypatch.setattr(dialog_module, "_iter_rows_before_header_filter", slow_iter_rows_before_header_filter)

    controller._query_var.set("beer")
    assert controller._scheduled_refresh_id is None

    started = time.monotonic()
    result = controller.trigger_refresh_now()
    elapsed = time.monotonic() - started

    assert result == "break"
    assert elapsed < 0.2
    assert controller._scheduled_refresh_id is None
    assert controller._summary_var.get().startswith("search_enter_trigger.csv | Loading matching rows")

    _wait_for_tree_values(dialog, tree, [["Peroni", "Beer"]])

    dialog.destroy()


def test_sorted_refresh_emits_preview_rows_before_exact_sorted_result(tmp_path):
    csv_path = tmp_path / "progressive_sort.csv"
    csv_path.write_text(
        "Name,Category\nPeroni,Beer\nAperol,Spritz\nNegroni,Cocktails\nCampari,Bitters\n",
        encoding="utf-8",
    )

    data = load_csv_preview(csv_path)
    pipeline = dialog_module._PreviewDataPipeline(data)
    filter_state = dialog_module._PreviewFilterState(
        query="",
        combine_sessions=False,
        header_filter_column_index=None,
        header_filter_value=None,
        sort_column_index=0,
        sort_descending=False,
    )

    messages = list(pipeline.iter_filtered_refresh_messages(7, filter_state, rendered_row_limit=2))
    preview_updates = [message for message in messages if isinstance(message, dialog_module._FilteredPreviewUpdate)]

    assert len(preview_updates) == 2
    assert preview_updates[0].total_rows is None
    assert [row[0] for row in preview_updates[0].displayed_rows] == ["Aperol", "Peroni"]
    assert preview_updates[1].total_rows == 4
    assert [row[0] for row in preview_updates[1].displayed_rows] == ["Aperol", "Campari"]


def test_filtered_refresh_emits_early_partial_preview_before_final_count(tmp_path):
    csv_path = tmp_path / "progressive_filter.csv"
    csv_path.write_text(
        "Name,Category\n" + "".join(f"Item {index},Beer\n" for index in range(30)),
        encoding="utf-8",
    )

    data = load_csv_preview(csv_path)
    pipeline = dialog_module._PreviewDataPipeline(data)
    filter_state = dialog_module._PreviewFilterState(
        query="beer",
        combine_sessions=False,
        header_filter_column_index=None,
        header_filter_value=None,
    )

    messages = list(pipeline.iter_filtered_refresh_messages(9, filter_state, rendered_row_limit=50))
    preview_updates = [message for message in messages if isinstance(message, dialog_module._FilteredPreviewUpdate)]
    count_updates = [message for message in messages if isinstance(message, dialog_module._FilteredCountUpdate)]

    assert [len(message.displayed_rows) for message in preview_updates[:-1]] == [1, 10, 25]
    assert all(message.total_rows is None for message in preview_updates[:-1])
    assert preview_updates[-1].total_rows == 30
    assert len(preview_updates[-1].displayed_rows) == 30
    assert count_updates == []


def test_open_csv_preview_dialog_reuses_filtered_rows_for_follow_up_sorts(tk_root, tmp_path, monkeypatch):
    csv_path = tmp_path / "sort_cache.csv"
    csv_path.write_text(
        "Name,Category\nPeroni,Beer\nAperol,Spritz\nNegroni,Cocktails\nCampari,Bitters\n",
        encoding="utf-8",
    )

    dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    tree = _find_descendant(dialog, ttk.Treeview)
    controller = getattr(dialog, "_csv_preview_controller", None)

    assert tree is not None
    assert controller is not None

    _wait_for_rows(dialog, tree, 4)

    original_iter_rows_before_header_filter = dialog_module._iter_rows_before_header_filter
    filter_calls = 0

    def counting_iter_rows_before_header_filter(*args, **kwargs):
        nonlocal filter_calls
        filter_calls += 1
        yield from original_iter_rows_before_header_filter(*args, **kwargs)

    monkeypatch.setattr(dialog_module, "_iter_rows_before_header_filter", counting_iter_rows_before_header_filter)

    controller.set_sort(0, descending=False)
    _wait_for_first_column_values(dialog, tree, ["Aperol", "Campari", "Negroni", "Peroni"])
    assert filter_calls == 0

    controller.set_sort(0, descending=True)
    _wait_for_first_column_values(dialog, tree, ["Peroni", "Negroni", "Campari", "Aperol"])
    assert filter_calls == 0

    dialog.destroy()


def test_open_csv_preview_dialog_reuses_tree_items_for_same_size_sort_refresh(tk_root, tmp_path, monkeypatch):
    csv_path = tmp_path / "tree_reuse_sort.csv"
    csv_path.write_text(
        "Name,Category\nPeroni,Beer\nAperol,Spritz\nNegroni,Cocktails\nCampari,Bitters\n",
        encoding="utf-8",
    )

    dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    tree = _find_descendant(dialog, ttk.Treeview)
    controller = getattr(dialog, "_csv_preview_controller", None)

    assert tree is not None
    assert controller is not None

    _wait_for_rows(dialog, tree, 4)

    original_insert = tree.insert
    insert_calls = 0

    def counting_insert(*args, **kwargs):
        nonlocal insert_calls
        insert_calls += 1
        return original_insert(*args, **kwargs)

    monkeypatch.setattr(tree, "insert", counting_insert)

    controller.set_sort(0, descending=True)
    _wait_for_first_column_values(dialog, tree, ["Peroni", "Negroni", "Campari", "Aperol"])

    assert insert_calls == 0

    dialog.destroy()


def test_open_csv_preview_dialog_prewarms_visible_header_filters_in_background(tk_root, tmp_path, monkeypatch):
    csv_path = tmp_path / "prewarm_popup.csv"
    csv_path.write_text(
        "Name,Category,Origin\nPeroni,Beer,Italy\nNegroni,Cocktails,Italy\nAperol,Spritz,Italy\n",
        encoding="utf-8",
    )

    prewarm_calls: list[tuple[str, tuple[int, ...]]] = []
    original_prewarm_header_filter_columns = dialog_module._PreviewDataPipeline.prewarm_header_filter_columns

    def counting_prewarm_header_filter_columns(self, filter_state, column_indices, **kwargs):
        prewarm_calls.append((filter_state.query, tuple(column_indices)))
        return original_prewarm_header_filter_columns(self, filter_state, column_indices, **kwargs)

    monkeypatch.setattr(
        dialog_module._PreviewDataPipeline,
        "prewarm_header_filter_columns",
        counting_prewarm_header_filter_columns,
    )

    dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    tree = _find_descendant(dialog, ttk.Treeview)

    assert tree is not None

    _wait_for_rows(dialog, tree, 3)

    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and not prewarm_calls:
        dialog.update()
        time.sleep(0.02)

    assert prewarm_calls == [("", (0, 1, 2))]

    dialog.destroy()


def test_open_csv_preview_dialog_skips_large_file_prewarm_rescans_without_source_snapshot(tk_root, tmp_path, monkeypatch):
    csv_path = tmp_path / "large_prewarm_skip.csv"
    rows = ["Name,Category"]
    rows.extend(f"Item {index},Beer" for index in range(PREVIEW_ROW_SAMPLE_SIZE + 25))
    csv_path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    prewarm_calls: list[tuple[str, tuple[int, ...]]] = []
    iter_calls = 0
    original_prewarm_header_filter_columns = dialog_module._PreviewDataPipeline.prewarm_header_filter_columns
    original_iter_csv_preview_rows = dialog_module.iter_csv_preview_rows

    def counting_prewarm_header_filter_columns(self, filter_state, column_indices, **kwargs):
        prewarm_calls.append((filter_state.query, tuple(column_indices)))
        return original_prewarm_header_filter_columns(self, filter_state, column_indices, **kwargs)

    def counting_iter_csv_preview_rows(*args, **kwargs):
        nonlocal iter_calls
        iter_calls += 1
        yield from original_iter_csv_preview_rows(*args, **kwargs)

    monkeypatch.setattr(
        dialog_module._PreviewDataPipeline,
        "prewarm_header_filter_columns",
        counting_prewarm_header_filter_columns,
    )
    monkeypatch.setattr(dialog_module, "iter_csv_preview_rows", counting_iter_csv_preview_rows)

    dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    tree = _find_descendant(dialog, ttk.Treeview)

    assert tree is not None

    _wait_for_rows(dialog, tree, PREVIEW_ROW_SAMPLE_SIZE)

    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and not prewarm_calls:
        dialog.update()
        time.sleep(0.02)

    assert prewarm_calls
    assert all(call == ("", (0, 1)) for call in prewarm_calls)

    deadline = time.monotonic() + 0.3
    while time.monotonic() < deadline:
        dialog.update()
        time.sleep(0.02)

    assert iter_calls == 0

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
    _wait_for_tree_values(dialog, tree, [["Pornstar Martini", "Lunch + Dinner", 1249, 12, "56.25"]])

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

    _wait_for_tree_values(dialog, tree, [["Target", "Lunch + Dinner", 5]])

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


def test_rendered_preview_row_limit_scales_down_for_wide_csvs():
    assert _rendered_preview_row_limit(3) == MAX_RENDERED_PREVIEW_ROWS
    assert _rendered_preview_row_limit(40) < MAX_RENDERED_PREVIEW_ROWS
    assert _rendered_preview_row_limit(120) < _rendered_preview_row_limit(40)


def test_open_csv_preview_dialog_uses_lower_row_cap_for_wide_large_files(tk_root, tmp_path):
    headers = [f"Col {index}" for index in range(1, 41)]
    row_limit = _rendered_preview_row_limit(len(headers))
    rows = [",".join([f"r{row}_c{col}" for col in range(1, 41)]) for row in range(1, row_limit + 401)]
    csv_path = tmp_path / "wide_large.csv"
    csv_path.write_text(
        "\n".join([",".join(headers)] + rows) + "\n",
        encoding="utf-8",
    )

    dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    tree = _find_descendant(dialog, ttk.Treeview)

    assert tree is not None

    _wait_for_rows(dialog, tree, row_limit)
    assert len(tree.get_children()) == row_limit

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

    monkeypatch.setattr(dialog_module._PreviewRefreshControllerBase, "_maybe_start_header_filter_prewarm", lambda *args, **kwargs: None)

    dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    controller = getattr(dialog, "_csv_preview_controller", None)

    assert controller is not None

    original_resolve_header_filter_options = controller._pipeline.resolve_header_filter_options
    resolve_calls = 0

    def counting_resolve_header_filter_options(*args, **kwargs):
        nonlocal resolve_calls
        resolve_calls += 1
        return original_resolve_header_filter_options(*args, **kwargs)

    monkeypatch.setattr(controller._pipeline, "resolve_header_filter_options", counting_resolve_header_filter_options)

    controller.show_header_filter_popup(1, 0, 0)
    dialog.update()
    first_popup = controller._header_filter_popup
    first_listbox = _find_descendant(first_popup, tk.Listbox) if first_popup is not None else None

    assert first_popup is not None
    assert first_listbox is not None

    _wait_for_listbox_values(dialog, first_listbox, ["Beer", "Cocktails"])

    controller.show_header_filter_popup(1, 0, 0)
    dialog.update()

    second_popup = controller._header_filter_popup
    second_listbox = _find_descendant(second_popup, tk.Listbox) if second_popup is not None else None

    assert second_popup is not None
    assert second_listbox is not None
    assert _listbox_values(second_listbox) == ["Beer", "Cocktails"]

    assert resolve_calls in {0, 1}

    dialog.destroy()


def test_resolve_header_filter_options_streams_distinct_values_without_row_snapshot_for_large_unfiltered_file(tmp_path, monkeypatch):
    csv_path = tmp_path / "large_popup.csv"
    rows = [f"Item {index},Category {index % 5}\n" for index in range(PREVIEW_ROW_SAMPLE_SIZE + 20)]
    csv_path.write_text("Name,Category\n" + "".join(rows), encoding="utf-8")

    data = load_csv_preview(csv_path)
    pipeline = dialog_module._PreviewDataPipeline(data)
    filter_state = dialog_module._PreviewFilterState(
        query="",
        combine_sessions=False,
        header_filter_column_index=None,
        header_filter_value=None,
    )

    snapshot_calls = 0
    original_rows_before_header_filter_snapshot = pipeline.rows_before_header_filter_snapshot

    def counting_rows_before_header_filter_snapshot(*args, **kwargs):
        nonlocal snapshot_calls
        snapshot_calls += 1
        return original_rows_before_header_filter_snapshot(*args, **kwargs)

    monkeypatch.setattr(pipeline, "rows_before_header_filter_snapshot", counting_rows_before_header_filter_snapshot)

    options = pipeline.resolve_header_filter_options(filter_state, 1)

    assert options == ["Category 0", "Category 1", "Category 2", "Category 3", "Category 4"]
    assert snapshot_calls == 0


def test_open_csv_preview_dialog_loads_header_filter_values_off_ui_thread(tk_root, tmp_path, monkeypatch):
    csv_path = tmp_path / "async_popup.csv"
    csv_path.write_text(
        "Name,Category\nPeroni,Beer\nNegroni,Cocktails\nAperol,Spritz\n",
        encoding="utf-8",
    )

    dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    controller = getattr(dialog, "_csv_preview_controller", None)

    assert controller is not None

    popup_controller = controller._popup_export_controller
    original_resolve_header_filter_options = controller._pipeline.resolve_header_filter_options

    monkeypatch.setattr(controller._pipeline, "cached_header_filter_options", lambda *args, **kwargs: None)

    def slow_resolve_header_filter_options(*args, **kwargs):
        time.sleep(0.35)
        return original_resolve_header_filter_options(*args, **kwargs)

    monkeypatch.setattr(controller._pipeline, "resolve_header_filter_options", slow_resolve_header_filter_options)

    started = time.monotonic()
    controller.show_header_filter_popup(1, 0, 0)
    elapsed = time.monotonic() - started

    popup = controller._header_filter_popup
    listbox = _find_descendant(popup, tk.Listbox) if popup is not None else None

    assert popup is not None
    assert listbox is not None
    assert elapsed < 0.2
    assert popup_controller._header_filter_popup_empty_var is not None
    assert popup_controller._header_filter_popup_empty_var.get() == "Loading values..."
    assert _listbox_values(listbox) == []

    _wait_for_listbox_values(dialog, listbox, ["Beer", "Cocktails", "Spritz"])

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
    _wait_for_tree_values(dialog, tree, [[long_value, "Peroni"]])

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


def test_open_csv_preview_dialog_can_sort_numeric_column_ascending_and_descending(tk_root, tmp_path):
    csv_path = tmp_path / "numeric_sort.csv"
    csv_path.write_text(
        "Name,Revenue1\nPeroni,2\nNegroni,10\nSpritz,3\n",
        encoding="utf-8",
    )

    dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    controller = getattr(dialog, "_csv_preview_controller", None)
    tree = _find_descendant(dialog, ttk.Treeview)

    assert controller is not None
    assert tree is not None

    _wait_for_rows(dialog, tree, 3)
    controller.show_header_filter_popup(1, 0, 0)
    dialog.update()

    popup = controller._header_filter_popup
    assert popup is not None

    sort_ascending_button = _find_button(popup, "Sort low to high")
    sort_descending_button = _find_button(popup, "Sort high to low")

    assert sort_ascending_button is not None
    assert sort_descending_button is not None

    sort_ascending_button.invoke()
    _wait_for_first_column_values(dialog, tree, ["Peroni", "Spritz", "Negroni"])

    ascending_names = [tree.item(item_id)["values"][0] for item_id in tree.get_children()]
    assert ascending_names == ["Peroni", "Spritz", "Negroni"]
    assert tree.heading("col_1")["text"].endswith("▲")

    controller.show_header_filter_popup(1, 0, 0)
    dialog.update()
    popup = controller._header_filter_popup

    assert popup is not None

    sort_descending_button = _find_button(popup, "Sort high to low")
    assert sort_descending_button is not None

    sort_descending_button.invoke()
    _wait_for_first_column_values(dialog, tree, ["Negroni", "Spritz", "Peroni"])

    descending_names = [tree.item(item_id)["values"][0] for item_id in tree.get_children()]
    assert descending_names == ["Negroni", "Spritz", "Peroni"]
    assert tree.heading("col_1")["text"].endswith("▼")

    dialog.destroy()


def test_open_csv_preview_dialog_can_sort_text_column_ascending_and_descending(tk_root, tmp_path):
    csv_path = tmp_path / "text_sort.csv"
    csv_path.write_text(
        "Name,Category\nPeroni,Beer\nNegroni,Cocktails\nAperol,Spritz\n",
        encoding="utf-8",
    )

    dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    controller = getattr(dialog, "_csv_preview_controller", None)
    tree = _find_descendant(dialog, ttk.Treeview)

    assert controller is not None
    assert tree is not None

    _wait_for_rows(dialog, tree, 3)
    controller.show_header_filter_popup(0, 0, 0)
    dialog.update()

    popup = controller._header_filter_popup
    assert popup is not None

    sort_ascending_button = _find_button(popup, "Sort A to Z")
    sort_descending_button = _find_button(popup, "Sort Z to A")

    assert sort_ascending_button is not None
    assert sort_descending_button is not None

    sort_descending_button.invoke()
    _wait_for_first_column_values(dialog, tree, ["Peroni", "Negroni", "Aperol"])

    descending_names = [tree.item(item_id)["values"][0] for item_id in tree.get_children()]
    assert descending_names == ["Peroni", "Negroni", "Aperol"]
    assert tree.heading("col_0")["text"].endswith("▼")

    controller.show_header_filter_popup(0, 0, 0)
    dialog.update()
    popup = controller._header_filter_popup

    assert popup is not None

    sort_ascending_button = _find_button(popup, "Sort A to Z")
    assert sort_ascending_button is not None

    sort_ascending_button.invoke()
    _wait_for_first_column_values(dialog, tree, ["Aperol", "Negroni", "Peroni"])

    ascending_names = [tree.item(item_id)["values"][0] for item_id in tree.get_children()]
    assert ascending_names == ["Aperol", "Negroni", "Peroni"]
    assert tree.heading("col_0")["text"].endswith("▲")

    dialog.destroy()


def test_open_csv_preview_dialog_restores_saved_sort_on_reopen_and_shows_it_in_summary(tk_root, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DEFAULT_PATH", tmp_path / "settings.json")
    csv_path = tmp_path / "sorted_reopen.csv"
    csv_path.write_text(
        "Name,Category\nPeroni,Beer\nNegroni,Cocktails\nAperol,Spritz\n",
        encoding="utf-8",
    )

    first_dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    first_controller = getattr(first_dialog, "_csv_preview_controller", None)

    assert first_controller is not None

    first_controller.set_sort(0, descending=True)
    first_dialog.update()
    first_dialog.destroy()

    second_dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    tree = _find_descendant(second_dialog, ttk.Treeview)
    summary = _find_descendant(second_dialog, ttk.Label)

    assert tree is not None
    assert summary is not None

    _wait_for_rows(second_dialog, tree, 3)

    values = [tree.item(item_id)["values"][0] for item_id in tree.get_children()]
    assert values == ["Peroni", "Negroni", "Aperol"]
    assert "Sorted by Name (Z to A)" in str(summary.cget("text"))

    second_dialog.destroy()


def test_open_csv_preview_dialog_can_save_current_view_as_new_csv_file(tk_root, tmp_path, monkeypatch):
    csv_path = tmp_path / "sessions.csv"
    csv_path.write_text(
        "Description1,Sessionname1,Quantity1,Revenue1\n"
        "Cuban,Lunch,2,12.5\n"
        "Cuban,Dinner,3,18.5\n"
        "French 75,Lunch,4,20\n",
        encoding="utf-8",
    )
    original_text = csv_path.read_text(encoding="utf-8")
    export_path = tmp_path / "sessions.preview.csv"

    dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    controller = getattr(dialog, "_csv_preview_controller", None)
    tree = _find_descendant(dialog, ttk.Treeview)
    query_entry = _find_descendant(dialog, ttk.Entry)
    combine_toggle = _find_descendant(dialog, ttk.Checkbutton)
    save_button = _find_button(dialog, "Save As CSV")
    seen_info: dict[str, str] = {}

    assert controller is not None
    assert tree is not None
    assert query_entry is not None
    assert combine_toggle is not None
    assert save_button is not None

    query_entry.insert(0, "cuban")
    controller.trigger_refresh_now()
    _wait_for_rows(dialog, tree, 2)
    combine_toggle.invoke()
    _wait_for_rows(dialog, tree, 1)
    controller._apply_visible_columns([0, 1, 2])
    _wait_for_rows(dialog, tree, 1)

    monkeypatch.setattr(dialog_module.filedialog, "asksaveasfilename", lambda **kwargs: str(export_path))
    monkeypatch.setattr(dialog_module.messagebox, "showinfo", lambda title, message: seen_info.update(title=title, message=message))
    monkeypatch.setattr(dialog_module.messagebox, "showerror", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected error dialog")))

    save_button.invoke()

    assert seen_info["title"] == "Save CSV As"
    assert "original CSV was not changed" in seen_info["message"]
    assert csv_path.read_text(encoding="utf-8") == original_text

    with export_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))

    assert rows == [
        ["Description1", "Sessionname1", "Quantity1"],
        ["Cuban", "Lunch + Dinner", "5"],
    ]

    dialog.destroy()


def test_open_csv_preview_dialog_save_as_defaults_to_favorites_csv_exports_folder(tk_root, tmp_path, monkeypatch):
    favorites_dir = tmp_path / "Favorites"
    desktop_dir = tmp_path / "Desktop"
    csv_path = desktop_dir / "sample.csv"
    csv_path.parent.mkdir(parents=True)
    csv_path.write_text("Name,Revenue1\nPeroni,2\n", encoding="utf-8")

    export_dir = favorites_dir / "csv_exports"
    export_path = export_dir / "sample.preview.csv"
    seen_dialog: dict[str, str] = {}

    dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    save_button = _find_button(dialog, "Save As CSV")

    assert save_button is not None

    def fake_asksaveasfilename(**kwargs):
        seen_dialog.update({key: str(value) for key, value in kwargs.items() if key in {"initialdir", "initialfile"}})
        return str(export_path)

    monkeypatch.setattr(dialog_module.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(dialog_module.filedialog, "asksaveasfilename", fake_asksaveasfilename)
    monkeypatch.setattr(dialog_module.messagebox, "showinfo", lambda *args, **kwargs: None)
    monkeypatch.setattr(dialog_module.messagebox, "showerror", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected error dialog")))

    save_button.invoke()

    assert export_dir.exists()
    assert seen_dialog["initialdir"] == str(export_dir)
    assert seen_dialog["initialfile"] == "sample.preview.csv"

    dialog.destroy()


def test_open_csv_preview_dialog_save_as_uses_current_numeric_sort_order(tk_root, tmp_path, monkeypatch):
    csv_path = tmp_path / "sorted_export.csv"
    csv_path.write_text(
        "Name,Revenue1\nPeroni,2\nNegroni,10\nSpritz,3\n",
        encoding="utf-8",
    )
    export_path = tmp_path / "sorted_export.preview.csv"

    dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    controller = getattr(dialog, "_csv_preview_controller", None)
    save_button = _find_button(dialog, "Save As CSV")

    assert controller is not None
    assert save_button is not None

    controller.set_sort(1, descending=True)
    monkeypatch.setattr(dialog_module.filedialog, "asksaveasfilename", lambda **kwargs: str(export_path))
    monkeypatch.setattr(dialog_module.messagebox, "showinfo", lambda *args, **kwargs: None)
    monkeypatch.setattr(dialog_module.messagebox, "showerror", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected error dialog")))

    save_button.invoke()

    with export_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))

    assert rows == [
        ["Name", "Revenue1"],
        ["Negroni", "10"],
        ["Spritz", "3"],
        ["Peroni", "2"],
    ]

    dialog.destroy()


def test_open_csv_preview_dialog_save_as_rejects_original_source_path(tk_root, tmp_path, monkeypatch):
    csv_path = tmp_path / "source.csv"
    csv_path.write_text("A,B\n1,2\n", encoding="utf-8")
    original_text = csv_path.read_text(encoding="utf-8")

    dialog = open_csv_preview_dialog(tk_root, csv_path, width=900, height=520)
    save_button = _find_button(dialog, "Save As CSV")
    seen_error: dict[str, str] = {}

    assert save_button is not None

    monkeypatch.setattr(dialog_module.filedialog, "asksaveasfilename", lambda **kwargs: str(csv_path))
    monkeypatch.setattr(dialog_module.messagebox, "showerror", lambda title, message: seen_error.update(title=title, message=message))
    monkeypatch.setattr(dialog_module.messagebox, "showinfo", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected info dialog")))

    save_button.invoke()

    assert seen_error["title"] == "Save CSV As"
    assert "different destination file" in seen_error["message"]
    assert csv_path.read_text(encoding="utf-8") == original_text

    dialog.destroy()
