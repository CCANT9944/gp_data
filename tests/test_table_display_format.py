import tkinter as tk
import pytest

from gp_data.ui import RecordTable
from gp_data.models import Record


def test_table_shows_currency_for_field6():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    root.withdraw()

    table = RecordTable(root)

    r = Record(field1="X", field3=10, field5="4", field6=2.5, field7=19.95)
    table.insert_record(r)

    values = table.item(r.id)["values"]
    cols = list(table["columns"])  # visible columns in order
    assert values[cols.index("field3")] == "\u00A310.00"
    assert values[cols.index("field6")] == "\u00A32.50"
    assert values[cols.index("field7")] == "\u00A319.95"

    # derived metrics should be present and formatted
    assert values[cols.index("gp")] == "84.96%"
    assert values[cols.index("cash_margin")] == "\u00A316.95"
    assert values[cols.index("gp70")] == "\u00A310.00"
    root.destroy()
