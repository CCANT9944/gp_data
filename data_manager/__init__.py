from __future__ import annotations

import warnings
from pathlib import Path
from typing import Optional

from .backends import CSVDataManager, SQLiteDataManager
from .constants import FIELDNAMES

DEFAULT_CSV = Path(__file__).resolve().parent.parent / "data.csv"
DEFAULT_DB = Path(__file__).resolve().parent.parent / "data.db"


class DataManager:
    """Wrapper that selects backend based on file extension."""

    def __init__(self, path: Optional[Path] = None):
        if path is None:
            db_should_migrate = False
            if not DEFAULT_DB.exists() and DEFAULT_CSV.exists():
                db_should_migrate = True
            elif DEFAULT_DB.exists() and DEFAULT_CSV.exists():
                try:
                    tmp = SQLiteDataManager(DEFAULT_DB)
                    if len(tmp.load_all()) == 0:
                        db_should_migrate = True
                    tmp._reset_conn()
                except Exception:
                    db_should_migrate = True
            if db_should_migrate and DEFAULT_CSV.exists():
                warnings.warn("legacy CSV detected; migrating to SQLite database", UserWarning)
                try:
                    DEFAULT_DB.unlink()
                except Exception:
                    pass
                DataManager.migrate_from_csv(DEFAULT_CSV, DEFAULT_DB)
            path = DEFAULT_DB
        else:
            path = Path(path)

        if path.suffix.lower() == ".csv":
            self._backend = CSVDataManager(path)
        else:
            self._backend = SQLiteDataManager(path)

    def __getattr__(self, name):
        return getattr(self._backend, name)

    @staticmethod
    def migrate_from_csv(src: Path, dest: Path) -> None:
        src = Path(src)
        dest = Path(dest)
        if dest.exists():
            try:
                dest.unlink()
            except Exception:
                pass
        csv_dm = CSVDataManager(src)
        rows = csv_dm.load_all()
        db_dm = SQLiteDataManager(dest)
        for row in rows:
            db_dm.save(row)


__all__ = [
    "CSVDataManager",
    "SQLiteDataManager",
    "DataManager",
    "FIELDNAMES",
    "DEFAULT_CSV",
    "DEFAULT_DB",
]