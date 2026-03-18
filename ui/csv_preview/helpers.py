from __future__ import annotations

from collections import OrderedDict
from decimal import Decimal, InvalidOperation

from .loader import CsvPreviewData


COMBINED_SESSION_SEPARATOR = " + "
HEADER_FILTER_POPUP_LABEL_MAX_LENGTH = 36


def _normalized_visible_column_indices(column_count: int, visible_indices: list[int] | None) -> list[int]:
    if not visible_indices:
        return list(range(column_count))

    normalized: list[int] = []
    seen: set[int] = set()
    for raw_index in visible_indices:
        try:
            index = int(raw_index)
        except (TypeError, ValueError):
            continue
        if index < 0 or index >= column_count or index in seen:
            continue
        normalized.append(index)
        seen.add(index)
    return normalized or list(range(column_count))


def _filter_label(header: str, index: int) -> str:
    display = header.strip() or f"Column {index + 1}"
    return f"{index + 1}: {display}"


def _compact_filter_popup_label(value: str, *, max_length: int = HEADER_FILTER_POPUP_LABEL_MAX_LENGTH) -> str:
    if len(value) <= max_length:
        return value
    if max_length <= 3:
        return value[:max_length]
    return f"{value[: max_length - 3].rstrip()}..."


def _sort_rows(rows: list[tuple[str, ...]], column_index: int, *, descending: bool, numeric: bool) -> list[tuple[str, ...]]:
    if not numeric:
        return sorted(rows, key=lambda row: row[column_index].casefold(), reverse=descending)

    numeric_rows: list[tuple[Decimal, tuple[str, ...]]] = []
    other_rows: list[tuple[str, ...]] = []
    for row in rows:
        numeric_value = _parse_decimal(row[column_index])
        if numeric_value is None:
            other_rows.append(row)
            continue
        numeric_rows.append((numeric_value, row))

    numeric_rows.sort(key=lambda item: item[0], reverse=descending)
    other_rows.sort(key=lambda row: row[column_index].casefold())
    return [row for _, row in numeric_rows] + other_rows


def _column_identity_keys(headers: list[str]) -> list[str]:
    seen_counts: dict[str, int] = {}
    keys: list[str] = []
    for index, header in enumerate(headers):
        display = header.strip() or f"Column {index + 1}"
        normalized_display = display.casefold()
        occurrence = seen_counts.get(normalized_display, 0) + 1
        seen_counts[normalized_display] = occurrence
        keys.append(f"{normalized_display}#{occurrence}")
    return keys


def _visible_column_keys(headers: list[str], visible_indices: list[int] | None) -> list[str]:
    normalized_indices = _normalized_visible_column_indices(len(headers), visible_indices)
    identity_keys = _column_identity_keys(headers)
    return [identity_keys[index] for index in normalized_indices]


def _visible_column_indices_from_keys(headers: list[str], visible_keys: list[str] | None) -> list[int] | None:
    if not visible_keys:
        return None

    identity_keys = _column_identity_keys(headers)
    index_by_key = {key: index for index, key in enumerate(identity_keys)}
    resolved_indices: list[int] = []
    seen_indices: set[int] = set()
    for raw_key in visible_keys:
        key = str(raw_key).strip().casefold()
        index = index_by_key.get(key)
        if index is None or index in seen_indices:
            continue
        resolved_indices.append(index)
        seen_indices.add(index)

    return sorted(resolved_indices) or None


def _column_index_from_identity_key(headers: list[str], key: str | None) -> int | None:
    normalized_key = str(key).strip().casefold() if key is not None else ""
    if not normalized_key:
        return None

    identity_keys = _column_identity_keys(headers)
    try:
        return identity_keys.index(normalized_key)
    except ValueError:
        return None


def _normalized_header(header: str) -> str:
    return "".join(ch for ch in header.casefold() if ch.isalnum())


def _detect_session_column(headers: list[str]) -> int | None:
    for index, header in enumerate(headers):
        if "session" in _normalized_header(header):
            return index
    return None


def _detect_quantity_column(headers: list[str]) -> int | None:
    for index, header in enumerate(headers):
        normalized = _normalized_header(header)
        if "quantity" in normalized or normalized == "qty":
            return index
    return None


def _header_suggests_numeric(header: str) -> bool:
    normalized = _normalized_header(header)
    numeric_tokens = ("qty", "quantity", "revenue", "sales", "amount", "total", "price", "cost", "value", "units")
    return any(token in normalized for token in numeric_tokens)


def _is_identifier_column(header: str) -> bool:
    normalized = _normalized_header(header)
    identifier_tokens = ("plu", "code", "sku", "barcode", "upc", "ean", "itemid", "productid")
    return any(token in normalized for token in identifier_tokens)


def _parse_decimal(value: str) -> Decimal | None:
    normalized = value.strip().replace(",", "")
    if not normalized:
        return None
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def _format_decimal(value: Decimal | None) -> str:
    if value is None:
        return ""
    normalized = value.normalize()
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _combined_sessions(values: list[str]) -> str:
    ordered = OrderedDict.fromkeys(value.strip() for value in values if value.strip())
    return COMBINED_SESSION_SEPARATOR.join(ordered)


def _detect_numeric_columns(
    data: CsvPreviewData,
    excluded_indices: set[int],
    rows=None,
    *,
    exclude_identifier_columns: bool = True,
) -> set[int]:
    numeric_columns: set[int] = set()
    numeric_tokens = ("qty", "quantity", "revenue", "sales", "amount", "total", "price", "cost", "value", "units")
    candidate_indices: list[int] = []
    for index, header in enumerate(data.headers):
        normalized = _normalized_header(header)
        if index in excluded_indices or (exclude_identifier_columns and _is_identifier_column(header)):
            continue
        if any(token in normalized for token in numeric_tokens):
            numeric_columns.add(index)
        else:
            candidate_indices.append(index)

    inspected_rows = data.rows if rows is None else rows
    column_counts = {index: [0, 0] for index in candidate_indices}
    for row in inspected_rows:
        for index in candidate_indices:
            value = row[index].strip()
            if not value:
                continue
            column_counts[index][0] += 1
            if _parse_decimal(value) is not None:
                column_counts[index][1] += 1

    for index, (non_empty_values, numeric_values) in column_counts.items():
        mostly_numeric = non_empty_values and (numeric_values / non_empty_values) >= 0.98
        small_sample_with_single_outlier = non_empty_values <= 5 and numeric_values >= max(2, non_empty_values - 1)
        if mostly_numeric or small_sample_with_single_outlier:
            numeric_columns.add(index)
    return numeric_columns


def _row_matches_query(row: tuple[str, ...], query: str) -> bool:
    return _row_matches_normalized_query(row, query.strip().casefold())


def _row_matches_normalized_query(row: tuple[str, ...], normalized_query: str) -> bool:
    if not normalized_query:
        return True
    for value in row:
        if normalized_query in value.casefold():
            return True
    return False


def _sorted_distinct_values(rows, column_index: int) -> list[str]:
    values = {row[column_index] for row in rows}
    return sorted(values, key=lambda value: value.casefold())


def _sorted_distinct_column_values(values) -> list[str]:
    return sorted(set(values), key=lambda value: value.casefold())


def _row_search_text(row: tuple[str, ...]) -> str:
    return "\x1f".join(value.casefold() for value in row)


def _summary_text(
    data: CsvPreviewData,
    *,
    visible_rows: int | None = None,
    displayed_rows: int | None = None,
    loaded_rows: int | None = None,
    filtered: bool = False,
    sort_description: str | None = None,
) -> str:
    known_total_rows = data.row_count
    matched_rows = known_total_rows if visible_rows is None else visible_rows
    if displayed_rows is not None:
        shown_rows = displayed_rows
    elif matched_rows is not None:
        shown_rows = matched_rows
    else:
        shown_rows = len(data.rows)

    if filtered:
        if visible_rows is None:
            row_text = f"Showing first {shown_rows} matching rows"
        elif shown_rows >= matched_rows:
            row_text = f"{matched_rows} matching rows"
        else:
            row_text = f"Showing first {shown_rows}/{matched_rows} matching rows"
    elif visible_rows is None:
        if known_total_rows is None:
            row_text = f"Showing first {shown_rows} preview rows"
        elif shown_rows >= known_total_rows:
            row_text = f"{known_total_rows} rows"
        else:
            row_text = f"Showing first {shown_rows}/{known_total_rows} rows"
    elif known_total_rows is not None and matched_rows == known_total_rows:
        if shown_rows >= matched_rows:
            row_text = f"{matched_rows} rows"
        else:
            row_text = f"Showing first {shown_rows}/{matched_rows} rows"
    elif shown_rows >= matched_rows:
        row_text = f"{matched_rows} matching rows"
    else:
        row_text = f"Showing first {shown_rows}/{matched_rows} matching rows"
    segments = [data.path.name, row_text]
    if sort_description:
        segments.append(sort_description)
    if loaded_rows is None or loaded_rows >= shown_rows:
        segments.extend((f"{data.column_count} columns", data.encoding))
        return " | ".join(segments)
    segments[1] = f"Loading {loaded_rows}/{shown_rows} shown rows"
    segments.extend((f"{data.column_count} columns", data.encoding))
    return " | ".join(segments)


def _loading_summary_text(data: CsvPreviewData, *, filtered: bool, sort_description: str | None = None) -> str:
    row_text = "Loading matching rows" if filtered else "Loading rows"
    segments = [data.path.name, row_text]
    if sort_description:
        segments.append(sort_description)
    segments.extend((f"{data.column_count} columns", data.encoding))
    return " | ".join(segments)


def _sort_direction_label(*, descending: bool, numeric: bool) -> str:
    if numeric:
        return "high to low" if descending else "low to high"
    return "Z to A" if descending else "A to Z"