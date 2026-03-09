from __future__ import annotations
from pathlib import Path
import csv
from typing import List, Optional
import shutil
from datetime import datetime
import sqlite3
import warnings

from .models import Record
from .settings import load_labels

FIELDNAMES = [
    "id",
    "field1",
    "field2",
    "field3",
    "field4",
    "field5",
    "field6",
    "field7",
    "gp",
    "cash_margin",
    "gp70",
    "created_at",
]
DEFAULT_CSV = Path(__file__).parent / "data.csv"
DEFAULT_DB = Path(__file__).parent / "data.db"


class CSVDataManager:
    """CSV-backed simple persistence layer for Record objects.

    The CSV header written by this class is user-friendly (uses renamable
    field labels for `field1`..`field7` and readable names for derived
    metrics). `FIELDNAMES` remains the canonical internal keys used when
    reading/writing rows so loading still works for legacy files.
    """

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else DEFAULT_CSV
        self.ensure_storage()

    def _header_labels(self) -> list[str]:
        """Return human-friendly header labels corresponding to FIELDNAMES."""
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
            with self.path.open("w", newline="", encoding="utf-8") as f:
                # write human-friendly header labels
                writer = csv.writer(f)
                writer.writerow(self._header_labels())

    def load_all(self) -> List[Record]:
        self.ensure_storage()
        records: List[Record] = []
        with self.path.open("r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            csv_headers = reader.fieldnames or []
            # build mapping from CSV header label -> canonical field name
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
                    # map human-friendly label back to canonical field name when possible
                    if csv_key in label_to_field:
                        normalized[label_to_field[csv_key]] = val
                    else:
                        # keep unknown columns as-is (pydantic will ignore extras)
                        normalized[csv_key] = val
                # normalize empty strings to None
                for k, v in normalized.items():
                    if v == "":
                        normalized[k] = None
                records.append(Record.from_dict(normalized))
        return records

    def _write_all(self, records: List[Record]) -> None:
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", newline="", encoding="utf-8") as f:
            # write human-friendly header labels (so CSV is readable)
            header_writer = csv.writer(f)
            header_writer.writerow(self._header_labels())
            # use canonical FIELDNAMES for writing rows so loading is deterministic
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            for r in records:
                # sanitize None -> empty string for CSV portability
                row = {k: ("" if v is None else v) for k, v in r.to_dict().items()}
                writer.writerow(row)
        shutil.move(str(tmp), str(self.path))

    def backfill_derived(self) -> int:
        """Rewrite the CSV so each row includes the derived metric columns.

        Returns the number of records written.
        """
        records = self.load_all()
        # writing via _write_all will include the derived fields from Record.to_dict()
        self._write_all(records)
        return len(records)

    def restore_backup(self) -> Path:
        """Restore the storage from the simple `.bak` file (non-timestamped).

        This method mirrors the CSV behaviour.  After overwriting the file we
        drop the in-memory connection so subsequent operations reopen the new
        database.
        """
        bak = self.path.with_name(self.path.name + ".bak")
        if not bak.exists():
            raise FileNotFoundError("Backup file not found")
        pre = self.path.with_name(self.path.name + ".pre_restore.bak")
        shutil.copyfile(str(self.path), str(pre))
        shutil.copyfile(str(bak), str(self.path))
        self._reset_conn()
        return pre

    def create_timestamped_backup(self, keep: int = 14) -> Path:
        """Create a timestamped backup in a `backups/` subdirectory and rotate.

        - backup filename: `<name>.<YYYYmmddTHHMMSSffffffZ>.bak`
        - keeps at most `keep` recent backups (oldest removed)
        - returns Path to the created backup
        """
        backup_dir = self.path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        # include microsecond precision so multiple rapid backups don't collide
        ts = datetime.now().strftime("%Y%m%dT%H%M%S%fZ")
        dest = backup_dir / f"{self.path.name}.{ts}.bak"
        shutil.copyfile(str(self.path), str(dest))

        # rotation: keep only the newest `keep` backups for this file
        pattern = f"{self.path.name}.*.bak"
        files = sorted(backup_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in files[keep:]:
            try:
                old.unlink()
            except Exception:
                pass
        return dest

    def list_backups(self) -> list[Path]:
        """Return list of timestamped backup Paths sorted newest->oldest."""
        backup_dir = self.path.parent / "backups"
        if not backup_dir.exists():
            return []
        files = sorted(backup_dir.glob(f"{self.path.name}.*.bak"), key=lambda p: p.stat().st_mtime, reverse=True)
        return files

    def delete_backup(self, backup: Path) -> None:
        """Delete the specified backup file (no-op if missing)."""
        try:
            backup.unlink()
        except Exception:
            pass

    def restore_from_backup(self, backup: Path) -> Path:
        """Restore the main storage from a specific timestamped backup file.

        Returns the path to a pre-restore backup created before overwriting.
        """
        if not backup.exists():
            raise FileNotFoundError("Specified backup not found")
        pre = self.path.with_name(self.path.name + ".pre_restore.bak")
        shutil.copyfile(str(self.path), str(pre))
        shutil.copyfile(str(backup), str(self.path))
        self._reset_conn()
        return pre

    def save(self, record: Record) -> Record:
        records = self.load_all()
        if any(r.id == record.id for r in records):
            return self.update(record.id, record)
        records.append(record)
        self._write_all(records)
        return record

    def update(self, id: str, record: Record) -> Record:
        records = self.load_all()
        updated = False
        for i, r in enumerate(records):
            if r.id == id:
                records[i] = record
                updated = True
                break
        if not updated:
            records.append(record)
        self._write_all(records)
        return record

    def delete(self, id: str) -> None:
        records = [r for r in self.load_all() if r.id != id]
        self._write_all(records)

    def export_csv(self, dest: Path) -> None:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(self.path), str(dest))


class SQLiteDataManager:
    """SQLite-backed persistence layer mirroring the CSV API.

    The schema mirrors FIELDNAMES. Numeric fields (`field3`, `field6`,
    `field7`, `gp`, `cash_margin`, `gp70`) are stored as REAL; others as
    TEXT. Derived values are not stored but computed via the Record model.

    Connection handling is defensive: the database file may be missing or
    corrupted, in which case operations will lazily open/reopen the
    connection.  After a restore or repair we drop any existing connection
    so it can be recreated against the new file contents.
    """

    CREATE_TABLE = (
        "CREATE TABLE IF NOT EXISTS records ("
        "id TEXT PRIMARY KEY,"
        "field1 TEXT,"
        "field2 TEXT,"
        "field3 REAL,"
        "field4 TEXT,"
        "field5 TEXT,"
        "field6 REAL,"
        "field7 REAL,"
        "gp REAL,"
        "cash_margin REAL,"
        "gp70 REAL,"
        "created_at TEXT"
        ")"
    )

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else DEFAULT_DB
        self._conn: Optional[sqlite3.Connection] = None
        self._ensure_conn()

    def _ensure_conn(self) -> None:
        if self._conn is not None:
            return
        try:
            self._conn = sqlite3.connect(str(self.path))
            self._conn.execute(self.CREATE_TABLE)
            self._conn.commit()
        except sqlite3.DatabaseError:
            # leave _conn None; calls will try again later or may fail
            self._conn = None

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
        records: List[Record] = []
        for row in rows:
            d = dict(zip([
                "id",
                "field1",
                "field2",
                "field3",
                "field4",
                "field5",
                "field6",
                "field7",
                "gp",
                "cash_margin",
                "gp70",
                "created_at",
            ], row))
            for k, v in d.items():
                if v == "":
                    d[k] = None
            records.append(Record.from_dict(d))
        return records

    def _write_all(self, records: List[Record]) -> None:
        self._ensure_conn()
        if self._conn is None:
            raise RuntimeError("database unavailable")
        cur = self._conn.cursor()
        cur.execute("DELETE FROM records")
        for r in records:
            data = r.to_dict()
            cur.execute(
                "INSERT OR REPLACE INTO records (id, field1, field2, field3, field4, field5, field6, field7, gp, cash_margin, gp70, created_at) "
                "VALUES (:id, :field1, :field2, :field3, :field4, :field5, :field6, :field7, :gp, :cash_margin, :gp70, :created_at)",
                data,
            )
        self._conn.commit()

    def backfill_derived(self) -> int:
        self._ensure_conn()
        if self._conn is None:
            return 0
        cur = self._conn.cursor()
        cur.execute("SELECT COUNT(*) FROM records")
        return cur.fetchone()[0]

    # backup/restore methods mirror CSV behaviour but operate on the file
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
        files = sorted(backup_dir.glob(f"{self.path.name}.*.bak"), key=lambda p: p.stat().st_mtime, reverse=True)
        return files

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
        # insert or replace
        cur = self._conn.cursor()
        data = record.to_dict()
        cur.execute(
            "INSERT OR REPLACE INTO records (id, field1, field2, field3, field4, field5, field6, field7, gp, cash_margin, gp70, created_at) "
            "VALUES (:id, :field1, :field2, :field3, :field4, :field5, :field6, :field7, :gp, :cash_margin, :gp70, :created_at)",
            data,
        )
        self._conn.commit()
        return record

    def update(self, id: str, record: Record) -> Record:
        return self.save(record)

    def delete(self, id: str) -> None:
        cur = self._conn.cursor()
        cur.execute("DELETE FROM records WHERE id = ?", (id,))
        self._conn.commit()

    def export_csv(self, dest: Path) -> None:
        # dump table to CSV file
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        rows = self.load_all()
        # reuse CSV write logic from CSVDataManager
        tmp_dm = CSVDataManager(dest)
        tmp_dm._write_all(rows)


class DataManager:
    """Wrapper that selects backend based on file extension.

    Default is SQLite (data.db). CSV remains supported for legacy usage and
    triggers a deprecation warning. When no path is provided and a legacy
    CSV exists at the default location, it is automatically migrated to the
    default database before the backend is opened.
    """

    def __init__(self, path: Optional[Path] = None):
        # determine which storage file to use, performing auto-migration when
        # necessary.
        if path is None:
            # prefer existing DB; if missing but CSV exists, or the existing DB
            # contains no records, migrate from CSV.  this covers the case where
            # an empty data.db was created earlier but the user has populated
            # data.csv afterwards.
            db_should_migrate = False
            if not DEFAULT_DB.exists() and DEFAULT_CSV.exists():
                db_should_migrate = True
            elif DEFAULT_DB.exists() and DEFAULT_CSV.exists():
                try:
                    # open temporary manager to inspect
                    tmp = SQLiteDataManager(DEFAULT_DB)
                    if len(tmp.load_all()) == 0:
                        db_should_migrate = True
                    # ensure connection is closed so we can delete later if needed
                    tmp._reset_conn()
                except Exception:
                    # if the database is corrupt, better to overwrite it
                    db_should_migrate = True
            if db_should_migrate and DEFAULT_CSV.exists():
                warnings.warn(
                    "legacy CSV detected; migrating to SQLite database",
                    UserWarning,
                )
                # remove existing destination if present, so migrate can write
                try:
                    DEFAULT_DB.unlink()
                except Exception:
                    pass
                DataManager.migrate_from_csv(DEFAULT_CSV, DEFAULT_DB)
            path = DEFAULT_DB
        else:
            path = Path(path)

        if path.suffix.lower() == ".csv":
            warnings.warn("CSV storage is deprecated; use a .db file", DeprecationWarning)
            self._backend = CSVDataManager(path)
        else:
            self._backend = SQLiteDataManager(path)

    def __getattr__(self, name):
        # delegate all unknown attributes to backend
        return getattr(self._backend, name)

    @staticmethod
    def migrate_from_csv(src: Path, dest: Path) -> None:
        """Copy all records from a CSV source into a SQLite destination.

        If the destination file already exists it will be removed first; the
        operation is therefore _idempotent_.  This simplifies auto-migration
        and avoids errors when the database is present but empty.
        """
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
        for r in rows:
            db_dm.save(r)
