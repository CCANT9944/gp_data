from __future__ import annotations

import csv
import gzip
import json
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path


FALLBACK_ENCODINGS = ("utf-8-sig", "utf-8", "cp1252", "latin-1")
PREVIEW_ROW_SAMPLE_SIZE = 5000
_METADATA_SIDECAR_SUFFIX = ".gp-preview.json"
_ROW_CACHE_SIDECAR_SUFFIX = ".gp-preview-rows.json.gz"
_PREVIEW_METADATA_VERSION = 2
_ROW_CACHE_VERSION = 1
PERSISTED_FULL_ROW_CACHE_MAX_FILE_BYTES = 32 * 1024 * 1024
PREVIEW_CACHE_MAX_ENTRIES = 32
_PREVIEW_CACHE: OrderedDict[tuple[str, int, int, bool], "CsvPreviewData"] = OrderedDict()

type CacheKey = tuple[str, int, int]
type PreviewCacheKey = tuple[str, int, int, bool]


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
    has_header_row: bool = True

    @property
    def column_count(self) -> int:
        return len(self.headers)

    @property
    def row_count(self) -> int | None:
        return self.row_total


@dataclass(frozen=True)
class _CachedPreviewMetadata:
    encoding: str
    headers: list[str]
    row_total: int
    has_header_row: bool
    preview_rows: list[tuple[str, ...]] | None


@dataclass(frozen=True)
class _CachedFullRowData:
    encoding: str
    headers: list[str]
    row_total: int
    has_header_row: bool
    rows: list[tuple[str, ...]]


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


def _cache_key(csv_path: Path) -> CacheKey:
    stat = csv_path.stat()
    return (str(csv_path.resolve()), stat.st_mtime_ns, stat.st_size)


def _preview_cache_key(cache_key: CacheKey, has_header_row: bool) -> PreviewCacheKey:
    return (*cache_key, bool(has_header_row))


def _metadata_sidecar_path(csv_path: Path) -> Path:
    return csv_path.with_name(f"{csv_path.name}{_METADATA_SIDECAR_SUFFIX}")


def _row_cache_sidecar_path(csv_path: Path) -> Path:
    return csv_path.with_name(f"{csv_path.name}{_ROW_CACHE_SIDECAR_SUFFIX}")


def _prioritized_encodings(cached_encoding: str | None):
    if not cached_encoding:
        return FALLBACK_ENCODINGS
    prioritized = [cached_encoding]
    prioritized.extend(encoding for encoding in FALLBACK_ENCODINGS if encoding != cached_encoding)
    return tuple(prioritized)


def _load_sidecar_payload(sidecar_path: Path, *, compressed: bool = False) -> dict[str, object] | None:
    try:
        if compressed:
            with gzip.open(sidecar_path, "rt", encoding="utf-8") as sidecar_file:
                payload = json.load(sidecar_file)
        else:
            with sidecar_path.open("r", encoding="utf-8") as sidecar_file:
                payload = json.load(sidecar_file)
    except (OSError, ValueError, json.JSONDecodeError):
        return None

    return payload if isinstance(payload, dict) else None


def _validated_sidecar_base(
    payload: dict[str, object] | None,
    cache_key: CacheKey,
    has_header_row: bool,
    *,
    supported_versions: tuple[int, ...],
) -> tuple[str, list[str], int, bool] | None:
    if payload is None:
        return None

    if payload.get("version") not in supported_versions:
        return None
    if payload.get("path") != cache_key[0] or payload.get("mtime_ns") != cache_key[1] or payload.get("size") != cache_key[2]:
        return None

    encoding = payload.get("encoding")
    headers = payload.get("headers")
    row_total = payload.get("row_total")
    cached_has_header_row = payload.get("has_header_row")
    if not isinstance(encoding, str) or not encoding:
        return None
    if not isinstance(headers, list) or not headers or not all(isinstance(header, str) for header in headers):
        return None
    if not isinstance(row_total, int) or row_total < 0:
        return None
    if cached_has_header_row is not None and (not isinstance(cached_has_header_row, bool) or cached_has_header_row != has_header_row):
        return None

    normalized_has_header_row = bool(cached_has_header_row) if isinstance(cached_has_header_row, bool) else True
    return encoding, list(headers), row_total, normalized_has_header_row


def _normalized_cached_rows(
    rows_payload: object,
    *,
    column_count: int,
    expected_count: int | None = None,
    max_count: int | None = None,
) -> list[tuple[str, ...]] | None:
    if not isinstance(rows_payload, list):
        return None
    if expected_count is not None and len(rows_payload) != expected_count:
        return None
    if max_count is not None and len(rows_payload) > max_count:
        return None

    normalized_rows: list[tuple[str, ...]] = []
    for row in rows_payload:
        if not isinstance(row, list) or not all(isinstance(value, str) for value in row):
            return None
        normalized_rows.append(_normalized_row(row, column_count))
    return normalized_rows


def _load_cached_preview_metadata(cache_key: CacheKey, csv_path: Path, has_header_row: bool) -> _CachedPreviewMetadata | None:
    payload = _load_sidecar_payload(_metadata_sidecar_path(csv_path))
    base = _validated_sidecar_base(
        payload,
        cache_key,
        has_header_row,
        supported_versions=(1, _PREVIEW_METADATA_VERSION),
    )
    if base is None:
        return None

    encoding, headers, row_total, normalized_has_header_row = base
    preview_rows_payload = payload.get("preview_rows") if payload is not None else None
    preview_rows = None
    if preview_rows_payload is not None:
        preview_rows = _normalized_cached_rows(
            preview_rows_payload,
            column_count=len(headers),
            max_count=PREVIEW_ROW_SAMPLE_SIZE,
        )
        if preview_rows is None:
            return None

    return _CachedPreviewMetadata(
        encoding=encoding,
        headers=headers,
        row_total=row_total,
        has_header_row=normalized_has_header_row,
        preview_rows=preview_rows,
    )


def _load_cached_full_row_cache(cache_key: CacheKey, csv_path: Path, has_header_row: bool) -> _CachedFullRowData | None:
    payload = _load_sidecar_payload(_row_cache_sidecar_path(csv_path), compressed=True)
    base = _validated_sidecar_base(
        payload,
        cache_key,
        has_header_row,
        supported_versions=(_ROW_CACHE_VERSION,),
    )
    if base is None:
        return None

    encoding, headers, row_total, normalized_has_header_row = base
    rows_payload = payload.get("rows") if payload is not None else None
    rows = _normalized_cached_rows(
        rows_payload,
        column_count=len(headers),
        expected_count=row_total,
    )
    if rows is None:
        return None

    return _CachedFullRowData(
        encoding=encoding,
        headers=headers,
        row_total=row_total,
        has_header_row=normalized_has_header_row,
        rows=rows,
    )


def _store_cached_preview_metadata(cache_key: CacheKey, data: CsvPreviewData) -> None:
    sidecar_path = _metadata_sidecar_path(data.path)
    if data.row_total is None or data.row_total <= PREVIEW_ROW_SAMPLE_SIZE:
        try:
            sidecar_path.unlink(missing_ok=True)
        except OSError:
            pass
        return

    payload = {
        "version": _PREVIEW_METADATA_VERSION,
        "path": cache_key[0],
        "mtime_ns": cache_key[1],
        "size": cache_key[2],
        "encoding": data.encoding,
        "headers": list(data.headers),
        "row_total": data.row_total,
        "preview_rows": [list(row) for row in data.rows[:PREVIEW_ROW_SAMPLE_SIZE]],
        "has_header_row": data.has_header_row,
    }
    try:
        with sidecar_path.open("w", encoding="utf-8", newline="") as sidecar_file:
            json.dump(payload, sidecar_file, ensure_ascii=True, separators=(",", ":"))
    except OSError:
        return


def _store_cached_full_row_cache(cache_key: CacheKey, data: CsvPreviewData, rows: list[tuple[str, ...]] | None) -> None:
    sidecar_path = _row_cache_sidecar_path(data.path)
    if (
        rows is None
        or data.row_total is None
        or data.row_total <= PREVIEW_ROW_SAMPLE_SIZE
        or len(rows) != data.row_total
        or cache_key[2] > PERSISTED_FULL_ROW_CACHE_MAX_FILE_BYTES
    ):
        try:
            sidecar_path.unlink(missing_ok=True)
        except OSError:
            pass
        return

    payload = {
        "version": _ROW_CACHE_VERSION,
        "path": cache_key[0],
        "mtime_ns": cache_key[1],
        "size": cache_key[2],
        "encoding": data.encoding,
        "headers": list(data.headers),
        "row_total": data.row_total,
        "rows": [list(row) for row in rows],
        "has_header_row": data.has_header_row,
    }
    try:
        with gzip.open(sidecar_path, "wt", encoding="utf-8", newline="") as sidecar_file:
            json.dump(payload, sidecar_file, ensure_ascii=True, separators=(",", ":"))
    except OSError:
        return


def _store_cached_preview(cache_key: PreviewCacheKey, data: CsvPreviewData) -> None:
    resolved_path = cache_key[0]
    has_header_row = cache_key[3]
    stale_keys = [key for key in _PREVIEW_CACHE if key[0] == resolved_path and key[3] == has_header_row and key != cache_key]
    for key in stale_keys:
        _PREVIEW_CACHE.pop(key, None)
    _PREVIEW_CACHE.pop(cache_key, None)
    _PREVIEW_CACHE[cache_key] = data
    while len(_PREVIEW_CACHE) > PREVIEW_CACHE_MAX_ENTRIES:
        _PREVIEW_CACHE.popitem(last=False)


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
    if data.has_header_row:
        next(row_iter, None)
    for row in row_iter:
        yield _normalized_row(row, data.column_count)


def load_cached_csv_row_cache(data: CsvPreviewData) -> list[tuple[str, ...]] | None:
    if data.fully_cached:
        return list(data.rows)

    try:
        cache_key = _cache_key(data.path)
    except OSError:
        return None

    cached = _load_cached_full_row_cache(cache_key, data.path, data.has_header_row)
    if cached is None:
        return None
    if cached.encoding != data.encoding or cached.headers != data.headers or cached.row_total != data.row_count:
        return None
    return list(cached.rows)


def resolve_csv_preview_metadata(data: CsvPreviewData) -> CsvPreviewData:
    if data.row_total is not None:
        return data

    row_iter = _iter_csv_file_rows(data.path, data.encoding)
    first_row = next(row_iter, None)
    if first_row is None:
        raise CsvPreviewError("The selected CSV file is empty.")

    column_count = len(first_row)
    row_total = 0 if data.has_header_row else 1
    cache_key: CacheKey | None = None
    full_row_candidates: list[list[str]] | None = None
    try:
        cache_key = _cache_key(data.path)
    except OSError:
        cache_key = None
    if cache_key is not None and cache_key[2] <= PERSISTED_FULL_ROW_CACHE_MAX_FILE_BYTES:
        full_row_candidates = []
    if not data.has_header_row and full_row_candidates is not None:
        full_row_candidates.append(list(first_row))
    for row in row_iter:
        row_total += 1
        column_count = max(column_count, len(row))
        if full_row_candidates is not None:
            full_row_candidates.append(list(row))

    headers = _display_headers(first_row if data.has_header_row else [], column_count)
    rows = [_normalized_row(list(row), column_count) for row in data.rows]
    full_rows = None if full_row_candidates is None else [_normalized_row(row, column_count) for row in full_row_candidates]
    updated = CsvPreviewData(
        path=data.path,
        encoding=data.encoding,
        headers=headers,
        rows=rows,
        row_total=row_total,
        fully_cached=row_total <= PREVIEW_ROW_SAMPLE_SIZE,
        has_header_row=data.has_header_row,
    )

    try:
        if cache_key is None:
            cache_key = _cache_key(data.path)
        _store_cached_preview(_preview_cache_key(cache_key, data.has_header_row), updated)
        _store_cached_preview_metadata(cache_key, updated)
        _store_cached_full_row_cache(cache_key, updated, full_rows)
    except OSError:
        pass
    return updated


def load_csv_preview(path: str | Path, *, has_header_row: bool = True) -> CsvPreviewData:
    csv_path = Path(path)
    if not csv_path.exists():
        raise CsvPreviewError("The selected CSV file could not be found.")

    try:
        cache_key = _cache_key(csv_path)
    except OSError as exc:
        raise CsvPreviewError(f"Could not inspect the selected CSV file.\n\nReason: {exc}") from exc

    preview_cache_key = _preview_cache_key(cache_key, has_header_row)

    cached = _PREVIEW_CACHE.get(preview_cache_key)
    if cached is not None:
        _PREVIEW_CACHE.move_to_end(preview_cache_key)
        return cached

    cached_metadata = _load_cached_preview_metadata(cache_key, csv_path, has_header_row)
    if cached_metadata is not None and cached_metadata.preview_rows is not None:
        rows = list(cached_metadata.preview_rows)
        row_total = cached_metadata.row_total
        data = CsvPreviewData(
            path=csv_path,
            encoding=cached_metadata.encoding,
            headers=list(cached_metadata.headers),
            rows=rows,
            row_total=row_total,
            fully_cached=row_total is not None and row_total <= len(rows),
            has_header_row=has_header_row,
        )
        _store_cached_preview(preview_cache_key, data)
        return data

    used_encoding: str | None = None
    decode_error: UnicodeDecodeError | None = None
    first_row: list[str] | None = None
    preview_rows: list[list[str]] = []
    row_total: int | None = 0
    column_count = 0

    for encoding in _prioritized_encodings(cached_metadata.encoding if cached_metadata is not None else None):
        try:
            row_iter = _iter_csv_file_rows(csv_path, encoding)
            first_row = next(row_iter, None)
            if first_row is None:
                raise CsvPreviewError("The selected CSV file is empty.")
            column_count = len(first_row)
            preview_rows = []
            row_total = 0 if has_header_row else 1
            if not has_header_row:
                preview_rows.append(first_row)
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

    if first_row is None or used_encoding is None:
        reason = decode_error or "Unknown encoding error"
        raise CsvPreviewError(f"Could not decode the selected CSV file.\n\nReason: {reason}")

    if column_count == 0:
        raise CsvPreviewError("The selected CSV file does not contain any columns.")

    cached_headers = None if cached_metadata is None else cached_metadata.headers
    if isinstance(cached_headers, list) and len(cached_headers) >= column_count:
        column_count = len(cached_headers)
        headers = list(cached_headers)
    else:
        headers = _display_headers(first_row if has_header_row else [], column_count)

    if row_total is None and cached_metadata is not None:
        cached_row_total = cached_metadata.row_total
        if isinstance(cached_row_total, int) and cached_row_total > PREVIEW_ROW_SAMPLE_SIZE:
            row_total = cached_row_total

    rows = [_normalized_row(row, column_count) for row in preview_rows]
    fully_cached = row_total is not None and row_total <= PREVIEW_ROW_SAMPLE_SIZE
    data = CsvPreviewData(
        path=csv_path,
        encoding=used_encoding,
        headers=headers,
        rows=rows,
        row_total=row_total,
        fully_cached=fully_cached,
        has_header_row=has_header_row,
    )
    _store_cached_preview(preview_cache_key, data)
    return data