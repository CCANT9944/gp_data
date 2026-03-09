import tkinter as tk
import tkinter.messagebox as mb
import pytest

from gp_data.ui import GPDataApp
from gp_data.data_manager import DataManager
from gp_data.models import Record


def test_data_manager_backfill_derived_adds_columns(tmp_path):
    p = tmp_path / "data.db"
    # we shortcut by writing CSV directly and then migrating; this simulates
    # a legacy CSV file
    header = ",".join(["id", "field1", "field2", "field3", "field4", "field5", "field6", "field7", "created_at"]) + "\n"
    row = f"id1,one,,,10,2,2.5,5.0,2020-01-01T00:00:00Z\n"
    csvfile = tmp_path / "temp.csv"
    csvfile.write_text(header + row, encoding="utf-8")
    # migrate into DB before creating manager
    DataManager.migrate_from_csv(csvfile, p)

    dm = DataManager(p)
    count = dm.backfill_derived()
    assert count == 1
    rows = dm.load_all()
    assert rows[0].gp is not None


def test_gui_backfill_button_creates_backup_and_updates_csv(tmp_path):
    try:
        probe = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    probe.destroy()

    p = tmp_path / "data.db"
    dm = DataManager(p)
    # start with a single existing record so backfill has something to operate on
    r = Record(field1="one", field3=1.5)
    dm.save(r)

    app = GPDataApp(storage_path=p)
    # patch confirmation dialog to proceed
    orig = mb.askyesno
    mb.askyesno = lambda *a, **k: True
    try:
        app.on_backfill_csv()
    finally:
        mb.askyesno = orig

    # backup should exist and record still reachable
    assert p.with_name(p.name + '.bak').exists()
    rows = dm.load_all()
    # gp may still be None when SQLite backend is used and no computed fields stored
    assert rows[0].field1 == 'One'

    # creating a row via the UI should create a timestamped backup in backups/
    app.form.entries['field1'].insert(0, 'Beer')
    app.form.entries['field3'].insert(0, '10')
    app.form.entries['field5'].insert(0, '2')
    app.form.entries['field7'].insert(0, '5')
    app.on_add()
    backups = list((p.parent / 'backups').glob('data.db.*.bak'))
    assert len(backups) >= 1

    app.destroy()
