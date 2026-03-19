import tkinter as tk
from datetime import datetime, timezone
from tkinter import ttk
import pytest

from gp_data import settings as settings_module
from gp_data.ui import RecordTable, GPDataApp
from gp_data.ui.app import DIRTY_MODE_BANNER_BG, EDIT_MODE_BANNER_BG, NEW_MODE_BANNER_BG
from gp_data.ui.table import ROW_TAG_EVEN, ROW_TAG_GP_LOW_EVEN, ROW_TAG_GP_LOW_ODD, ROW_TAG_ODD, SEPARATOR_GLYPH, SEPARATOR_PREFIX, TABLE_HEADING_STYLE, TABLE_STYLE
from gp_data.models import NumericChange, Record


def test_record_table_hides_id_and_uses_iid(tk_root):
    table = RecordTable(tk_root)

    # `id` should not be a visible column
    assert "id" not in table["columns"]
    assert any(str(col).startswith(SEPARATOR_PREFIX) for col in table["columns"])

    # insert a record and ensure iid is the record.id
    r = Record(field1="alpha")
    item = table.insert_record(r)
    assert item == r.id

    # selecting the row should return the record id
    table.selection_set(item)
    assert table.get_selected_id() == r.id
    assert ROW_TAG_ODD in table.item(item)["tags"]

    # ensure table displays Field1 unchanged here (model capitalizes)
    assert r.field1 == "Alpha"

    # update column labels and verify heading text changes
    new_labels = ["A", "B", "C", "D", "E", "F", "G"]
    table.update_column_labels(new_labels)
    assert table.heading("field1")["text"] == "A"

    # compact column widths for numeric fields and derived metric columns
    for c in ("field3", "field4", "field5", "field6", "field7", "gp", "cash_margin", "gp70"):
        assert table.column(c)["width"] == 80
        assert table.column(c)["anchor"] == "e"
        assert table.heading(c)["anchor"] == "e"

    # text columns should be left-aligned
    for c in ("field1", "field2"):
        assert table.column(c)["anchor"] == "w"
        assert table.heading(c)["anchor"] == "w"

    assert table.cget("style") == TABLE_STYLE
    style = ttk.Style(table)
    assert int(style.configure(TABLE_STYLE)["rowheight"]) == 30
    assert int(style.configure(TABLE_STYLE)["borderwidth"]) == 2
    assert int(style.configure(TABLE_HEADING_STYLE)["borderwidth"]) == 2
    separator_cols = [col for col in table["columns"] if str(col).startswith(SEPARATOR_PREFIX)]
    assert separator_cols
    assert table.heading(separator_cols[0])["text"] == SEPARATOR_GLYPH



def test_record_table_applies_alternating_row_tags(tk_root):
    table = RecordTable(tk_root)
    first = Record(field1="alpha")
    second = Record(field1="beta")

    first_id = table.insert_record(first)
    second_id = table.insert_record(second)

    assert ROW_TAG_ODD in table.item(first_id)["tags"]
    assert ROW_TAG_EVEN in table.item(second_id)["tags"]
    assert SEPARATOR_GLYPH in table.item(first_id)["values"]



def test_record_table_reorders_columns_and_calls_callback(tk_root):
    seen: list[list[str]] = []
    table = RecordTable(tk_root, on_column_order_changed=lambda order: seen.append(list(order)))

    moved = table._move_data_column("field7", "field1")

    assert moved is True
    assert table.get_column_order()[0] == "field7"
    assert seen[-1][0] == "field7"



def test_record_table_tracks_column_width_changes(tk_root):
    seen: list[dict[str, int]] = []
    table = RecordTable(tk_root, on_column_widths_changed=lambda widths: seen.append(dict(widths)))

    table.column("field1", width=210)
    table._notify_if_widths_changed()

    assert seen
    assert seen[-1]["field1"] == 210
    assert table.get_column_widths()["field1"] == 210



def test_record_table_gp_header_click_calls_callback(tk_root):
    seen: list[str] = []
    table = RecordTable(tk_root, on_heading_click=lambda column: seen.append(column))
    table._column_name_from_event = lambda event: "gp"  # type: ignore[method-assign]

    event = type("Event", (), {"x": 24, "y": 8})()
    table._on_button_press(event)
    table._on_button_release(event)

    assert seen == ["gp"]



def test_record_table_can_highlight_rows_below_gp_threshold(tk_root):
    table = RecordTable(tk_root)
    low_gp = Record(field1="low", field6=2.0, field7=5.0)
    high_gp = Record(field1="high", field6=1.0, field7=5.0)
    table.load([low_gp, high_gp])

    table.set_gp_highlight_threshold(60)

    assert ROW_TAG_GP_LOW_ODD in table.item(low_gp.id)["tags"]
    assert ROW_TAG_EVEN in table.item(high_gp.id)["tags"]

    table.set_gp_highlight_threshold(None)

    assert ROW_TAG_ODD in table.item(low_gp.id)["tags"]



def test_record_table_hides_columns_and_keeps_visible_order(tk_root):
    seen: list[list[str]] = []
    table = RecordTable(tk_root, on_visible_columns_changed=lambda columns: seen.append(list(columns)))

    table.set_visible_columns(["field1", "field3", "gp"])

    assert table.get_visible_columns() == ["field1", "field3", "gp"]
    assert list(table.cget("displaycolumns")) == ["field1", f"{SEPARATOR_PREFIX}0", "field3", f"{SEPARATOR_PREFIX}1", "gp"]
    assert seen[-1] == ["field1", "field3", "gp"]



def test_record_table_rolls_back_visible_columns_when_callback_fails(tk_root, monkeypatch):
    seen: dict[str, str] = {}
    table = RecordTable(tk_root, on_visible_columns_changed=lambda columns: (_ for _ in ()).throw(RuntimeError("visible callback failed")))
    monkeypatch.setattr("gp_data.ui.table.messagebox.showerror", lambda title, message, parent=None: seen.update({"title": title, "message": message}))

    original_visible = table.get_visible_columns()
    original_display = list(table.cget("displaycolumns"))

    table.set_visible_columns(["field1", "field3", "gp"])

    assert table.get_visible_columns() == original_visible
    assert list(table.cget("displaycolumns")) == original_display
    assert seen["title"] == "Columns not updated"
    assert "visible callback failed" in seen["message"]



def test_double_click_uses_visible_column_mapping_when_columns_are_hidden(tk_root):
    table = RecordTable(tk_root)
    record = Record(field1="whisky", field2="woodford reserve", field3=31.99, field5="28", field6=1.14, field7=5.75)
    table.insert_record(record)
    table.set_visible_columns(["field1", "field2", "field3", "field6", "field7", "gp", "cash_margin", "gp70"])

    seen: list[tuple[str, str]] = []

    def fake_start_cell_edit(iid: str, col: str) -> None:
        seen.append((iid, col))

    table.start_cell_edit = fake_start_cell_edit  # type: ignore[method-assign]
    table.identify_row = lambda y: record.id  # type: ignore[method-assign]
    table.identify_column = lambda x: "#9"  # type: ignore[method-assign]

    event = type("Event", (), {"x": 0, "y": 0})()
    table._on_double_click(event)

    assert seen == [(record.id, "field7")]



def test_record_table_rolls_back_column_widths_when_callback_fails(tk_root, monkeypatch):
    seen: dict[str, str] = {}
    table = RecordTable(tk_root, on_column_widths_changed=lambda widths: (_ for _ in ()).throw(RuntimeError("width callback failed")))
    monkeypatch.setattr("gp_data.ui.table.messagebox.showerror", lambda title, message, parent=None: seen.update({"title": title, "message": message}))

    original_width = int(table.column("field1", "width"))
    table.column("field1", width=210)

    table._notify_if_widths_changed()

    assert int(table.column("field1", "width")) == original_width
    assert seen["title"] == "Column widths not updated"
    assert "width callback failed" in seen["message"]



def test_record_table_rolls_back_column_order_when_callback_fails(tk_root, monkeypatch):
    seen: dict[str, str] = {}
    table = RecordTable(tk_root, on_column_order_changed=lambda order: (_ for _ in ()).throw(RuntimeError("order callback failed")))
    monkeypatch.setattr("gp_data.ui.table.messagebox.showerror", lambda title, message, parent=None: seen.update({"title": title, "message": message}))

    original_order = table.get_column_order()

    moved = table._move_data_column("field7", "field1")

    assert moved is False
    assert table.get_column_order() == original_order
    assert seen["title"] == "Column order not updated"
    assert "order callback failed" in seen["message"]



def test_record_table_shows_error_when_heading_callback_fails(tk_root, monkeypatch):
    seen: dict[str, str] = {}
    table = RecordTable(tk_root, on_heading_click=lambda column: (_ for _ in ()).throw(RuntimeError("heading callback failed")))
    monkeypatch.setattr("gp_data.ui.table.messagebox.showerror", lambda title, message, parent=None: seen.update({"title": title, "message": message}))
    table._column_name_from_event = lambda event: "gp"  # type: ignore[method-assign]

    event = type("Event", (), {"x": 24, "y": 8})()
    table._on_button_press(event)
    table._on_button_release(event)

    assert seen["title"] == "Header action failed"
    assert "heading callback failed" in seen["message"]



def test_app_loads_saved_column_order(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    settings_module.save_settings(
        {
            "labels": ["Type", "Name", "Price", "Quantity", "Units In", "Cost/Unit", "MENU PRICE"],
            "column_order": ["field7", "field1", "field2", "field3", "field4", "field5", "field6", "gp", "cash_margin", "gp70"],
        },
        settings_path,
    )
    monkeypatch.setattr(settings_module, "DEFAULT_PATH", settings_path)

    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    app.withdraw()

    assert app.table.get_column_order()[0] == "field7"
    assert app.table.heading("field7")["text"] == "MENU PRICE"

    app.destroy()


def test_app_loads_saved_column_widths(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    settings_module.save_settings(
        {
            "labels": ["Type", "Name", "Price", "Quantity", "Units In", "Cost/Unit", "MENU PRICE"],
            "column_order": ["field1", "field2", "field3", "field4", "field5", "field6", "field7", "gp", "cash_margin", "gp70"],
            "column_widths": {"field1": 220, "field3": 104, "gp": 96},
        },
        settings_path,
    )
    monkeypatch.setattr(settings_module, "DEFAULT_PATH", settings_path)

    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    app.withdraw()

    assert int(app.table.column("field1", "width")) == 220
    assert int(app.table.column("field3", "width")) == 104
    assert int(app.table.column("gp", "width")) == 96

    app.destroy()


def test_app_loads_saved_visible_columns(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    settings_module.save_settings(
        {
            "labels": ["Type", "Name", "Price", "Quantity", "Units In", "Cost/Unit", "MENU PRICE"],
            "column_order": ["field1", "field2", "field3", "field4", "field5", "field6", "field7", "gp", "cash_margin", "gp70"],
            "column_widths": {"field1": 220},
            "visible_columns": ["field1", "field3", "field7"],
        },
        settings_path,
    )
    monkeypatch.setattr(settings_module, "DEFAULT_PATH", settings_path)

    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    app.withdraw()

    assert app.table.get_visible_columns() == ["field1", "field3", "field7"]
    assert list(app.table.cget("displaycolumns")) == ["field1", f"{SEPARATOR_PREFIX}0", "field3", f"{SEPARATOR_PREFIX}1", "field7"]

    app.destroy()


def test_app_loads_saved_gp_highlight_threshold(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    settings_module.save_settings(
        {
            "labels": ["Type", "Name", "Price", "Quantity", "Units In", "Cost/Unit", "MENU PRICE"],
            "column_order": ["field1", "field2", "field3", "field4", "field5", "field6", "field7", "gp", "cash_margin", "gp70"],
            "column_widths": {"field1": 220},
            "visible_columns": ["field1", "field3", "field7", "gp"],
            "gp_highlight_threshold": 60,
        },
        settings_path,
    )
    monkeypatch.setattr(settings_module, "DEFAULT_PATH", settings_path)

    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    app.withdraw()

    assert app.table.get_gp_highlight_threshold() == 60.0

    app.destroy()


def test_main_controls_show_open_csv_button(app_factory, tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(settings_module, "DEFAULT_PATH", settings_path)
    app = app_factory()

    assert _find_descendant(app, ttk.Button, text="Open CSV") is not None
    assert _find_descendant(app, ttk.Button, text="Last CSV") is not None
    assert _find_descendant(app, ttk.Menubutton, text="Recent CSVs") is not None
    assert str(app._open_last_csv_button.cget("state")) == "disabled"
    assert str(app._open_recent_csv_button.cget("state")) == "disabled"


def test_open_csv_preview_launches_dialog(app_factory, tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(settings_module, "DEFAULT_PATH", settings_path)
    app = app_factory()
    csv_path = tmp_path / "raw.csv"
    csv_path.write_text("A,B,C\n1,2,3\n", encoding="utf-8")

    seen: dict[str, object] = {}

    monkeypatch.setattr("gp_data.ui.app.filedialog.askopenfilename", lambda **kwargs: str(csv_path))
    monkeypatch.setattr("gp_data.ui.app.messagebox.askyesnocancel", lambda *args, **kwargs: True)

    def fake_open(parent, csv_path, *, width, height, has_header_row):
        seen["parent"] = parent
        seen["path"] = csv_path
        seen["width"] = width
        seen["height"] = height
        seen["has_header_row"] = has_header_row
        return None

    monkeypatch.setattr("gp_data.ui.app.open_csv_preview_dialog", fake_open)

    app.on_open_csv_preview()

    assert seen["parent"] is app
    assert seen["path"] == csv_path
    assert seen["has_header_row"] is True
    assert int(seen["width"]) >= app.table.winfo_width()
    assert int(seen["height"]) >= app.table.winfo_height()
    assert app._settings.load_csv_preview_last_path() == str(csv_path)
    assert app._settings.load_csv_preview_recent_paths() == [str(csv_path)]
    assert app._settings.load_csv_preview_has_header_row(str(csv_path)) is True
    assert str(app._open_last_csv_button.cget("state")) == "normal"
    assert str(app._open_recent_csv_button.cget("state")) == "normal"
    assert app._recent_csv_menu.entrycget(0, "label") == str(csv_path)


def test_open_csv_preview_cancel_does_not_launch_dialog(app_factory, tmp_path, monkeypatch):
    monkeypatch.setattr(settings_module, "DEFAULT_PATH", tmp_path / "settings.json")
    app = app_factory()

    monkeypatch.setattr("gp_data.ui.app.filedialog.askopenfilename", lambda **kwargs: "")
    monkeypatch.setattr("gp_data.ui.app.open_csv_preview_dialog", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("dialog should not open")))

    app.on_open_csv_preview()


def test_open_csv_preview_can_generate_default_headers_for_headerless_files(app_factory, tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(settings_module, "DEFAULT_PATH", settings_path)
    app = app_factory()
    csv_path = tmp_path / "raw.csv"
    csv_path.write_text("1,2,3\n4,5,6\n", encoding="utf-8")

    seen: dict[str, object] = {}

    monkeypatch.setattr("gp_data.ui.app.filedialog.askopenfilename", lambda **kwargs: str(csv_path))
    monkeypatch.setattr("gp_data.ui.app.messagebox.askyesnocancel", lambda *args, **kwargs: False)

    def fake_open(parent, csv_path, *, width, height, has_header_row):
        seen["path"] = csv_path
        seen["has_header_row"] = has_header_row
        return None

    monkeypatch.setattr("gp_data.ui.app.open_csv_preview_dialog", fake_open)

    app.on_open_csv_preview()

    assert seen["path"] == csv_path
    assert seen["has_header_row"] is False
    assert app._settings.load_csv_preview_has_header_row(str(csv_path)) is False


def test_open_last_csv_button_enabled_from_saved_settings(tmp_path, monkeypatch):
    csv_path = tmp_path / "saved.csv"
    other_csv_path = tmp_path / "other.csv"
    csv_path.write_text("A,B\n1,2\n", encoding="utf-8")
    other_csv_path.write_text("A,B\n3,4\n", encoding="utf-8")
    settings_path = tmp_path / "settings.json"
    settings_module.save_settings(
        {
            "labels": settings_module.DEFAULT_LABELS,
            "column_order": settings_module.DEFAULT_COLUMN_ORDER,
            "column_widths": settings_module.DEFAULT_COLUMN_WIDTHS,
            "visible_columns": settings_module.DEFAULT_VISIBLE_COLUMNS,
            "gp_highlight_threshold": None,
            "csv_preview_last_path": str(csv_path),
            "csv_preview_recent_paths": [str(csv_path), str(other_csv_path)],
        },
        settings_path,
    )
    monkeypatch.setattr(settings_module, "DEFAULT_PATH", settings_path)

    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    app.withdraw()

    assert str(app._open_last_csv_button.cget("state")) == "normal"
    assert str(app._open_recent_csv_button.cget("state")) == "normal"
    assert app._recent_csv_menu.entrycget(1, "label") == str(other_csv_path)

    app.destroy()


def test_open_last_csv_preview_launches_saved_path(app_factory, tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(settings_module, "DEFAULT_PATH", settings_path)
    app = app_factory()
    csv_path = tmp_path / "saved.csv"
    csv_path.write_text("A,B\n1,2\n", encoding="utf-8")
    app._settings.save_csv_preview_last_path(str(csv_path))
    app._update_open_last_csv_button_state()

    seen: dict[str, object] = {}

    def fake_open(parent, csv_path, *, width, height, has_header_row):
        seen["parent"] = parent
        seen["path"] = csv_path
        seen["has_header_row"] = has_header_row
        return None

    monkeypatch.setattr("gp_data.ui.app.open_csv_preview_dialog", fake_open)
    monkeypatch.setattr("gp_data.ui.app.messagebox.askyesnocancel", lambda *args, **kwargs: True)

    app.on_open_last_csv_preview()

    assert seen["parent"] is app
    assert seen["path"] == csv_path
    assert seen["has_header_row"] is True


def test_open_last_csv_preview_reuses_saved_header_mode(app_factory, tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(settings_module, "DEFAULT_PATH", settings_path)
    app = app_factory()
    csv_path = tmp_path / "saved.csv"
    csv_path.write_text("1,2,3\n4,5,6\n", encoding="utf-8")
    app._settings.save_csv_preview_last_path(str(csv_path))
    app._settings.save_csv_preview_has_header_row(str(csv_path), False)
    app._update_open_last_csv_button_state()

    seen: dict[str, object] = {}

    def fake_open(parent, csv_path, *, width, height, has_header_row):
        seen["path"] = csv_path
        seen["has_header_row"] = has_header_row
        return None

    monkeypatch.setattr("gp_data.ui.app.open_csv_preview_dialog", fake_open)
    monkeypatch.setattr(
        "gp_data.ui.app.messagebox.askyesnocancel",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("header prompt should not be shown")),
    )

    app.on_open_last_csv_preview()

    assert seen["path"] == csv_path
    assert seen["has_header_row"] is False


def test_open_last_csv_preview_shows_processing_message_while_loading(app_factory, tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(settings_module, "DEFAULT_PATH", settings_path)
    app = app_factory()
    csv_path = tmp_path / "saved.csv"
    csv_path.write_text("A,B\n1,2\n", encoding="utf-8")
    app._settings.save_csv_preview_last_path(str(csv_path))
    app._update_open_last_csv_button_state()

    seen: dict[str, object] = {}

    def fake_open(parent, csv_path, *, width, height, has_header_row):
        dialog = parent._csv_preview_status_dialog
        seen["dialog_exists"] = bool(dialog is not None and dialog.winfo_exists())
        seen["dialog_title"] = dialog.title() if dialog is not None else ""
        seen["status_during_open"] = parent._csv_preview_status_var.get()
        seen["path"] = csv_path
        seen["has_header_row"] = has_header_row
        return None

    monkeypatch.setattr("gp_data.ui.app.open_csv_preview_dialog", fake_open)
    monkeypatch.setattr("gp_data.ui.app.messagebox.askyesnocancel", lambda *args, **kwargs: True)

    app.on_open_last_csv_preview()

    assert seen["path"] == csv_path
    assert seen["has_header_row"] is True
    assert seen["dialog_exists"] is True
    assert seen["dialog_title"] == "Processing CSV"
    assert seen["status_during_open"] == "Processing last CSV..."
    assert app._csv_preview_status_var.get() == ""
    assert app._csv_preview_status_dialog is None


def test_csv_preview_processing_dialog_is_centered_over_app(app_factory):
    app = app_factory(withdraw=False)
    app.geometry("900x600+120+140")
    app.update()

    app._set_csv_preview_status("Processing last CSV...")

    dialog = app._csv_preview_status_dialog
    assert dialog is not None
    app.update()
    dialog.update_idletasks()

    app_center_x = app.winfo_rootx() + (app.winfo_width() / 2)
    app_center_y = app.winfo_rooty() + (app.winfo_height() / 2)
    dialog_center_x = dialog.winfo_rootx() + (dialog.winfo_width() / 2)
    dialog_center_y = dialog.winfo_rooty() + (dialog.winfo_height() / 2)

    assert abs(dialog_center_x - app_center_x) <= 20
    assert abs(dialog_center_y - app_center_y) <= 40

    app._clear_csv_preview_status()


def test_open_recent_csv_preview_launches_selected_saved_path(app_factory, tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(settings_module, "DEFAULT_PATH", settings_path)
    app = app_factory()
    first_csv = tmp_path / "first.csv"
    second_csv = tmp_path / "second.csv"
    first_csv.write_text("A,B\n1,2\n", encoding="utf-8")
    second_csv.write_text("A,B\n3,4\n", encoding="utf-8")
    app._settings.save_csv_preview_recent_paths([str(first_csv), str(second_csv)])
    app._settings.save_csv_preview_has_header_row(str(second_csv), True)
    app._update_open_last_csv_button_state()

    seen: dict[str, object] = {}

    def fake_open(parent, csv_path, *, width, height, has_header_row):
        seen["parent"] = parent
        seen["path"] = csv_path
        seen["has_header_row"] = has_header_row
        return None

    monkeypatch.setattr("gp_data.ui.app.open_csv_preview_dialog", fake_open)

    app._recent_csv_menu.invoke(1)

    assert seen["parent"] is app
    assert seen["path"] == second_csv
    assert seen["has_header_row"] is True
    assert app._settings.load_csv_preview_recent_paths()[0] == str(second_csv)


def _menu_index_by_label(menu: tk.Menu, expected: str) -> int:
    end_index = menu.index("end")
    assert end_index is not None
    for index in range(end_index + 1):
        if menu.type(index) == "separator":
            continue
        if menu.entrycget(index, "label") == expected:
            return index
    raise AssertionError(f"Menu label not found: {expected}")


def _find_descendant(root: tk.Misc, cls, text: str | None = None):
    for widget in root.winfo_children():
        if isinstance(widget, cls):
            if text is None:
                return widget
            try:
                if widget.cget("text") == text:
                    return widget
            except tk.TclError:
                pass
        found = _find_descendant(widget, cls, text=text)
        if found is not None:
            return found
    return None

def test_app_gp_heading_click_opens_menu(tmp_path):
    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    app.withdraw()

    seen: list[tuple[int, int]] = []
    app._gp_highlight_menu.tk_popup = lambda x, y: seen.append((x, y))  # type: ignore[method-assign]
    app._show_gp_highlight_menu = lambda: seen.append((app.winfo_pointerx(), app.winfo_pointery()))  # type: ignore[method-assign]

    app._on_table_heading_click("gp")

    assert len(seen) == 1

    app.destroy()


def test_app_warns_when_storage_issue_detected_on_startup(tmp_path, monkeypatch):
    broken_db = tmp_path / "broken.db"
    broken_db.write_text("not a sqlite database", encoding="utf-8")

    seen: dict[str, str] = {}
    monkeypatch.setattr("gp_data.ui.app.messagebox.showwarning", lambda title, message: seen.update({"title": title, "message": message}))

    try:
        app = GPDataApp(storage_path=broken_db)
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    app.withdraw()

    assert seen["title"] == "Storage issue"
    assert "could not fully open" in seen["message"].lower()

    app.destroy()

def test_app_gp_heading_menu_sets_and_clears_highlight_threshold(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(settings_module, "DEFAULT_PATH", settings_path)
    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    app.withdraw()

    low_gp = Record(field1="low", field6=2.0, field7=5.0)
    high_gp = Record(field1="high", field6=1.0, field7=5.0)
    app.data_manager.save(low_gp)
    app.data_manager.save(high_gp)
    app.load_records()

    highlight_index = _menu_index_by_label(app._gp_highlight_menu, "Highlight below 60%")
    app._gp_highlight_menu.invoke(highlight_index)

    assert app.table.get_gp_highlight_threshold() == 60.0
    assert settings_module.load_gp_highlight_threshold(settings_path) == 60.0
    assert any(tag in (ROW_TAG_GP_LOW_ODD, ROW_TAG_GP_LOW_EVEN) for tag in app.table.item(low_gp.id)["tags"])

    clear_index = _menu_index_by_label(app._gp_highlight_menu, "Clear GP highlight")
    app._gp_highlight_menu.invoke(clear_index)

    assert app.table.get_gp_highlight_threshold() is None
    assert settings_module.load_gp_highlight_threshold(settings_path) is None
    assert any(tag in (ROW_TAG_ODD, ROW_TAG_EVEN) for tag in app.table.item(low_gp.id)["tags"])

    app.destroy()


def test_add_can_cancel_when_safety_backup_fails(tmp_path, monkeypatch):
    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    app.withdraw()

    asked: dict[str, str] = {}
    monkeypatch.setattr(app.data_manager, "create_timestamped_backup", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("sharing violation")))

    def fake_askyesno(title, message):
        asked["title"] = title
        asked["message"] = message
        return False

    monkeypatch.setattr("gp_data.ui.app.messagebox.askyesno", fake_askyesno)

    app.form.entries["field1"].insert(0, "Soft Drink")
    app.form.entries["field2"].insert(0, "Cola")
    app.on_add()

    assert app.data_manager.load_all() == []
    assert asked["title"] == "Backup unavailable"
    assert "continue adding this record without creating a backup" in asked["message"].lower()

    app.destroy()

def test_app_gp_heading_menu_custom_threshold(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(settings_module, "DEFAULT_PATH", settings_path)
    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    app.withdraw()

    low_gp = Record(field1="low", field6=2.0, field7=5.0)
    app.data_manager.save(low_gp)
    app.load_records()

    monkeypatch.setattr("gp_data.ui.app.simpledialog.askstring", lambda *args, **kwargs: "55")
    custom_index = _menu_index_by_label(app._gp_highlight_menu, "Custom...")
    app._gp_highlight_menu.invoke(custom_index)

    assert app.table.get_gp_highlight_threshold() == 55.0
    assert settings_module.load_gp_highlight_threshold(settings_path) == 55.0
    assert any(tag in (ROW_TAG_GP_LOW_ODD, ROW_TAG_GP_LOW_EVEN) for tag in app.table.item(low_gp.id)["tags"])

    app.destroy()


def test_form_can_open_full_change_history_dialog(tmp_path):
    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    app.withdraw()

    record = Record(
        field1="alpha",
        field2="house",
        numeric_change_history=[
            NumericChange(field_name="field7", from_value=3.0, to_value=3.5, changed_at=datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc)),
            NumericChange(field_name="field7", from_value=3.5, to_value=4.0, changed_at=datetime(2026, 3, 11, 12, 0, tzinfo=timezone.utc)),
            NumericChange(field_name="field7", from_value=4.0, to_value=4.5, changed_at=datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc)),
            NumericChange(field_name="field7", from_value=4.5, to_value=5.0, changed_at=datetime(2026, 3, 13, 12, 0, tzinfo=timezone.utc)),
            NumericChange(field_name="field7", from_value=5.0, to_value=5.5, changed_at=datetime(2026, 3, 14, 12, 0, tzinfo=timezone.utc)),
        ],
        last_numeric_field="field7",
        last_numeric_from=5.0,
        last_numeric_to=5.5,
        last_numeric_changed_at=datetime(2026, 3, 14, 12, 0, tzinfo=timezone.utc),
    )
    app.data_manager.save(record)
    app.load_records()
    app.table.selection_set(record.id)
    app.on_edit()

    history_window = app.form.open_change_history()
    history_text = _find_descendant(history_window, tk.Text)

    assert history_text is not None
    full_text = history_text.get("1.0", "end")
    assert "2026-03-10 12:00:00 UTC" in full_text
    assert "2026-03-14 12:00:00 UTC" in full_text

    history_window.destroy()
    app.destroy()


def test_add_duplicate_warning_can_cancel_new_record(tmp_path, monkeypatch):
    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    app.withdraw()

    existing = Record(field1="soft drink", field2="frobisher pineapple")
    app.data_manager.save(existing)
    app.load_records()

    asked: dict[str, str] = {}

    def fake_askyesno(title, message):
        asked["title"] = title
        asked["message"] = message
        return False

    monkeypatch.setattr("gp_data.ui.app.messagebox.askyesno", fake_askyesno)

    app.form.entries["field1"].insert(0, "Soft Drink")
    app.form.entries["field2"].insert(0, "Frobisher Pineapple")
    app.form.entries["field3"].insert(0, "24.11")
    app.form.entries["field5"].insert(0, "24")
    app.form.entries["field7"].insert(0, "4.00")
    app.on_add()

    rows = app.data_manager.load_all()
    assert len(rows) == 1
    assert asked["title"] == "Duplicate item"
    assert "already exists" in asked["message"]
    assert app.table.get_selected_id() == existing.id

    app.destroy()


def test_add_duplicate_warning_can_allow_new_record(tmp_path, monkeypatch):
    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    app.withdraw()

    existing = Record(field1="soft drink", field2="frobisher pineapple")
    app.data_manager.save(existing)
    app.load_records()

    monkeypatch.setattr("gp_data.ui.app.messagebox.askyesno", lambda *args, **kwargs: True)

    app.form.entries["field1"].insert(0, "Soft Drink")
    app.form.entries["field2"].insert(0, "Frobisher Pineapple")
    app.form.entries["field3"].insert(0, "24.11")
    app.form.entries["field5"].insert(0, "24")
    app.form.entries["field7"].insert(0, "4.00")
    app.on_add()

    rows = app.data_manager.load_all()
    assert len(rows) == 2
    assert sum(1 for row in rows if row.field1 == "Soft Drink" and row.field2 == "Frobisher Pineapple") == 2

    app.destroy()


def test_record_table_copy_and_delete(tmp_path):
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    root.withdraw()

    table = RecordTable(root)

    r = Record(field1="alpha")
    table.insert_record(r)

    # copy selected id to clipboard
    table.selection_set(r.id)
    table.copy_selected_id_to_clipboard()
    assert root.clipboard_get() == r.id

    # delete selected row
    table.selection_set(r.id)
    table.delete_selected()
    assert table.get_children() == ()

    root.destroy()


def test_field6_autocompute_and_edgecases():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    root.withdraw()

    form_parent = tk.Frame(root)
    form_parent.pack()
    form = RecordTable(root)  # we'll use RecordTable only for UI-independent test of compute via InputForm next

    # create InputForm to test live compute
    from gp_data.ui import InputForm
    inp = InputForm(form_parent)

    # normal division
    inp.entries['field3'].delete(0, tk.END); inp.entries['field3'].insert(0, '10')
    inp.entries['field5'].delete(0, tk.END); inp.entries['field5'].insert(0, '4')
    inp.recalc_field6()
    assert inp.entries['field6'].get() == '£2.50'

    # division by zero -> N/A
    inp.entries['field5'].delete(0, tk.END); inp.entries['field5'].insert(0, '0')
    inp.recalc_field6()
    assert inp.entries['field6'].get() == 'N/A'

    # invalid input -> N/A
    inp.entries['field3'].delete(0, tk.END); inp.entries['field3'].insert(0, 'abc')
    inp.entries['field5'].delete(0, tk.END); inp.entries['field5'].insert(0, '2')
    inp.recalc_field6()
    assert inp.entries['field6'].get() == 'N/A'

    # readonly state
    assert str(inp.entries['field6'].cget('state')) == 'readonly'

    root.destroy()


def test_form_shows_existing_last_numeric_change(tmp_path):
    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    app.withdraw()

    changed_at = datetime(2026, 3, 14, 12, 30, tzinfo=timezone.utc)
    record = Record(
        field1="alpha",
        field2="house",
        field3=10.0,
        last_numeric_field="field7",
        last_numeric_from=4.0,
        last_numeric_to=5.0,
        last_numeric_changed_at=changed_at,
        numeric_change_history=[
            NumericChange(field_name="field3", from_value=3.0, to_value=10.0, changed_at=datetime(2026, 3, 13, 18, 0, tzinfo=timezone.utc)),
            NumericChange(field_name="field7", from_value=4.0, to_value=5.0, changed_at=changed_at),
        ],
    )
    app.data_manager.save(record)
    app.load_records()
    app.table.selection_set(record.id)
    app.on_edit()

    summary = app.form.last_numeric_change_var.get()
    assert app.form.labels[0] in summary
    assert 'Alpha' in summary
    assert app.form.labels[1] in summary
    assert 'House' in summary
    assert app.form.labels[2] in summary
    assert '£3.00' in summary
    assert '£10.00' in summary
    assert app.form.labels[6] in summary
    assert '£4.00' in summary
    assert '£5.00' in summary
    assert '2026-03-14 12:30:00 UTC' in summary
    app.destroy()


def test_form_shows_selected_item_when_no_changes_exist(tmp_path):
    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    app.withdraw()

    record = Record(field1="lager", field2="house")
    app.data_manager.save(record)
    app.load_records()
    app.table.selection_set(record.id)
    app.on_edit()

    summary = app.form.last_numeric_change_var.get()
    assert app.form.labels[0] in summary
    assert 'Lager' in summary
    assert app.form.labels[1] in summary
    assert 'House' in summary
    assert 'No changes recorded' in summary
    app.destroy()


def test_app_shows_newest_records_first(tmp_path):
    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    app.withdraw()

    older = Record(field1="older", created_at=datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc))
    newer = Record(field1="newer", created_at=datetime(2026, 3, 15, 12, 1, tzinfo=timezone.utc))
    for record in (older, newer):
        app.data_manager.save(record)

    app.load_records()

    assert app.table.get_children() == (newer.id, older.id)

    app.destroy()


def test_app_type_heading_click_opens_type_filter_menu(tmp_path):
    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    app.withdraw()

    for record in (
        Record(field1="wine", field2="house"),
        Record(field1="beer", field2="lager"),
    ):
        app.data_manager.save(record)

    seen: list[tuple[int, int]] = []
    app._type_filter_menu.tk_popup = lambda x, y: seen.append((x, y))  # type: ignore[method-assign]

    app._on_table_heading_click("field1")

    assert len(seen) == 1
    assert app._type_filter_menu.index("end") is not None
    assert app._type_filter_menu.entrycget(0, "label") == "Beer"
    assert app._type_filter_menu.entrycget(1, "label") == "Wine"
    assert app._type_filter_menu.entrycget(app._type_filter_menu.index("end"), "label") == "Remove type filter"

    app.destroy()


def test_app_type_filter_menu_can_apply_and_clear(tmp_path):
    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    app.withdraw()

    gin = Record(field1="gin", field2="house", created_at=datetime(2026, 3, 15, 12, 2, tzinfo=timezone.utc))
    vodka = Record(field1="vodka", field2="rail", created_at=datetime(2026, 3, 15, 12, 1, tzinfo=timezone.utc))
    wine = Record(field1="wine", field2="glass", created_at=datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc))
    for record in (gin, vodka, wine):
        app.data_manager.save(record)

    app.load_records()
    assert app.table.get_children() == (gin.id, vodka.id, wine.id)

    app._on_table_heading_click("field1")
    gin_index = _menu_index_by_label(app._type_filter_menu, "Gin")
    app._type_filter_menu.invoke(gin_index)

    assert app.table.get_children() == (gin.id,)

    app._on_table_heading_click("field1")
    clear_index = _menu_index_by_label(app._type_filter_menu, "Remove type filter")
    app._type_filter_menu.invoke(clear_index)

    assert app.table.get_children() == (gin.id, vodka.id, wine.id)

    app.destroy()


def test_main_controls_hide_add_button_and_keep_new_item(tmp_path):
    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    app.withdraw()

    button_labels = [
        child.cget("text")
        for child in app.winfo_children()
        if isinstance(child, ttk.Frame)
        for child in child.winfo_children()
        if isinstance(child, ttk.Button)
    ]

    assert "New item" in button_labels
    assert "Add" not in button_labels
    assert "Save changes" in button_labels
    assert "Edit selected" not in button_labels
    assert str(app._save_changes_button.cget("state")) == "disabled"
    assert str(app._delete_selected_button.cget("state")) == "disabled"

    app.destroy()


def test_app_opens_tall_enough_to_show_main_controls(tmp_path):
    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not available in this environment")

    app.update_idletasks()
    new_item_button = _find_descendant(app, ttk.Button, text="New item")

    assert new_item_button is not None
    controls = new_item_button.nametowidget(new_item_button.winfo_parent())
    assert controls.winfo_y() + controls.winfo_height() <= app.winfo_height()

    app.destroy()


def test_main_controls_do_not_show_import_button(tmp_path):
    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    app.withdraw()

    assert _find_descendant(app, ttk.Button, text="Import CSV") is None

    app.destroy()


def test_save_changes_without_selection_shows_edit_prompt(tmp_path, monkeypatch):
    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    app.withdraw()

    seen: dict[str, str] = {}

    def fake_showinfo(title, message):
        seen["title"] = title
        seen["message"] = message

    monkeypatch.setattr("gp_data.ui.app.messagebox.showinfo", fake_showinfo)

    app.on_save_changes()

    assert seen["title"] == "Select"
    assert seen["message"] == "Please select a record to edit."

    app.destroy()


def test_delete_without_selection_shows_delete_prompt(tmp_path, monkeypatch):
    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    app.withdraw()

    seen: dict[str, str] = {}

    def fake_showinfo(title, message):
        seen["title"] = title
        seen["message"] = message

    monkeypatch.setattr("gp_data.ui.app.messagebox.showinfo", fake_showinfo)

    app.on_delete()

    assert seen["title"] == "Select"
    assert seen["message"] == "Please select a record to delete."

    app.destroy()


def test_confirmed_delete_removes_record_and_resets_form(tmp_path, monkeypatch):
    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    app.withdraw()

    record = Record(field1="lager", field2="house")
    app.data_manager.save(record)
    app.load_records()
    app.table.selection_set(record.id)
    app.on_edit()

    monkeypatch.setattr("gp_data.ui.app.messagebox.askyesno", lambda title, message: True)

    app.on_delete()

    assert app.data_manager.load_all() == []
    assert app.table.get_children() == ()
    assert app.form.current_record_id is None

    app.destroy()


def test_rename_fields_shows_error_and_keeps_existing_labels_when_settings_save_fails(tmp_path, monkeypatch):
    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    app.withdraw()

    original_label = app.form.labels[0]
    seen: dict[str, str] = {}

    def fake_showerror(title, message, parent=None):
        seen["title"] = title
        seen["message"] = message

    monkeypatch.setattr(app.form, "_save_labels", lambda labels: (_ for _ in ()).throw(OSError("settings locked")))
    monkeypatch.setattr("gp_data.ui.form.messagebox.showerror", fake_showerror)

    rename_window = app.form.rename_fields()
    entries = [widget for widget in rename_window.winfo_children() if isinstance(widget, ttk.Entry)]
    apply_button = _find_descendant(rename_window, ttk.Button, text="Apply")

    assert entries
    assert apply_button is not None

    entries[0].delete(0, tk.END)
    entries[0].insert(0, "Product")
    apply_button.invoke()

    assert seen["title"] == "Rename failed"
    assert "settings locked" in seen["message"]
    assert app.form.labels[0] == original_label
    assert app.form.grid_slaves(row=0, column=0)[0].cget("text") == original_label
    assert app.table.heading("field1")["text"] == original_label
    assert rename_window.winfo_exists() == 1

    rename_window.destroy()
    app.destroy()


def test_rename_fields_rolls_back_when_table_label_update_fails(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(settings_module, "DEFAULT_PATH", settings_path)

    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    app.withdraw()

    original_label = app.form.labels[0]
    seen: dict[str, str] = {}

    def fake_showerror(title, message, parent=None):
        seen["title"] = title
        seen["message"] = message

    monkeypatch.setattr(app.table, "update_column_labels", lambda labels: (_ for _ in ()).throw(tk.TclError("table unavailable")))
    monkeypatch.setattr("gp_data.ui.form.messagebox.showerror", fake_showerror)

    rename_window = app.form.rename_fields()
    entries = [widget for widget in rename_window.winfo_children() if isinstance(widget, ttk.Entry)]
    apply_button = _find_descendant(rename_window, ttk.Button, text="Apply")

    assert entries
    assert apply_button is not None

    entries[0].delete(0, tk.END)
    entries[0].insert(0, "Product")
    apply_button.invoke()

    assert seen["title"] == "Rename failed"
    assert "table unavailable" in seen["message"]
    assert app.form.labels[0] == original_label
    assert app.form.grid_slaves(row=0, column=0)[0].cget("text") == original_label
    assert app.table.heading("field1")["text"] == original_label
    assert settings_module.load_labels(settings_path)[0] == original_label
    assert rename_window.winfo_exists() == 1

    rename_window.destroy()
    app.destroy()


def test_app_warns_once_when_visible_columns_settings_cannot_be_saved(tmp_path, monkeypatch):
    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    app.withdraw()

    seen: list[tuple[str, str]] = []

    monkeypatch.setattr(app._settings, "save_visible_columns", lambda columns: (_ for _ in ()).throw(OSError("settings locked")))
    monkeypatch.setattr("gp_data.ui.app.messagebox.showwarning", lambda title, message: seen.append((title, message)))

    app.on_visible_columns_changed(["field1", "field2"])
    app.on_visible_columns_changed(["field1", "field3"])

    assert len(seen) == 1
    assert seen[0][0] == "Settings not saved"
    assert "visible columns" in seen[0][1].lower()
    assert "settings locked" in seen[0][1].lower()

    app.destroy()


def test_main_controls_show_search_label(tmp_path):
    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    app.withdraw()

    label_texts = [
        child.cget("text")
        for child in app.winfo_children()
        if isinstance(child, ttk.Frame)
        for child in child.winfo_children()
        if isinstance(child, ttk.Label)
    ]

    assert "Search" in label_texts

    app.destroy()


def test_new_item_clears_form_and_selection(tmp_path):
    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    app.withdraw()

    record = Record(field1="gin", field2="house")
    app.data_manager.save(record)
    app.load_records()

    app.table.selection_set(record.id)
    app._on_table_select()

    assert app.form.entries["field1"].get() == "Gin"
    assert app.form.entries["field2"].get() == "House"
    assert app.table.get_selected_id() == record.id
    assert app._form_mode_var.get() == "EDITING: Gin / House"
    assert app._form_mode_label.cget("bg") == EDIT_MODE_BANNER_BG
    assert str(app._save_changes_button.cget("state")) == "normal"
    assert str(app._delete_selected_button.cget("state")) == "normal"

    app.on_new_item()

    assert app.form.current_record_id is None
    assert app.form.entries["field1"].get() == ""
    assert app.form.entries["field2"].get() == ""
    assert app.table.get_selected_id() is None
    assert app._form_mode_var.get() == "NEW ITEM MODE"
    assert app._form_mode_label.cget("bg") == NEW_MODE_BANNER_BG
    assert str(app._save_changes_button.cget("state")) == "disabled"
    assert str(app._delete_selected_button.cget("state")) == "disabled"

    app.destroy()


def test_new_item_can_cancel_discarding_unsaved_changes(tmp_path, monkeypatch):
    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    app.withdraw()

    asked: dict[str, str] = {}

    def fake_askyesno(title, message):
        asked["title"] = title
        asked["message"] = message
        return False

    monkeypatch.setattr("gp_data.ui.app.messagebox.askyesno", fake_askyesno)

    app.form.entries["field1"].insert(0, "Gin")
    app.form.entries["field2"].insert(0, "House")

    app.on_new_item()

    assert app.form.current_record_id is None
    assert app.form.entries["field1"].get() == "Gin"
    assert app.form.entries["field2"].get() == "House"
    assert app.table.get_selected_id() is None
    assert asked["title"] == "Discard changes"
    assert "unsaved changes" in asked["message"]

    app.destroy()


def test_new_item_dirty_state_updates_mode_banner(tmp_path):
    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    app.withdraw()

    app.form.entries["field1"].insert(0, "Gin")
    app.form._notify_dirty_state()

    assert app._form_mode_var.get() == "NEW ITEM MODE (UNSAVED CHANGES)"
    assert app._form_mode_label.cget("bg") == DIRTY_MODE_BANNER_BG

    app.destroy()


def test_selecting_row_updates_mode_label_and_enables_save(tmp_path):
    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    app.withdraw()

    record = Record(field1="vodka", field2="house")
    app.data_manager.save(record)
    app.load_records()

    assert app._form_mode_var.get() == "NEW ITEM MODE"
    assert app._form_mode_label.cget("bg") == NEW_MODE_BANNER_BG
    assert str(app._save_changes_button.cget("state")) == "disabled"
    assert str(app._delete_selected_button.cget("state")) == "disabled"

    app.table.selection_set(record.id)
    app._on_table_select()

    assert app._form_mode_var.get() == "EDITING: Vodka / House"
    assert app._form_mode_label.cget("bg") == EDIT_MODE_BANNER_BG
    assert str(app._save_changes_button.cget("state")) == "normal"
    assert str(app._delete_selected_button.cget("state")) == "normal"

    app.destroy()


def test_selecting_new_row_can_cancel_discarding_unsaved_changes(tmp_path, monkeypatch):
    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    app.withdraw()

    first = Record(field1="gin", field2="house")
    second = Record(field1="vodka", field2="rail")
    app.data_manager.save(first)
    app.data_manager.save(second)
    app.load_records()

    asked: dict[str, str] = {}

    def fake_askyesno(title, message):
        asked["title"] = title
        asked["message"] = message
        return False

    monkeypatch.setattr("gp_data.ui.app.messagebox.askyesno", fake_askyesno)

    app.table.selection_set(first.id)
    app._on_table_select()
    app.form.entries["field2"].delete(0, tk.END)
    app.form.entries["field2"].insert(0, "changed")
    app.form._notify_dirty_state()

    app.table.selection_set(second.id)
    app._on_table_select()

    assert app.table.get_selected_id() == first.id
    assert app.form.current_record_id == first.id
    assert app.form.entries["field2"].get() == "changed"
    assert app._form_mode_var.get() == "EDITING: Gin / House (UNSAVED CHANGES)"
    assert asked["title"] == "Discard changes"
    assert "unsaved changes" in asked["message"]

    app.destroy()


def test_editing_dirty_state_updates_mode_banner(tmp_path):
    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    app.withdraw()

    record = Record(field1="gin", field2="house")
    app.data_manager.save(record)
    app.load_records()

    app.table.selection_set(record.id)
    app._on_table_select()
    app.form.entries["field2"].delete(0, tk.END)
    app.form.entries["field2"].insert(0, "changed")
    app.form._notify_dirty_state()

    assert app._form_mode_var.get() == "EDITING: Gin / House (UNSAVED CHANGES)"
    assert app._form_mode_label.cget("bg") == DIRTY_MODE_BANNER_BG

    app.destroy()


def test_delete_can_cancel_discarding_unsaved_changes(tmp_path, monkeypatch):
    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    app.withdraw()

    record = Record(field1="gin", field2="house")
    app.data_manager.save(record)
    app.load_records()
    app.table.selection_set(record.id)
    app.on_edit()
    app.form.entries["field2"].delete(0, tk.END)
    app.form.entries["field2"].insert(0, "changed")

    asked: list[tuple[str, str]] = []

    def fake_askyesno(title, message):
        asked.append((title, message))
        return False

    monkeypatch.setattr("gp_data.ui.app.messagebox.askyesno", fake_askyesno)

    app.on_delete()

    assert app.data_manager.load_all()[0].field2 == "House"
    assert asked == [("Discard changes", "You have unsaved changes in the form.\n\nDiscard them?")]

    app.destroy()


def test_close_can_cancel_discarding_unsaved_changes(tmp_path, monkeypatch):
    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    app.withdraw()

    app.form.entries["field1"].insert(0, "Gin")
    asked: dict[str, str] = {}
    destroyed = {"called": False}
    original_destroy = app.destroy

    def fake_askyesno(title, message):
        asked["title"] = title
        asked["message"] = message
        return False

    monkeypatch.setattr("gp_data.ui.app.messagebox.askyesno", fake_askyesno)
    monkeypatch.setattr(app, "destroy", lambda: destroyed.update({"called": True}))

    app.on_close()

    assert asked["title"] == "Discard changes"
    assert "unsaved changes" in asked["message"]
    assert destroyed["called"] is False

    monkeypatch.setattr(app, "destroy", original_destroy)
    app.destroy()


def test_enter_in_last_field_saves_selected_record(tmp_path):
    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    app.withdraw()

    record = Record(field1="gin", field2="house", field3=10.0, field5="5", field7=4.0)
    app.data_manager.save(record)
    app.load_records()

    app.table.selection_set(record.id)
    app.on_edit()
    app.form.entries["field2"].delete(0, tk.END)
    app.form.entries["field2"].insert(0, "updated")
    app.form._on_enter(type("Event", (), {"widget": app.form.entries["field7"]})())

    saved = app.data_manager.load_all()[0]
    assert saved.field2 == "Updated"
    assert app.form.current_record_id == record.id

    app.destroy()
