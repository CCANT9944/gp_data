import tkinter as tk
import pytest

from gp_data.ui import InputForm


def test_gp_uses_cost_multiplier():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    root.withdraw()

    frm = tk.Frame(root)
    frm.pack()
    inp = InputForm(frm)

    # cost = £2.00, menu = £5.00 -> GP = 1 - (2 * 1.2) / 5 = 0.52 -> 52.00%
    # set price/qty so field6 computes to £2.00, and menu=5.00
    inp.entries['field3'].delete(0, tk.END); inp.entries['field3'].insert(0, '10')
    inp.entries['field5'].delete(0, tk.END); inp.entries['field5'].insert(0, '5')
    inp.entries['field7'].delete(0, tk.END); inp.entries['field7'].insert(0, '5')
    inp.recalc_field6()
    inp.recalc_metrics()
    assert inp.metrics_entries['gp'].get() == '52.00%'

    root.destroy()


def test_gp_updates_when_cost_computed():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    root.withdraw()

    frm = tk.Frame(root)
    frm.pack()
    inp = InputForm(frm)

    # set price/quantity so field6 computes to 2.0, menu=5.0 -> GP 52.00%
    inp.entries['field3'].delete(0, tk.END); inp.entries['field3'].insert(0, '10')
    inp.entries['field5'].delete(0, tk.END); inp.entries['field5'].insert(0, '5')
    inp.entries['field7'].delete(0, tk.END); inp.entries['field7'].insert(0, '5')
    inp.recalc_field6()
    inp.recalc_metrics()

    assert inp.entries['field6'].get() == '£2.00'
    assert inp.metrics_entries['gp'].get() == '52.00%'

    root.destroy()


def test_gp_empty_when_menu_missing_or_zero():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    root.withdraw()

    frm = tk.Frame(root)
    frm.pack()
    inp = InputForm(frm)

    inp.set_values({"field6": 2.0, "field7": None})
    inp.recalc_metrics()
    assert inp.metrics_entries['gp'].get() == ''

    inp.set_values({"field6": 2.0, "field7": 0})
    inp.recalc_metrics()
    assert inp.metrics_entries['gp'].get() == ''

    root.destroy()


def test_get_values_tolerates_recalc_field6_tclerror(monkeypatch):
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    root.withdraw()

    frm = tk.Frame(root)
    frm.pack()
    inp = InputForm(frm)
    inp.entries['field1'].insert(0, 'beer')

    monkeypatch.setattr(inp, 'recalc_field6', lambda: (_ for _ in ()).throw(tk.TclError('widget unavailable')))

    values = inp.get_values()

    assert values['field1'] == 'beer'

    root.destroy()


def test_loading_record_values_does_not_expand_input_form_width():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    root.withdraw()

    frm = tk.Frame(root)
    frm.pack()
    inp = InputForm(frm)
    inp.update_idletasks()
    initial_width = inp.winfo_reqwidth()

    inp.set_values(
        {
            "field1": "white wine",
            "field2": "175ml chardonnay reserve",
            "field7": 11.5,
            "numeric_change_history": [
                {
                    "field_name": "field7",
                    "from_value": 9.5,
                    "to_value": 11.5,
                    "changed_at": "2026-03-23T18:30:00+00:00",
                },
                {
                    "field_name": "field3",
                    "from_value": 18.0,
                    "to_value": 19.5,
                    "changed_at": "2026-03-23T18:40:00+00:00",
                },
                {
                    "field_name": "field5",
                    "from_value": 150,
                    "to_value": 175,
                    "changed_at": "2026-03-23T18:50:00+00:00",
                },
            ],
        }
    )
    inp.update_idletasks()

    assert inp.winfo_reqwidth() <= initial_width

    root.destroy()
