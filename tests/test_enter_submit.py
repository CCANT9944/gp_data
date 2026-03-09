import tkinter as tk
import pytest

from gp_data.ui import GPDataApp


def test_enter_on_last_field_submits(tmp_path):
    # check whether Tk is available (create+destroy a root) then create app
    try:
        probe = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    probe.destroy()

    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    # fill form fields
    app.form.entries['field1'].insert(0, 'beer')
    app.form.entries['field2'].insert(0, 'lager')
    app.form.entries['field3'].insert(0, '10')
    app.form.entries['field4'].insert(0, '700')
    app.form.entries['field5'].insert(0, '28')
    # field6 is computed; field7 is menu price
    app.form.entries['field7'].insert(0, '5')

    # simulate Enter on last field
    evt = type('E', (), {'widget': app.form.entries['field7']})()
    app.form._on_enter(evt)

    rows = app.data_manager.load_all()
    assert len(rows) == 1
    assert rows[0].field1 == 'Beer'  # normalized/title-cased by model

    app.destroy()
