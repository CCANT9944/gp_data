from __future__ import annotations

import logging
import tkinter as tk
from tkinter import messagebox, ttk

from ..formulas import get_active_formula_expressions, set_active_formula_expressions, validate_formula_expressions
from ..settings import SettingsStore
from .form import InputForm
from .formula_explanation import build_formula_panel_text, build_formula_settings_overview


LOGGER = logging.getLogger(__name__)


class _FormulaDisplayController:
    def __init__(
        self,
        owner: tk.Misc,
        settings: SettingsStore,
        form: InputForm,
        table,
        panel: ttk.LabelFrame,
        panel_text: tk.Text,
        refresh_record_view,
        warn_settings_save_failure,
    ) -> None:
        self._owner = owner
        self._settings = settings
        self._form = form
        self._table = table
        self._panel = panel
        self._panel_text = panel_text
        self._refresh_record_view = refresh_record_view
        self._warn_settings_save_failure = warn_settings_save_failure
        self._panel_visible = bool(self._settings.load_show_formula_panel())
        self.set_panel_visible(self._panel_visible, persist=False)
        self.refresh()

    def _refresh_after_formula_change(self) -> None:
        current_record_id = self._form.current_record_id
        self._refresh_record_view()
        if current_record_id and self._table.exists(current_record_id):
            try:
                self._table.selection_set(current_record_id)
            except tk.TclError:
                LOGGER.debug("Unable to restore table selection after formula change", exc_info=True)
        try:
            self._form.recalc_field6()
        except tk.TclError:
            LOGGER.debug("Unable to recalculate form values after formula change", exc_info=True)
        self.refresh()

    def _set_panel_text(self, text: str) -> None:
        previous_state = str(self._panel_text.cget("state"))
        try:
            if previous_state == "disabled":
                self._panel_text.configure(state="normal")
            self._panel_text.delete("1.0", "end")
            self._panel_text.insert("1.0", text)
        finally:
            if previous_state == "disabled":
                self._panel_text.configure(state="disabled")

    def refresh(self) -> None:
        self._set_panel_text(build_formula_panel_text(self._form.get_values(recalculate=False), self._form.labels))

    def on_labels_changed(self) -> None:
        self.refresh()

    def set_panel_visible(self, show_panel: bool, *, persist: bool = True) -> None:
        self._panel_visible = bool(show_panel)
        if self._panel_visible:
            if not self._panel.winfo_manager():
                self._panel.pack(fill="x", expand=False, pady=(8, 0))
            self.refresh()
        else:
            if self._panel.winfo_manager():
                self._panel.pack_forget()

        if not persist:
            return
        try:
            self._settings.save_show_formula_panel(self._panel_visible)
        except (OSError, TypeError, ValueError) as exc:
            LOGGER.warning("Unable to persist formula panel visibility", exc_info=True)
            self._warn_settings_save_failure("the formula panel visibility", exc)

    def on_manage_formula_settings(self) -> None:
        win = tk.Toplevel(self._owner)
        win.title("Formula settings")
        win.geometry("680x560")

        body = ttk.Frame(win)
        body.pack(fill="both", expand=True, padx=10, pady=10)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(2, weight=1)

        show_panel_var = tk.BooleanVar(value=self._panel_visible)
        ttk.Checkbutton(
            body,
            text="Show calculation details below the main table",
            variable=show_panel_var,
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        formulas_frame = ttk.LabelFrame(body, text="Formula expressions")
        formulas_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        formulas_frame.columnconfigure(1, weight=1)

        current_expressions = get_active_formula_expressions()
        formula_labels = {
            "field6": "Field 6 expression",
            "gp": "GP expression",
            "cash_margin": "Cash margin expression",
            "gp70": "WITH 70% GP expression",
        }
        formula_entries: dict[str, ttk.Entry] = {}
        for row_index, formula_key in enumerate(("field6", "gp", "cash_margin", "gp70")):
            ttk.Label(formulas_frame, text=formula_labels[formula_key]).grid(
                row=row_index,
                column=0,
                sticky="w",
                padx=(8, 6),
                pady=4,
            )
            entry = ttk.Entry(formulas_frame)
            entry.grid(row=row_index, column=1, sticky="ew", padx=(0, 8), pady=4)
            entry.insert(0, current_expressions[formula_key])
            formula_entries[formula_key] = entry

        hint = ttk.Label(
            formulas_frame,
            text="Use stable field names: field3, field5, field6, field7. Allowed syntax: numbers, parentheses, +, -, *, /.",
            justify="left",
            anchor="w",
        )
        hint.grid(row=4, column=0, columnspan=2, sticky="ew", padx=8, pady=(4, 8))

        overview = tk.Text(body, height=14, wrap="word")
        overview.grid(row=2, column=0, sticky="nsew")

        def refresh_overview(_event=None) -> None:
            preview_expressions = {
                formula_key: entry.get().strip() or current_expressions[formula_key]
                for formula_key, entry in formula_entries.items()
            }
            overview.configure(state="normal")
            overview.delete("1.0", "end")
            overview.insert("1.0", build_formula_settings_overview(self._form.labels, preview_expressions))
            overview.configure(state="disabled")

        for entry in formula_entries.values():
            entry.bind("<KeyRelease>", refresh_overview, add="+")

        refresh_overview()
        overview.configure(state="disabled")

        buttons = ttk.Frame(win)
        buttons.pack(fill="x", padx=10, pady=(0, 10))

        def apply_settings() -> None:
            raw_expressions = {formula_key: entry.get() for formula_key, entry in formula_entries.items()}
            try:
                validated_expressions = validate_formula_expressions(raw_expressions)
            except ValueError as exc:
                messagebox.showerror(
                    "Formula settings",
                    f"Could not apply the formula settings.\n\nReason: {exc}",
                    parent=win,
                )
                return

            set_active_formula_expressions(validated_expressions)
            self._refresh_after_formula_change()

            try:
                self._settings.save_formula_expressions(validated_expressions)
            except (OSError, TypeError, ValueError) as exc:
                LOGGER.warning("Unable to persist formula expressions", exc_info=True)
                self._warn_settings_save_failure("the formula settings", exc)

            self.set_panel_visible(show_panel_var.get())
            win.destroy()

        ttk.Button(buttons, text="Apply", command=apply_settings).pack(side="right", padx=(4, 0))
        ttk.Button(buttons, text="Close", command=win.destroy).pack(side="right")

        try:
            win.transient(self._owner.winfo_toplevel())
            win.grab_set()
        except tk.TclError:
            LOGGER.debug("Unable to make formula settings dialog modal", exc_info=True)

        self._owner.wait_window(win)
