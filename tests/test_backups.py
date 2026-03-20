from pathlib import Path
import time

import pytest

from gp_data.data_manager import CSVDataManager, DataManager
from gp_data.data_manager import backup_ops
from gp_data.models import Record


def test_create_timestamped_backups_and_rotation(tmp_path: Path):
    p = tmp_path / "data.db"
    dm = DataManager(p)

    # ensure base CSV exists
    r = Record(field1="one", field3=10, field5="2", field6=5.0, field7=10.0)
    dm.save(r)

    # create several backups
    paths = []
    for _ in range(5):
        paths.append(dm.create_timestamped_backup())
        time.sleep(0.01)

    backup_dir = p.parent / "backups"
    files = sorted(list(backup_dir.glob("data.db.*.bak")))
    assert len(files) == 5

    # rotation: keep only 3
    dm.create_timestamped_backup(keep=3)
    files = sorted(list(backup_dir.glob("data.db.*.bak")))
    assert len(files) == 3
    # newest backup should be present
    assert files[-1].exists()


def test_csv_restore_from_timestamped_backup(tmp_path: Path):
    p = tmp_path / "data.csv"
    dm = CSVDataManager(p)
    dm.save(Record(field1="one"))

    backup = dm.create_timestamped_backup()

    dm.save(Record(field1="two"))
    pre = dm.restore_from_backup(backup)

    assert pre.exists()
    rows = dm.load_all()
    assert any(r.field1.lower() == "one" for r in rows)
    assert not any(r.field1.lower() == "two" for r in rows)


def test_create_timestamped_backup_logs_prune_failures_and_keeps_new_backup(tmp_path: Path, monkeypatch, caplog):
    storage = tmp_path / "data.db"
    dm = DataManager(storage)
    dm.save(Record(field1="one"))

    for _ in range(3):
        dm.create_timestamped_backup()
        time.sleep(0.01)

    backup_dir = storage.parent / "backups"
    old_backups = sorted(backup_dir.glob("data.db.*.bak"), key=lambda item: item.stat().st_mtime)
    locked_backup = old_backups[0]
    original_unlink = Path.unlink

    def fake_unlink(path: Path, *args, **kwargs):
        if path == locked_backup:
            raise OSError("file is locked")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fake_unlink)

    with caplog.at_level("WARNING"):
        newest = dm.create_timestamped_backup(keep=1)

    assert newest.exists()
    assert any("Unable to prune old backup" in message for message in caplog.messages)
    assert locked_backup.exists()


def test_restore_from_backup_does_not_overwrite_live_file_when_pre_restore_copy_fails(tmp_path: Path, monkeypatch):
    path = tmp_path / "data.db"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    backup = backup_dir / "data.db.20260316T120000000000Z.bak"
    path.write_text("live-data", encoding="utf-8")
    backup.write_text("backup-data", encoding="utf-8")

    def fail_pre_restore_copy(src: str, dest: str):
        raise OSError("sharing violation")

    monkeypatch.setattr(backup_ops.shutil, "copyfile", fail_pre_restore_copy)

    with pytest.raises(OSError):
        backup_ops.restore_from_backup(path, backup)

    assert path.read_text(encoding="utf-8") == "live-data"
    assert not path.with_name(path.name + ".pre_restore.bak").exists()


def test_restore_from_backup_rejects_paths_outside_expected_backup_locations(tmp_path: Path):
    path = tmp_path / "data.db"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    path.write_text("live-data", encoding="utf-8")

    unexpected = tmp_path / "other.db.20260316T120000000000Z.bak"
    unexpected.write_text("backup-data", encoding="utf-8")

    with pytest.raises(ValueError, match="Backup path"):
        backup_ops.restore_from_backup(path, unexpected)


def test_delete_backup_rejects_paths_outside_expected_backup_locations(tmp_path: Path):
    path = tmp_path / "data.db"
    path.write_text("live-data", encoding="utf-8")
    unexpected = tmp_path / "unrelated.bak"
    unexpected.write_text("backup-data", encoding="utf-8")

    with pytest.raises(ValueError, match="Backup path"):
        backup_ops.delete_backup(path, unexpected)

    assert unexpected.exists()