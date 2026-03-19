from __future__ import annotations

import logging
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk
from weakref import WeakKeyDictionary


LOGGER = logging.getLogger(__name__)


PROCESSING_DIALOG_MIN_WIDTH = 360
PROCESSING_DIALOG_MIN_HEIGHT = 156


@dataclass(frozen=True)
class _ProcessingDialogState:
    detail_label: tk.Label
    style_name: str


_PROCESSING_DIALOG_STATE: WeakKeyDictionary[tk.Toplevel, _ProcessingDialogState] = WeakKeyDictionary()


class ProcessingDialogHandle:
    def __init__(
        self,
        parent: tk.Misc,
        *,
        title: str,
        eyebrow_text: str = "LOADING",
        detail_text: str,
    ) -> None:
        self._parent = parent
        self._title = title
        self._eyebrow_text = eyebrow_text
        self._detail_text = detail_text
        self._message_var = tk.StringVar(value="")
        self._dialog: tk.Toplevel | None = None

    @property
    def message_var(self) -> tk.StringVar:
        return self._message_var

    @property
    def dialog(self) -> tk.Toplevel | None:
        return self._dialog

    def show(self, message: str) -> tk.Toplevel:
        self._message_var.set(message)
        self._dialog = show_centered_processing_dialog(
            self._parent,
            self._dialog,
            self._message_var,
            title=self._title,
            eyebrow_text=self._eyebrow_text,
            detail_text=self._detail_text,
        )
        return self._dialog

    def clear(self) -> None:
        self._message_var.set("")
        dialog = self._dialog
        self._dialog = None
        close_processing_dialog(self._parent, dialog)


def show_centered_processing_dialog(
    parent: tk.Misc,
    dialog: tk.Toplevel | None,
    message_var: tk.StringVar,
    *,
    title: str,
    eyebrow_text: str = "LOADING",
    detail_text: str,
) -> tk.Toplevel:
    palette = _processing_dialog_palette(parent)
    if dialog is None or not dialog.winfo_exists():
        dialog = tk.Toplevel(parent)
        dialog.withdraw()
        dialog.title(title)
        dialog.configure(bg=palette["shell_bg"])
        dialog.resizable(False, False)
        try:
            dialog.transient(parent)
        except tk.TclError:
            LOGGER.debug("Unable to make processing dialog transient", exc_info=True)
        dialog.protocol("WM_DELETE_WINDOW", lambda: None)

        style_name = f"GPDataProcessing.{dialog.winfo_id()}.Horizontal.TProgressbar"
        _configure_processing_progressbar_style(ttk.Style(dialog), style_name, palette)

        shell = tk.Frame(dialog, bg=palette["shell_bg"], padx=12, pady=12)
        shell.pack(fill="both", expand=True)

        card = tk.Frame(
            dialog,
            bg=palette["card_bg"],
            bd=1,
            relief="solid",
            highlightthickness=1,
            highlightbackground=palette["border"],
            highlightcolor=palette["border"],
        )
        card.place(in_=shell, relx=0.0, rely=0.0, relwidth=1.0, relheight=1.0)

        accent = tk.Frame(card, bg=palette["accent"], height=5)
        accent.pack(fill="x")

        content = tk.Frame(card, bg=palette["card_bg"], padx=18, pady=16)
        content.pack(fill="both", expand=True)

        tk.Label(
            content,
            text=eyebrow_text,
            bg=palette["card_bg"],
            fg=palette["muted_fg"],
            font=("TkDefaultFont", 8, "bold"),
            anchor="center",
        ).pack(fill="x")
        tk.Label(
            content,
            textvariable=message_var,
            bg=palette["card_bg"],
            fg=palette["text_fg"],
            font=("TkDefaultFont", 11, "bold"),
            justify="center",
            anchor="center",
            wraplength=300,
        ).pack(fill="x", pady=(8, 4))
        detail_label = tk.Label(
            content,
            text=detail_text,
            bg=palette["card_bg"],
            fg=palette["muted_fg"],
            font=("TkDefaultFont", 9),
            justify="center",
            anchor="center",
            wraplength=300,
        )
        detail_label.pack(fill="x")
        progress = ttk.Progressbar(content, mode="indeterminate", length=280, style=style_name)
        progress.pack(fill="x", pady=(16, 0))
        progress.start(11)

        _PROCESSING_DIALOG_STATE[dialog] = _ProcessingDialogState(detail_label=detail_label, style_name=style_name)
    else:
        dialog.withdraw()
        dialog.title(title)
        state = _PROCESSING_DIALOG_STATE.get(dialog)
        if state is not None:
            state.detail_label.configure(text=detail_text)

    position_centered_dialog(parent, dialog)
    try:
        dialog.deiconify()
        dialog.lift()
        dialog.attributes("-topmost", True)
        dialog.update()
        dialog.attributes("-topmost", False)
    except tk.TclError:
        LOGGER.debug("Unable to raise processing dialog", exc_info=True)
    return dialog


def close_processing_dialog(parent: tk.Misc, dialog: tk.Toplevel | None) -> None:
    if dialog is None:
        try:
            parent.update_idletasks()
        except tk.TclError:
            LOGGER.debug("Unable to refresh parent while closing processing dialog", exc_info=True)
        return
    _PROCESSING_DIALOG_STATE.pop(dialog, None)
    try:
        dialog.destroy()
    except tk.TclError:
        LOGGER.debug("Unable to close processing dialog", exc_info=True)
    try:
        parent.update_idletasks()
    except tk.TclError:
        LOGGER.debug("Unable to refresh parent after closing processing dialog", exc_info=True)


def position_centered_dialog(parent: tk.Misc, dialog: tk.Toplevel) -> None:
    parent.update_idletasks()
    dialog.update_idletasks()
    width = max(dialog.winfo_reqwidth(), PROCESSING_DIALOG_MIN_WIDTH)
    height = max(dialog.winfo_reqheight(), PROCESSING_DIALOG_MIN_HEIGHT)
    parent_width = max(parent.winfo_width(), parent.winfo_reqwidth(), width)
    parent_height = max(parent.winfo_height(), parent.winfo_reqheight(), height)
    x = parent.winfo_rootx() + max((parent_width - width) // 2, 0)
    y = parent.winfo_rooty() + max((parent_height - height) // 2, 0)
    dialog.geometry(f"{width}x{height}+{x}+{y}")


def _configure_processing_progressbar_style(style: ttk.Style, style_name: str, palette: dict[str, str]) -> None:
    try:
        style.configure(
            style_name,
            thickness=16,
            troughcolor=palette["trough"],
            background=palette["accent"],
            bordercolor=palette["border"],
            lightcolor=palette["accent_light"],
            darkcolor=palette["accent_dark"],
        )
    except tk.TclError:
        LOGGER.debug("Unable to style processing progress bar", exc_info=True)


def _processing_dialog_palette(widget: tk.Misc) -> dict[str, str]:
    style = ttk.Style(widget)
    base_bg = _normalize_color(widget, style.lookup("TFrame", "background"), fallback="#f0f0f0")
    card_bg = _normalize_color(
        widget,
        style.lookup("TEntry", "fieldbackground") or style.lookup("TCombobox", "fieldbackground"),
        fallback="#ffffff",
    )
    text_fg = _normalize_color(widget, style.lookup("TLabel", "foreground"), fallback="#1f1f1f")
    accent = _normalize_color(
        widget,
        style.lookup("Treeview", "selectbackground") or style.lookup("TNotebook.Tab", "background"),
        fallback="#2f7dd1",
    )
    shell_bg = _blend_colors(widget, base_bg, accent, 0.08)
    border = _blend_colors(widget, base_bg, accent, 0.22)
    muted_fg = _blend_colors(widget, text_fg, base_bg, 0.42)
    trough = _blend_colors(widget, base_bg, accent, 0.16)
    accent_light = _blend_colors(widget, accent, card_bg, 0.22)
    accent_dark = _blend_colors(widget, accent, text_fg, 0.28)
    return {
        "shell_bg": shell_bg,
        "card_bg": card_bg,
        "text_fg": text_fg,
        "muted_fg": muted_fg,
        "accent": accent,
        "accent_light": accent_light,
        "accent_dark": accent_dark,
        "trough": trough,
        "border": border,
    }


def _normalize_color(widget: tk.Misc, color: str | None, *, fallback: str) -> str:
    candidate = color or fallback
    try:
        red, green, blue = widget.winfo_rgb(candidate)
    except tk.TclError:
        red, green, blue = widget.winfo_rgb(fallback)
    return f"#{red // 256:02x}{green // 256:02x}{blue // 256:02x}"


def _blend_colors(widget: tk.Misc, first: str, second: str, ratio: float) -> str:
    start_red, start_green, start_blue = widget.winfo_rgb(first)
    end_red, end_green, end_blue = widget.winfo_rgb(second)
    clamped_ratio = max(0.0, min(1.0, ratio))
    red = round((start_red * (1.0 - clamped_ratio)) + (end_red * clamped_ratio))
    green = round((start_green * (1.0 - clamped_ratio)) + (end_green * clamped_ratio))
    blue = round((start_blue * (1.0 - clamped_ratio)) + (end_blue * clamped_ratio))
    return f"#{red // 256:02x}{green // 256:02x}{blue // 256:02x}"


def focus_widget(widget: tk.Misc | None) -> None:
    if widget is None:
        return
    try:
        widget.focus_set()
        widget.focus_force()
    except tk.TclError:
        try:
            widget.focus_set()
        except tk.TclError:
            LOGGER.debug("Unable to focus widget", exc_info=True)


def recalc_form_field6(form, context: str) -> None:
    try:
        form.recalc_field6()
    except tk.TclError:
        LOGGER.debug("Unable to recalculate field6 while %s", context, exc_info=True)


def clear_table_selection(table) -> None:
    try:
        selection = table.selection()
        if selection:
            table.selection_remove(*selection)
    except tk.TclError:
        LOGGER.debug("Unable to clear table selection", exc_info=True)


def restore_table_selection(table, record_id: str | None) -> None:
    try:
        selection = table.selection()
        if selection:
            table.selection_remove(*selection)
        if record_id:
            table.selection_set(record_id)
            table.see(record_id)
    except tk.TclError:
        LOGGER.debug("Unable to restore table selection", exc_info=True)


def focus_record_in_table(table, record_id: str, reload_records) -> None:
    if not table.exists(record_id):
        reload_records()
    if not table.exists(record_id):
        return
    try:
        table.selection_set(record_id)
        table.see(record_id)
    except tk.TclError:
        LOGGER.debug("Unable to focus record %s in the table", record_id, exc_info=True)