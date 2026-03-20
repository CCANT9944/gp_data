from __future__ import annotations

from dataclasses import dataclass, field

from .loader import CsvPreviewData
from .pipeline import _PreviewFilterState


@dataclass
class _PreviewSummaryState:
    filtered: bool = False
    loading: bool = False
    visible_rows: int | None = None
    displayed_rows: int = 0
    loaded_rows: int | None = None

    loading_summary_text_impl = staticmethod(lambda data, *, filtered, sort_description=None: "")
    summary_text_impl = staticmethod(
        lambda data, *, visible_rows, displayed_rows, loaded_rows, filtered=False, sort_description=None: ""
    )

    def set_loading(self, *, filtered: bool) -> None:
        self.filtered = filtered
        self.loading = True
        self.visible_rows = None
        self.displayed_rows = 0
        self.loaded_rows = 0

    def set_ready(self, *, filtered: bool, visible_rows: int | None, displayed_rows: int) -> None:
        self.filtered = filtered
        self.loading = False
        self.visible_rows = visible_rows
        self.displayed_rows = displayed_rows
        self.loaded_rows = 0 if displayed_rows else None

    def apply_loaded_chunk(
        self,
        *,
        filtered: bool,
        total_visible_rows: int | None,
        displayed_rows: int,
        loaded_rows: int,
    ) -> None:
        self.filtered = filtered
        if self.visible_rows is None:
            self.visible_rows = total_visible_rows
        self.displayed_rows = displayed_rows
        self.loaded_rows = loaded_rows

    def render_text(self, data: CsvPreviewData, *, sort_description: str | None = None) -> str:
        if self.loading:
            return self.loading_summary_text_impl(data, filtered=self.filtered, sort_description=sort_description)
        return self.summary_text_impl(
            data,
            visible_rows=self.visible_rows,
            displayed_rows=self.displayed_rows,
            loaded_rows=self.loaded_rows,
            filtered=self.filtered,
            sort_description=sort_description,
        )


@dataclass
class _PreviewViewState:
    visible_column_indices: list[int]
    header_filter_column_index: int | None = None
    header_filter_value: str | None = None
    sort_column_index: int | None = None
    sort_descending: bool = False
    summary: _PreviewSummaryState = field(default_factory=_PreviewSummaryState)

    normalize_visible_column_indices_impl = staticmethod(lambda column_count, visible_indices: list(range(column_count)))

    def filter_state(self, *, query: str, combine_sessions: bool) -> _PreviewFilterState:
        return _PreviewFilterState(
            query=query,
            combine_sessions=combine_sessions,
            header_filter_column_index=self.header_filter_column_index,
            header_filter_value=self.header_filter_value,
            sort_column_index=self.sort_column_index,
            sort_descending=self.sort_descending,
        )

    def visible_column_ids(self, all_column_ids: list[str]) -> list[str]:
        return [all_column_ids[index] for index in self.visible_column_indices]

    def set_header_filter(self, column_index: int | None, value: str | None) -> None:
        self.header_filter_column_index = column_index
        self.header_filter_value = value

    def set_sort(self, column_index: int | None, *, descending: bool = False) -> None:
        self.sort_column_index = column_index
        self.sort_descending = bool(descending) if column_index is not None else False

    def apply_visible_columns(self, all_column_ids: list[str], visible_indices: list[int]) -> tuple[bool, bool]:
        self.visible_column_indices = self.normalize_visible_column_indices_impl(len(all_column_ids), visible_indices)
        header_filter_cleared = False
        sort_cleared = False
        if self.header_filter_column_index is not None and self.header_filter_column_index not in self.visible_column_indices:
            self.header_filter_column_index = None
            self.header_filter_value = None
            header_filter_cleared = True
        if self.sort_column_index is not None and self.sort_column_index not in self.visible_column_indices:
            self.sort_column_index = None
            self.sort_descending = False
            sort_cleared = True
        return header_filter_cleared, sort_cleared