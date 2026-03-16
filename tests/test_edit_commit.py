from datetime import datetime, timezone

import tkinter as tk
import pytest

from gp_data.ui import GPDataApp
from gp_data.models import Record


def test_edit_commit_updates_storage(tmp_path):
    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    app.withdraw()

    # add a record
    r = Record(field1="orig", field2="two", field3=10, field5="5", field6=2.0, field7=4.0)
    app.data_manager.save(r)
    app.load_records()

    # select and load into the main form
    app.table.selection_set(r.id)
    app.on_edit()

    # change the name and price in the form
    app.form.entries['field2'].delete(0, tk.END); app.form.entries['field2'].insert(0, 'updated')
    app.form.entries['field3'].delete(0, tk.END); app.form.entries['field3'].insert(0, '12.00')
    app.on_save_changes()

    # verify storage updated
    rows = app.data_manager.load_all()
    assert len(rows) == 1
    assert rows[0].field2 == 'Updated'  # title-cased by model
    assert rows[0].field3 == 12.0
    assert rows[0].last_numeric_field == 'field3'
    assert rows[0].last_numeric_from == pytest.approx(10.0)
    assert rows[0].last_numeric_to == pytest.approx(12.0)
    assert rows[0].last_numeric_changed_at is not None
    summary = app.form.last_numeric_change_var.get()
    assert app.form.labels[0] in summary
    assert 'Orig' in summary
    assert app.form.labels[1] in summary
    assert 'Updated' in summary
    assert app.form.labels[2] in summary
    assert '£10.00' in summary
    assert '£12.00' in summary

    app.destroy()


def test_form_edit_preserves_row_position(tmp_path):
    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    app.withdraw()

    first = Record(field1="orig", field2="first", created_at=datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc))
    second = Record(field1="other", field2="second", created_at=datetime(2026, 3, 15, 12, 1, tzinfo=timezone.utc))
    for record in (first, second):
        app.data_manager.save(record)
    app.load_records()

    assert app.table.get_children() == (second.id, first.id)

    app.table.selection_set(first.id)
    app.on_edit()
    app.form.entries['field2'].delete(0, tk.END)
    app.form.entries['field2'].insert(0, 'updated')
    app.on_save_changes()

    assert app.table.get_children() == (second.id, first.id)

    app.destroy()


def test_form_edit_duplicate_warning_can_cancel_edit(tmp_path, monkeypatch):
    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    app.withdraw()

    first = Record(field1="soft drink", field2="first")
    second = Record(field1="soft drink", field2="second")
    for record in (first, second):
        app.data_manager.save(record)
    app.load_records()

    asked: dict[str, str] = {}

    def fake_askyesno(title, message):
        asked["title"] = title
        asked["message"] = message
        return False

    monkeypatch.setattr("gp_data.ui.app.messagebox.askyesno", fake_askyesno)

    app.table.selection_set(first.id)
    app.on_edit()
    app.form.entries['field2'].delete(0, tk.END)
    app.form.entries['field2'].insert(0, 'second')
    app.on_save_changes()

    rows = app.data_manager.load_all()
    first_row = next(row for row in rows if row.id == first.id)
    assert first_row.field2 == 'First'
    assert asked["title"] == "Duplicate item"
    assert "already exists" in asked["message"]
    assert app.table.get_selected_id() == second.id

    app.destroy()
