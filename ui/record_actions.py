from __future__ import annotations

from typing import Callable

from pydantic import ValidationError

from ..data_manager import DataManager
from ..models import Record


class RecordActions:
    def __init__(
        self,
        data_manager: DataManager,
        *,
        show_validation_error: Callable[[str], None],
        show_selection_error: Callable[[str], None],
        show_missing_record_error: Callable[[], None],
        confirm_duplicate_record: Callable[..., bool],
        create_safety_backup_or_confirm: Callable[[str], bool],
        show_storage_error: Callable[[str, str, Exception], None],
        apply_saved_record: Callable[..., None],
        load_records: Callable[[], None],
        reset_to_new_item: Callable[[], None],
    ):
        self._data_manager = data_manager
        self._show_validation_error = show_validation_error
        self._show_selection_error = show_selection_error
        self._show_missing_record_error = show_missing_record_error
        self._confirm_duplicate_record = confirm_duplicate_record
        self._create_safety_backup_or_confirm = create_safety_backup_or_confirm
        self._show_storage_error = show_storage_error
        self._apply_saved_record = apply_saved_record
        self._load_records = load_records
        self._reset_to_new_item = reset_to_new_item

    def record_by_id(self, record_id: str) -> Record | None:
        records = self._data_manager.load_all()
        return next((record for record in records if record.id == record_id), None)

    def record_id_or_show_selection_error(self, record_id: str | None, message: str) -> str | None:
        if record_id:
            return record_id
        self._show_selection_error(message)
        return None

    def record_or_show_missing_error(self, record_id: str | None, *, selection_message: str | None = None) -> Record | None:
        resolved_record_id = record_id
        if selection_message is not None:
            resolved_record_id = self.record_id_or_show_selection_error(record_id, selection_message)
            if resolved_record_id is None:
                return None
        elif resolved_record_id is None:
            return None

        record = self.record_by_id(resolved_record_id)
        if record is None:
            self._show_missing_record_error()
            return None
        return record

    def build_record_or_show_error(self, data: dict, *, record_id: str | None = None, created_at=None) -> Record | None:
        payload = dict(data)
        if record_id is not None:
            payload["id"] = record_id
            payload["created_at"] = created_at
        try:
            return Record(**payload)
        except (ValidationError, ValueError, TypeError) as exc:
            self._show_validation_error(str(exc))
            return None

    def save_new_record(self, record: Record) -> bool:
        if not self._create_safety_backup_or_confirm("adding this record"):
            return False
        try:
            self._data_manager.save(record)
        except (OSError, RuntimeError, ValueError) as exc:
            self._show_storage_error("Save failed", "save the new record", exc)
            return False
        self._load_records()
        self._reset_to_new_item()
        return True

    def save_existing_record(
        self,
        original_record: Record,
        updated_record: Record,
        *,
        duplicate_action_text: str,
        backup_action: str,
        error_title: str,
        error_action: str,
        refresh_form_mode: bool = True,
    ) -> Record | None:
        if not self._confirm_duplicate_record(updated_record, exclude_id=original_record.id, action_text=duplicate_action_text):
            return None
        if not self._create_safety_backup_or_confirm(backup_action):
            return None
        try:
            saved = self._data_manager.update(original_record.id, updated_record)
        except (OSError, RuntimeError, ValueError) as exc:
            self._show_storage_error(error_title, error_action, exc)
            return None
        self._apply_saved_record(saved, refresh_form_mode=refresh_form_mode)
        return saved

    def delete_record(
        self,
        record_id: str,
        *,
        backup_action: str,
        error_title: str,
        error_action: str,
    ) -> bool:
        if not self._create_safety_backup_or_confirm(backup_action):
            return False
        try:
            self._data_manager.delete(record_id)
        except (OSError, RuntimeError, ValueError) as exc:
            self._show_storage_error(error_title, error_action, exc)
            return False
        self._load_records()
        self._reset_to_new_item()
        return True