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

    # select and open edit dialog
    app.table.selection_set(r.id)
    app.on_edit()

    # change the name and price in the form
    app.form.entries['field2'].delete(0, tk.END); app.form.entries['field2'].insert(0, 'updated')
    app.form.entries['field3'].delete(0, tk.END); app.form.entries['field3'].insert(0, '12.00')

    # find the Edit dialog's Apply button and invoke it
    apply_btn = None
    for w in app.winfo_children():
        if isinstance(w, tk.Toplevel):
            for child in w.winfo_children():
                if getattr(child, 'cget', lambda x: '')('text') == 'Apply':
                    apply_btn = child
                    break

    assert apply_btn is not None
    apply_btn.invoke()

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
