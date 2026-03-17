from datetime import datetime, timezone

import tkinter as tk
import pytest

from gp_data.ui import RecordTable
from gp_data.models import Record


def test_inline_edit_commit_updates_storage(app_factory, tmp_path):
    app = app_factory(withdraw=False)
    # keep the app mapped so Treeview bbox() works for inline editor placement

    r = Record(field1="orig", field2="two", field3=10, field5="5", field6=2.0, field7=4.0)
    app.data_manager.save(r)
    app.load_records()
    # ensure geometry is calculated so Treeview.bbox() returns a value
    app.update_idletasks()

    # start inline edit on field2
    app.table.start_cell_edit(r.id, 'field2')
    editor = getattr(app.table, '_editor')
    assert editor is not None
    editor.delete(0, tk.END)
    editor.insert(0, 'updated')

    # commit inline edit
    app.table._commit_edit()

    rows = app.data_manager.load_all()
    assert rows[0].field2 == 'Updated'

    # verify a timestamped backup was created for the inline edit
    backups = list((tmp_path / 'backups').glob('data.db.*.bak'))
    assert len(backups) == 1

    # inline edit price (field3) should update stored field6 (cost)
    # also verify editor is pre-filled with raw numeric value (no £)
    app.table.start_cell_edit(r.id, 'field3')
    editor = getattr(app.table, '_editor')
    assert editor.get() in ("10", "10.0")
    editor.delete(0, tk.END)
    editor.insert(0, '20')
    app.table._commit_edit()

    # a second inline edit should create an additional backup
    backups = list((tmp_path / 'backups').glob('data.db.*.bak'))
    assert len(backups) == 2

    rows = app.data_manager.load_all()
    assert rows[0].field3 == 20.0
    assert rows[0].field6 == pytest.approx(20.0 / 5.0)
    assert rows[0].last_numeric_field == 'field3'
    assert rows[0].last_numeric_from == pytest.approx(10.0)
    assert rows[0].last_numeric_to == pytest.approx(20.0)
    assert rows[0].last_numeric_changed_at is not None
    summary = app.form.last_numeric_change_var.get()
    assert app.form.labels[2] in summary
    assert '£10.00' in summary
    assert '£20.00' in summary



def test_inline_edit_preserves_active_search_filter(app_factory):
    app = app_factory(withdraw=False)

    first = Record(field1="lager", field2="draught")
    second = Record(field1="wine", field2="bottle")
    for record in (first, second):
        app.data_manager.save(record)
    app.load_records()
    app.update_idletasks()

    app._search_entry.insert(0, "draught")
    app.on_search()

    ids = app.table.get_children()
    assert ids == (first.id,)

    app.table.start_cell_edit(first.id, 'field2')
    editor = getattr(app.table, '_editor')
    assert editor is not None
    editor.delete(0, tk.END)
    editor.insert(0, 'draught premium')
    app.table._commit_edit()

    ids_after = app.table.get_children()
    assert ids_after == (first.id,)
    row = app.table.item(first.id)['values']
    assert 'draught premium' in [str(v).lower() for v in row]



def test_inline_edit_preserves_row_position(app_factory):
    app = app_factory(withdraw=False)

    first = Record(field1="lager", field2="first", created_at=datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc))
    second = Record(field1="wine", field2="second", created_at=datetime(2026, 3, 15, 12, 1, tzinfo=timezone.utc))
    for record in (first, second):
        app.data_manager.save(record)
    app.load_records()
    app.update_idletasks()

    assert app.table.get_children() == (second.id, first.id)

    app.table.start_cell_edit(first.id, 'field2')
    editor = getattr(app.table, '_editor')
    assert editor is not None
    editor.delete(0, tk.END)
    editor.insert(0, 'updated')
    app.table._commit_edit()

    assert app.table.get_children() == (second.id, first.id)



def test_inline_edit_field5_invalidates_field6_consistently(app_factory):
    app = app_factory(withdraw=False)

    record = Record(field1="lager", field3=20, field5="5", field6=4.0, field7=7.0)
    app.data_manager.save(record)
    app.load_records()
    app.update_idletasks()

    app.table.start_cell_edit(record.id, 'field5')
    editor = getattr(app.table, '_editor')
    assert editor is not None
    editor.delete(0, tk.END)
    editor.insert(0, 'abc')
    app.table._commit_edit()

    rows = app.data_manager.load_all()
    assert rows[0].field5 == 'abc'
    assert rows[0].field6 is None



def test_inline_edit_duplicate_warning_can_cancel_edit(app_factory, monkeypatch):
    app = app_factory(withdraw=False)

    first = Record(field1="soft drink", field2="first")
    second = Record(field1="soft drink", field2="second")
    for record in (first, second):
        app.data_manager.save(record)
    app.load_records()
    app.update_idletasks()

    asked: dict[str, str] = {}

    def fake_askyesno(title, message):
        asked["title"] = title
        asked["message"] = message
        return False

    monkeypatch.setattr("gp_data.ui.app.messagebox.askyesno", fake_askyesno)

    app.table.start_cell_edit(first.id, 'field2')
    editor = getattr(app.table, '_editor')
    assert editor is not None
    editor.delete(0, tk.END)
    editor.insert(0, 'second')
    app.table._commit_edit()

    rows = app.data_manager.load_all()
    first_row = next(row for row in rows if row.id == first.id)
    assert first_row.field2 == 'First'
    assert asked["title"] == "Duplicate item"
    assert "already exists" in asked["message"]
    assert app.table.get_selected_id() == second.id



def test_inline_edit_commit_failure_keeps_editor_open_and_preserves_value(app_factory, monkeypatch):
    app = app_factory(withdraw=False)

    record = Record(field1="lager", field2="house")
    app.data_manager.save(record)
    app.load_records()
    app.update_idletasks()

    seen: dict[str, str] = {}

    def fake_showerror(title, message, parent=None):
        seen["title"] = title
        seen["message"] = message

    monkeypatch.setattr(app.table, "_on_commit", lambda iid, col, value: (_ for _ in ()).throw(RuntimeError("write failed")))
    monkeypatch.setattr("gp_data.ui.table.messagebox.showerror", fake_showerror)

    app.table.start_cell_edit(record.id, 'field2')
    editor = getattr(app.table, '_editor')
    assert editor is not None
    editor.delete(0, tk.END)
    editor.insert(0, 'updated')

    app.table._commit_edit()

    assert seen["title"] == "Edit failed"
    assert "write failed" in seen["message"]
    assert getattr(app.table, '_editor') is editor
    assert getattr(app.table, '_editing') == (record.id, 'field2')
    assert editor.get() == 'updated'
    rows = app.data_manager.load_all()
    assert rows[0].field2 == 'House'



def test_inline_edit_cancel_clears_state_when_destroy_fails(app_factory, monkeypatch):
    app = app_factory(withdraw=False)

    record = Record(field1="lager", field2="house")
    app.data_manager.save(record)
    app.load_records()
    app.update_idletasks()

    app.table.start_cell_edit(record.id, 'field2')
    editor = getattr(app.table, '_editor')
    assert editor is not None

    original_destroy = editor.destroy
    monkeypatch.setattr(editor, 'destroy', lambda: (_ for _ in ()).throw(tk.TclError('destroy failed')))

    app.table._cancel_edit()

    assert getattr(app.table, '_editor') is None
    assert getattr(app.table, '_editing') is None

    monkeypatch.setattr(editor, 'destroy', original_destroy)



def test_inline_edit_without_callback_clears_state_when_local_apply_fails(tk_root, monkeypatch):
    table = RecordTable(tk_root)
    record = Record(field1="lager", field2="house")
    table.insert_record(record)
    table.update_idletasks()
    table.start_cell_edit(record.id, 'field2')

    editor = getattr(table, '_editor')
    assert editor is not None
    editor.delete(0, tk.END)
    editor.insert(0, 'updated')

    original_item = table.item

    def fake_item(iid, **kwargs):
        if kwargs:
            raise tk.TclError('row update failed')
        return original_item(iid)

    monkeypatch.setattr(table, 'item', fake_item)

    table._commit_edit()

    assert getattr(table, '_editor') is None
    assert getattr(table, '_editing') is None

