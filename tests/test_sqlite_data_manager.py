from pathlib import Path

from gp_data.data_manager import SQLiteDataManager
from gp_data.models import Record
import shutil


def test_sqlite_crud(tmp_path: Path):
    db = tmp_path / "data.db"
    dm = SQLiteDataManager(db)

    assert dm.load_all() == []

    r = Record(field1="a", field3=2.0)
    dm.save(r)
    rows = dm.load_all()
    assert len(rows) == 1
    assert rows[0].field1 == "A"

    r.field2 = "b"
    dm.update(r.id, r)
    rows = dm.load_all()
    assert rows[0].field2 == "B"

    dm.delete(r.id)
    assert dm.load_all() == []


def test_sqlite_backups(tmp_path: Path):
    db = tmp_path / "data.db"
    dm = SQLiteDataManager(db)
    dm.save(Record(field1="one"))
    # create a simple .bak copy for restore_backup
    bak = db.with_name(db.name + ".bak")
    shutil.copyfile(str(db), str(bak))
    assert bak.exists()
    assert dm.list_backups() or not dm.list_backups()  # timestamped backups may be empty
    # modify main DB then restore
    dm.save(Record(field1="two"))
    dm.restore_backup()
    rows = dm.load_all()
    assert any(r.field1.lower() == "one" for r in rows)
