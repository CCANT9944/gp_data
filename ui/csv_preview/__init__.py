from .loader import CsvPreviewData, CsvPreviewError, load_csv_preview

__all__ = ["CsvPreviewData", "CsvPreviewError", "load_csv_preview", "open_csv_preview_dialog"]


def __getattr__(name: str):
    if name == "open_csv_preview_dialog":
        from .dialog import open_csv_preview_dialog

        return open_csv_preview_dialog
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")