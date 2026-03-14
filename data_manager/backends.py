from __future__ import annotations

import csv
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from ..models import NumericChange, Record
from ..settings import load_labels
from .constants import FIELDNAMES

TRACKED_NUMERIC_FIELDS = ("field7", "field3", "field6")
MAX_NUMERIC_CHANGE_HISTORY = 8
SQLITE_COLUMN_DEFS = [
    ("id", "TEXT PRIMARY KEY"),
    ("field1", "TEXT"),
    ("field2", "TEXT"),
    ("field3", "REAL"),
    ("field4", "TEXT"),
    ("field5", "TEXT"),
    ("field6", "REAL"),
    ("field7", "REAL"),
    ("gp", "REAL"),
    ("cash_margin", "REAL"),
    ("gp70", "REAL"),
    ("created_at", "TEXT"),
    ("last_numeric_field", "TEXT"),
    ("last_numeric_from", "REAL"),
    ("last_numeric_to", "REAL"),
    ("last_numeric_changed_at", "TEXT"),
    ("numeric_change_history", "TEXT"),
]
SQLITE_COLUMN_NAMES = [name for name, _definition in SQLITE_COLUMN_DEFS]
SQLITE_CREATE_TABLE_SQL = (
    "CREATE TABLE IF NOT EXISTS records ("
    + ", ".join(f"{name} {definition}" for name, definition in SQLITE_COLUMN_DEFS)
    + ")"
)
SQLITE_INSERT_SQL = (
    "INSERT INTO records ("
    + ", ".join(SQLITE_COLUMN_NAMES)
    + ") VALUES ("
    + ", ".join(f":{name}" for name in SQLITE_COLUMN_NAMES)
    + ") ON CONFLICT(id) DO UPDATE SET "
    + ", ".join(f"{name} = excluded.{name}" for name in SQLITE_COLUMN_NAMES if name != "id")
)

if SQLITE_COLUMN_NAMES != FIELDNAMES:
    raise ValueError("SQLite columns must stay aligned with FIELDNAMES")


def _record_with_last_numeric_change(previous: Record | None, record: Record) -> Record:
    if previous is None:
        return record

    for field in TRACKED_NUMERIC_FIELDS:
        previous_value = getattr(previous, field)
        current_value = getattr(record, field)
        if previous_value != current_value:
            now = datetime.now(timezone.utc)
            history = list(previous.numeric_change_history)
            history.append(
                NumericChange(
                    field_name=field,
                    from_value=previous_value,
                    to_value=current_value,
                    changed_at=now,
                )
            )
            return record.model_copy(update={
                "last_numeric_field": field,
                "last_numeric_from": previous_value,
                "last_numeric_to": current_value,
                "last_numeric_changed_at": now,
                "numeric_change_history": history[-MAX_NUMERIC_CHANGE_HISTORY:],
            })

    return record.model_copy(update={
        "last_numeric_field": previous.last_numeric_field,
        "last_numeric_from": previous.last_numeric_from,
        "last_numeric_to": previous.last_numeric_to,
        "last_numeric_changed_at": previous.last_numeric_changed_at,
        "numeric_change_history": previous.numeric_change_history,
    })


def _default_csv_path() -> Path:
    from . import DEFAULT_CSV

    return DEFAULT_CSV


def _default_db_path() -> Path:
    from . import DEFAULT_DB

    return DEFAULT_DB


def _record_from_sqlite_row(row: tuple) -> Record:
    data = dict(zip(SQLITE_COLUMN_NAMES, row))
    for key, val in data.items():
        if val == "":
            data[key] = None
    return Record.from_dict(data)


def _sqlite_record_params(record: Record) -> dict:
    data = record.to_dict()
    return {name: data.get(name) for name in SQLITE_COLUMN_NAMES}


class CSVDataManager:
    """CSV-backed simple persistence layer for Record objects."""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else _default_csv_path()
        self.ensure_storage()

    def _header_labels(self) -> list[str]:
        labels = load_labels()
        out: list[str] = []
        for fname in FIELDNAMES:
            if fname.startswith("field") and fname[5:].isdigit():
                idx = int(fname[5:]) - 1
                out.append(labels[idx])
            elif fname == "gp":
                out.append("GP")
            elif fname == "cash_margin":
                out.append("CASH MARGIN")
            elif fname == "gp70":
                out.append("WITH 70% GP")
            else:
                out.append(fname)
        return out

    def ensure_storage(self) -> None:
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(self._header_labels())

    def load_all(self) -> List[Record]:
        self.ensure_storage()
        records: List[Record] = []
        with self.path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            csv_headers = reader.fieldnames or []
            header_labels = self._header_labels()
            label_to_field: dict[str, str] = {}
            for canonical, label in zip(FIELDNAMES, header_labels):
                if label in csv_headers:
                    label_to_field[label] = canonical
                if canonical in csv_headers:
                    label_to_field[canonical] = canonical

            for row in reader:
                normalized: dict = {}
                for csv_key, val in row.items():
                    if csv_key in label_to_field:
                        normalized[label_to_field[csv_key]] = val
                    else:
                        normalized[csv_key] = val
                for key, val in normalized.items():
                    if val == "":
                        normalized[key] = None
                records.append(Record.from_dict(normalized))
        return records

    def _write_all(self, records: List[Record]) -> None:
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", newline="", encoding="utf-8") as handle:
            header_writer = csv.writer(handle)
            header_writer.writerow(self._header_labels())
            writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
            for record in records:
                row = {key: ("" if val is None else val) for key, val in record.to_dict().items()}
                writer.writerow(row)
        shutil.move(str(tmp), str(self.path))

    def restore_backup(self) -> Path:
        bak = self.path.with_name(self.path.name + ".bak")
        if not bak.exists():
            raise FileNotFoundError("Backup file not found")
        pre = self.path.with_name(self.path.name + ".pre_restore.bak")
        shutil.copyfile(str(self.path), str(pre))
        shutil.copyfile(str(bak), str(self.path))
        return pre

    def create_timestamped_backup(self, keep: int = 14) -> Path:
        backup_dir = self.path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%dT%H%M%S%fZ")
        dest = backup_dir / f"{self.path.name}.{ts}.bak"
        shutil.copyfile(str(self.path), str(dest))

        pattern = f"{self.path.name}.*.bak"
        files = sorted(backup_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in files[keep:]:
            try:
                old.unlink()
            except Exception:
                pass
        return dest

    def list_backups(self) -> list[Path]:
        backup_dir = self.path.parent / "backups"
        if not backup_dir.exists():
            return []
        return sorted(backup_dir.glob(f"{self.path.name}.*.bak"), key=lambda p: p.stat().st_mtime, reverse=True)

    def delete_backup(self, backup: Path) -> None:
        try:
            backup.unlink()
        except Exception:
            pass

    def restore_from_backup(self, backup: Path) -> Path:
        if not backup.exists():
            raise FileNotFoundError("Specified backup not found")
        pre = self.path.with_name(self.path.name + ".pre_restore.bak")
        shutil.copyfile(str(self.path), str(pre))
        shutil.copyfile(str(backup), str(self.path))
        return pre

    def save(self, record: Record) -> Record:
        records = self.load_all()
        if any(existing.id == record.id for existing in records):
            return self.update(record.id, record)
        records.append(record)
        self._write_all(records)
        return record

    def update(self, id: str, record: Record) -> Record:
        records = self.load_all()
        updated = False
        for i, existing in enumerate(records):
            if existing.id == id:
                records[i] = _record_with_last_numeric_change(existing, record)
                updated = True
                break
        if not updated:
            records.append(record)
        self._write_all(records)
        return next((existing for existing in records if existing.id == id), record)

    def delete(self, id: str) -> None:
        records = [record for record in self.load_all() if record.id != id]
        self._write_all(records)

    def export_csv(self, dest: Path) -> None:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(self.path), str(dest))


class SQLiteDataManager:
    """SQLite-backed persistence layer mirroring the CSV API."""

    CREATE_TABLE = SQLITE_CREATE_TABLE_SQL

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else _default_db_path()
        self._conn: Optional[sqlite3.Connection] = None
        self._ensure_conn()

    def _ensure_conn(self) -> None:
        if self._conn is not None:
            return
        try:
            self._conn = sqlite3.connect(str(self.path))
            self._conn.execute(self.CREATE_TABLE)
            self._ensure_schema_columns()
            self._conn.commit()
        except sqlite3.DatabaseError:
            self._conn = None

    def _ensure_schema_columns(self) -> None:
        if self._conn is None:
            return
        cur = self._conn.cursor()
        cur.execute("PRAGMA table_info(records)")
        existing = {row[1] for row in cur.fetchall()}
        changed = False
        for name, definition in SQLITE_COLUMN_DEFS:
            if name == "id" or name in existing:
                continue
            cur.execute(f"ALTER TABLE records ADD COLUMN {name} {definition}")
            changed = True
        if changed:
            self._conn.commit()

    def _load_record_by_id(self, id: str) -> Record | None:
        self._ensure_conn()
        if self._conn is None:
            return None
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM records WHERE id = ?", (id,))
        row = cur.fetchone()
        if row is None:
            return None
        return _record_from_sqlite_row(row)

    def _reset_conn(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
        self._conn = None

    def ensure_storage(self) -> None:
        self._ensure_conn()

    def load_all(self) -> List[Record]:
        self._ensure_conn()
        if self._conn is None:
            return []
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM records")
        rows = cur.fetchall()
        return [_record_from_sqlite_row(row) for row in rows]

    def _write_all(self, records: List[Record]) -> None:
        self._ensure_conn()
        if self._conn is None:
            raise RuntimeError("database unavailable")
        cur = self._conn.cursor()
        cur.execute("DELETE FROM records")
        for record in records:
            cur.execute(SQLITE_INSERT_SQL, _sqlite_record_params(record))
        self._conn.commit()

    def restore_backup(self) -> Path:
        bak = self.path.with_name(self.path.name + ".bak")
        if not bak.exists():
            raise FileNotFoundError("Backup file not found")
        pre = self.path.with_name(self.path.name + ".pre_restore.bak")
        shutil.copyfile(str(self.path), str(pre))
        shutil.copyfile(str(bak), str(self.path))
        self._reset_conn()
        return pre

    def create_timestamped_backup(self, keep: int = 14) -> Path:
        backup_dir = self.path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%dT%H%M%S%fZ")
        dest = backup_dir / f"{self.path.name}.{ts}.bak"
        shutil.copyfile(str(self.path), str(dest))
        pattern = f"{self.path.name}.*.bak"
        files = sorted(backup_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in files[keep:]:
            try:
                old.unlink()
            except Exception:
                pass
        return dest

    def list_backups(self) -> list[Path]:
        backup_dir = self.path.parent / "backups"
        if not backup_dir.exists():
            return []
        return sorted(backup_dir.glob(f"{self.path.name}.*.bak"), key=lambda p: p.stat().st_mtime, reverse=True)

    def delete_backup(self, backup: Path) -> None:
        try:
            backup.unlink()
        except Exception:
            pass

    def restore_from_backup(self, backup: Path) -> Path:
        if not backup.exists():
            raise FileNotFoundError("Specified backup not found")
        pre = self.path.with_name(self.path.name + ".pre_restore.bak")
        shutil.copyfile(str(self.path), str(pre))
        shutil.copyfile(str(backup), str(self.path))
        self._reset_conn()
        return pre

    def save(self, record: Record) -> Record:
        self._ensure_conn()
        if self._conn is None:
            raise RuntimeError("database unavailable")
        record = _record_with_last_numeric_change(self._load_record_by_id(record.id), record)
        cur = self._conn.cursor()
        cur.execute(SQLITE_INSERT_SQL, _sqlite_record_params(record))
        self._conn.commit()
        return record

    def update(self, id: str, record: Record) -> Record:
        return self.save(record)

    def delete(self, id: str) -> None:
        cur = self._conn.cursor()
        cur.execute("DELETE FROM records WHERE id = ?", (id,))
        self._conn.commit()

    def export_csv(self, dest: Path) -> None:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        rows = self.load_all()
        tmp_dm = CSVDataManager(dest)
        tmp_dm._write_all(rows)