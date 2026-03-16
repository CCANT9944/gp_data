import tkinter as tk
from datetime import datetime, timezone
from tkinter import ttk
import pytest

from gp_data import settings as settings_module
from gp_data.ui import RecordTable, GPDataApp
from gp_data.ui.table import ROW_TAG_EVEN, ROW_TAG_ODD, SEPARATOR_GLYPH, SEPARATOR_PREFIX, TABLE_HEADING_STYLE, TABLE_STYLE
from gp_data.models import NumericChange, Record


def test_record_table_hides_id_and_uses_iid():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    root.withdraw()

    table = RecordTable(root)

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

    root.destroy()


def test_record_table_applies_alternating_row_tags():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    root.withdraw()

    table = RecordTable(root)
    first = Record(field1="alpha")
    second = Record(field1="beta")

    first_id = table.insert_record(first)
    second_id = table.insert_record(second)

    assert ROW_TAG_ODD in table.item(first_id)["tags"]
    assert ROW_TAG_EVEN in table.item(second_id)["tags"]
    assert SEPARATOR_GLYPH in table.item(first_id)["values"]

    root.destroy()


def test_record_table_reorders_columns_and_calls_callback():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    root.withdraw()

    seen: list[list[str]] = []
    table = RecordTable(root, on_column_order_changed=lambda order: seen.append(list(order)))

    moved = table._move_data_column("field7", "field1")

    assert moved is True
    assert table.get_column_order()[0] == "field7"
    assert seen[-1][0] == "field7"

    root.destroy()


def test_record_table_tracks_column_width_changes():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    root.withdraw()

    seen: list[dict[str, int]] = []
    table = RecordTable(root, on_column_widths_changed=lambda widths: seen.append(dict(widths)))

    table.column("field1", width=210)
    table._notify_if_widths_changed()

    assert seen
    assert seen[-1]["field1"] == 210
    assert table.get_column_widths()["field1"] == 210

    root.destroy()


def test_record_table_hides_columns_and_keeps_visible_order():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    root.withdraw()

    seen: list[list[str]] = []
    table = RecordTable(root, on_visible_columns_changed=lambda columns: seen.append(list(columns)))

    table.set_visible_columns(["field1", "field3", "gp"])

    assert table.get_visible_columns() == ["field1", "field3", "gp"]
    assert list(table.cget("displaycolumns")) == ["field1", f"{SEPARATOR_PREFIX}0", "field3", f"{SEPARATOR_PREFIX}1", "gp"]
    assert seen[-1] == ["field1", "field3", "gp"]

    root.destroy()


def test_double_click_uses_visible_column_mapping_when_columns_are_hidden():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk not available in this environment")

    table = RecordTable(root)
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

    root.destroy()


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

    app.on_new_item()

    assert app.form.current_record_id is None
    assert app.form.entries["field1"].get() == ""
    assert app.form.entries["field2"].get() == ""
    assert app.table.get_selected_id() is None

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
