from __future__ import annotations

import logging
import sqlite3
import tkinter as tk
from datetime import datetime
from pathlib import Path
from time import perf_counter
from tkinter import messagebox, ttk
from typing import Callable

from .storage_feedback import describe_storage_error


LOGGER = logging.getLogger(__name__)


def _log_backup_dialog_performance(operation: str, started_at: float, **fields: object) -> None:
    if not LOGGER.isEnabledFor(logging.DEBUG):
        return
    duration_ms = (perf_counter() - started_at) * 1000.0
    details = ", ".join(f"{key}={value}" for key, value in fields.items())
    if details:
        LOGGER.debug("Backup dialog %s took %.1fms (%s)", operation, duration_ms, details)
        return
    LOGGER.debug("Backup dialog %s took %.1fms", operation, duration_ms)


def _format_backup_label(path: Path) -> str:
    name = path.name
    if not name.endswith(".bak"):
        return name
    stem = name[:-4]
    base, sep, stamp = stem.rpartition(".")
    if not sep:
        return name
    try:
        dt = datetime.strptime(stamp, "%Y%m%dT%H%M%S%fZ")
    except ValueError:
        return name
    return f"{dt.strftime('%Y-%m-%d %H:%M:%S.%f')} UTC - {base}"


def _is_sqlite_backup(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(16) == b"SQLite format 3\x00"
    except OSError:
        return False


def _preview_metadata(path: Path) -> list[str]:
    stat = path.stat()
    modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    return [
        f"Name: {path.name}",
        f"Saved: {modified}",
        f"Size: {stat.st_size:,} bytes",
    ]


def _build_sqlite_backup_preview(path: Path) -> str:
    lines = _preview_metadata(path)
    lines.append("Type: SQLite backup")
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row[0] for row in cur.fetchall()]
        lines.append(f"Tables: {', '.join(tables) if tables else '(none)'}")
        if "records" not in tables:
            return "\n".join(lines + ["", "No records table found in this backup."])

        cur.execute("SELECT COUNT(*) FROM records")
        count = cur.fetchone()[0]
        lines.append(f"Records: {count}")
        lines.append("")
        lines.append("Recent entries:")
        cur.execute("SELECT field1, field2, created_at FROM records ORDER BY created_at DESC LIMIT 5")
        rows = cur.fetchall()
        if not rows:
            lines.append("- No rows in records")
        else:
            for field1, field2, created_at in rows:
                left = field1 or "(blank)"
                right = field2 or "(blank)"
                stamp = created_at or "(no timestamp)"
                lines.append(f"- {left} | {right} | {stamp}")
        return "\n".join(lines)
    finally:
        conn.close()


def _build_backup_preview(path: Path) -> str:
    started_at = perf_counter()
    if _is_sqlite_backup(path):
        try:
            preview_text = _build_sqlite_backup_preview(path)
            _log_backup_dialog_performance("build backup preview", started_at, path=path.name, kind="sqlite")
            return preview_text
        except (sqlite3.DatabaseError, OSError, ValueError) as exc:
            lines = _preview_metadata(path)
            lines.append("Type: SQLite backup")
            lines.append("")
            lines.append(f"Unable to inspect database contents: {exc}")
            preview_text = "\n".join(lines)
            _log_backup_dialog_performance("build backup preview", started_at, path=path.name, kind="sqlite-error")
            return preview_text

    lines = _preview_metadata(path)
    lines.append("Type: Text backup")
    lines.append("")
    try:
        text = path.read_text(encoding="utf-8")
        lines.append(text[:2000])
    except (OSError, UnicodeDecodeError) as exc:
        lines.append(f"Unable to preview text contents: {exc}")
    preview_text = "\n".join(lines)
    _log_backup_dialog_performance("build backup preview", started_at, path=path.name, kind="text")
    return preview_text


def open_manage_backups_dialog(
    parent: tk.Misc,
    data_manager,
    on_restored: Callable[[], None] | None = None,
    build_preview: Callable[[Path], str] = _build_backup_preview,
) -> tk.Toplevel:
    win = tk.Toplevel(parent)
    win.title("Manage Backups")
    win.geometry("720x360")

    btn_frame = ttk.Frame(win)
    btn_frame.pack(side="bottom", fill="x", padx=8, pady=6)
    btn_restore = ttk.Button(btn_frame, text="Restore", state="disabled")
    btn_delete = ttk.Button(btn_frame, text="Delete", state="disabled")
    btn_close = ttk.Button(btn_frame, text="Close", command=win.destroy)
    btn_delete.pack(side="right", padx=4)
    btn_restore.pack(side="right", padx=4)
    btn_close.pack(side="right", padx=4)

    content = ttk.Frame(win)
    content.pack(fill="both", expand=True)

    left = ttk.Frame(content)
    left.pack(side="left", fill="y", padx=8, pady=8)
    lb = tk.Listbox(left, width=48, height=18)
    lb.pack(side="top", fill="y", expand=True)

    info = ttk.Label(left, text="Select a backup to preview or restore")
    info.pack(side="top", pady=(6, 0))

    right = ttk.Frame(content)
    right.pack(side="left", fill="both", expand=True, padx=8, pady=8)
    preview = tk.Text(right, wrap="none", height=20)
    preview.pack(fill="both", expand=True)

    backup_paths: list[Path] = []
    preview_cache: dict[Path, str] = {}

    def _selected_backup_path() -> Path | None:
        selection = lb.curselection()
        if not selection:
            return None
        index = selection[0]
        if index >= len(backup_paths):
            return None
        return backup_paths[index]

    def _refresh_list() -> None:
        nonlocal backup_paths
        started_at = perf_counter()
        backup_paths = list(data_manager.list_backups())
        preview_cache_keys = set(backup_paths)
        for cached_path in list(preview_cache):
            if cached_path not in preview_cache_keys:
                del preview_cache[cached_path]
        lb.delete(0, "end")
        for path in backup_paths:
            lb.insert("end", _format_backup_label(path))
        preview.delete("1.0", "end")
        btn_restore.config(state="disabled")
        btn_delete.config(state="disabled")
        _log_backup_dialog_performance("refresh backups list", started_at, backups=len(backup_paths))

    _refresh_list()

    def _on_select(_event=None) -> None:
        path = _selected_backup_path()
        if path is None:
            preview.delete("1.0", "end")
            btn_restore.config(state="disabled")
            btn_delete.config(state="disabled")
            return
        started_at = perf_counter()
        preview.delete("1.0", "end")
        cached = path in preview_cache
        preview_text = preview_cache.get(path)
        if preview_text is None:
            preview_text = build_preview(path)
            preview_cache[path] = preview_text
        preview.insert("1.0", preview_text)
        btn_restore.config(state="normal")
        btn_delete.config(state="normal")
        _log_backup_dialog_performance("select backup", started_at, path=path.name, cached=cached)

    def _do_restore() -> None:
        path = _selected_backup_path()
        if path is None:
            return
        label = _format_backup_label(path)
        if not messagebox.askyesno("Restore", f"Restore from {label}?"):
            return
        try:
            pre_restore = data_manager.restore_from_backup(path)
            if on_restored is not None:
                on_restored()
            messagebox.showinfo("Restored", f"Restored {label}; pre-restore at {pre_restore}")
            _refresh_list()
        except (OSError, RuntimeError, ValueError, sqlite3.DatabaseError) as exc:
            messagebox.showerror("Restore failed", describe_storage_error("restore the selected backup", path, exc))

    def _do_delete() -> None:
        path = _selected_backup_path()
        if path is None:
            return
        label = _format_backup_label(path)
        if not messagebox.askyesno("Delete", f"Delete backup {label}?"):
            return
        try:
            data_manager.delete_backup(path)
            _refresh_list()
        except (OSError, RuntimeError, ValueError) as exc:
            messagebox.showerror("Delete failed", describe_storage_error("delete the selected backup", path, exc))

    lb.bind("<<ListboxSelect>>", _on_select)
    btn_restore.config(command=_do_restore)
    btn_delete.config(command=_do_delete)
    try:
        win.transient(parent)
        win.grab_set()
    except tk.TclError:
        LOGGER.debug("Unable to make backups dialog modal", exc_info=True)
    return win