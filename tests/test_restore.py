from pathlib import Path
import tkinter as tk
import tkinter.messagebox as mb
import pytest

from gp_data.data_manager import DataManager
from gp_data.ui import GPDataApp
from gp_data.models import Record
import shutil


def test_data_manager_restore_backup(tmp_path: Path):
    p = tmp_path / "data.db"
    dm = DataManager(p)
    # insert initial record and back it up manually
    r1 = dm.save(Record(field1='old'))
    bak = p.with_name(p.name + ".bak")
    shutil.copyfile(str(p), str(bak))
    # modify main DB
    r2 = dm.save(Record(field1='restored'))

    pre = dm.restore_backup()
    assert pre.exists()
    rows = dm.load_all()
    assert any(r.field1.lower() == 'old' for r in rows)


def test_gui_restore_button_restores_backup(tmp_path: Path):
    try:
        probe = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    probe.destroy()

    p = tmp_path / "data.db"
    dm = DataManager(p)
    # similar to non-GUI test: create two states
    dm.save(Record(field1='old'))
    bak = p.with_name(p.name + ".bak")
    shutil.copyfile(str(p), str(bak))
    dm.save(Record(field1='restored'))

    app = GPDataApp(storage_path=p)
    orig = mb.askyesno
    mb.askyesno = lambda *a, **k: True
    try:
        app.on_restore_backup()
    finally:
        mb.askyesno = orig

    # restored state should be reflected in DB
    rows = dm.load_all()
    assert any(r.field1.lower() == 'old' for r in rows)
    # pre-restore backup should exist
    assert p.with_name(p.name + ".pre_restore.bak").exists()

    app.destroy()
