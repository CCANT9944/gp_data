from __future__ import annotations
import json
import logging

import tkinter as tk
from datetime import datetime, timezone
from tkinter import messagebox, ttk
from typing import Callable, Sequence

from ..models import calculate_field6
from ..settings import save_labels as save_labels_to_settings


LOGGER = logging.getLogger(__name__)


def _focus_widget(widget: tk.Misc | None) -> None:
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


class InputForm(ttk.Frame):
    """Encapsulates seven input fields. Labels can be renamed at runtime."""

    def __init__(self, parent, labels: Sequence[str] | None = None, on_rename: Callable[[list[str]], None] | None = None, on_submit: Callable[[], None] | None = None, save_labels_callback: Callable[[list[str]], object] | None = None, on_dirty_change: Callable[[bool], None] | None = None, **kwargs):
        super().__init__(parent, **kwargs)
        default = ["Field 1", "Field 2", "Field 3", "Field 4", "Field 5", "Field 6", "Field 7"]
        self.labels = list(labels or default)
        self.entries: dict[str, ttk.Entry] = {}
        self.on_rename = on_rename
        self.on_submit = on_submit
        self._save_labels = save_labels_callback or save_labels_to_settings
        self.on_dirty_change = on_dirty_change
        self.current_record_id: str | None = None
        self._clean_snapshot: dict | None = None
        self._current_change_data: dict = {}

        label_padx = 3
        field_padx = 3
        row_pady = 1

        for i, lab in enumerate(self.labels, start=1):
            lbl = ttk.Label(self, text=lab)
            lbl.grid(row=i - 1, column=0, sticky="w", padx=label_padx, pady=row_pady)
            ent = ttk.Entry(self, width=22)
            if i == 6:
                ent.config(state="readonly")
            ent.grid(row=i - 1, column=1, sticky="ew", padx=field_padx, pady=row_pady)
            self.entries[f"field{i}"] = ent

        self.metrics_entries: dict[str, ttk.Entry] = {}
        metrics = [("GP", "gp"), ("CASH MARGIN", "cash_margin"), ("WITH 70% GP", "gp70")]
        base_row = len(self.labels)
        for j, (label_text, key) in enumerate(metrics, start=1):
            lbl = ttk.Label(self, text=label_text)
            lbl.grid(row=base_row - 1 + j, column=0, sticky="w", padx=label_padx, pady=row_pady)
            ent = ttk.Entry(self, state="readonly", width=22)
            ent.grid(row=base_row - 1 + j, column=1, sticky="ew", padx=field_padx, pady=row_pady)
            self.metrics_entries[key] = ent

        info_row = base_row + len(metrics)
        self.last_numeric_change_var = tk.StringVar(value="No changes recorded")
        self.changes_box = ttk.LabelFrame(self, text="Change history")
        self.changes_box.grid(row=info_row, column=0, columnspan=2, sticky="ew", padx=3, pady=(6, 2))
        self.changes_box.columnconfigure(0, weight=1)
        self.changes_summary_label = ttk.Label(
            self.changes_box,
            textvariable=self.last_numeric_change_var,
            justify="left",
            anchor="w",
            wraplength=260,
        )
        self.changes_summary_label.grid(row=0, column=0, sticky="ew", padx=6, pady=4)
        self.history_button = ttk.Button(self.changes_box, text="View full history", command=self.open_change_history)
        self.history_button.grid(row=1, column=0, sticky="e", padx=6, pady=(0, 6))

        if "field3" in self.entries and "field5" in self.entries:
            self.entries["field3"].bind("<KeyRelease>", lambda e: (self.recalc_field6(), self.recalc_metrics()))
            self.entries["field5"].bind("<KeyRelease>", lambda e: (self.recalc_field6(), self.recalc_metrics()))
        if "field6" in self.entries:
            self.entries["field6"].bind("<KeyRelease>", lambda e: self.recalc_metrics())
        if "field7" in self.entries:
            self.entries["field7"].bind("<KeyRelease>", lambda e: self.recalc_metrics())

        for ent in self.entries.values():
            ent.bind("<Return>", self._on_enter)

        if "field1" in self.entries:
            self.entries["field1"].bind("<KeyRelease>", lambda e: self._capitalize_field("field1"))
        if "field2" in self.entries:
            self.entries["field2"].bind("<KeyRelease>", lambda e: self._capitalize_field("field2"))

        for key, ent in self.entries.items():
            if key == "field6":
                continue
            ent.bind("<KeyRelease>", lambda e: self._notify_dirty_state(), add="+")

        self.columnconfigure(1, weight=1)
        self._mark_clean()

    def _snapshot_values(self) -> dict:
        return self.get_values()

    def _mark_clean(self) -> None:
        self._clean_snapshot = self._snapshot_values()

    def is_dirty(self) -> bool:
        if self._clean_snapshot is None:
            return False
        return self._snapshot_values() != self._clean_snapshot

    def _notify_dirty_state(self) -> None:
        if callable(self.on_dirty_change):
            self.on_dirty_change(self.is_dirty())

    def _set_changes_text(self, text: str) -> None:
        self.last_numeric_change_var.set(text)

    def _history_entries(self, data: dict) -> list[dict]:
        history = data.get("numeric_change_history")
        if isinstance(history, str):
            try:
                history = json.loads(history)
            except json.JSONDecodeError:
                history = []
        return history if isinstance(history, list) else []

    def _build_change_history_text(self, data: dict, limit: int | None = 4) -> str:
        item_lines: list[str] = []
        first_value = (data.get("field1") or "").strip()
        second_value = (data.get("field2") or "").strip()
        if first_value:
            item_lines.append(f"{self.labels[0]}: {first_value}")
        if second_value:
            item_lines.append(f"{self.labels[1]}: {second_value}")

        history = self._history_entries(data)
        if limit is not None:
            history = history[-limit:]

        history_lines: list[str] = []
        for entry in reversed(history):
            field_name = entry.get("field_name") if isinstance(entry, dict) else None
            if not field_name:
                continue
            label = self._field_label_for(field_name)
            from_value = self._format_money(entry.get("from_value") if isinstance(entry, dict) else None)
            to_value = self._format_money(entry.get("to_value") if isinstance(entry, dict) else None)
            changed_at = self._format_changed_at(entry.get("changed_at") if isinstance(entry, dict) else None)
            history_lines.extend([
                f"{label} changed",
                f"{from_value} -> {to_value}",
                changed_at,
                "",
            ])
        if history_lines and history_lines[-1] == "":
            history_lines.pop()

        field_name = data.get("last_numeric_field")
        if not field_name and not history_lines:
            lines = item_lines or []
            if lines:
                lines.append("")
            lines.append("No changes recorded")
            return "\n".join(lines)

        lines = item_lines or []
        if lines:
            lines.append("")
        if history_lines:
            lines.extend(history_lines)
        else:
            label = self._field_label_for(field_name)
            from_value = self._format_money(data.get("last_numeric_from"))
            to_value = self._format_money(data.get("last_numeric_to"))
            changed_at = self._format_changed_at(data.get("last_numeric_changed_at"))
            lines.extend([
                f"{label} changed",
                f"{from_value} -> {to_value}",
                changed_at,
            ])
        return "\n".join(lines)

    def open_change_history(self) -> tk.Toplevel:
        history_text = self._build_change_history_text(self._current_change_data, limit=None)

        win = tk.Toplevel(self)
        win.title("Full change history")
        win.geometry("520x420")

        text = tk.Text(win, wrap="word")
        text.pack(fill="both", expand=True, padx=10, pady=10)
        text.insert("1.0", history_text)
        text.config(state="disabled")

        ttk.Button(win, text="Close", command=win.destroy).pack(anchor="e", padx=10, pady=(0, 10))
        return win

    def _safe_recalc_field6(self, context: str) -> None:
        try:
            self.recalc_field6()
        except tk.TclError:
            LOGGER.debug("Unable to recalculate field6 while %s", context, exc_info=True)

    def _safe_get_values_for_metrics(self) -> dict:
        try:
            return self.get_values(recalculate=False)
        except tk.TclError:
            LOGGER.debug("Unable to read values while recalculating metrics", exc_info=True)
            return {}

    def _safe_recalc_metrics(self) -> None:
        try:
            self.recalc_metrics()
        except tk.TclError:
            LOGGER.debug("Unable to refresh derived metrics", exc_info=True)

    def _cursor_index_or_fallback(self, entry: ttk.Entry, fallback: int, *, field_name: str | None = None) -> int:
        try:
            return int(entry.index(tk.INSERT))
        except tk.TclError:
            if field_name is not None:
                LOGGER.debug("Unable to read cursor position while capitalizing %s", field_name, exc_info=True)
            return fallback

    def _set_cursor_safely(self, entry: ttk.Entry, position, *, context: str) -> None:
        try:
            entry.icursor(position)
        except tk.TclError:
            LOGGER.debug("Unable to %s", context, exc_info=True)

    def get_values(self, recalculate: bool = True) -> dict:
        if recalculate:
            self._safe_recalc_field6("reading form values")

        out: dict = {}
        for key, entry in self.entries.items():
            val = entry.get()
            if key == "field6":
                if not val or val.upper() == "N/A":
                    out[key] = None
                else:
                    s = str(val).replace("£", "").replace(",", "").strip()
                    try:
                        out[key] = float(s)
                    except (TypeError, ValueError):
                        out[key] = val
            else:
                out[key] = val
        return out

    def _set_field6_text(self, text: str) -> None:
        ent = self.entries.get("field6")
        if ent is None:
            return
        prev_state = str(ent.cget("state"))
        try:
            if prev_state == "readonly":
                ent.config(state="normal")
            ent.delete(0, tk.END)
            ent.insert(0, text)
        finally:
            if prev_state == "readonly":
                ent.config(state="readonly")

    def _capitalize_field(self, field_name: str) -> None:
        ent = self.entries.get(field_name)
        if ent is None:
            return
        txt = ent.get()
        if not txt:
            return
        stripped = txt.lstrip()
        if not stripped:
            return
        titlecased = stripped.title()
        if stripped != titlecased:
            start_ws = len(txt) - len(stripped)
            new = txt[:start_ws] + titlecased
            pos = self._cursor_index_or_fallback(ent, len(new), field_name=field_name)
            ent.delete(0, tk.END)
            ent.insert(0, new)
            self._set_cursor_safely(
                ent,
                min(pos, len(new)),
                context=f"restore cursor position while capitalizing {field_name}",
            )

    def _field_label_for(self, field_name: str | None) -> str:
        if not field_name or not field_name.startswith("field"):
            return "Unknown field"
        try:
            idx = int(field_name[5:]) - 1
        except ValueError:
            return field_name
        if 0 <= idx < len(self.labels):
            return self.labels[idx]
        return field_name

    def _format_money(self, value) -> str:
        if value is None or value == "":
            return "empty"
        try:
            return f"£{float(value):.2f}"
        except (TypeError, ValueError):
            return str(value)

    def _format_changed_at(self, value) -> str:
        if not value:
            return "unknown time"
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value)
            except ValueError:
                return value
        if isinstance(value, datetime):
            if value.tzinfo is not None:
                value = value.astimezone(timezone.utc)
                return value.strftime("%Y-%m-%d %H:%M:%S UTC")
            return value.strftime("%Y-%m-%d %H:%M:%S")
        return str(value)

    def _set_last_numeric_change(self, data: dict) -> None:
        self._current_change_data = dict(data)
        self._set_changes_text(self._build_change_history_text(data))

    def set_values(self, data: dict) -> None:
        self.current_record_id = data.get("id")
        for key, entry in self.entries.items():
            entry.delete(0, tk.END)
            val = data.get(key)
            if val is not None:
                if key in ("field1", "field2") and isinstance(val, str) and val:
                    val = val.strip().title()
                entry.insert(0, str(val))
        self._set_last_numeric_change(data)
        self._safe_recalc_field6("loading record values")
        self._mark_clean()
        self._notify_dirty_state()

    def recalc_field6(self) -> None:
        v3 = self.entries.get("field3").get() if self.entries.get("field3") else None
        v5 = self.entries.get("field5").get() if self.entries.get("field5") else None
        if not v3 or not v5:
            self._set_field6_text("")
            return
        value = calculate_field6(v3, v5)
        if value is None:
            self._set_field6_text("N/A")
        else:
            self._set_field6_text(f"\u00A3{value:.2f}")
        self._safe_recalc_metrics()

    def recalc_metrics(self) -> None:
        vals = self._safe_get_values_for_metrics()

        def as_float(key):
            val = vals.get(key)
            try:
                return None if val is None or val == "" else float(val)
            except (TypeError, ValueError):
                return None

        cost = as_float("field6")
        menu = as_float("field7")

        from ..models import calculate_cash_margin, calculate_gp, calculate_gp70

        gp_val = calculate_gp(cost, menu)
        gp_text = f"{gp_val * 100:.2f}%" if gp_val is not None else ""

        cm_val = calculate_cash_margin(cost, menu)
        cm_text = f"\u00A3{cm_val:.2f}" if cm_val is not None else ""

        gp70_val = calculate_gp70(cost)
        gp70_text = f"\u00A3{gp70_val:.2f}" if gp70_val is not None else ""

        def _update_entry(key: str, text: str) -> None:
            try:
                ent = self.metrics_entries.get(key)
                if ent:
                    prev = str(ent.cget("state"))
                    if prev == "readonly":
                        ent.config(state="normal")
                    ent.delete(0, tk.END)
                    ent.insert(0, text)
                    if prev == "readonly":
                        ent.config(state="readonly")
            except tk.TclError:
                LOGGER.debug("Unable to update derived metric %s", key, exc_info=True)

        _update_entry("gp", gp_text)
        _update_entry("cash_margin", cm_text)
        _update_entry("gp70", gp70_text)

    def _on_enter(self, event) -> None:
        self._safe_recalc_field6("handling the Enter key")

        widget = getattr(event, "widget", None)
        if widget is None:
            return "break"

        keys = list(self.entries.keys())
        try:
            idx = next(i for i, (_, entry) in enumerate(self.entries.items()) if entry is widget)
        except StopIteration:
            return "break"
        next_idx = (idx + 1) % len(keys)
        next_key = keys[next_idx]

        if next_idx == 0 and callable(getattr(self, "on_submit", None)):
            try:
                self.on_submit()
            except (RuntimeError, tk.TclError) as exc:
                LOGGER.exception("Form submit callback failed")
                messagebox.showerror(
                    "Submit failed",
                    f"Could not submit the form.\n\nReason: {exc}",
                    parent=self.winfo_toplevel(),
                )
                _focus_widget(widget)
                self._last_focused = widget
                return "break"
        nxt = self.entries.get(next_key)
        if nxt is None:
            return "break"
        _focus_widget(nxt)
        self._last_focused = nxt
        self._set_cursor_safely(nxt, "end", context=f"move cursor to the end of {next_key}")
        return "break"

    def clear(self) -> None:
        self.current_record_id = None
        for entry in self.entries.values():
            entry.delete(0, tk.END)
        self._set_changes_text("No changes recorded")
        self._set_field6_text("")
        self._current_change_data = {}
        self._mark_clean()
        self._notify_dirty_state()

    def _apply_field_labels_to_form(self, labels: Sequence[str]) -> None:
        for index, label in enumerate(labels):
            self.grid_slaves(row=index, column=0)[0].config(text=label)

    def rename_fields(self) -> tk.Toplevel:
        win = tk.Toplevel(self)
        win.title("Rename fields")
        edits: list[ttk.Entry] = []
        for i, label in enumerate(self.labels, start=1):
            ttk.Label(win, text=f"Field {i}").grid(row=i - 1, column=0, padx=4, pady=2)
            ent = ttk.Entry(win)
            ent.insert(0, label)
            ent.grid(row=i - 1, column=1, padx=4, pady=2, sticky="ew")
            edits.append(ent)

        def apply():
            original_labels = list(self.labels)
            updated_labels = [ent.get().strip() or self.labels[i] for i, ent in enumerate(edits)]

            try:
                self._save_labels(updated_labels)
            except (OSError, TypeError, ValueError) as exc:
                LOGGER.warning("Unable to persist renamed field labels", exc_info=True)
                messagebox.showerror(
                    "Rename failed",
                    f"Could not save renamed field labels.\n\nReason: {exc}",
                    parent=win,
                )
                return

            if callable(self.on_rename):
                try:
                    self.on_rename(updated_labels)
                except Exception as exc:
                    LOGGER.exception("Rename callback failed")
                    try:
                        self._save_labels(original_labels)
                    except (OSError, TypeError, ValueError):
                        LOGGER.warning("Unable to roll back renamed field labels after callback failure", exc_info=True)
                    messagebox.showerror(
                        "Rename failed",
                        f"Could not apply renamed field labels.\n\nReason: {exc}",
                        parent=win,
                    )
                    return

            self.labels = list(updated_labels)
            self._apply_field_labels_to_form(self.labels)
            self._safe_recalc_field6("renaming labels")
            win.destroy()

        ttk.Button(win, text="Apply", command=apply).grid(row=len(edits), column=0, columnspan=2, pady=6)
        return win