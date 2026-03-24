from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Iterable, Optional

from pydantic import ValidationError

from .data_manager import DataManager
from .formulas import set_active_formula_expressions
from .settings import SettingsStore


CSV_PREVIEW_DEBUG_ENV = "GP_DATA_CSV_PREVIEW_DEBUG"
CSV_PREVIEW_DEBUG_LOG_ENV = "GP_DATA_CSV_PREVIEW_DEBUG_LOG"
DEFAULT_CSV_PREVIEW_DEBUG_LOG = Path(__file__).with_name("csv_preview_debug.log")
CSV_PREVIEW_LOGGER_NAME = "gp_data.ui.csv_preview"
CSV_PREVIEW_LOG_HANDLER_NAME = "gp_data.csv_preview_debug_file"


def _env_flag_enabled(raw_value: str | None) -> bool:
    if raw_value is None:
        return False
    return raw_value.strip().casefold() not in {"", "0", "false", "no", "off"}


def _configure_csv_preview_debug_logging(log_path: Path) -> Path:
    resolved_path = Path(log_path)
    resolved_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(CSV_PREVIEW_LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    stale_handlers = [
        handler
        for handler in logger.handlers
        if getattr(handler, "name", "") == CSV_PREVIEW_LOG_HANDLER_NAME
    ]
    for handler in stale_handlers:
        logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass

    file_handler = logging.FileHandler(resolved_path, encoding="utf-8")
    file_handler.name = CSV_PREVIEW_LOG_HANDLER_NAME
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(file_handler)
    return resolved_path


def _resolve_csv_preview_debug_log_path(args) -> Path | None:
    requested_path = args.csv_preview_debug_log
    if requested_path is not None:
        return Path(requested_path)

    env_path = os.getenv(CSV_PREVIEW_DEBUG_LOG_ENV)
    if env_path:
        return Path(env_path)

    if args.csv_preview_debug or _env_flag_enabled(os.getenv(CSV_PREVIEW_DEBUG_ENV)):
        return DEFAULT_CSV_PREVIEW_DEBUG_LOG
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gp_data")
    parser.add_argument("--storage", type=Path, help="path to storage file (SQLite .db or legacy .csv)")
    parser.add_argument(
        "--csv-preview-debug",
        action="store_true",
        help="write CSV preview timing logs to a local debug log file",
    )
    parser.add_argument(
        "--csv-preview-debug-log",
        type=Path,
        help="path for the CSV preview timing log file (implies CSV preview debug logging)",
    )
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
    from .ui import GPDataApp

    app = GPDataApp(storage_path)
    app.run()


def _load_data_manager(command: str, storage: Optional[Path]) -> DataManager | None:
    if command == "migrate":
        return None
    return DataManager(storage) if storage else DataManager()


def _initialize_runtime_formula_expressions() -> None:
    set_active_formula_expressions(SettingsStore().load_formula_expressions())


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
    csv_preview_debug_log_path = _resolve_csv_preview_debug_log_path(args)
    if csv_preview_debug_log_path is not None:
        csv_preview_debug_log_path = _configure_csv_preview_debug_logging(csv_preview_debug_log_path)
    data_manager = _load_data_manager(command, args.storage)

    if command not in {"gui", "migrate", "cleanup"}:
        _initialize_runtime_formula_expressions()

    if command == "gui":
        if csv_preview_debug_log_path is not None:
            print(f"csv preview timing logs -> {csv_preview_debug_log_path}")
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