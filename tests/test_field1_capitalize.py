from gp_data.models import Record


def test_field1_model_capitalizes():
    r = Record(field1="alice")
    assert r.field1 == "Alice"


def test_field1_model_strips_and_capitalizes():
    r = Record(field1="  bob  ")
    assert r.field1 == "Bob"


def test_field2_model_capitalizes():
    r = Record(field1="X", field2="charlie")
    assert r.field2 == "Charlie"


def test_field2_model_strips_and_capitalizes():
    r = Record(field1="X", field2="  dave  ")
    assert r.field2 == "Dave"


def test_inputform_field1_and_field2_live_capitalize():
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

    # field1
    f.entries['field1'].insert(0, 'alice')
    f._capitalize_field('field1')
    assert f.entries['field1'].get().startswith('Alice')

    # field2
    f.entries['field2'].insert(0, 'bob')
    f._capitalize_field('field2')
    assert f.entries['field2'].get().startswith('Bob')

    root.destroy()
