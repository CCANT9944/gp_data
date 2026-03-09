from pathlib import Path
import time

from gp_data.data_manager import DataManager
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