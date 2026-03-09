import tkinter as tk
import pytest

from gp_data.ui import InputForm


def test_enter_moves_focus_and_wraps():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    root.withdraw()

    frame = tk.Frame(root)
    frame.pack()
    f = InputForm(frame)

    # focus field1, press Enter -> moves to field2
    f.entries['field1'].focus_set()
    evt = type('E', (), {'widget': f.entries['field1']})()
    f._on_enter(evt)
    # use internal marker set by _on_enter (robust in headless tests)
    assert getattr(f, '_last_focused', None) == f.entries['field2']

    # focus last field -> pressing Enter wraps to field1
    f.entries['field7'].focus_set()
    evt2 = type('E', (), {'widget': f.entries['field7']})()
    f._on_enter(evt2)
    assert getattr(f, '_last_focused', None) == f.entries['field1']

    root.destroy()


def test_enter_triggers_field6_recalc():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    root.withdraw()

    frame = tk.Frame(root)
    frame.pack()
    f = InputForm(frame)

    f.entries['field3'].insert(0, '8')
    f.entries['field5'].insert(0, '4')
    evt = type('E', (), {'widget': f.entries['field3']})()
    f._on_enter(evt)

    assert f.entries['field6'].get() == '£2.00'

    root.destroy()
