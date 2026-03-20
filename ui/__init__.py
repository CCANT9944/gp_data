"""Tkinter UI package for gp_data."""

__all__ = ["GPDataApp", "InputForm", "RecordTable", "filedialog", "messagebox"]


def __getattr__(name: str):
    if name == "GPDataApp":
        from .app import GPDataApp

        return GPDataApp
    if name == "InputForm":
        from .form import InputForm

        return InputForm
    if name == "RecordTable":
        from .table import RecordTable

        return RecordTable
    if name == "filedialog":
        from tkinter import filedialog

        return filedialog
    if name == "messagebox":
        from tkinter import messagebox

        return messagebox
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")