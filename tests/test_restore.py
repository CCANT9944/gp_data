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


def test_main_window_uses_manage_backups_instead_of_restore_button(tmp_path: Path):
    try:
        probe = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    probe.destroy()

    try:
        app = GPDataApp(storage_path=tmp_path / "data.db")
    except tk.TclError:
        pytest.skip("Tk not usable for GPDataApp in this environment")

    buttons = []
    for child in app.winfo_children():
        for grandchild in child.winfo_children():
            if isinstance(grandchild, tk.Button):
                buttons.append(grandchild.cget("text"))
            else:
                try:
                    buttons.append(grandchild.cget("text"))
                except Exception:
                    pass

    assert "Manage backups" in buttons
    assert "Restore backup" not in buttons

    app.destroy()
