from pathlib import Path

import pytest

from gp_data.main import run_cli
from gp_data.data_manager import DataManager
from gp_data.models import Record


def test_cli_add_and_list(tmp_path: Path, capsys):
    storage = tmp_path / "data.db"
    # add a record
    run_cli(["--storage", str(storage), "add", "--field1", "foo"])
    out = capsys.readouterr().out
    assert "added" in out

    # listing should show the record (case shouldn't matter)
    run_cli(["--storage", str(storage), "list"])
    out = capsys.readouterr().out
    assert "foo" in out.lower()


def test_cli_backup_and_restore(tmp_path: Path, capsys):
    storage = tmp_path / "data.db"
    dm = DataManager(storage)
    r = Record(field1="bar")
    dm.save(r)

    # backup should create a file under backups/
    run_cli(["--storage", str(storage), "backup"])
    out = capsys.readouterr().out
    assert "backup saved" in out
    backups = dm.list_backups()
    assert backups

    # corrupt the main csv then restore
    storage.write_text("corrupted")
    run_cli(["--storage", str(storage), "restore"])
    out = capsys.readouterr().out
    assert "restored" in out
    # recreate manager so it reopens the restored DB
    dm = DataManager(storage)
    rows = dm.load_all()
    assert rows and rows[0].field1 == "Bar"


def test_cli_migration(tmp_path: Path, capsys):
    # create a legacy CSV and migrate it
    csv_path = tmp_path / "old.csv"
    csv_path.write_text("id,field1\n1,foo\n", encoding="utf-8")
    db_path = tmp_path / "new.db"

    run_cli(["migrate", str(csv_path), str(db_path)])
    out = capsys.readouterr().out
    assert "migrated" in out

    dm = DataManager(db_path)
    rows = dm.load_all()
    assert rows and rows[0].field1.lower() == "foo"


def test_cli_migration_default(tmp_path: Path, capsys, monkeypatch):
    # migrating without specifying --storage should not create the default
    # database prematurely (regression for issue where run_cli created it)
    csv_path = tmp_path / "old.csv"
    csv_path.write_text("id,field1\n1,bar\n", encoding="utf-8")
    default_db = tmp_path / "data.db"
    import gp_data.data_manager as dm_mod
    monkeypatch.setattr(dm_mod, "DEFAULT_DB", default_db)

    # ensure default doesn't exist ahead of time
    if default_db.exists():
        default_db.unlink()

    run_cli(["migrate", str(csv_path), str(default_db)])
    out = capsys.readouterr().out
    assert "migrated" in out
    assert default_db.exists()

    dm = DataManager()
    rows = dm.load_all()
    assert rows and rows[0].field1.lower() == "bar"


def test_cli_migrate_overwrite(tmp_path: Path, capsys):
    # creating a DB first and then migrating over it should succeed (no error)
    csv1 = tmp_path / "one.csv"
    csv1.write_text("id,field1\n1,one\n", encoding="utf-8")
    csv2 = tmp_path / "two.csv"
    csv2.write_text("id,field1\n1,two\n", encoding="utf-8")
    db_path = tmp_path / "dest.db"
    # initial migration
    run_cli(["migrate", str(csv1), str(db_path)])
    dm = DataManager(db_path)
    assert dm.load_all()[0].field1.lower() == "one"

    # migrate second file over same destination
    run_cli(["migrate", str(csv2), str(db_path)])
    out = capsys.readouterr().out
    assert "migrated" in out
    dm2 = DataManager(db_path)
    assert dm2.load_all()[0].field1.lower() == "two"


def test_cli_migration_failure_returns_error(tmp_path: Path, capsys):
    invalid_src = tmp_path / "src-dir"
    invalid_src.mkdir()
    db_path = tmp_path / "dest.db"

    result = run_cli(["migrate", str(invalid_src), str(db_path)])
    captured = capsys.readouterr()

    assert result == 1
    assert "migration failed:" in captured.err
