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


def test_enter_on_last_field_shows_error_when_submit_callback_fails(tmp_path, monkeypatch):
    try:
        probe = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    probe.destroy()

    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not available in this environment")

    seen: dict[str, str] = {}

    def fake_showerror(title, message, parent=None):
        seen["title"] = title
        seen["message"] = message

    monkeypatch.setattr(app.form, "on_submit", lambda: (_ for _ in ()).throw(RuntimeError("submit callback failed")))
    monkeypatch.setattr("gp_data.ui.form.messagebox.showerror", fake_showerror)

    evt = type('E', (), {'widget': app.form.entries['field7']})()
    result = app.form._on_enter(evt)

    assert result == "break"
    assert seen["title"] == "Submit failed"
    assert "submit callback failed" in seen["message"]
    assert app.data_manager.load_all() == []

    app.destroy()


def test_enter_on_last_field_does_not_hide_unexpected_submit_errors(tmp_path, monkeypatch):
    try:
        probe = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    probe.destroy()

    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not available in this environment")

    monkeypatch.setattr(app.form, "on_submit", lambda: (_ for _ in ()).throw(ValueError("unexpected submit bug")))

    evt = type('E', (), {'widget': app.form.entries['field7']})()
    with pytest.raises(ValueError, match="unexpected submit bug"):
        app.form._on_enter(evt)

    app.destroy()
