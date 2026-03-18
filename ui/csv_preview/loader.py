from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path


FALLBACK_ENCODINGS = ("utf-8-sig", "utf-8", "cp1252", "latin-1")
PREVIEW_ROW_SAMPLE_SIZE = 5000
_METADATA_SIDECAR_SUFFIX = ".gp-preview.json"
_PREVIEW_CACHE: dict[tuple[str, int, int], "CsvPreviewData"] = {}


class CsvPreviewError(RuntimeError):
    pass


@dataclass(frozen=True)
class CsvPreviewData:
    path: Path
    encoding: str
    headers: list[str]
    rows: list[tuple[str, ...]]
    row_total: int | None
    fully_cached: bool

    @property
    def column_count(self) -> int:
        return len(self.headers)

    @property
    def row_count(self) -> int | None:
        return self.row_total


def _display_headers(header_row: list[str], column_count: int) -> list[str]:
    headers = list(header_row)
    for index in range(len(headers), column_count):
        headers.append(f"Column {index + 1}")
    return headers


def _normalized_row(row: list[str], column_count: int) -> tuple[str, ...]:
    normalized = list(row[:column_count])
    if len(normalized) < column_count:
        normalized.extend([""] * (column_count - len(normalized)))
    return tuple(normalized)


def _cache_key(csv_path: Path) -> tuple[str, int, int]:
    stat = csv_path.stat()
    return (str(csv_path.resolve()), stat.st_mtime_ns, stat.st_size)


def _metadata_sidecar_path(csv_path: Path) -> Path:
    return csv_path.with_name(f"{csv_path.name}{_METADATA_SIDECAR_SUFFIX}")


def _prioritized_encodings(cached_encoding: str | None):
    if not cached_encoding:
        return FALLBACK_ENCODINGS
    prioritized = [cached_encoding]
    prioritized.extend(encoding for encoding in FALLBACK_ENCODINGS if encoding != cached_encoding)
    return tuple(prioritized)


def _load_cached_preview_metadata(cache_key: tuple[str, int, int], csv_path: Path) -> dict[str, object] | None:
    sidecar_path = _metadata_sidecar_path(csv_path)
    try:
        with sidecar_path.open("r", encoding="utf-8") as sidecar_file:
            payload = json.load(sidecar_file)
    except (OSError, ValueError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict):
        return None
    if payload.get("version") != 1:
        return None
    if payload.get("path") != cache_key[0] or payload.get("mtime_ns") != cache_key[1] or payload.get("size") != cache_key[2]:
        return None

    encoding = payload.get("encoding")
    headers = payload.get("headers")
    row_total = payload.get("row_total")
    if not isinstance(encoding, str) or not encoding:
        return None
    if not isinstance(headers, list) or not headers or not all(isinstance(header, str) and header for header in headers):
        return None
    if not isinstance(row_total, int) or row_total < 0:
        return None

    return {"encoding": encoding, "headers": list(headers), "row_total": row_total}


def _store_cached_preview_metadata(cache_key: tuple[str, int, int], data: CsvPreviewData) -> None:
    sidecar_path = _metadata_sidecar_path(data.path)
    if data.row_total is None or data.row_total <= PREVIEW_ROW_SAMPLE_SIZE:
        try:
            sidecar_path.unlink(missing_ok=True)
        except OSError:
            pass
        return

    payload = {
        "version": 1,
        "path": cache_key[0],
        "mtime_ns": cache_key[1],
        "size": cache_key[2],
        "encoding": data.encoding,
        "headers": list(data.headers),
        "row_total": data.row_total,
    }
    try:
        with sidecar_path.open("w", encoding="utf-8", newline="") as sidecar_file:
            json.dump(payload, sidecar_file, ensure_ascii=True, separators=(",", ":"))
    except OSError:
        return


def _store_cached_preview(cache_key: tuple[str, int, int], data: CsvPreviewData) -> None:
    resolved_path = cache_key[0]
    stale_keys = [key for key in _PREVIEW_CACHE if key[0] == resolved_path and key != cache_key]
    for key in stale_keys:
        _PREVIEW_CACHE.pop(key, None)
    _PREVIEW_CACHE[cache_key] = data


def _iter_csv_file_rows(csv_path: Path, encoding: str):
    try:
        with csv_path.open("r", encoding=encoding, newline="") as csv_file:
            reader = csv.reader(csv_file)
            for row in reader:
                yield [str(value) for value in row]
    except OSError as exc:
        raise CsvPreviewError(f"Could not open the selected CSV file.\n\nReason: {exc}") from exc
    except csv.Error as exc:
        raise CsvPreviewError(f"Could not read the selected CSV file.\n\nReason: {exc}") from exc


def iter_csv_preview_rows(data: CsvPreviewData):
    if data.fully_cached:
        yield from data.rows
        return

    row_iter = _iter_csv_file_rows(data.path, data.encoding)
    next(row_iter, None)
    for row in row_iter:
        yield _normalized_row(row, data.column_count)


def resolve_csv_preview_metadata(data: CsvPreviewData) -> CsvPreviewData:
    if data.row_total is not None:
        return data

    row_iter = _iter_csv_file_rows(data.path, data.encoding)
    header_row = next(row_iter, None)
    if header_row is None:
        raise CsvPreviewError("The selected CSV file is empty.")

    column_count = len(header_row)
    row_total = 0
    for row in row_iter:
        row_total += 1
        column_count = max(column_count, len(row))

    headers = _display_headers(header_row, column_count)
    rows = [_normalized_row(list(row), column_count) for row in data.rows]
    updated = CsvPreviewData(
        path=data.path,
        encoding=data.encoding,
        headers=headers,
        rows=rows,
        row_total=row_total,
        fully_cached=row_total <= PREVIEW_ROW_SAMPLE_SIZE,
    )

    try:
        cache_key = _cache_key(data.path)
        _store_cached_preview(cache_key, updated)
        _store_cached_preview_metadata(cache_key, updated)
    except OSError:
        pass
    return updated


def load_csv_preview(path: str | Path) -> CsvPreviewData:
    csv_path = Path(path)
    if not csv_path.exists():
        raise CsvPreviewError("The selected CSV file could not be found.")

    try:
        cache_key = _cache_key(csv_path)
    except OSError as exc:
        raise CsvPreviewError(f"Could not inspect the selected CSV file.\n\nReason: {exc}") from exc

    cached = _PREVIEW_CACHE.get(cache_key)
    if cached is not None:
        return cached

    cached_metadata = _load_cached_preview_metadata(cache_key, csv_path)

    used_encoding: str | None = None
    decode_error: UnicodeDecodeError | None = None
    header_row: list[str] | None = None
    preview_rows: list[list[str]] = []
    row_total: int | None = 0
    column_count = 0

    for encoding in _prioritized_encodings(cached_metadata["encoding"] if cached_metadata is not None else None):
        try:
            row_iter = _iter_csv_file_rows(csv_path, encoding)
            header_row = next(row_iter, None)
            if header_row is None:
                raise CsvPreviewError("The selected CSV file is empty.")
            column_count = len(header_row)
            preview_rows = []
            row_total = 0
            for row in row_iter:
                if len(preview_rows) < PREVIEW_ROW_SAMPLE_SIZE:
                    row_total += 1
                    column_count = max(column_count, len(row))
                    preview_rows.append(row)
                    continue

                row_total = None
                break
            used_encoding = encoding
            break
        except UnicodeDecodeError as exc:
            decode_error = exc
            continue

    if header_row is None or used_encoding is None:
        reason = decode_error or "Unknown encoding error"
        raise CsvPreviewError(f"Could not decode the selected CSV file.\n\nReason: {reason}")

    if column_count == 0:
        raise CsvPreviewError("The selected CSV file does not contain any columns.")

    cached_headers = None if cached_metadata is None else cached_metadata["headers"]
    if isinstance(cached_headers, list) and len(cached_headers) >= column_count:
        column_count = len(cached_headers)
        headers = list(cached_headers)
    else:
        headers = _display_headers(header_row, column_count)

    if row_total is None and cached_metadata is not None:
        cached_row_total = cached_metadata["row_total"]
        if isinstance(cached_row_total, int) and cached_row_total > PREVIEW_ROW_SAMPLE_SIZE:
            row_total = cached_row_total

    rows = [_normalized_row(row, column_count) for row in preview_rows]
    fully_cached = row_total is not None and row_total <= PREVIEW_ROW_SAMPLE_SIZE
    data = CsvPreviewData(path=csv_path, encoding=used_encoding, headers=headers, rows=rows, row_total=row_total, fully_cached=fully_cached)
    _store_cached_preview(cache_key, data)
    return data