import tkinter as tk
import pytest

from gp_data.ui import GPDataApp
from gp_data.models import Record


def test_search_filters_table(tmp_path):
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk not available")
    root.withdraw()

    app = GPDataApp(storage_path=tmp_path / "data.db")
    # add a few records
    a = Record(field1="apple", field2="fruit")
    b = Record(field1="banana", field2="fruit")
    c = Record(field1="carrot", field2="vegetable")
    for r in (a, b, c):
        app.data_manager.save(r)
    app.load_records()

    # search for "ban" should show only banana (invoke live behaviour)
    for ch in "ban":
        app._search_entry.insert('end', ch)
        # simulate event and call handler explicitly
        app._search_entry.event_generate('<KeyRelease>')
        app.on_search()
    ids = app.table.get_children()
    assert len(ids) == 1
    row = app.table.item(ids[0])['values']
    assert 'banana' in [str(v).lower() for v in row]

    # backspace should clear letter-by-letter
    app._search_entry.delete(2, 'end')
    app._search_entry.event_generate('<KeyRelease>')
    app.on_search()
    # now query 'ba' still matches banana
    ids = app.table.get_children()
    assert len(ids) == 1

    # clear completely by deleting all text (should reload whole table)
    app._search_entry.delete(0, 'end')
    app._search_entry.event_generate('<KeyRelease>')
    app.on_search()
    ids2 = app.table.get_children()
    assert len(ids2) == 3

    app.destroy()
    root.destroy()


def test_export_filtered(tmp_path, monkeypatch):
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk not available")
    root.withdraw()

    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not usable for GPDataApp")
    # prepare dataset
    a = Record(field1="alpha", field2="x")
    b = Record(field1="beta", field2="y")
    c = Record(field1="gamma", field2="z")
    for r in (a, b, c):
        app.data_manager.save(r)
    app.load_records()

    # filter to beta only
    app._search_entry.insert(0, "beta")
    app._search_entry.event_generate('<KeyRelease>')
    app.on_search()

    dest = tmp_path / "out.csv"
    monkeypatch.setattr("gp_data.ui.filedialog.asksaveasfilename", lambda **kw: str(dest))
    # perform export
    app.on_export()

    txt = dest.read_text().lower()
    assert "beta" in txt
    assert "alpha" not in txt
    assert "gamma" not in txt

    app.destroy()
    root.destroy()
