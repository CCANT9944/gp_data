from __future__ import annotations

import logging
import sqlite3
import warnings
from pathlib import Path
from typing import Optional, Protocol

from .backends import CSVDataManager, SQLiteDataManager, export_records_to_csv
from .constants import FIELDNAMES
from .duplicates import DuplicateDetector

DEFAULT_CSV = Path(__file__).resolve().parent.parent / "data.csv"
DEFAULT_DB = Path(__file__).resolve().parent.parent / "data.db"
LOGGER = logging.getLogger(__name__)


class DataBackend(Protocol):
    path: Path

    def ensure_storage(self) -> None: ...
    def load_all(self) -> list: ...
    def save(self, record): ...
    def update(self, id: str, record): ...
    def delete(self, id: str) -> None: ...
    def export_csv(self, dest: Path) -> None: ...
    def restore_backup(self) -> Path: ...
    def create_timestamped_backup(self, keep: int = 14) -> Path: ...
    def list_backups(self) -> list[Path]: ...
    def delete_backup(self, backup: Path) -> None: ...
    def restore_from_backup(self, backup: Path) -> Path: ...
    def replace_all(self, records: list) -> None: ...
    def storage_issue(self) -> Exception | None: ...


def _build_backend(path: Path) -> DataBackend:
    return CSVDataManager(path) if path.suffix.lower() == ".csv" else SQLiteDataManager(path)


def _default_storage_path() -> Path:
    csv_exists = DEFAULT_CSV.exists()
    db_needs_migration = False

    if csv_exists and not DEFAULT_DB.exists():
        db_needs_migration = True
    elif csv_exists and DEFAULT_DB.exists():
        db_needs_migration = _default_db_is_empty_or_unavailable(DEFAULT_DB)

    if db_needs_migration and csv_exists:
        warnings.warn("legacy CSV detected; migrating to SQLite database", UserWarning)
        DataManager.migrate_from_csv(DEFAULT_CSV, DEFAULT_DB)

    return DEFAULT_DB


def _default_db_is_empty_or_unavailable(path: Path) -> bool:
    backend = SQLiteDataManager(path)
    try:
        return len(backend.load_all()) == 0
    except (sqlite3.DatabaseError, OSError, RuntimeError, ValueError):
        LOGGER.warning("Unable to inspect existing SQLite database; falling back to CSV migration", exc_info=True)
        return True
    finally:
        backend._reset_conn()


class DataManager:
    """Stable app-facing API over the CSV and SQLite backends."""

    def __init__(self, path: Optional[Path] = None):
        path = _default_storage_path() if path is None else Path(path)

        self._backend = _build_backend(path)
        self._duplicate_detector = DuplicateDetector(self.load_all)

    @property
    def path(self) -> Path:
        return self._backend.path

    def ensure_storage(self) -> None:
        self._backend.ensure_storage()

    def load_all(self) -> list:
        return self._backend.load_all()

    def save(self, record):
        return self._backend.save(record)

    def update(self, id: str, record):
        return self._backend.update(id, record)

    def delete(self, id: str) -> None:
        self._backend.delete(id)

    def export_csv(self, dest: Path) -> None:
        self._backend.export_csv(dest)

    def restore_backup(self) -> Path:
        return self._backend.restore_backup()

    def create_timestamped_backup(self, keep: int = 14) -> Path:
        return self._backend.create_timestamped_backup(keep=keep)

    def list_backups(self) -> list[Path]:
        return self._backend.list_backups()

    def delete_backup(self, backup: Path) -> None:
        self._backend.delete_backup(backup)

    def restore_from_backup(self, backup: Path) -> Path:
        return self._backend.restore_from_backup(backup)

    def replace_all(self, records: list) -> None:
        self._backend.replace_all(records)

    def storage_issue(self) -> Exception | None:
        return self._backend.storage_issue()

    def duplicate_identity(self, record):
        return self._duplicate_detector.duplicate_identity(record)

    def possible_duplicate_identity(self, record):
        return self._duplicate_detector.possible_duplicate_identity(record)

    def find_duplicate_record(self, record, exclude_id: str | None = None):
        return self._duplicate_detector.find_duplicate_record(record, exclude_id=exclude_id)

    def find_possible_duplicate_record(self, record, exclude_id: str | None = None):
        return self._duplicate_detector.find_possible_duplicate_record(record, exclude_id=exclude_id)

    @staticmethod
    def migrate_from_csv(src: Path, dest: Path) -> None:
        src = Path(src)
        dest = Path(dest)
        csv_dm = CSVDataManager(src)
        rows = csv_dm.load_all()
        db_dm = SQLiteDataManager(dest)
        db_dm.replace_all(rows)


__all__ = [
    "CSVDataManager",
    "SQLiteDataManager",
    "DataManager",
    "DuplicateDetector",
    "export_records_to_csv",
    "FIELDNAMES",
    "DEFAULT_CSV",
    "DEFAULT_DB",
]