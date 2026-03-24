import csv
from pathlib import Path
import logging

import pytest

import gp_data.cli as cli_module
from gp_data import settings as settings_module
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


def test_cli_list_uses_saved_formula_expressions(tmp_path: Path, capsys, monkeypatch):
    storage = tmp_path / "data.db"
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(settings_module, "DEFAULT_PATH", settings_path)
    settings_module.SettingsStore(settings_path).save_formula_expressions(
        {
            "field6": "field3 / field5",
            "gp": "1 - (field6 * 1.2) / field7",
            "cash_margin": "field7 - (field6 * 1.2)",
            "gp70": "field6 * 2",
        }
    )
    DataManager(storage).save(Record(field1="beer", field3=24.0, field5="24", field7=5.5))

    run_cli(["--storage", str(storage), "list"])
    out = capsys.readouterr().out

    assert "'field6': 1.0" in out
    assert "'gp70': 2.0" in out


def test_cli_export_uses_saved_formula_expressions(tmp_path: Path, capsys, monkeypatch):
    storage = tmp_path / "data.db"
    settings_path = tmp_path / "settings.json"
    export_path = tmp_path / "export.csv"
    monkeypatch.setattr(settings_module, "DEFAULT_PATH", settings_path)
    settings_module.SettingsStore(settings_path).save_formula_expressions(
        {
            "field6": "field3 / field5",
            "gp": "1 - (field6 * 1.2) / field7",
            "cash_margin": "field7 - (field6 * 1.2)",
            "gp70": "field6 * 2",
        }
    )
    DataManager(storage).save(Record(field1="beer", field3=24.0, field5="24", field7=5.5))

    run_cli(["--storage", str(storage), "export", str(export_path)])
    _ = capsys.readouterr()

    with export_path.open("r", encoding="utf-8") as handle:
        row = next(csv.DictReader(handle))

    assert row[settings_module.DEFAULT_LABELS[5]] == "1.0"
    assert row["WITH 70% GP"] == "2.0"


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


def test_configure_csv_preview_debug_logging_writes_to_requested_file(tmp_path: Path):
    log_path = tmp_path / "logs" / "csv_preview_debug.log"

    configured_path = cli_module._configure_csv_preview_debug_logging(log_path)
    logger = logging.getLogger(cli_module.CSV_PREVIEW_LOGGER_NAME)
    logger.debug("timing test line")

    assert configured_path == log_path
    assert log_path.exists()
    assert "timing test line" in log_path.read_text(encoding="utf-8")


def test_run_cli_uses_env_debug_log_for_gui(tmp_path: Path, capsys, monkeypatch):
    log_path = tmp_path / "csv_preview_debug.log"
    seen_storage: dict[str, Path | None] = {}

    monkeypatch.setenv(cli_module.CSV_PREVIEW_DEBUG_ENV, "1")
    monkeypatch.setenv(cli_module.CSV_PREVIEW_DEBUG_LOG_ENV, str(log_path))
    monkeypatch.setattr(cli_module, "run_gui", lambda storage_path=None: seen_storage.setdefault("path", storage_path))

    result = run_cli(["gui"])
    output = capsys.readouterr().out

    assert result == 0
    assert seen_storage["path"] is None
    assert str(log_path) in output
    assert log_path.exists()
