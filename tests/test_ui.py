import tkinter as tk
import pytest

from gp_data.ui import RecordTable, GPDataApp
from gp_data.models import Record


def test_record_table_hides_id_and_uses_iid():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    root.withdraw()

    table = RecordTable(root)

    # `id` should not be a visible column
    assert "id" not in table["columns"]

    # insert a record and ensure iid is the record.id
    r = Record(field1="alpha")
    item = table.insert_record(r)
    assert item == r.id

    # selecting the row should return the record id
    table.selection_set(item)
    assert table.get_selected_id() == r.id

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

    root.destroy()


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
