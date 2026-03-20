from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Callable


LOGGER = logging.getLogger(__name__)


def _legacy_backup_path(path: Path) -> Path:
    return path.with_name(path.name + ".bak")


def _backup_directory(path: Path) -> Path:
    return path.parent / "backups"


def _is_timestamped_backup_name(path: Path, backup: Path) -> bool:
    return backup.name.startswith(f"{path.name}.") and backup.name.endswith(".bak")


def _validate_backup_path(path: Path, backup: Path) -> Path:
    resolved_backup = backup.resolve()
    if resolved_backup == _legacy_backup_path(path).resolve():
        return resolved_backup

    backup_dir = _backup_directory(path)
    try:
        resolved_backup.relative_to(backup_dir.resolve())
    except ValueError as exc:
        raise ValueError("Backup path must be inside the storage backups directory") from exc

    if not _is_timestamped_backup_name(path, resolved_backup):
        raise ValueError("Backup path does not match the expected backup naming pattern")
    return resolved_backup


def restore_backup(path: Path, after_restore: Callable[[], None] | None = None) -> Path:
    backup = _legacy_backup_path(path)
    if not backup.exists():
        raise FileNotFoundError("Backup file not found")
    return restore_from_backup(path, backup, after_restore=after_restore)


def create_timestamped_backup(path: Path, keep: int = 14) -> Path:
    backup_dir = _backup_directory(path)
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S%fZ")
    destination = backup_dir / f"{path.name}.{timestamp}.bak"
    shutil.copyfile(str(path), str(destination))

    pattern = f"{path.name}.*.bak"
    files = sorted(backup_dir.glob(pattern), key=lambda item: item.stat().st_mtime, reverse=True)
    for old_file in files[keep:]:
        try:
            old_file.unlink()
        except OSError:
            LOGGER.warning("Unable to prune old backup %s", old_file, exc_info=True)
    return destination


def list_backups(path: Path) -> list[Path]:
    backup_dir = _backup_directory(path)
    if not backup_dir.exists():
        return []
    return sorted(backup_dir.glob(f"{path.name}.*.bak"), key=lambda item: item.stat().st_mtime, reverse=True)


def delete_backup(path: Path, backup: Path) -> None:
    backup = _validate_backup_path(path, backup)
    try:
        backup.unlink()
    except FileNotFoundError:
        return


def restore_from_backup(path: Path, backup: Path, after_restore: Callable[[], None] | None = None) -> Path:
    backup = _validate_backup_path(path, backup)
    if not backup.exists():
        raise FileNotFoundError("Specified backup not found")
    pre_restore = path.with_name(path.name + ".pre_restore.bak")
    shutil.copyfile(str(path), str(pre_restore))
    shutil.copyfile(str(backup), str(path))
    if after_restore is not None:
        after_restore()
    return pre_restore