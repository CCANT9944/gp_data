from __future__ import annotations

import sqlite3
from pathlib import Path


def _path_text(path: Path | None) -> str:
    return str(path) if path is not None else "the selected file"


def describe_storage_error(action: str, path: Path | None, exc: Exception) -> str:
    reason = str(exc).strip() or exc.__class__.__name__
    location = _path_text(path)
    lower_reason = reason.lower()

    if isinstance(exc, PermissionError) or "sharing violation" in lower_reason or "used by another process" in lower_reason:
        guidance = "Close Excel or any other program using the file, then try again."
    elif isinstance(exc, FileNotFoundError):
        guidance = "Check that the file still exists and that the folder is available."
    elif isinstance(exc, sqlite3.DatabaseError):
        guidance = "The database contents look unreadable. Restore a backup or recover from another known-good copy."
    else:
        guidance = "Check that the folder exists and that Windows is allowing the app to read and write there."

    return f"Could not {action} for {location}.\n\nReason: {reason}\n\n{guidance}"


def describe_backup_failure(action: str, path: Path | None, exc: Exception) -> str:
    location = _path_text(path)
    base = describe_storage_error(f"create a safety backup before {action}", path, exc)
    return f"{base}\n\nContinue {action} without creating a backup of {location}?"


def describe_startup_storage_issue(path: Path | None, exc: Exception) -> str:
    location = _path_text(path)
    reason = str(exc).strip() or exc.__class__.__name__
    return (
        f"The app could not fully open {location}.\n\n"
        f"Reason: {reason}\n\n"
        "Your existing file has not been deleted. You can try closing other programs that may be using it, restore from a backup, or recover from another known-good copy."
    )
