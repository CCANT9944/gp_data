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


def test_export_filtered_with_no_visible_rows_writes_empty_export(tmp_path, monkeypatch):
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk not available")
    root.withdraw()

    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not usable for GPDataApp")

    for record in (
        Record(field1="alpha", field2="x"),
        Record(field1="beta", field2="y"),
    ):
        app.data_manager.save(record)
    app.load_records()

    app._search_entry.insert(0, "missing")
    app._search_entry.event_generate('<KeyRelease>')
    app.on_search()
    assert len(app.table.get_children()) == 0

    dest = tmp_path / "empty.csv"
    monkeypatch.setattr("gp_data.ui.filedialog.asksaveasfilename", lambda **kw: str(dest))
    app.on_export()

    exported_text = dest.read_text(encoding="utf-8").lower()
    assert "alpha" not in exported_text
    assert "beta" not in exported_text
    assert exported_text.count("\n") <= 1

    app.destroy()
    root.destroy()


def test_search_prefers_exact_word_over_substring(tmp_path):
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk not available")
    root.withdraw()

    app = GPDataApp(storage_path=tmp_path / "data.db")
    records = [
        Record(field1="gin", field2="beefeater"),
        Record(field1="gin", field2="tanqueray"),
        Record(field1="soft drink", field2="ginger beer"),
    ]
    for record in records:
        app.data_manager.save(record)
    app.load_records()

    app._search_entry.insert(0, "gin")
    app._search_entry.event_generate("<KeyRelease>")
    app.on_search()

    ids = app.table.get_children()
    values = [app.table.item(item_id)["values"] for item_id in ids]
    rendered = {" ".join(str(value).lower() for value in row) for row in values}

    assert len(ids) == 2
    assert any("beefeater" in row for row in rendered)
    assert any("tanqueray" in row for row in rendered)
    assert all("ginger beer" not in row for row in rendered)

    app.destroy()
    root.destroy()
