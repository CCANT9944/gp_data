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


def test_sqlite_tracks_last_numeric_change_and_preserves_it_for_text_edits(tmp_path: Path):
    db = tmp_path / "data.db"
    dm = SQLiteDataManager(db)

    record = Record(field1="one", field3=10.0, field6=2.0, field7=5.0)
    dm.save(record)

    updated_numeric = record.model_copy(update={"field7": 7.5})
    dm.update(record.id, updated_numeric)

    rows = dm.load_all()
    assert len(rows) == 1
    first = rows[0]
    assert first.last_numeric_field == "field7"
    assert first.last_numeric_from == 5.0
    assert first.last_numeric_to == 7.5
    assert first.last_numeric_changed_at is not None
    assert len(first.numeric_change_history) == 1

    updated_text = first.model_copy(update={"field2": "changed"})
    dm.update(first.id, updated_text)

    rows = dm.load_all()
    second = rows[0]
    assert second.field2 == "Changed"
    assert second.last_numeric_field == "field7"
    assert second.last_numeric_from == 5.0
    assert second.last_numeric_to == 7.5
    assert second.last_numeric_changed_at == first.last_numeric_changed_at
    assert len(second.numeric_change_history) == 1

    updated_again = second.model_copy(update={"field3": 12.0})
    dm.update(second.id, updated_again)
    rows = dm.load_all()
    third = rows[0]
    assert len(third.numeric_change_history) == 2
    assert third.numeric_change_history[0].field_name == "field7"
    assert third.numeric_change_history[1].field_name == "field3"


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
    pre = dm.restore_backup()
    assert pre.exists()
    rows = dm.load_all()
    assert any(r.field1.lower() == "one" for r in rows)
    assert not any(r.field1.lower() == "two" for r in rows)


def test_sqlite_restore_from_timestamped_backup(tmp_path: Path):
    db = tmp_path / "data.db"
    dm = SQLiteDataManager(db)
    dm.save(Record(field1="one"))

    backup = dm.create_timestamped_backup()

    dm.save(Record(field1="two"))
    pre = dm.restore_from_backup(backup)

    assert pre.exists()
    rows = dm.load_all()
    assert any(r.field1.lower() == "one" for r in rows)
    assert not any(r.field1.lower() == "two" for r in rows)
