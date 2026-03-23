from __future__ import annotations

import logging
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Sequence

from pydantic import ValidationError

from ...data_manager.duplicates import (
    duplicate_identity_for_values,
    import_selection_possible_duplicate_identity_for_values,
    possible_duplicate_identity_for_values,
)
from gp_data.settings import SettingsStore
from ...models import Record, calculate_field6
from .analysis import PreviewAnalysisSnapshot, build_preview_analysis_snapshot
from .analysis_dialog import build_csv_preview_analysis_view, open_csv_preview_analysis_dialog_from_snapshot
from .analysis_launcher import _AnalysisSnapshotCoordinator, _PreviewAnalysisLauncher
from .dialog_support import (
    _build_tree as _build_tree_impl,
    _column_ids as _column_ids_impl,
    _column_width as _column_width_impl,
    _default_csv_preview_export_directory as _default_csv_preview_export_directory_impl,
    _default_csv_preview_export_path as _default_csv_preview_export_path_impl,
    _normalized_visible_column_indices as _normalized_visible_column_indices_impl,
    _paths_match as _paths_match_impl,
    _prepare_csv_preview_export_directory as _prepare_csv_preview_export_directory_impl,
    _rendered_preview_row_limit as _rendered_preview_row_limit_impl,
    _widget_descends_from as _widget_descends_from_impl,
    _write_csv_preview_export as _write_csv_preview_export_impl,
)
from .helpers import (
    HEADER_FILTER_POPUP_LABEL_MAX_LENGTH,
    _compact_filter_popup_label,
    _detect_numeric_columns,
    _detect_quantity_column,
    _detect_session_column,
    _filter_label,
    _header_suggests_numeric,
    _is_identifier_column,
    _loading_summary_text,
    _parse_decimal,
    _row_search_text,
    _sorted_distinct_values,
    _sort_rows,
    _summary_text,
)
from .loader import CsvPreviewData, iter_csv_preview_rows, load_csv_preview, resolve_csv_preview_metadata
from .pipeline import (
    MAX_INDEXED_SOURCE_MEMORY_BYTES as _PIPELINE_MAX_INDEXED_SOURCE_MEMORY_BYTES,
    _FilteredCountUpdate,
    _FilteredPreviewUpdate,
    _PreviewFilterState,
)
from .preview_pipeline import _PreviewDataPipeline
from .runtime_hooks import configure_preview_runtime
from .preview_settings import build_preview_dialog_settings_bindings
from .preview_state import _PreviewViewState
from .refresh_controller import (
    CSV_PREVIEW_LOADING_ROW_TEXT,
    _MetadataErrorUpdate,
    _MetadataResolvedUpdate,
    _PreviewRefreshControllerBase,
)
from .row_combiner import (
    _iter_combined_rows as _iter_combined_rows_impl,
    _iter_rows_before_header_filter as _iter_rows_before_header_filter_impl,
)
from .table_helpers import _PreviewColumnManager, _PreviewRowRenderer
from .table_controller import _PreviewPopupExportController, _PreviewTableController
from ..view_helpers import ProcessingDialogHandle


LOGGER = logging.getLogger(__name__)


MIN_PREVIEW_WIDTH = 800
MIN_PREVIEW_HEIGHT = 420
DEFAULT_COLUMN_WIDTH = 140
MAX_COLUMN_WIDTH = 320
MIN_COLUMN_WIDTH = 80
ROW_INSERT_CHUNK_SIZE = 250
MAX_RENDERED_PREVIEW_ROWS = 5000
MIN_RENDERED_PREVIEW_ROWS = 750
MAX_RENDERED_PREVIEW_CELLS = 60000
HEADER_FILTER_POPUP_WIDTH = 320
HEADER_FILTER_POPUP_HEIGHT = 300
HEADER_FILTER_POPUP_LIST_HEIGHT = 10
CSV_PREVIEW_EXPORT_ENCODING = "utf-8-sig"
MAX_INDEXED_SOURCE_MEMORY_BYTES = _PIPELINE_MAX_INDEXED_SOURCE_MEMORY_BYTES
DEFAULT_IMPORT_FIELD_LABELS = ["Field 1", "Field 2", "Field 3", "Field 4", "Field 5", "Field 6", "Field 7"]
IMPORT_REVIEW_TABLE_COLUMNS = ("include", "field1", "field2", "field7", "status")
LARGE_IMPORT_PREFLIGHT_ROW_COUNT = 250
IMPORT_SELECTION_DUPLICATE_STATUS = "Duplicate with another included import row"
IMPORT_SELECTION_POSSIBLE_DUPLICATE_STATUS = "Possible duplicate with another included import row"


def _log_preview_performance(operation: str, started_at: float, **fields: object) -> None:
    if not LOGGER.isEnabledFor(logging.DEBUG):
        return
    duration_ms = (perf_counter() - started_at) * 1000.0
    details = ", ".join(f"{key}={value}" for key, value in fields.items())
    if details:
        LOGGER.debug("CSV preview %s took %.1fms (%s)", operation, duration_ms, details)
        return
    LOGGER.debug("CSV preview %s took %.1fms", operation, duration_ms)


def _header_mode_text(has_header_row: bool) -> str:
    if has_header_row:
        return "Headers: Row 1"
    return "Headers: Generated"


@dataclass(frozen=True)
class _PreviewDialogWidgets:
    win: tk.Toplevel
    container: ttk.Frame
    workspace_row: ttk.Frame
    summary: ttk.Label
    filter_row: ttk.Frame
    summary_var: tk.StringVar
    query_var: tk.StringVar
    query_entry: ttk.Entry
    combine_sessions_var: tk.BooleanVar
    table_frame: ttk.Frame
    tree: ttk.Treeview
    button_row: ttk.Frame


@dataclass
class _ImportReviewRow:
    row_id: str
    source_row: tuple[str, ...]
    payload: dict[str, object]
    include: bool = True
    overwrite_record_id: str | None = None


@dataclass
class _ReviewRowAnalysis:
    status_by_row_id: dict[str, str]
    collisions_by_row_id: dict[str, _ImportReviewRow]


def _normalized_mapping_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(str(value).replace("_", " ").strip().lower().split())


def _normalized_import_field_labels(labels: Sequence[str] | None) -> list[str]:
    normalized = list(labels or DEFAULT_IMPORT_FIELD_LABELS)
    if len(normalized) < len(DEFAULT_IMPORT_FIELD_LABELS):
        normalized.extend(DEFAULT_IMPORT_FIELD_LABELS[len(normalized):])
    return normalized[: len(DEFAULT_IMPORT_FIELD_LABELS)]


def _header_contains_any(normalized_header: str, tokens: Sequence[str]) -> bool:
    return any(token in normalized_header for token in tokens)


def _import_header_hints(field_name: str) -> tuple[str, ...]:
    if field_name == "field1":
        return ("type", "class", "class name", "classname", "category")
    if field_name == "field2":
        return ("name", "description", "item", "product")
    if field_name == "field3":
        return ("cost", "buy", "purchase", "total")
    if field_name == "field4":
        return ("note", "notes", "supplier", "brand", "size")
    if field_name == "field5":
        return ("unit", "units", "qty", "quantity", "volume", "ml")
    if field_name == "field7":
        return ("selling price", "menu price", "sell price", "price", "revenue", "amount", "sales")
    return ()


def _import_header_match_score(field_name: str, label: str, header: str) -> int:
    normalized_header = _normalized_mapping_text(header)
    normalized_label = _normalized_mapping_text(label)
    if not normalized_header:
        return -1

    header_looks_like_buy_price = _header_contains_any(normalized_header, ("cost", "buy", "purchase", "wholesale"))
    header_looks_like_sell_price = _header_contains_any(normalized_header, ("selling", "menu", "sell", "revenue", "sales"))
    header_has_generic_price = "price" in normalized_header

    score = 0
    if normalized_label and normalized_header == normalized_label:
        score += 100
    elif normalized_label and normalized_label in normalized_header:
        score += 35

    for hint in _import_header_hints(field_name):
        if normalized_header == hint:
            score += 80
        elif hint in normalized_header:
            score += 30

    if field_name == "field7" and "cost" in normalized_header and "price" not in normalized_header:
        score -= 20
    if field_name == "field3" and header_looks_like_sell_price:
        score -= 80
    if field_name == "field3" and header_has_generic_price and not header_looks_like_buy_price:
        score -= 45
    if field_name == "field7" and header_looks_like_buy_price and not header_looks_like_sell_price:
        score -= 60
    return score


def _guess_import_mapping(headers: Sequence[str], field_labels: Sequence[str]) -> dict[str, int | None]:
    guessed_mapping: dict[str, int | None] = {"field6": None}
    used_indices: set[int] = set()
    for offset, field_name in enumerate(("field1", "field2", "field3", "field4", "field5", "field7")):
        label_index = int(field_name[5:]) - 1
        label = field_labels[label_index] if 0 <= label_index < len(field_labels) else field_name
        best_index: int | None = None
        best_score = 0
        for index, header in enumerate(headers):
            if index in used_indices:
                continue
            score = _import_header_match_score(field_name, label, header)
            if score > best_score:
                best_score = score
                best_index = index
        guessed_mapping[field_name] = best_index
        if best_index is not None:
            used_indices.add(best_index)
    return guessed_mapping


def _sample_value_for_column(rows: Sequence[tuple[str, ...]], column_index: int | None) -> str:
    if column_index is None:
        return "Skip this field"
    for row in rows:
        if column_index >= len(row):
            continue
        value = str(row[column_index]).strip()
        if not value:
            continue
        if len(value) > 40:
            return f"Sample: {value[:37]}..."
        return f"Sample: {value}"
    return "Sample: (blank)"


def _mapped_import_value(row: tuple[str, ...], mapping: dict[str, int | None], field_name: str) -> str | None:
    column_index = mapping.get(field_name)
    if column_index is None or column_index < 0 or column_index >= len(row):
        return None
    value = str(row[column_index]).strip()
    return value or None


def _build_import_payload(row: tuple[str, ...], mapping: dict[str, int | None]) -> dict[str, object]:
    payload: dict[str, object] = {
        "field1": _mapped_import_value(row, mapping, "field1"),
        "field2": _mapped_import_value(row, mapping, "field2"),
        "field3": _mapped_import_value(row, mapping, "field3"),
        "field4": _mapped_import_value(row, mapping, "field4"),
        "field5": _mapped_import_value(row, mapping, "field5"),
        "field7": _mapped_import_value(row, mapping, "field7"),
    }
    payload["field6"] = calculate_field6(payload.get("field3"), payload.get("field5"))
    return payload


def _build_import_review_rows(
    filtered_rows: Sequence[tuple[str, ...]],
    mapping: dict[str, int | None],
) -> list[_ImportReviewRow]:
    return [
        _ImportReviewRow(row_id=str(index), source_row=row, payload=_build_import_payload(row, mapping))
        for index, row in enumerate(filtered_rows, start=1)
    ]


def _payload_duplicate_identity(payload: dict[str, object]) -> tuple[str, str] | None:
    return duplicate_identity_for_values(payload.get("field1"), payload.get("field2"))


def _payload_possible_duplicate_identity(payload: dict[str, object]) -> tuple[str, str] | None:
    return possible_duplicate_identity_for_values(payload.get("field1"), payload.get("field2"))


def _payload_import_selection_possible_duplicate_identity(payload: dict[str, object]) -> tuple[str, str] | None:
    return import_selection_possible_duplicate_identity_for_values(payload.get("field1"), payload.get("field2"))


def _match_summary(record: Record, field_labels: Sequence[str]) -> str:
    parts = [
        f"{field_labels[0]}: {record.field1}",
        f"{field_labels[1]}: {record.field2 or '(blank)'}",
    ]
    if record.field3 is not None:
        parts.append(f"{field_labels[2]}: GBP {record.field3:.2f}")
    if record.field5 is not None:
        parts.append(f"{field_labels[4]}: {record.field5}")
    if record.field6 is not None:
        parts.append(f"{field_labels[5]}: GBP {record.field6:.2f}")
    if record.field7 is not None:
        parts.append(f"{field_labels[6]}: GBP {record.field7:.2f}")
    return " | ".join(parts)


def _overwrite_target_record(
    row: _ImportReviewRow,
    existing_exact_match_records: dict[tuple[str, str], Record] | None = None,
    existing_possible_match_records: dict[tuple[str, str], list[Record]] | None = None,
) -> Record | None:
    exact_match_records = existing_exact_match_records or {}
    possible_match_records = existing_possible_match_records or {}

    if row.overwrite_record_id is None:
        return None

    for record in exact_match_records.values():
        if record.id == row.overwrite_record_id:
            return record
    for records in possible_match_records.values():
        for record in records:
            if record.id == row.overwrite_record_id:
                return record

    return None


def _match_candidate_records(
    row: _ImportReviewRow,
    existing_exact_match_records: dict[tuple[str, str], Record] | None = None,
    existing_possible_match_records: dict[tuple[str, str], list[Record]] | None = None,
) -> tuple[list[Record], str | None]:
    exact_match_records = existing_exact_match_records or {}
    possible_match_records = existing_possible_match_records or {}

    identity = _payload_duplicate_identity(row.payload)
    if identity is not None and identity in exact_match_records:
        return [exact_match_records[identity]], "Exact match"

    possible_identity = _payload_possible_duplicate_identity(row.payload)
    if possible_identity is not None and possible_identity in possible_match_records:
        matched_records = list(possible_match_records[possible_identity])
        if matched_records:
            return matched_records, "Possible match" if len(matched_records) == 1 else "Possible matches"

    return [], None


def _match_choice_label(index: int, record: Record, field_labels: Sequence[str]) -> str:
    return f"{index}. {_match_summary(record, field_labels)}"


def _match_panel_text(match_kind: str, records: Sequence[Record], field_labels: Sequence[str]) -> str:
    if len(records) == 1:
        return f"{match_kind}: {_match_summary(records[0], field_labels)}"
    preview_rows = [f"{index}. {_match_summary(record, field_labels)}" for index, record in enumerate(records[:3], start=1)]
    if len(records) > 3:
        preview_rows.append(f"...and {len(records) - 3} more saved match(es).")
    return f"{match_kind} ({len(records)}):\n" + "\n".join(preview_rows)


def _import_review_row_summary(row: _ImportReviewRow, field_labels: Sequence[str]) -> str:
    parts = [
        f"{field_labels[0]}: {row.payload.get('field1') or '(blank)'}",
        f"{field_labels[1]}: {row.payload.get('field2') or '(blank)'}",
    ]
    if row.payload.get("field7") not in {None, ""}:
        parts.append(f"{field_labels[6]}: {row.payload.get('field7')}")
    return " | ".join(parts)


def _build_review_row_analysis(
    rows: Sequence[_ImportReviewRow],
    field_labels: Sequence[str] | None = None,
    existing_identities: set[tuple[str, str]] | None = None,
    existing_possible_identities: set[tuple[str, str]] | None = None,
    existing_exact_match_records: dict[tuple[str, str], Record] | None = None,
    existing_possible_match_records: dict[tuple[str, str], list[Record]] | None = None,
) -> _ReviewRowAnalysis:
    exact_match_records = existing_exact_match_records or {}
    possible_match_records = existing_possible_match_records or {}
    exact_match_identities = set(existing_identities or exact_match_records.keys())
    possible_match_identities = set(existing_possible_identities or possible_match_records.keys())
    matched_record_ids = {record.id for record in exact_match_records.values()} | {
        record.id for records in possible_match_records.values() for record in records
    }

    status_by_row_id: dict[str, str] = {}
    collisions_by_row_id: dict[str, _ImportReviewRow] = {}
    seen_identities: dict[tuple[str, str], _ImportReviewRow] = {}
    seen_possible_identities: dict[tuple[str, str], _ImportReviewRow] = {}
    seen_overwrite_record_ids: dict[str, _ImportReviewRow] = {}

    for row in rows:
        validation_status = _validated_import_status(row.payload, field_labels)
        identity = _payload_duplicate_identity(row.payload)
        possible_identity = _payload_possible_duplicate_identity(row.payload)
        import_selection_possible_identity = _payload_import_selection_possible_duplicate_identity(row.payload)
        exact_existing_record = exact_match_records.get(identity) if identity is not None else None
        possible_existing_records = list(possible_match_records.get(possible_identity, [])) if possible_identity is not None else []
        overwrite_target = _overwrite_target_record(row, exact_match_records, possible_match_records)
        overwrite_target_matches_row = (
            overwrite_target is not None
            and (
                (exact_existing_record is not None and exact_existing_record.id == overwrite_target.id)
                or any(record.id == overwrite_target.id for record in possible_existing_records)
            )
        )

        if validation_status != "Ready":
            status = validation_status
        elif row.overwrite_record_id is not None:
            if row.overwrite_record_id not in matched_record_ids:
                status = "Missing overwrite target"
            elif not overwrite_target_matches_row:
                status = "Overwrite target no longer matches row"
            elif row.overwrite_record_id in seen_overwrite_record_ids:
                status = "Overwrite target already used in import selection"
            elif identity is not None and exact_existing_record is not None and exact_existing_record.id != row.overwrite_record_id:
                status = "Duplicate existing Type + Name"
            elif identity is not None and identity in seen_identities:
                status = IMPORT_SELECTION_DUPLICATE_STATUS
            elif (
                import_selection_possible_identity is not None
                and import_selection_possible_identity in seen_possible_identities
            ):
                status = IMPORT_SELECTION_POSSIBLE_DUPLICATE_STATUS
            else:
                status = "Ready to overwrite matched row"
        elif identity is None:
            status = "Ready"
        elif identity in exact_match_identities:
            status = "Duplicate existing Type + Name"
        elif identity in seen_identities:
            status = IMPORT_SELECTION_DUPLICATE_STATUS
        elif possible_identity is not None and possible_identity in possible_match_identities:
            status = "Possible duplicate existing item"
        elif (
            import_selection_possible_identity is not None
            and import_selection_possible_identity in seen_possible_identities
        ):
            status = IMPORT_SELECTION_POSSIBLE_DUPLICATE_STATUS
        else:
            status = "Ready"

        status_by_row_id[row.row_id] = status

        if status == IMPORT_SELECTION_DUPLICATE_STATUS and identity is not None and identity in seen_identities:
            collisions_by_row_id[row.row_id] = seen_identities[identity]
        elif (
            status == IMPORT_SELECTION_POSSIBLE_DUPLICATE_STATUS
            and import_selection_possible_identity is not None
            and import_selection_possible_identity in seen_possible_identities
        ):
            collisions_by_row_id[row.row_id] = seen_possible_identities[import_selection_possible_identity]
        elif (
            status == "Overwrite target already used in import selection"
            and row.overwrite_record_id is not None
            and row.overwrite_record_id in seen_overwrite_record_ids
        ):
            collisions_by_row_id[row.row_id] = seen_overwrite_record_ids[row.overwrite_record_id]

        if not row.include:
            continue
        if identity is not None and identity not in seen_identities:
            seen_identities[identity] = row
        if import_selection_possible_identity is not None and import_selection_possible_identity not in seen_possible_identities:
            seen_possible_identities[import_selection_possible_identity] = row
        if status == "Ready to overwrite matched row" and row.overwrite_record_id is not None:
            seen_overwrite_record_ids.setdefault(row.overwrite_record_id, row)

    return _ReviewRowAnalysis(status_by_row_id=status_by_row_id, collisions_by_row_id=collisions_by_row_id)


def _review_row_import_collisions(
    rows: Sequence[_ImportReviewRow],
    field_labels: Sequence[str] | None = None,
    existing_identities: set[tuple[str, str]] | None = None,
    existing_possible_identities: set[tuple[str, str]] | None = None,
    existing_exact_match_records: dict[tuple[str, str], Record] | None = None,
    existing_possible_match_records: dict[tuple[str, str], list[Record]] | None = None,
) -> dict[str, _ImportReviewRow]:
    return _build_review_row_analysis(
        rows,
        field_labels,
        existing_identities,
        existing_possible_identities,
        existing_exact_match_records,
        existing_possible_match_records,
    ).collisions_by_row_id


def _status_field_label(field_name: object, field_labels: Sequence[str] | None) -> str:
    if not isinstance(field_name, str) or not field_name.startswith("field"):
        return "Row"
    try:
        index = int(field_name[5:]) - 1
    except ValueError:
        return field_name
    resolved_labels = _normalized_import_field_labels(field_labels)
    if 0 <= index < len(resolved_labels):
        return resolved_labels[index]
    return field_name


def _validated_import_status(payload: dict[str, object], field_labels: Sequence[str] | None = None) -> str:
    try:
        Record(**dict(payload))
    except ValidationError as exc:
        errors = exc.errors()
        if not errors:
            return "Invalid row"
        first_error = errors[0]
        field_name = first_error.get("loc", [None])[0]
        field_label = _status_field_label(field_name, field_labels)
        error_type = str(first_error.get("type") or "")
        message = str(first_error.get("msg") or "Invalid value").strip()
        if message.startswith("Value error, "):
            message = message[len("Value error, "):]
        if error_type in {"missing", "string_too_short", "string_type"} and field_name == "field1":
            return f"{field_label} is required"
        if message.lower() == "input should be a valid string" and field_name == "field1":
            return f"{field_label} is required"
        if message.startswith(str(field_name)):
            message = field_label + message[len(str(field_name)):]
        return f"{field_label}: {message}"
    except Exception as exc:
        message = str(exc).strip().splitlines()[0] if str(exc).strip() else exc.__class__.__name__
        return f"Invalid row: {message}"
    return "Ready"


def _review_row_status(
    row: _ImportReviewRow,
    rows: Sequence[_ImportReviewRow],
    field_labels: Sequence[str] | None = None,
    existing_identities: set[tuple[str, str]] | None = None,
    existing_possible_identities: set[tuple[str, str]] | None = None,
    existing_exact_match_records: dict[tuple[str, str], Record] | None = None,
    existing_possible_match_records: dict[tuple[str, str], list[Record]] | None = None,
) -> str:
    return _review_row_statuses(
        rows,
        field_labels,
        existing_identities,
        existing_possible_identities,
        existing_exact_match_records,
        existing_possible_match_records,
    ).get(row.row_id, "Ready")


def _review_row_statuses(
    rows: Sequence[_ImportReviewRow],
    field_labels: Sequence[str] | None = None,
    existing_identities: set[tuple[str, str]] | None = None,
    existing_possible_identities: set[tuple[str, str]] | None = None,
    existing_exact_match_records: dict[tuple[str, str], Record] | None = None,
    existing_possible_match_records: dict[tuple[str, str], list[Record]] | None = None,
) -> dict[str, str]:
    return _build_review_row_analysis(
        rows,
        field_labels,
        existing_identities,
        existing_possible_identities,
        existing_exact_match_records,
        existing_possible_match_records,
    ).status_by_row_id


def _review_status_counts(status_by_row_id: dict[str, str]) -> dict[str, int]:
    counts = {
        "ready": 0,
        "overwrite": 0,
        "invalid": 0,
        "duplicate_existing": 0,
        "duplicate_selection": 0,
        "possible_existing": 0,
        "possible_selection": 0,
    }
    for status in status_by_row_id.values():
        if status == "Ready":
            counts["ready"] += 1
        elif status == "Ready to overwrite matched row":
            counts["overwrite"] += 1
        elif status == "Duplicate existing Type + Name":
            counts["duplicate_existing"] += 1
        elif status == IMPORT_SELECTION_DUPLICATE_STATUS:
            counts["duplicate_selection"] += 1
        elif status == "Possible duplicate existing item":
            counts["possible_existing"] += 1
        elif status == IMPORT_SELECTION_POSSIBLE_DUPLICATE_STATUS:
            counts["possible_selection"] += 1
        else:
            counts["invalid"] += 1
    return counts


def _large_import_preflight_summary_text(review_rows: Sequence[_ImportReviewRow], status_by_row_id: dict[str, str]) -> str:
    counts = _review_status_counts(status_by_row_id)
    return "\n".join(
        (
            f"Selected rows for import: {len(review_rows)}",
            "",
            f"Ready rows: {counts['ready']}",
            f"Overwrite rows: {counts['overwrite']}",
            f"Invalid rows: {counts['invalid']}",
            f"Duplicate existing Type + Name: {counts['duplicate_existing']}",
            f"{IMPORT_SELECTION_DUPLICATE_STATUS}: {counts['duplicate_selection']}",
            f"Possible duplicate existing item: {counts['possible_existing']}",
            f"{IMPORT_SELECTION_POSSIBLE_DUPLICATE_STATUS}: {counts['possible_selection']}",
            "",
            "Open the detailed review now?",
        )
    )


def _review_tree_values(row: _ImportReviewRow, status: str) -> tuple[str, str, str, str, str]:
    return (
        "Yes" if row.include else "No",
        str(row.payload.get("field1") or ""),
        str(row.payload.get("field2") or ""),
        str(row.payload.get("field7") or ""),
        status,
    )


def _review_summary_text(rows: Sequence[_ImportReviewRow], status_by_row_id: dict[str, str]) -> str:
    included_ready = 0
    included_blocked = 0
    excluded_rows = 0
    for row in rows:
        status = status_by_row_id.get(row.row_id, "Ready")
        if not row.include:
            excluded_rows += 1
            continue
        if status in {"Ready", "Ready to overwrite matched row"}:
            included_ready += 1
        else:
            included_blocked += 1
    return f"Ready to import: {included_ready} | Blocked included rows: {included_blocked} | Excluded rows: {excluded_rows}"


def _selection_conflict_message(
    row: _ImportReviewRow,
    rows: Sequence[_ImportReviewRow],
    status: str,
    field_labels: Sequence[str] | None = None,
    existing_identities: set[tuple[str, str]] | None = None,
    existing_possible_identities: set[tuple[str, str]] | None = None,
    existing_exact_match_records: dict[tuple[str, str], Record] | None = None,
    existing_possible_match_records: dict[tuple[str, str], list[Record]] | None = None,
    collision_row: _ImportReviewRow | None = None,
) -> str | None:
    resolved_labels = _normalized_import_field_labels(field_labels)
    resolved_collision_row = collision_row
    if resolved_collision_row is None:
        resolved_collision_row = _review_row_import_collisions(
            rows,
            resolved_labels,
            existing_identities,
            existing_possible_identities,
            existing_exact_match_records,
            existing_possible_match_records,
        ).get(row.row_id)
    if status == IMPORT_SELECTION_DUPLICATE_STATUS:
        if resolved_collision_row is None:
            return "No saved match in existing data. This row duplicates another included import row."
        return (
            "No saved match in existing data. This row duplicates another included import row.\n"
            f"Conflicts with import row {resolved_collision_row.row_id}: {_import_review_row_summary(resolved_collision_row, resolved_labels)}"
        )
    if status == IMPORT_SELECTION_POSSIBLE_DUPLICATE_STATUS:
        if resolved_collision_row is None:
            return "No saved match in existing data. This row may match another included import row after format cleanup."
        return (
            "No saved match in existing data. This row may match another included import row after format cleanup.\n"
            f"Conflicts with import row {resolved_collision_row.row_id}: {_import_review_row_summary(resolved_collision_row, resolved_labels)}"
        )
    return None


def _prompt_import_review(
    parent: tk.Misc,
    filtered_rows: Sequence[tuple[str, ...]],
    mapping: dict[str, int | None],
    field_labels: Sequence[str] | None,
    existing_identities: set[tuple[str, str]] | None = None,
    existing_possible_identities: set[tuple[str, str]] | None = None,
    existing_exact_match_records: dict[tuple[str, str], Record] | None = None,
    existing_possible_match_records: dict[tuple[str, str], list[Record]] | None = None,
    review_rows: Sequence[_ImportReviewRow] | None = None,
) -> list[dict[str, object]] | None:
    resolved_labels = _normalized_import_field_labels(field_labels)
    resolved_review_rows = list(review_rows) if review_rows is not None else _build_import_review_rows(filtered_rows, mapping)
    result: list[dict[str, object]] | None = None

    win = tk.Toplevel(parent)
    win.title("Review Filtered Import")
    win.transient(parent)
    win.geometry("980x520")
    win.minsize(860, 460)

    container = ttk.Frame(win, padding=12)
    container.pack(fill="both", expand=True)
    container.columnconfigure(0, weight=1)
    container.rowconfigure(1, weight=1)

    current_analysis = _build_review_row_analysis(
        resolved_review_rows,
        resolved_labels,
        existing_identities,
        existing_possible_identities,
        existing_exact_match_records,
        existing_possible_match_records,
    )
    status_by_row_id = current_analysis.status_by_row_id
    summary_var = tk.StringVar(value=_review_summary_text(resolved_review_rows, status_by_row_id))
    ttk.Label(
        container,
        text="Review the mapped rows before importing. Edit the selected row below, then use Import Ready Rows.",
        wraplength=760,
    ).grid(row=0, column=0, sticky="w")
    ttk.Label(container, textvariable=summary_var).grid(row=0, column=0, sticky="e")

    table_frame = ttk.Frame(container)
    table_frame.grid(row=1, column=0, sticky="nsew", pady=(10, 10))
    table_frame.columnconfigure(0, weight=1)
    table_frame.rowconfigure(0, weight=1)

    tree = ttk.Treeview(table_frame, columns=IMPORT_REVIEW_TABLE_COLUMNS, show="headings", height=12, selectmode="browse")
    headings = {
        "include": "Import",
        "field1": resolved_labels[0],
        "field2": resolved_labels[1],
        "field7": resolved_labels[6],
        "status": "Status",
    }
    widths = {
        "include": 70,
        "field1": 180,
        "field2": 260,
        "field7": 120,
        "status": 260,
    }
    for column in IMPORT_REVIEW_TABLE_COLUMNS:
        tree.heading(column, text=headings[column])
        tree.column(column, width=widths[column], stretch=column in {"field1", "field2", "status"})

    y_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=y_scroll.set)
    tree.grid(row=0, column=0, sticky="nsew")
    y_scroll.grid(row=0, column=1, sticky="ns")

    editor_frame = ttk.LabelFrame(container, text="Selected row")
    editor_frame.grid(row=2, column=0, sticky="ew")
    editor_frame.columnconfigure(1, weight=1)
    editor_frame.columnconfigure(3, weight=1)

    include_var = tk.BooleanVar(value=True)
    editor_entries: dict[str, ttk.Entry] = {}
    editable_fields = ("field1", "field2", "field3", "field4", "field5", "field7")
    for index, field_name in enumerate(editable_fields):
        row_number = index // 2
        column_offset = (index % 2) * 2
        label_index = int(field_name[5:]) - 1
        ttk.Label(editor_frame, text=resolved_labels[label_index]).grid(row=row_number, column=column_offset, sticky="w", padx=(8, 8), pady=4)
        entry = ttk.Entry(editor_frame)
        entry.grid(row=row_number, column=column_offset + 1, sticky="ew", padx=(0, 12), pady=4)
        editor_entries[field_name] = entry

    ttk.Checkbutton(editor_frame, text="Include selected row", variable=include_var).grid(row=3, column=0, columnspan=2, sticky="w", padx=8, pady=(6, 8))
    selection_status_var = tk.StringVar(value="")
    ttk.Label(editor_frame, textvariable=selection_status_var).grid(row=3, column=2, columnspan=2, sticky="e", padx=8, pady=(6, 8))
    match_var = tk.StringVar(value="No saved match for this row.")
    ttk.Label(editor_frame, textvariable=match_var, wraplength=760, justify="left").grid(row=4, column=0, columnspan=4, sticky="w", padx=8, pady=(0, 8))
    match_choice_prompt = "Choose saved match to overwrite"
    match_choice_var = tk.StringVar(value=match_choice_prompt)
    ttk.Label(editor_frame, text="Saved match").grid(row=5, column=0, sticky="w", padx=(8, 8), pady=(0, 8))
    match_choice_combobox = ttk.Combobox(editor_frame, state="disabled", textvariable=match_choice_var)
    match_choice_combobox.grid(row=5, column=1, columnspan=3, sticky="ew", padx=(0, 12), pady=(0, 8))
    overwrite_button: ttk.Button | None = None
    match_choice_ids_by_label: dict[str, str] = {}

    action_row = ttk.Frame(container)
    action_row.grid(row=3, column=0, sticky="ew", pady=(10, 0))

    def _selected_review_row() -> _ImportReviewRow | None:
        selection = tree.selection()
        if not selection:
            return None
        selected_id = selection[0]
        return next((row for row in resolved_review_rows if row.row_id == selected_id), None)

    def _refresh_all_rows() -> dict[str, str]:
        nonlocal current_analysis
        current_analysis = _build_review_row_analysis(
            resolved_review_rows,
            resolved_labels,
            existing_identities,
            existing_possible_identities,
            existing_exact_match_records,
            existing_possible_match_records,
        )
        refreshed_statuses = current_analysis.status_by_row_id
        for review_row in resolved_review_rows:
            values = _review_tree_values(review_row, refreshed_statuses.get(review_row.row_id, "Ready"))
            if tree.exists(review_row.row_id):
                tree.item(review_row.row_id, values=values)
        summary_var.set(_review_summary_text(resolved_review_rows, refreshed_statuses))
        selected_row = _selected_review_row()
        if selected_row is not None:
            selection_status_var.set(refreshed_statuses.get(selected_row.row_id, "Ready"))
        return refreshed_statuses

    def _set_match_choice_options(row: _ImportReviewRow, matched_records: Sequence[Record]) -> None:
        nonlocal match_choice_ids_by_label
        if len(matched_records) <= 1:
            match_choice_ids_by_label = {}
            match_choice_combobox.configure(values=(), state="disabled")
            match_choice_var.set(match_choice_prompt)
            return

        match_choice_ids_by_label = {
            _match_choice_label(index, record, resolved_labels): record.id
            for index, record in enumerate(matched_records, start=1)
        }
        selected_label = next(
            (
                label
                for label, record_id in match_choice_ids_by_label.items()
                if record_id == row.overwrite_record_id
            ),
            match_choice_prompt,
        )
        match_choice_combobox.configure(values=[match_choice_prompt, *match_choice_ids_by_label.keys()], state="readonly")
        match_choice_var.set(selected_label)

    def _select_match_choice(_event=None) -> None:
        row = _selected_review_row()
        if row is None:
            return
        selected_label = match_choice_var.get().strip()
        if selected_label == match_choice_prompt or not selected_label:
            if row.overwrite_record_id is not None:
                row.overwrite_record_id = None
                _refresh_tree_row(row)
            return
        selected_record_id = match_choice_ids_by_label.get(selected_label)
        if selected_record_id is None:
            return
        row.overwrite_record_id = selected_record_id
        row.include = True
        _refresh_tree_row(row)

    def _update_match_panel(row: _ImportReviewRow) -> None:
        matched_records, match_kind = _match_candidate_records(
            row,
            existing_exact_match_records,
            existing_possible_match_records,
        )
        overwrite_target = _overwrite_target_record(
            row,
            existing_exact_match_records,
            existing_possible_match_records,
        )
        current_status = current_analysis.status_by_row_id.get(row.row_id, "Ready")
        _set_match_choice_options(row, matched_records)
        if not matched_records or match_kind is None:
            if overwrite_target is not None and row.overwrite_record_id is not None:
                match_var.set(f"Overwrite target no longer matches this row: {_match_summary(overwrite_target, resolved_labels)}")
                if overwrite_button is not None:
                    overwrite_button.configure(text="Keep As New Row", state="normal")
                return
            match_var.set(
                _selection_conflict_message(
                    row,
                    resolved_review_rows,
                    current_status,
                    resolved_labels,
                    existing_identities,
                    existing_possible_identities,
                    existing_exact_match_records,
                    existing_possible_match_records,
                    collision_row=current_analysis.collisions_by_row_id.get(row.row_id),
                )
                or "No saved match in existing data for this row."
            )
            if overwrite_button is not None:
                overwrite_button.configure(text="Overwrite Matched Row", state="disabled")
            return
        match_var.set(_match_panel_text(match_kind, matched_records, resolved_labels))
        if overwrite_button is not None:
            if len(matched_records) > 1:
                overwrite_button.configure(
                    text="Keep As New Row" if row.overwrite_record_id is not None else "Choose Match To Overwrite",
                    state="normal" if row.overwrite_record_id is not None else "disabled",
                )
                return
            can_overwrite = row.overwrite_record_id is not None or not current_status.startswith("Invalid")
            overwrite_button.configure(
                text="Keep As New Row" if row.overwrite_record_id is not None else "Overwrite Matched Row",
                state="normal" if can_overwrite else "disabled",
            )

    def _refresh_tree_row(row: _ImportReviewRow) -> None:
        _refresh_all_rows()
        _update_match_panel(row)

    def _load_selected_row(_event=None) -> None:
        row = _selected_review_row()
        if row is None:
            return
        include_var.set(row.include)
        for field_name, entry in editor_entries.items():
            entry.delete(0, tk.END)
            value = row.payload.get(field_name)
            if value is not None:
                entry.insert(0, str(value))
        selection_status_var.set(current_analysis.status_by_row_id.get(row.row_id, "Ready"))
        _update_match_panel(row)

    def _apply_selected_changes() -> bool:
        row = _selected_review_row()
        if row is None:
            return False
        original_duplicate_identity = _payload_duplicate_identity(row.payload)
        original_possible_identity = _payload_possible_duplicate_identity(row.payload)
        row.include = include_var.get()
        for field_name, entry in editor_entries.items():
            value = entry.get().strip()
            row.payload[field_name] = value or None
        row.payload["field6"] = calculate_field6(row.payload.get("field3"), row.payload.get("field5"))
        if row.overwrite_record_id is not None:
            updated_duplicate_identity = _payload_duplicate_identity(row.payload)
            updated_possible_identity = _payload_possible_duplicate_identity(row.payload)
            if (
                updated_duplicate_identity != original_duplicate_identity
                or updated_possible_identity != original_possible_identity
            ):
                row.overwrite_record_id = None
        _refresh_tree_row(row)
        selection_status_var.set(current_analysis.status_by_row_id.get(row.row_id, "Ready"))
        return True

    def _toggle_overwrite_selected_row() -> None:
        _apply_selected_changes()
        row = _selected_review_row()
        if row is None:
            return
        if row.overwrite_record_id is not None:
            row.overwrite_record_id = None
            _refresh_tree_row(row)
            return
        matched_records, _match_kind = _match_candidate_records(
            row,
            existing_exact_match_records,
            existing_possible_match_records,
        )
        if len(matched_records) != 1:
            return
        matched_record = matched_records[0]
        row.overwrite_record_id = matched_record.id
        row.include = True
        _refresh_tree_row(row)

    def _import_ready_rows() -> None:
        nonlocal result
        _apply_selected_changes()
        ready_rows = []
        for row in resolved_review_rows:
            if not row.include:
                continue
            status = current_analysis.status_by_row_id.get(row.row_id, "Ready")
            if status not in {"Ready", "Ready to overwrite matched row"}:
                continue
            payload = dict(row.payload)
            if row.overwrite_record_id is not None:
                payload["__overwrite_record_id"] = row.overwrite_record_id
            ready_rows.append(payload)
        if not ready_rows:
            messagebox.showinfo("Review Filtered Import", "There are no ready rows selected for import.", parent=win)
            return
        result = ready_rows
        win.destroy()

    def _exclude_non_ready_rows() -> None:
        _apply_selected_changes()
        for row in resolved_review_rows:
            if current_analysis.status_by_row_id.get(row.row_id, "Ready") not in {"Ready", "Ready to overwrite matched row"}:
                row.include = False
        _refresh_all_rows()
        _load_selected_row()

    for row in resolved_review_rows:
        tree.insert(
            "",
            "end",
            iid=row.row_id,
            values=_review_tree_values(row, status_by_row_id.get(row.row_id, "Ready")),
        )

    tree.bind("<<TreeviewSelect>>", _load_selected_row, add="+")
    match_choice_combobox.bind("<<ComboboxSelected>>", _select_match_choice, add="+")
    if resolved_review_rows:
        tree.selection_set(resolved_review_rows[0].row_id)
        _load_selected_row()

    ttk.Button(action_row, text="Exclude Non-ready", command=_exclude_non_ready_rows).pack(side="left")
    overwrite_button = ttk.Button(action_row, text="Overwrite Matched Row", command=_toggle_overwrite_selected_row)
    overwrite_button.pack(side="left", padx=(8, 0))
    ttk.Button(action_row, text="Apply Changes", command=_apply_selected_changes).pack(side="left", padx=(8, 0))
    ttk.Button(action_row, text="Cancel", command=win.destroy).pack(side="right")
    ttk.Button(action_row, text="Import Ready Rows", command=_import_ready_rows).pack(side="right", padx=(0, 8))

    win.update_idletasks()
    win.grab_set()
    tree.focus_set()
    parent.wait_window(win)
    return result


def _prompt_import_mapping(
    parent: tk.Misc,
    headers: Sequence[str],
    filtered_rows: Sequence[tuple[str, ...]],
    field_labels: Sequence[str] | None,
) -> dict[str, int | None] | None:
    resolved_labels = _normalized_import_field_labels(field_labels)
    default_mapping = _guess_import_mapping(headers, resolved_labels)
    values = ["Skip", *headers]
    result: dict[str, int | None] | None = None

    win = tk.Toplevel(parent)
    win.title("Import Selected/Filtered Rows")
    win.transient(parent)
    win.resizable(False, False)

    container = ttk.Frame(win, padding=12)
    container.pack(fill="both", expand=True)
    container.columnconfigure(1, weight=1)
    container.columnconfigure(2, weight=1)

    ttk.Label(
        container,
        text=f"Map {len(filtered_rows)} row(s) from the CSV preview into the main form fields.",
        wraplength=560,
    ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))

    ttk.Label(
        container,
        text="Selected preview rows are imported when present; otherwise the full filtered result is used. Buying price and selling price are treated separately.",
        wraplength=560,
    ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 10))

    ttk.Label(container, text="Main field").grid(row=2, column=0, sticky="w", padx=(0, 12))
    ttk.Label(container, text="CSV column").grid(row=2, column=1, sticky="w", padx=(0, 12))
    ttk.Label(container, text="Preview").grid(row=2, column=2, sticky="w")

    comboboxes: dict[str, ttk.Combobox] = {}
    sample_labels: dict[str, ttk.Label] = {}

    def _update_sample(field_name: str) -> None:
        if field_name == "field6":
            return
        combobox = comboboxes[field_name]
        selected_header = combobox.get()
        selected_index = headers.index(selected_header) if selected_header in headers else None
        sample_labels[field_name].configure(text=_sample_value_for_column(filtered_rows, selected_index))

    for row_index, field_name in enumerate(("field1", "field2", "field3", "field4", "field5", "field6", "field7"), start=3):
        label_index = int(field_name[5:]) - 1
        label_text = resolved_labels[label_index]
        suffix = " (required)" if field_name == "field1" else ""
        ttk.Label(container, text=f"{label_text}{suffix}").grid(row=row_index, column=0, sticky="w", padx=(0, 12), pady=3)

        if field_name == "field6":
            ttk.Label(container, text="Calculated automatically").grid(row=row_index, column=1, sticky="w", padx=(0, 12), pady=3)
            ttk.Label(container, text=f"Uses {resolved_labels[2]} and {resolved_labels[4]}").grid(row=row_index, column=2, sticky="w", pady=3)
            continue

        default_index = default_mapping.get(field_name)
        default_value = headers[default_index] if default_index is not None and 0 <= default_index < len(headers) else "Skip"
        combobox = ttk.Combobox(container, state="readonly", values=values, width=28)
        combobox.set(default_value)
        combobox.grid(row=row_index, column=1, sticky="ew", padx=(0, 12), pady=3)
        sample_label = ttk.Label(container, text="")
        sample_label.grid(row=row_index, column=2, sticky="w", pady=3)
        comboboxes[field_name] = combobox
        sample_labels[field_name] = sample_label
        combobox.bind("<<ComboboxSelected>>", lambda _event, name=field_name: _update_sample(name), add="+")
        _update_sample(field_name)

    button_row = ttk.Frame(container)
    button_row.grid(row=10, column=0, columnspan=3, sticky="e", pady=(12, 0))

    def _confirm() -> None:
        nonlocal result
        selected_field1 = comboboxes["field1"].get()
        if selected_field1 not in headers:
            messagebox.showerror("Import Selected/Filtered Rows", f"Choose a CSV column for {resolved_labels[0]}.", parent=win)
            return

        result = {"field6": None}
        for field_name, combobox in comboboxes.items():
            selected_header = combobox.get()
            result[field_name] = headers.index(selected_header) if selected_header in headers else None
        win.destroy()

    ttk.Button(button_row, text="Cancel", command=win.destroy).pack(side="right")
    ttk.Button(button_row, text="Continue", command=_confirm).pack(side="right", padx=(0, 8))

    win.update_idletasks()
    win.grab_set()
    if comboboxes:
        next(iter(comboboxes.values())).focus_set()
    parent.wait_window(win)
    return result


def _column_width(header: str) -> int:
    return _column_width_impl(
        header,
        default_width=DEFAULT_COLUMN_WIDTH,
        min_width=MIN_COLUMN_WIDTH,
        max_width=MAX_COLUMN_WIDTH,
    )


def _column_ids(data: CsvPreviewData) -> list[str]:
    return _column_ids_impl(data)


def _rendered_preview_row_limit(column_count: int) -> int:
    return _rendered_preview_row_limit_impl(
        column_count,
        max_rendered_preview_rows=MAX_RENDERED_PREVIEW_ROWS,
        min_rendered_preview_rows=MIN_RENDERED_PREVIEW_ROWS,
        max_rendered_preview_cells=MAX_RENDERED_PREVIEW_CELLS,
    )


def _normalized_visible_column_indices(column_count: int, visible_indices: list[int] | None) -> list[int]:
    return _normalized_visible_column_indices_impl(column_count, visible_indices)


def _build_tree(parent: tk.Misc, data: CsvPreviewData) -> ttk.Treeview:
    column_ids = _column_ids(data)
    return _build_tree_impl(
        parent,
        data,
        column_ids=column_ids,
        column_width_for_header=_column_width,
        min_column_width=MIN_COLUMN_WIDTH,
    )


def _default_csv_preview_export_path(source_path: Path) -> Path:
    return _default_csv_preview_export_path_impl(source_path)


def _default_csv_preview_export_directory(source_path: Path) -> Path:
    return _default_csv_preview_export_directory_impl(source_path)


def _prepare_csv_preview_export_directory(source_path: Path) -> Path:
    return _prepare_csv_preview_export_directory_impl(source_path)


def _paths_match(first: Path, second: Path) -> bool:
    return _paths_match_impl(first, second)


def _write_csv_preview_export(dest_path: Path, headers: list[str], rows) -> None:
    _write_csv_preview_export_impl(dest_path, headers, rows, encoding=CSV_PREVIEW_EXPORT_ENCODING)


def _widget_descends_from(widget: tk.Misc | None, ancestor: tk.Misc | None) -> bool:
    return _widget_descends_from_impl(widget, ancestor)


def _iter_combined_rows(data: CsvPreviewData, enabled: bool):
    yield from _iter_combined_rows_impl(data, enabled)


def _iter_rows_before_header_filter(
    data: CsvPreviewData,
    query: str,
    combine_sessions: bool,
    combined_rows: list[tuple[str, ...]] | None = None,
):
    yield from _iter_rows_before_header_filter_impl(
        data,
        query,
        combine_sessions,
        combined_rows=combined_rows,
    )


configure_preview_runtime(
    max_indexed_source_memory_bytes=lambda: MAX_INDEXED_SOURCE_MEMORY_BYTES,
    log_preview_performance=lambda operation, started_at, **fields: _log_preview_performance(
        operation,
        started_at,
        **fields,
    ),
    row_search_text=lambda row: _row_search_text(row),
    iter_csv_preview_rows=lambda data: iter_csv_preview_rows(data),
    iter_rows_before_header_filter=lambda data, query, combine_sessions, combined_rows=None: _iter_rows_before_header_filter(
        data,
        query,
        combine_sessions,
        combined_rows=combined_rows,
    ),
    sort_rows=lambda rows, column_index, *, descending, numeric: _sort_rows(
        rows,
        column_index,
        descending=descending,
        numeric=numeric,
    ),
    sorted_distinct_values=lambda rows, column_index: _sorted_distinct_values(rows, column_index),
    header_suggests_numeric=lambda header: _header_suggests_numeric(header),
    is_identifier_column=lambda header: _is_identifier_column(header),
    parse_decimal=lambda value: _parse_decimal(value),
    resolve_metadata=lambda data: resolve_csv_preview_metadata(data),
    metadata_resolved_update_factory=lambda resolved_data: _MetadataResolvedUpdate(resolved_data=resolved_data),
    metadata_error_update_factory=lambda error: _MetadataErrorUpdate(error=error),
    iter_combined_rows=lambda data, enabled: _iter_combined_rows(data, enabled),
    perf_counter_impl=lambda: perf_counter(),
    loading_summary_text=lambda data, *, filtered, sort_description=None: _loading_summary_text(
        data,
        filtered=filtered,
        sort_description=sort_description,
    ),
    summary_text=lambda data, *, visible_rows, displayed_rows, loaded_rows, filtered=False, sort_description=None: _summary_text(
        data,
        visible_rows=visible_rows,
        displayed_rows=displayed_rows,
        loaded_rows=loaded_rows,
        filtered=filtered,
        sort_description=sort_description,
    ),
    normalize_visible_column_indices=lambda column_count, visible_indices: _normalized_visible_column_indices(
        column_count,
        visible_indices,
    ),
)


def _build_preview_dialog_widgets(
    parent: tk.Misc,
    data: CsvPreviewData,
    *,
    width: int,
    height: int,
) -> _PreviewDialogWidgets:
    win = tk.Toplevel(parent)
    win.title(f"CSV Preview - {data.path.name}")
    win.geometry(f"{max(width, MIN_PREVIEW_WIDTH)}x{max(height, MIN_PREVIEW_HEIGHT)}")

    container = ttk.Frame(win)
    container.pack(fill="both", expand=True, padx=8, pady=8)
    container.columnconfigure(0, weight=1)
    container.rowconfigure(3, weight=1)

    workspace_row = ttk.Frame(container)
    workspace_row.grid(row=0, column=0, sticky="ew", pady=(0, 6))

    initial_displayed_rows = min(data.row_count or len(data.rows), _rendered_preview_row_limit(data.column_count))
    summary_var = tk.StringVar(
        value=_summary_text(
            data,
            visible_rows=data.row_count,
            displayed_rows=initial_displayed_rows,
            loaded_rows=0 if initial_displayed_rows else None,
        )
    )
    summary = ttk.Label(container, textvariable=summary_var, anchor="w")
    summary.grid(row=1, column=0, sticky="ew", pady=(0, 6))

    filter_row = ttk.Frame(container)
    filter_row.grid(row=2, column=0, sticky="ew", pady=(0, 6))
    ttk.Label(filter_row, text="Search").pack(side="left")

    query_var = tk.StringVar()
    query_entry = ttk.Entry(filter_row, textvariable=query_var, width=24)
    query_entry.pack(side="left", padx=(6, 12))
    ttk.Label(filter_row, text="Press Enter to search").pack(side="left", padx=(0, 12))
    ttk.Label(filter_row, text=_header_mode_text(data.has_header_row), anchor="e").pack(side="right")

    combine_sessions_supported = _detect_session_column(data.headers) is not None and _detect_quantity_column(data.headers) is not None
    combine_sessions_var = tk.BooleanVar(value=False)
    combine_sessions_toggle = ttk.Checkbutton(filter_row, text="Combine sessions", variable=combine_sessions_var)
    combine_sessions_toggle.pack(side="left", padx=(0, 12))
    if not combine_sessions_supported:
        combine_sessions_toggle.configure(state="disabled")

    table_frame = ttk.Frame(container)
    table_frame.grid(row=3, column=0, sticky="nsew")
    table_frame.columnconfigure(0, weight=1)
    table_frame.rowconfigure(0, weight=1)

    tree = _build_tree(table_frame, data)
    y_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
    x_scroll = ttk.Scrollbar(table_frame, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

    tree.grid(row=0, column=0, sticky="nsew")
    y_scroll.grid(row=0, column=1, sticky="ns")
    x_scroll.grid(row=1, column=0, sticky="ew")

    button_row = ttk.Frame(container)
    button_row.grid(row=4, column=0, sticky="ew", pady=(8, 0))

    return _PreviewDialogWidgets(
        win=win,
        container=container,
        workspace_row=workspace_row,
        summary=summary,
        filter_row=filter_row,
        summary_var=summary_var,
        query_var=query_var,
        query_entry=query_entry,
        combine_sessions_var=combine_sessions_var,
        table_frame=table_frame,
        tree=tree,
        button_row=button_row,
    )


def create_csv_preview_dialog(
    parent: tk.Misc,
    data: CsvPreviewData,
    *,
    width: int,
    height: int,
    initial_visible_column_indices: list[int] | None = None,
    initial_sort_column_index: int | None = None,
    initial_sort_descending: bool = False,
    on_visible_columns_changed=None,
    on_sort_changed=None,
    import_field_labels: Sequence[str] | None = None,
    on_import_filtered_rows: Callable[[CsvPreviewData, list[dict[str, object]]], None] | None = None,
    existing_import_identities: set[tuple[str, str]] | None = None,
    existing_import_possible_identities: set[tuple[str, str]] | None = None,
    existing_import_exact_match_records: dict[tuple[str, str], Record] | None = None,
    existing_import_possible_match_records: dict[tuple[str, str], list[Record]] | None = None,
) -> tk.Toplevel:
    widgets = _build_preview_dialog_widgets(parent, data, width=width, height=height)
    analysis_frame: ttk.Frame | None = None
    cached_analysis_snapshot: PreviewAnalysisSnapshot | None = None
    cached_analysis_request_state: tuple[_PreviewFilterState, tuple[int, ...], frozenset[int]] | None = None

    def _current_analysis_request_state() -> tuple[_PreviewFilterState, tuple[int, ...], frozenset[int]]:
        filter_state, visible_column_indices, numeric_column_indices = controller._analysis_request_state()
        return filter_state, tuple(visible_column_indices), frozenset(numeric_column_indices)

    def _sync_workspace_buttons() -> None:
        preview_button.configure(state="disabled" if analysis_frame is None else "normal")
        analysis_button.configure(state="normal" if analysis_frame is None else "disabled")

    def _show_preview_workspace() -> None:
        nonlocal analysis_frame
        if analysis_frame is not None and analysis_frame.winfo_exists():
            analysis_frame.destroy()
        analysis_frame = None
        widgets.summary.grid()
        widgets.filter_row.grid()
        widgets.table_frame.grid()
        _sync_workspace_buttons()
        widgets.query_entry.focus_set()

    def _show_analysis_snapshot(snapshot) -> None:
        nonlocal analysis_frame, cached_analysis_request_state, cached_analysis_snapshot
        widgets.summary.grid_remove()
        widgets.filter_row.grid_remove()
        widgets.table_frame.grid_remove()
        if analysis_frame is not None and analysis_frame.winfo_exists():
            analysis_frame.destroy()
        cached_analysis_snapshot = snapshot
        cached_analysis_request_state = _current_analysis_request_state()
        analysis_frame = build_csv_preview_analysis_view(
            widgets.container,
            snapshot,
            close_command=_show_preview_workspace,
            popup_parent=widgets.win,
            chart_message_wraplength=max(widgets.win.winfo_width() - 120, 240),
        )
        analysis_frame.grid(row=1, column=0, rowspan=3, sticky="nsew")
        _sync_workspace_buttons()

    def _open_analysis_workspace() -> None:
        current_request_state = _current_analysis_request_state()
        if cached_analysis_snapshot is not None and current_request_state == cached_analysis_request_state:
            _show_analysis_snapshot(cached_analysis_snapshot)
            return
        controller.open_analysis_dialog()

    controller = _PreviewTableController(
        widgets.win,
        widgets.tree,
        data,
        widgets.summary_var,
        widgets.query_var,
        widgets.combine_sessions_var,
        _column_ids(data),
        initial_visible_column_indices=initial_visible_column_indices,
        initial_sort_column_index=initial_sort_column_index,
        initial_sort_descending=initial_sort_descending,
        on_visible_columns_changed=on_visible_columns_changed,
        on_sort_changed=on_sort_changed,
        view_state_factory=_PreviewViewState,
        normalize_visible_column_indices=_normalized_visible_column_indices,
        pipeline_factory=_PreviewDataPipeline,
        popup_export_controller_factory=lambda owner: _PreviewPopupExportController(
            owner,
            popup_width=HEADER_FILTER_POPUP_WIDTH,
            popup_height=HEADER_FILTER_POPUP_HEIGHT,
            popup_list_height=HEADER_FILTER_POPUP_LIST_HEIGHT,
            prepare_export_directory=_prepare_csv_preview_export_directory,
            default_export_path=_default_csv_preview_export_path,
            paths_match=_paths_match,
            write_export=_write_csv_preview_export,
            filter_label=_filter_label,
            compact_filter_popup_label=_compact_filter_popup_label,
            widget_descends_from=_widget_descends_from,
        ),
        column_manager_factory=lambda *args, **kwargs: _PreviewColumnManager(
            *args,
            **kwargs,
            column_ids_for_data=_column_ids,
            column_width_for_header=_column_width,
            min_column_width=MIN_COLUMN_WIDTH,
            normalize_visible_column_indices=_normalized_visible_column_indices,
            filter_label=_filter_label,
        ),
        row_renderer_factory=lambda *args: _PreviewRowRenderer(
            *args,
            row_insert_chunk_size=ROW_INSERT_CHUNK_SIZE,
            log_preview_performance=_log_preview_performance,
        ),
        analysis_launcher_factory=lambda *args: _PreviewAnalysisLauncher(
            *args,
            coordinator_factory=lambda win: _AnalysisSnapshotCoordinator(
                win,
                processing_dialog_factory=lambda analysis_win: ProcessingDialogHandle(
                    analysis_win,
                    title="Preparing Analysis",
                    eyebrow_text="ANALYSIS",
                    detail_text="Collecting filtered rows and preparing chart summaries.",
                ),
                pipeline_factory=_PreviewDataPipeline,
                build_snapshot=lambda *launcher_args, **launcher_kwargs: build_preview_analysis_snapshot(
                    *launcher_args,
                    **launcher_kwargs,
                ),
                show_error=lambda title, message: messagebox.showerror(title, message),
                open_analysis_dialog_from_snapshot=lambda parent, snapshot: _show_analysis_snapshot(snapshot),
            ),
        ),
        processing_dialog_factory=lambda win: ProcessingDialogHandle(
            win,
            title="Processing CSV",
            eyebrow_text="SESSION MERGE",
            detail_text="Combining sessions and rebuilding the visible preview rows.",
        ),
        rendered_row_limit=_rendered_preview_row_limit,
    )
    widgets.win._csv_preview_controller = controller  # type: ignore[attr-defined]
    controller._apply_displaycolumns()

    def _clear_filters() -> None:
        widgets.query_var.set("")
        widgets.combine_sessions_var.set(False)
        controller.clear_sort()
        controller.clear_header_filter()

    def _import_filtered_rows() -> None:
        if on_import_filtered_rows is None:
            return
        selected_rows = controller.selected_displayed_rows_snapshot()
        rows_to_import = selected_rows or controller.filtered_rows_snapshot()
        if not rows_to_import:
            messagebox.showinfo("Import filtered rows", "There are no filtered rows to import.")
            return
        mapping = _prompt_import_mapping(widgets.win, data.headers, rows_to_import, import_field_labels)
        if mapping is None:
            return
        review_rows = _build_import_review_rows(rows_to_import, mapping)
        if len(review_rows) >= LARGE_IMPORT_PREFLIGHT_ROW_COUNT:
            status_by_row_id = _review_row_statuses(
                review_rows,
                import_field_labels,
                existing_import_identities,
                existing_import_possible_identities,
                existing_import_exact_match_records,
                existing_import_possible_match_records,
            )
            should_continue = messagebox.askyesno(
                "Large import summary",
                _large_import_preflight_summary_text(review_rows, status_by_row_id),
                parent=widgets.win,
            )
            if not should_continue:
                return
        reviewed_rows = _prompt_import_review(
            widgets.win,
            rows_to_import,
            mapping,
            import_field_labels,
            existing_import_identities,
            existing_import_possible_identities,
            existing_import_exact_match_records,
            existing_import_possible_match_records,
            review_rows=review_rows,
        )
        if reviewed_rows is None:
            return
        on_import_filtered_rows(data, reviewed_rows)

    preview_button = ttk.Button(widgets.workspace_row, text="Preview", command=_show_preview_workspace)
    preview_button.pack(side="left")
    analysis_button = ttk.Button(widgets.workspace_row, text="Analysis", command=_open_analysis_workspace)
    analysis_button.pack(side="left", padx=(8, 0))
    _sync_workspace_buttons()

    ttk.Button(widgets.filter_row, text="Columns", command=controller.open_column_dialog).pack(side="left", padx=(0, 12))
    if on_import_filtered_rows is not None:
        ttk.Button(widgets.filter_row, text="Import Filtered Rows", command=_import_filtered_rows).pack(side="left", padx=(0, 12))
    ttk.Button(widgets.filter_row, text="Save As CSV", command=controller.export_current_view_as_csv).pack(side="left", padx=(0, 12))
    ttk.Button(widgets.filter_row, text="Clear filters", command=_clear_filters).pack(side="left")

    ttk.Button(widgets.button_row, text="Close", command=widgets.win.destroy).pack(side="right")

    widgets.query_var.trace_add("write", controller.on_query_changed)
    widgets.combine_sessions_var.trace_add("write", controller.on_combine_sessions_changed)
    widgets.query_entry.bind("<Return>", controller.trigger_refresh_now, add="+")
    widgets.tree.bind("<ButtonRelease-1>", controller.on_tree_click, add="+")
    widgets.win.after_idle(controller.refresh)
    widgets.query_entry.focus_set()

    return widgets.win


def open_csv_preview_dialog(
    parent: tk.Misc,
    csv_path: str | Path,
    *,
    width: int,
    height: int,
    has_header_row: bool = True,
    import_field_labels: Sequence[str] | None = None,
    on_import_filtered_rows: Callable[[CsvPreviewData, list[dict[str, object]]], None] | None = None,
    existing_import_identities: set[tuple[str, str]] | None = None,
    existing_import_possible_identities: set[tuple[str, str]] | None = None,
    existing_import_exact_match_records: dict[tuple[str, str], Record] | None = None,
    existing_import_possible_match_records: dict[tuple[str, str], list[Record]] | None = None,
) -> tk.Toplevel:
    data = load_csv_preview(csv_path, has_header_row=has_header_row)
    settings_store = SettingsStore()
    settings_bindings = build_preview_dialog_settings_bindings(
        data,
        settings_store,
        messagebox.showerror,
    )

    return create_csv_preview_dialog(
        parent,
        data,
        width=width,
        height=height,
        initial_visible_column_indices=settings_bindings.initial_visible_column_indices,
        initial_sort_column_index=settings_bindings.initial_sort_column_index,
        initial_sort_descending=settings_bindings.initial_sort_descending,
        on_visible_columns_changed=settings_bindings.on_visible_columns_changed,
        on_sort_changed=settings_bindings.on_sort_changed,
        import_field_labels=import_field_labels,
        on_import_filtered_rows=on_import_filtered_rows,
        existing_import_identities=existing_import_identities,
        existing_import_possible_identities=existing_import_possible_identities,
        existing_import_exact_match_records=existing_import_exact_match_records,
        existing_import_possible_match_records=existing_import_possible_match_records,
    )
