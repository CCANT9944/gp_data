from datetime import datetime
from pathlib import Path
import tkinter as tk
import tkinter.messagebox as mb
import pytest

from gp_data.ui import GPDataApp
from gp_data.ui.backup_dialog import _build_backup_preview, open_manage_backups_dialog
from gp_data.data_manager import DataManager
from gp_data.models import Record


def _backup_label(path):
    stem = path.name[:-4]
    base, _, stamp = stem.rpartition('.')
    dt = datetime.strptime(stamp, "%Y%m%dT%H%M%S%fZ")
    return f"{dt.strftime('%Y-%m-%d %H:%M:%S.%f')} UTC - {base}"


def _find_backup_index(labels, expected: str):
    for idx, label in enumerate(labels):
        if label == expected:
            return idx
    return None


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
    dlg.update_idletasks()

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

    buttons = []
    def _collect_buttons(root):
        for widget in root.winfo_children():
            if getattr(widget, "cget", None):
                try:
                    if widget.cget("text") in ("Delete", "Restore", "Close"):
                        buttons.append(widget)
                except Exception:
                    pass
            _collect_buttons(widget)

    _collect_buttons(dlg)
    button_map = {button.cget('text'): button for button in buttons}
    assert {"Delete", "Restore", "Close"}.issubset(button_map)

    packed_children = dlg.pack_slaves()
    assert len(packed_children) >= 2
    assert any(button in packed_children[0].winfo_children() for button in button_map.values())

    # determine index for b1 in the listbox and select it
    names = lb.get(0, 'end')
    idx_b1 = _find_backup_index(names, _backup_label(b1))
    assert idx_b1 is not None
    lb.selection_clear(0, 'end')
    lb.selection_set(idx_b1)
    lb.event_generate('<<ListboxSelect>>')

    # patch confirmation dialogs
    orig = mb.askyesno
    orig_showinfo = mb.showinfo
    mb.askyesno = lambda *a, **k: True
    mb.showinfo = lambda *a, **k: None
    try:
        delete_btn = button_map['Delete']
        restore_btn = button_map['Restore']

        # ensure delete button is enabled then invoke
        assert str(delete_btn.cget('state')) in ('normal', 'active')
        delete_btn.invoke()
        # UI may remove the entry or the file itself may be deleted; accept either
        names_after = lb.get(0, 'end')
        assert (len(names_after) < len(names)) or (not b1.exists())

        # select the remaining (newest) backup and restore it
        names = lb.get(0, 'end')
        idx_b2 = _find_backup_index(names, _backup_label(b2))
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
        mb.showinfo = orig_showinfo

    dlg.destroy()
    app.destroy()


def test_build_backup_preview_for_sqlite_backup(tmp_path):
    p = tmp_path / "data.db"
    dm = DataManager(p)
    dm.save(Record(field1='one', field2='first'))
    backup = dm.create_timestamped_backup()

    preview = _build_backup_preview(backup)

    assert "Type: SQLite backup" in preview
    assert "Records: 1" in preview
    assert "one" in preview.lower()


def test_build_backup_preview_for_sqlite_backup_with_uri_special_characters_in_name(tmp_path):
    p = tmp_path / "data#archive.db"
    dm = DataManager(p)
    dm.save(Record(field1='one', field2='first'))
    backup = dm.create_timestamped_backup()

    preview = _build_backup_preview(backup)

    assert "Type: SQLite backup" in preview
    assert "Records: 1" in preview
    assert "one" in preview.lower()


def test_manage_backups_dialog_reuses_cached_preview(tmp_path):
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    root.withdraw()

    p = tmp_path / "data.db"
    dm = DataManager(p)
    dm.save(Record(field1='one', field2='first'))
    backup = dm.create_timestamped_backup()
    seen_paths: list[Path] = []

    def fake_build_preview(path):
        seen_paths.append(path)
        return f"Preview for {path.name}"

    dlg = open_manage_backups_dialog(root, dm, build_preview=fake_build_preview)
    dlg.update_idletasks()

    def _find(root_widget, cls):
        for widget in root_widget.winfo_children():
            if isinstance(widget, cls):
                return widget
            found = _find(widget, cls)
            if found is not None:
                return found
        return None

    lb = _find(dlg, tk.Listbox)
    assert lb is not None

    labels = lb.get(0, 'end')
    idx = _find_backup_index(labels, _backup_label(backup))
    assert idx is not None

    lb.selection_clear(0, 'end')
    lb.selection_set(idx)
    lb.event_generate('<<ListboxSelect>>')
    lb.event_generate('<<ListboxSelect>>')

    assert seen_paths == [backup]

    dlg.destroy()
    root.destroy()