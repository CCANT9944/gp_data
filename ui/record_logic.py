from __future__ import annotations

import re
from typing import Iterable

from ..models import Record


def search_words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def record_matches_substring_query(record: Record, query: str) -> bool:
    return query in (record.field1 or "").lower() or query in (record.field2 or "").lower()


def record_matches_exact_word_query(record: Record, query: str) -> bool:
    return query in search_words(record.field1 or "") or query in search_words(record.field2 or "")


def filtered_records(records: Iterable[Record], query: str) -> list[Record]:
    records = list(records)
    if not query:
        return records

    exact_matches = [record for record in records if record_matches_exact_word_query(record, query)]
    if exact_matches:
        return exact_matches

    return [record for record in records if record_matches_substring_query(record, query)]


def record_matches_query(record: Record, query: str, records: Iterable[Record]) -> bool:
    records = list(records)
    if not query:
        return True
    if any(record_matches_exact_word_query(existing, query) for existing in records):
        return record_matches_exact_word_query(record, query)
    return record_matches_substring_query(record, query)