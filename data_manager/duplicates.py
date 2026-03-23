from __future__ import annotations

import re
from collections.abc import Callable, Iterable

from ..models import Record


_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_LIKELY_FORMAT_TOKENS = frozenset({"btl", "btls"})
_SIZE_TOKEN_RE = re.compile(r"^\d+(?:ml|cl|l)$")
_SIZE_NUMBER_TOKEN_RE = re.compile(r"^\d+(?:\.\d+)?$")
_SIZE_UNIT_TOKEN_RE = re.compile(r"^(?:ml|cl|l)$")


def _normalized_duplicate_text(value: str | None) -> str:
    normalized = _NON_ALNUM_RE.sub(" ", str(value or "").strip().lower())
    return " ".join(normalized.split())


def duplicate_identity_for_values(field1: str | None, field2: str | None) -> tuple[str, str] | None:
    normalized_field1 = _normalized_duplicate_text(field1)
    normalized_field2 = _normalized_duplicate_text(field2)
    if not normalized_field1 or not normalized_field2:
        return None
    return normalized_field1, normalized_field2


def _trim_leading_possible_duplicate_tokens(tokens: list[str]) -> list[str]:
    trimmed_tokens = list(tokens)
    while len(trimmed_tokens) > 1 and trimmed_tokens and trimmed_tokens[0] in _LIKELY_FORMAT_TOKENS:
        trimmed_tokens.pop(0)
    while len(trimmed_tokens) > 1 and trimmed_tokens and _SIZE_TOKEN_RE.fullmatch(trimmed_tokens[0]):
        trimmed_tokens.pop(0)
    while (
        len(trimmed_tokens) > 2
        and _SIZE_NUMBER_TOKEN_RE.fullmatch(trimmed_tokens[0])
        and _SIZE_UNIT_TOKEN_RE.fullmatch(trimmed_tokens[1])
    ):
        trimmed_tokens = trimmed_tokens[2:]
    return trimmed_tokens


def _trim_trailing_possible_duplicate_tokens(tokens: list[str]) -> list[str]:
    trimmed_tokens = list(tokens)
    while len(trimmed_tokens) > 1 and trimmed_tokens and _SIZE_TOKEN_RE.fullmatch(trimmed_tokens[-1]):
        trimmed_tokens.pop()
    while (
        len(trimmed_tokens) > 2
        and _SIZE_NUMBER_TOKEN_RE.fullmatch(trimmed_tokens[-2])
        and _SIZE_UNIT_TOKEN_RE.fullmatch(trimmed_tokens[-1])
    ):
        trimmed_tokens = trimmed_tokens[:-2]
    return trimmed_tokens


def _trim_format_tokens_only(tokens: list[str]) -> list[str]:
    trimmed_tokens = list(tokens)
    while len(trimmed_tokens) > 1 and trimmed_tokens and trimmed_tokens[0] in _LIKELY_FORMAT_TOKENS:
        trimmed_tokens.pop(0)
    return trimmed_tokens


def possible_duplicate_identity_for_values(field1: str | None, field2: str | None) -> tuple[str, str] | None:
    normalized_field1 = _normalized_duplicate_text(field1)
    normalized_name = _normalized_duplicate_text(field2)
    if not normalized_field1 or not normalized_name:
        return None

    tokens = normalized_name.split()
    trimmed_tokens = _trim_leading_possible_duplicate_tokens(tokens)
    trimmed_tokens = _trim_trailing_possible_duplicate_tokens(trimmed_tokens)

    candidate_name = " ".join(trimmed_tokens or tokens)
    if not candidate_name:
        return None
    return normalized_field1, candidate_name


def import_selection_possible_duplicate_identity_for_values(
    field1: str | None,
    field2: str | None,
) -> tuple[str, str] | None:
    normalized_field1 = _normalized_duplicate_text(field1)
    normalized_name = _normalized_duplicate_text(field2)
    if not normalized_field1 or not normalized_name:
        return None

    tokens = normalized_name.split()
    trimmed_tokens = _trim_format_tokens_only(tokens)

    candidate_name = " ".join(trimmed_tokens or tokens)
    if not candidate_name:
        return None
    return normalized_field1, candidate_name


class DuplicateDetector:
    def __init__(self, load_records: Callable[[], Iterable[Record]]):
        self._load_records = load_records

    def duplicate_identity(self, record: Record) -> tuple[str, str] | None:
        return duplicate_identity_for_values(record.field1, record.field2)

    def possible_duplicate_identity(self, record: Record) -> tuple[str, str] | None:
        return possible_duplicate_identity_for_values(record.field1, record.field2)

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

    def find_possible_duplicate_record(self, record: Record, exclude_id: str | None = None) -> Record | None:
        identity = self.possible_duplicate_identity(record)
        if identity is None:
            return None
        for existing in self._load_records():
            if exclude_id is not None and existing.id == exclude_id:
                continue
            if self.possible_duplicate_identity(existing) == identity:
                return existing
        return None