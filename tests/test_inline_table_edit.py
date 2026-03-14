import tkinter as tk
import pytest

from gp_data.ui import GPDataApp
from gp_data.models import Record


def test_inline_edit_commit_updates_storage(tmp_path):
    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
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

    app.destroy()


def test_inline_edit_preserves_active_search_filter(tmp_path):
    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not available in this environment")

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

    app.destroy()
