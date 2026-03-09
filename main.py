"""Entrypoint for gp_data UI.

This module is runnable both as a package (python -m gp_data) and as a
standalone script (python main.py) from the `gp_data/` directory.
"""
from pathlib import Path

# When run as a script (python main.py) the module has no package context;
# add the parent folder to sys.path and set __package__ so relative imports
# (used across the package) resolve correctly. If the module is executed
# with -m (python -m gp_data) this block is a no-op.
if __package__ is None:
    import os
    import sys

    parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if parent not in sys.path:
        sys.path.insert(0, parent)
    __package__ = "gp_data"

from .ui import GPDataApp
from .data_manager import DataManager

import argparse
import sys
from pathlib import Path
from typing import Iterable, Optional


# --- CLI / entrypoint helpers ---------------------------------------------

def run_gui(storage_path: Optional[Path] = None) -> None:
    """Start the graphical Tkinter application."""
    app = GPDataApp(storage_path)
    app.run()


def run_cli(argv: Optional[Iterable[str]] = None) -> None:
    """Command-line interface for basic data operations.

    If no subcommand is provided the GUI is launched by default (alias
    ``gui``).
    """
    parser = argparse.ArgumentParser(prog="gp_data")
    parser.add_argument("--storage", type=Path, help="path to storage file (SQLite .db or legacy .csv)")
    subs = parser.add_subparsers(dest="command", help="sub-commands")
    subs.required = False

    subs.add_parser("gui", help="run the graphical UI (default)")
    subs.add_parser("list", help="list all records")

    add = subs.add_parser("add", help="add a new record")
    add.add_argument("--field1", required=True, help="value for Field 1")
    add.add_argument("--field2", help="value for Field 2")
    add.add_argument("--field3", type=float, help="numeric value for Field 3")
    add.add_argument("--field4", help="value for Field 4")
    add.add_argument("--field5", help="value for Field 5")
    add.add_argument("--field6", type=float, help="numeric value for Field 6 / cost")
    add.add_argument("--field7", type=float, help="numeric value for Field 7 / menu price")

    subs.add_parser("backup", help="create a timestamped backup of the CSV")
    subs.add_parser("restore", help="restore from the latest `.bak` file")

    exp = subs.add_parser("export", help="export CSV to a destination path")
    exp.add_argument("dest", help="destination file path")

    mig = subs.add_parser("migrate", help="convert CSV storage to SQLite database")
    mig.add_argument("src", help="source CSV file path")
    mig.add_argument("dest", help="destination DB file path")

    cleanup = subs.add_parser("cleanup", help="remove legacy CSV files and simple backups")
    cleanup.add_argument("--path", type=Path, help="optional storage folder to clean (defaults to package")

    args = parser.parse_args(argv)
    cmd = args.command or "gui"
    # create storage backend only for commands that need it; on migrate we
    # avoid touching the default DB path so we don't accidentally create a
    # file before the migration logic checks for destination existence.
    dm = None
    if cmd not in ("migrate",):
        dm = DataManager(args.storage) if args.storage else DataManager()

    if cmd == "gui":
        run_gui(args.storage)
    elif cmd == "list":
        for r in dm.load_all():
            print(r.to_dict())
    elif cmd == "add":
        data: dict = {}
        for f in ("field1", "field2", "field3", "field4", "field5", "field6", "field7"):
            val = getattr(args, f)
            if val is not None:
                data[f] = val
        from .models import Record

        rec = Record(**data)
        dm.save(rec)
        print("added", rec.id)
    elif cmd == "backup":
        path = dm.create_timestamped_backup()
        print(f"backup saved to {path}")
    elif cmd == "restore":
        try:
            # first try the simple `.bak` file, which is what the GUI and
            # legacy tests expect.  if that doesn't exist fall back to the
            # more modern timestamped backups created by `backup` and
            # `DataManager.create_timestamped_backup`.
            try:
                pre = dm.restore_backup()
            except FileNotFoundError:
                backups = dm.list_backups()
                if not backups:
                    raise
                pre = dm.restore_from_backup(backups[0])
            print(f"restored from backup (pre-restore at {pre})")
        except FileNotFoundError:
            print("no backup file found", file=sys.stderr)
            sys.exit(1)
    elif cmd == "export":
        dest = Path(args.dest)
        dm.export_csv(dest)
        print(f"exported to {dest}")
    elif cmd == "migrate":
        try:
            DataManager.migrate_from_csv(Path(args.src), Path(args.dest))
            print(f"migrated data from {args.src} to {args.dest}")
        except Exception as exc:
            print("migration failed:", exc, file=sys.stderr)
            sys.exit(1)
    elif cmd == "cleanup":
        # remove legacy CSV storage and simple backups
        base = Path(args.path) if args.path else Path(__file__).parent
        files = [
            base / "data.csv",
            base / "data.csv.bak",
            base / "data.csv.pre_restore.bak",
            base / "old.csv",
        ]
        removed = []
        for f in files:
            try:
                if f.exists():
                    f.unlink()
                    removed.append(str(f))
            except Exception:
                pass
        if removed:
            print("removed:", ", ".join(removed))
        else:
            print("nothing to clean")
    else:
        parser.print_help()


if __name__ == "__main__":
    # delegate to CLI entrypoint so `python -m gp_data` supports subcommands
    run_cli()
