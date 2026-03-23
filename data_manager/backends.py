from __future__ import annotations

import csv
import logging
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from ..models import NumericChange, Record
from ..settings import load_labels
from . import backup_ops
from .constants import FIELDNAMES


LOGGER = logging.getLogger(__name__)

TRACKED_NUMERIC_FIELDS = ("field7", "field3", "field6")
MAX_NUMERIC_CHANGE_HISTORY = 8
CSV_COMPUTED_FIELD_LABELS = {
    "gp": "GP",
    "cash_margin": "CASH MARGIN",
    "gp70": "WITH 70% GP",
}
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
    return Record.from_dict(_normalize_storage_values(dict(zip(SQLITE_COLUMN_NAMES, row))))


def _sqlite_record_params(record: Record) -> dict:
    return _record_to_storage_row(record, SQLITE_COLUMN_NAMES)


def _csv_header_labels(labels: list[str]) -> list[str]:
    header_labels: list[str] = []
    for field_name in FIELDNAMES:
        if field_name.startswith("field") and field_name[5:].isdigit():
            header_labels.append(labels[int(field_name[5:]) - 1])
        else:
            header_labels.append(CSV_COMPUTED_FIELD_LABELS.get(field_name, field_name))
    return header_labels


def _csv_label_to_field_map(csv_headers: list[str], header_labels: list[str]) -> dict[str, str]:
    label_to_field: dict[str, str] = {}
    for canonical, label in zip(FIELDNAMES, header_labels):
        if label in csv_headers:
            label_to_field[label] = canonical
        if canonical in csv_headers:
            label_to_field[canonical] = canonical
    return label_to_field


def _normalize_storage_values(data: dict) -> dict:
    return {key: (None if value == "" else value) for key, value in data.items()}


def _record_to_storage_row(record: Record, field_names: list[str] | None = None) -> dict:
    field_names = field_names or FIELDNAMES
    data = record.to_dict()
    return {name: ("" if data.get(name) is None else data.get(name)) for name in field_names}


def export_records_to_csv(dest: Path, records: List[Record]) -> None:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        header_writer = csv.writer(handle)
        header_writer.writerow(_csv_header_labels(load_labels()))
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        for record in records:
            writer.writerow(_record_to_storage_row(record))
    shutil.move(str(tmp), str(dest))


class CSVDataManager:
    """CSV-backed simple persistence layer for Record objects."""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else _default_csv_path()
        self.ensure_storage()

    def storage_issue(self) -> Exception | None:
        return None

    def _header_labels(self) -> list[str]:
        return _csv_header_labels(load_labels())

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
            label_to_field = _csv_label_to_field_map(csv_headers, header_labels)

            for row in reader:
                normalized = {
                    label_to_field.get(csv_key, csv_key): val
                    for csv_key, val in row.items()
                }
                records.append(Record.from_dict(_normalize_storage_values(normalized)))
        return records

    def _write_all(self, records: List[Record]) -> None:
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", newline="", encoding="utf-8") as handle:
            header_writer = csv.writer(handle)
            header_writer.writerow(self._header_labels())
            writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
            for record in records:
                writer.writerow(_record_to_storage_row(record))
        shutil.move(str(tmp), str(self.path))

    def replace_all(self, records: List[Record]) -> None:
        self._write_all(records)

    def restore_backup(self) -> Path:
        return backup_ops.restore_backup(self.path)

    def create_timestamped_backup(self, keep: int = 14) -> Path:
        return backup_ops.create_timestamped_backup(self.path, keep=keep)

    def list_backups(self) -> list[Path]:
        return backup_ops.list_backups(self.path)

    def delete_backup(self, backup: Path) -> None:
        backup_ops.delete_backup(self.path, backup)

    def restore_from_backup(self, backup: Path) -> Path:
        return backup_ops.restore_from_backup(self.path, backup)

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
        self._last_error: Exception | None = None
        self._ensure_conn()

    def _ensure_conn(self) -> None:
        if self._conn is not None:
            return
        try:
            self._conn = sqlite3.connect(str(self.path))
            self._conn.execute(self.CREATE_TABLE)
            self._ensure_schema_columns()
            self._conn.commit()
            self._last_error = None
        except sqlite3.DatabaseError as exc:
            self._last_error = exc
            self._conn = None

    def storage_issue(self) -> Exception | None:
        return self._last_error

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
            except sqlite3.Error:
                LOGGER.debug("Unable to close SQLite connection cleanly", exc_info=True)
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

    def replace_all(self, records: List[Record]) -> None:
        self._write_all(records)

    def restore_backup(self) -> Path:
        return backup_ops.restore_backup(self.path, after_restore=self._reset_conn)

    def create_timestamped_backup(self, keep: int = 14) -> Path:
        return backup_ops.create_timestamped_backup(self.path, keep=keep)

    def list_backups(self) -> list[Path]:
        return backup_ops.list_backups(self.path)

    def delete_backup(self, backup: Path) -> None:
        backup_ops.delete_backup(self.path, backup)

    def restore_from_backup(self, backup: Path) -> Path:
        return backup_ops.restore_from_backup(self.path, backup, after_restore=self._reset_conn)

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
        self._ensure_conn()
        if self._conn is None:
            raise RuntimeError("database unavailable")
        cur = self._conn.cursor()
        cur.execute("DELETE FROM records WHERE id = ?", (id,))
        self._conn.commit()

    def export_csv(self, dest: Path) -> None:
        dest = Path(dest)
        rows = self.load_all()
        export_records_to_csv(dest, rows)