from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable, Optional

from pydantic import ValidationError

from .data_manager import DataManager
from .ui import GPDataApp


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gp_data")
    parser.add_argument("--storage", type=Path, help="path to storage file (SQLite .db or legacy .csv)")
    subs = parser.add_subparsers(dest="command", help="sub-commands")
    subs.required = False

    subs.add_parser("gui", help="run the graphical UI (default)")
    subs.add_parser("list", help="list all records")

    add = subs.add_parser("add", help="add a new record")
    add.add_argument("--field1", required=True, help="value for Field 1")
    add.add_argument("--field2", help="value for Field 2")
    add.add_argument("--field3", type=float, help="numeric value for Field 3")
    add.add_argument("--field4", help="value for Field 4")
    add.add_argument("--field5", help="value for Field 5")
    add.add_argument("--field6", type=float, help="numeric value for Field 6 / cost")
    add.add_argument("--field7", type=float, help="numeric value for Field 7 / menu price")

    subs.add_parser("backup", help="create a timestamped backup of the CSV")
    subs.add_parser("restore", help="restore from the latest `.bak` file")

    exp = subs.add_parser("export", help="export CSV to a destination path")
    exp.add_argument("dest", help="destination file path")

    mig = subs.add_parser("migrate", help="convert CSV storage to SQLite database")
    mig.add_argument("src", help="source CSV file path")
    mig.add_argument("dest", help="destination DB file path")

    cleanup = subs.add_parser("cleanup", help="remove legacy CSV files and simple backups")
    cleanup.add_argument("--path", type=Path, help="optional storage folder to clean (defaults to package)")
    return parser


def run_gui(storage_path: Optional[Path] = None) -> None:
    app = GPDataApp(storage_path)
    app.run()


def _load_data_manager(command: str, storage: Optional[Path]) -> DataManager | None:
    if command == "migrate":
        return None
    return DataManager(storage) if storage else DataManager()


def _handle_restore(dm: DataManager) -> int:
    try:
        try:
            pre = dm.restore_backup()
        except FileNotFoundError:
            backups = dm.list_backups()
            if not backups:
                raise
            pre = dm.restore_from_backup(backups[0])
        print(f"restored from backup (pre-restore at {pre})")
        return 0
    except FileNotFoundError:
        print("no backup file found", file=sys.stderr)
        return 1


def _handle_cleanup(base: Path) -> None:
    files = [
        base / "data.csv",
        base / "data.csv.bak",
        base / "data.csv.pre_restore.bak",
        base / "old.csv",
    ]
    removed: list[str] = []
    failed: list[str] = []
    for path in files:
        try:
            if path.exists():
                path.unlink()
                removed.append(str(path))
        except FileNotFoundError:
            continue
        except OSError:
            failed.append(str(path))
    if removed:
        print("removed:", ", ".join(removed))
    if failed:
        print("unable to remove:", ", ".join(failed), file=sys.stderr)
    if not removed and not failed:
        print("nothing to clean")


def run_cli(argv: Optional[Iterable[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    command = args.command or "gui"
    data_manager = _load_data_manager(command, args.storage)

    if command == "gui":
        run_gui(args.storage)
        return 0

    if command == "list":
        for record in data_manager.load_all():
            print(record.to_dict())
        return 0

    if command == "add":
        from .models import Record

        data: dict = {}
        for field in ("field1", "field2", "field3", "field4", "field5", "field6", "field7"):
            val = getattr(args, field)
            if val is not None:
                data[field] = val
        record = Record(**data)
        data_manager.save(record)
        print("added", record.id)
        return 0

    if command == "backup":
        path = data_manager.create_timestamped_backup()
        print(f"backup saved to {path}")
        return 0

    if command == "restore":
        return _handle_restore(data_manager)

    if command == "export":
        dest = Path(args.dest)
        data_manager.export_csv(dest)
        print(f"exported to {dest}")
        return 0

    if command == "migrate":
        try:
            DataManager.migrate_from_csv(Path(args.src), Path(args.dest))
            print(f"migrated data from {args.src} to {args.dest}")
            return 0
        except (OSError, RuntimeError, ValueError, ValidationError) as exc:
            print("migration failed:", exc, file=sys.stderr)
            return 1

    if command == "cleanup":
        base = Path(args.path) if args.path else Path(__file__).parent
        _handle_cleanup(base)
        return 0

    parser.print_help()
    return 0


def main(argv: Optional[Iterable[str]] = None) -> int:
    return run_cli(argv)