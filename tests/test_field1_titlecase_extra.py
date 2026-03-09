from gp_data.models import Record


def test_field1_and_field2_titlecase_multiple_words():
    r = Record(field1="mary jane", field2="anne-marie o'connor")
    assert r.field1 == "Mary Jane"
    assert r.field2 == "Anne-Marie O'Connor"


def test_inputform_multword_titlecase():
    import tkinter as tk
    try:
        root = tk.Tk()
    except tk.TclError:
        import pytest
        pytest.skip("Tk not available in this environment")
    root.withdraw()

    from gp_data.ui import InputForm
    frame = tk.Frame(root)
    frame.pack()
    f = InputForm(frame)

    f.entries['field1'].insert(0, 'mary jane')
    f._capitalize_field('field1')
    assert f.entries['field1'].get() == 'Mary Jane'

    f.entries['field2'].insert(0, "anne-marie o'connor")
    f._capitalize_field('field2')
    assert f.entries['field2'].get() == "Anne-Marie O'Connor"

    root.destroy()
