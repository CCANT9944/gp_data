from __future__ import annotations

from collections.abc import Callable, Iterable

from ..models import Record


class DuplicateDetector:
    def __init__(self, load_records: Callable[[], Iterable[Record]]):
        self._load_records = load_records

    def duplicate_identity(self, record: Record) -> tuple[str, str] | None:
        field1 = (record.field1 or "").strip().lower()
        field2 = (record.field2 or "").strip().lower()
        if not field1 or not field2:
            return None
        return field1, field2

    def find_duplicate_record(self, record: Record, exclude_id: str | None = None) -> Record | None:
        identity = self.duplicate_identity(record)
        if identity is None:
            return None
        for existing in self._load_records():
            if exclude_id is not None and existing.id == exclude_id:
                continue
            if self.duplicate_identity(existing) == identity:
                return existing
        return None