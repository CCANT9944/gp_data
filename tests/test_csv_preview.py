import tkinter as tk
from tkinter import ttk

import pytest

from gp_data.ui.csv_preview import CsvPreviewError, load_csv_preview, open_csv_preview_dialog


def _find_descendant(root: tk.Misc, cls):
    for widget in root.winfo_children():
        if isinstance(widget, cls):
            return widget
        found = _find_descendant(widget, cls)
        if found is not None:
            return found
    return None


def _wait_for_rows(window: tk.Misc, tree: ttk.Treeview, expected_count: int) -> None:
    for _ in range(50):
        window.update()
        if len(tree.get_children()) == expected_count:
            return
    assert len(tree.get_children()) == expected_count


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