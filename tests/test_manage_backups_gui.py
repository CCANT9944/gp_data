import tkinter as tk
import tkinter.messagebox as mb
import pytest

from gp_data.ui import GPDataApp
from gp_data.data_manager import DataManager
from gp_data.models import Record


def test_manage_backups_dialog_lists_and_allows_delete_and_restore(tmp_path):
    try:
        probe = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    probe.destroy()

    p = tmp_path / "data.db"
    dm = DataManager(p)
    # create base data and two backups by saving records
    dm.save(Record(field1='one'))
    b1 = dm.create_timestamped_backup()
    dm.save(Record(field1='changed'))
    b2 = dm.create_timestamped_backup()
    try:
        app = GPDataApp(storage_path=p)
    except tk.TclError:
        pytest.skip("Tk not usable for GPDataApp in this environment")

    # open dialog
    dlg = app.on_manage_backups()
    # helper: find descendant widget by class
    def _find(root, cls):
        for w in root.winfo_children():
            if isinstance(w, cls):
                return w
            res = _find(w, cls)
            if res:
                return res
        return None

    lb = _find(dlg, tk.Listbox)
    assert lb is not None

# determine index for b1 in the listbox and select it
    names = lb.get(0, 'end')
    try:
        idx_b1 = names.index(b1.name)
    except ValueError:
        idx_b1 = None
    assert idx_b1 is not None
    lb.selection_clear(0, 'end')
    lb.selection_set(idx_b1)
    lb.event_generate('<<ListboxSelect>>')

    # patch confirmation dialogs
    orig = mb.askyesno
    mb.askyesno = lambda *a, **k: True
    try:
        # find Delete and Restore buttons by scanning for ttk.Button
        flat_buttons = []
        for c in dlg.winfo_children():
            for ch in c.winfo_children():
                if getattr(ch, 'cget', None):
                    try:
                        if ch.cget('text') in ('Delete', 'Restore'):
                            flat_buttons.append(ch)
                    except Exception:
                        pass
        btn_map = {b.cget('text'): b for b in flat_buttons}
        delete_btn = btn_map['Delete']
        restore_btn = btn_map['Restore']

        # ensure delete button is enabled then invoke
        assert str(delete_btn.cget('state')) in ('normal', 'active')
        delete_btn.invoke()
        # UI may remove the entry or the file itself may be deleted; accept either
        names_after = lb.get(0, 'end')
        assert (b1.name not in names_after) or (not b1.exists())

        # select the remaining (newest) backup and restore it
        names = lb.get(0, 'end')
        idx_b2 = names.index(b2.name)
        lb.selection_clear(0, 'end')
        lb.selection_set(idx_b2)
        lb.event_generate('<<ListboxSelect>>')
        restore_btn.invoke()
        # restored contents should match the backup (contains 'changed'?)
        dm = DataManager(p)
        rows = dm.load_all()
        assert any(r.field1.lower() == 'changed' for r in rows)
    finally:
        mb.askyesno = orig

    dlg.destroy()
    app.destroy()