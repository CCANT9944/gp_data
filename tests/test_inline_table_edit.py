import tkinter as tk
import pytest

from gp_data.ui import GPDataApp
from gp_data.models import Record


def test_inline_edit_commit_updates_storage(tmp_path):
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    root.withdraw()

    app = GPDataApp(storage_path=tmp_path / "data.db")
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

    app.destroy()
    root.destroy()
