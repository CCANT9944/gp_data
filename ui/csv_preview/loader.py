from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


FALLBACK_ENCODINGS = ("utf-8-sig", "utf-8", "cp1252", "latin-1")
_PREVIEW_CACHE: dict[tuple[str, int, int], "CsvPreviewData"] = {}


class CsvPreviewError(RuntimeError):
    pass


@dataclass(frozen=True)
class CsvPreviewData:
    path: Path
    encoding: str
    headers: list[str]
    rows: list[tuple[str, ...]]

    @property
    def column_count(self) -> int:
        return len(self.headers)

    @property
    def row_count(self) -> int:
        return len(self.rows)


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


def _store_cached_preview(cache_key: tuple[str, int, int], data: CsvPreviewData) -> None:
    resolved_path = cache_key[0]
    stale_keys = [key for key in _PREVIEW_CACHE if key[0] == resolved_path and key != cache_key]
    for key in stale_keys:
        _PREVIEW_CACHE.pop(key, None)
    _PREVIEW_CACHE[cache_key] = data


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

    raw_rows: list[list[str]] | None = None
    used_encoding: str | None = None
    decode_error: UnicodeDecodeError | None = None

    for encoding in FALLBACK_ENCODINGS:
        try:
            with csv_path.open("r", encoding=encoding, newline="") as csv_file:
                raw_rows = [[str(value) for value in row] for row in csv.reader(csv_file)]
            used_encoding = encoding
            break
        except UnicodeDecodeError as exc:
            decode_error = exc
            continue
        except OSError as exc:
            raise CsvPreviewError(f"Could not open the selected CSV file.\n\nReason: {exc}") from exc
        except csv.Error as exc:
            raise CsvPreviewError(f"Could not read the selected CSV file.\n\nReason: {exc}") from exc

    if raw_rows is None or used_encoding is None:
        reason = decode_error or "Unknown encoding error"
        raise CsvPreviewError(f"Could not decode the selected CSV file.\n\nReason: {reason}")

    if not raw_rows:
        raise CsvPreviewError("The selected CSV file is empty.")

    header_row = raw_rows[0]
    data_rows = raw_rows[1:]
    column_count = max(len(header_row), max((len(row) for row in data_rows), default=0))
    if column_count == 0:
        raise CsvPreviewError("The selected CSV file does not contain any columns.")

    headers = _display_headers(header_row, column_count)
    rows = [_normalized_row(row, column_count) for row in data_rows]
    data = CsvPreviewData(path=csv_path, encoding=used_encoding, headers=headers, rows=rows)
    _store_cached_preview(cache_key, data)
    return data