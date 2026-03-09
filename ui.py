"""Tkinter UI for gp_data (MVP): input form + table + basic CRUD + CSV export."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from typing import Sequence, Callable
import shutil

from .models import Record
from .data_manager import DataManager, CSVDataManager
from .settings import load_labels, save_labels


class InputForm(ttk.Frame):
    """Encapsulates seven input fields. Labels can be renamed at runtime."""

    def __init__(self, parent, labels: Sequence[str] | None = None, on_rename: Callable[[list[str]], None] | None = None, on_submit: Callable[[], None] | None = None, **kwargs):
        super().__init__(parent, **kwargs)
        default = ["Field 1", "Field 2", "Field 3", "Field 4", "Field 5", "Field 6", "Field 7"]
        self.labels = list(labels or default)
        self.entries: dict[str, ttk.Entry] = {}
        self.on_rename = on_rename
        self.on_submit = on_submit

        for i, lab in enumerate(self.labels, start=1):
            lbl = ttk.Label(self, text=lab)
            lbl.grid(row=i - 1, column=0, sticky="w", padx=4, pady=2)
            ent = ttk.Entry(self)
            # make field6 read-only to prevent manual edits (auto-calculated)
            if i == 6:
                ent.config(state="readonly")
            ent.grid(row=i - 1, column=1, sticky="ew", padx=4, pady=2)
            self.entries[f"field{i}"] = ent

        # read-only computed metrics (not persisted): GP, CASH MARGIN, WITH 70% GP
        self.metrics_entries: dict[str, ttk.Entry] = {}
        metrics = [("GP", "gp"), ("CASH MARGIN", "cash_margin"), ("WITH 70% GP", "gp70")]
        base_row = len(self.labels)
        for j, (label_text, key) in enumerate(metrics, start=1):
            lbl = ttk.Label(self, text=label_text)
            lbl.grid(row=base_row - 1 + j, column=0, sticky="w", padx=4, pady=2)
            ent = ttk.Entry(self, state="readonly")
            ent.grid(row=base_row - 1 + j, column=1, sticky="ew", padx=4, pady=2)
            self.metrics_entries[key] = ent

        # live-autocomplete for field6: update when field3 or field5 change
        # bind key-release so calculation occurs as the user types.
        if "field3" in self.entries and "field5" in self.entries:
            self.entries["field3"].bind("<KeyRelease>", lambda e: (self.recalc_field6(), self.recalc_metrics()))
            self.entries["field5"].bind("<KeyRelease>", lambda e: (self.recalc_field6(), self.recalc_metrics()))
        # also update metrics when cost or menu price change
        if "field6" in self.entries:
            self.entries["field6"].bind("<KeyRelease>", lambda e: self.recalc_metrics())
        if "field7" in self.entries:
            self.entries["field7"].bind("<KeyRelease>", lambda e: self.recalc_metrics())

        # Enter navigation: pressing Enter moves focus to the next input (wraps).
        for ent in self.entries.values():
            ent.bind("<Return>", self._on_enter)

        # live-capitalize first character for field1 and field2 (as you type)
        if "field1" in self.entries:
            self.entries["field1"].bind("<KeyRelease>", lambda e: self._capitalize_field("field1"))
        if "field2" in self.entries:
            self.entries["field2"].bind("<KeyRelease>", lambda e: self._capitalize_field("field2"))

        self.columnconfigure(1, weight=1)

    def get_values(self) -> dict:
        # ensure computed field6 is up-to-date before returning values
        try:
            self.recalc_field6()
        except Exception:
            pass

        out: dict = {}
        for k, e in self.entries.items():
            val = e.get()
            if k == "field6":
                if not val or val.upper() == "N/A":
                    out[k] = None
                else:
                    # strip currency symbol and parse to float for storage
                    s = str(val).replace("£", "").replace(",", "").strip()
                    try:
                        out[k] = float(s)
                    except Exception:
                        out[k] = val
            else:
                out[k] = val
        return out

    def _set_field6_text(self, text: str) -> None:
        """Safely set the text of field6 (respecting readonly state)."""
        ent = self.entries.get("field6")
        if ent is None:
            return
        # temporarily enable if necessary, update, then restore readonly
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
        """Title-case the first non-space character of each word for `field_name` (live)."""
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
            # compute new text preserving leading whitespace
            start_ws = len(txt) - len(stripped)
            new = txt[:start_ws] + titlecased
            # preserve cursor position
            try:
                pos = ent.index(tk.INSERT)
            except Exception:
                pos = len(new)
            ent.delete(0, tk.END)
            ent.insert(0, new)
            try:
                ent.icursor(min(pos, len(new)))
            except Exception:
                pass

    def set_values(self, data: dict) -> None:
        for k, e in self.entries.items():
            e.delete(0, tk.END)
            v = data.get(k)
            if v is not None:
                # ensure field1 displays capitalized
                if k in ("field1", "field2") and isinstance(v, str) and v:
                    v = v.strip()
                    v = v.title()
                e.insert(0, str(v))
        # if field3/field5 are present, ensure field6 reflects computed value
        try:
            self.recalc_field6()
        except Exception:
            pass

    def recalc_field6(self) -> None:
        """Recalculate field6 = field3 / field5 and update the readonly field.

        - If inputs are invalid or division-by-zero, show 'N/A'.
        - This runs live as the user types and is idempotent.
        """
        v3 = self.entries.get("field3").get() if self.entries.get("field3") else None
        v5 = self.entries.get("field5").get() if self.entries.get("field5") else None
        if not v3 or not v5:
            # empty inputs -> clear computed field
            self._set_field6_text("")
            return
        try:
            n3 = float(v3)
            n5 = float(v5)
            if n5 == 0:
                self._set_field6_text("N/A")
                return
            res = n3 / n5
            # currency format with 2 decimals and pound sign
            text = f"\u00A3{res:.2f}"
            self._set_field6_text(text)
        except Exception:
            self._set_field6_text("N/A")
        # update dependent readonly metrics whenever cost changes
        try:
            self.recalc_metrics()
        except Exception:
            pass

    def recalc_metrics(self) -> None:
        """Recalculate read-only metrics (GP, CASH MARGIN, WITH 70% GP).

        Rather than reimplementing the formulas here we delegate to the
        helpers defined in :mod:`gp_data.models` so that the logic stays
        consistent with the underlying record model and is easier to test.
        """
        try:
            vals = self.get_values()
        except Exception:
            vals = {}

        def as_float(k):
            v = vals.get(k)
            try:
                return None if v is None or v == "" else float(v)
            except Exception:
                return None

        cost = as_float('field6')
        menu = as_float('field7')

        # import helpers lazily to avoid circular imports at module import time
        from .models import calculate_gp, calculate_cash_margin, calculate_gp70

        gp_text = ""
        try:
            gp_val = calculate_gp(cost, menu)
            if gp_val is not None:
                gp_text = f"{gp_val * 100:.2f}%"
        except Exception:
            gp_text = ""

        cm_text = ""
        try:
            cm_val = calculate_cash_margin(cost, menu)
            if cm_val is not None:
                cm_text = f"\u00A3{cm_val:.2f}"
        except Exception:
            cm_text = ""

        gp70_text = ""
        try:
            gp70_val = calculate_gp70(cost)
            if gp70_val is not None:
                gp70_text = f"\u00A3{gp70_val:.2f}"
        except Exception:
            gp70_text = ""

        # helper to update a readonly entry safely
        def _update_entry(key: str, text: str) -> None:
            try:
                ent = self.metrics_entries.get(key)
                if ent:
                    prev = str(ent.cget('state'))
                    if prev == 'readonly':
                        ent.config(state='normal')
                    ent.delete(0, tk.END)
                    ent.insert(0, text)
                    if prev == 'readonly':
                        ent.config(state='readonly')
            except Exception:
                pass

        _update_entry('gp', gp_text)
        _update_entry('cash_margin', cm_text)
        _update_entry('gp70', gp70_text)

    def _on_enter(self, event) -> None:
        """Handle Return key: recalc computed fields and move focus to next entry (wraps).

        This method is bound to each Entry's <Return> event and is also callable
        from tests (where we pass a fake event with a `widget` attribute).
        """
        # ensure computed values are up-to-date
        try:
            self.recalc_field6()
        except Exception:
            pass

        widget = getattr(event, "widget", None)
        if widget is None:
            return "break"

        # determine the key name for the widget and focus next
        keys = list(self.entries.keys())
        try:
            idx = next(i for i, (k, w) in enumerate(self.entries.items()) if w is widget)
        except StopIteration:
            return "break"
        next_idx = (idx + 1) % len(keys)
        next_key = keys[next_idx]

        # if we wrapped from the last field back to the first, and a submit
        # callback is provided, treat this as a form submit (Add) instead of
        # just wrapping focus.
        if next_idx == 0 and callable(getattr(self, 'on_submit', None)):
            try:
                self.on_submit()
            except Exception:
                pass
            # still move focus to first field afterwards
        try:
            nxt = self.entries[next_key]
            try:
                nxt.focus_set()
                nxt.focus_force()
            except Exception:
                try:
                    nxt.focus_set()
                except Exception:
                    pass
            # record last focused widget (test-friendly)
            try:
                self._last_focused = nxt
            except Exception:
                pass
            # place cursor at end for convenience
            try:
                nxt.icursor('end')
            except Exception:
                pass
        except Exception:
            pass
        return "break"


    def clear(self) -> None:
        for e in self.entries.values():
            e.delete(0, tk.END)
        # ensure computed field6 is cleared as well
        try:
            self._set_field6_text("")
        except Exception:
            pass

    def rename_fields(self) -> None:
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
            for i, ent in enumerate(edits):
                new = ent.get().strip() or self.labels[i]
                self.labels[i] = new
                # update visible label
                self.grid_slaves(row=i, column=0)[0].config(text=new)
            try:
                save_labels(self.labels)
            except Exception:
                # non-fatal — don't block the UI if settings can't be saved
                pass
            # notify optional listener (will update table headings)
            if callable(self.on_rename):
                try:
                    self.on_rename(self.labels)
                except Exception:
                    pass
            # recalculate field6 in case field3/5 values exist
            try:
                self.recalc_field6()
            except Exception:
                pass
            win.destroy()

        ttk.Button(win, text="Apply", command=apply).grid(row=len(edits), column=0, columnspan=2, pady=6)


class RecordTable(ttk.Treeview):
    """Table-like display using ttk.Treeview.

    The internal `id` field is not displayed. Each Treeview item's `iid` is set
    to the record's `id` so selection/edit/delete can still use the stable id.
    """

    def __init__(self, parent, columns: Sequence[str] | None = None, labels: Sequence[str] | None = None, on_commit: Callable[[str, str, str], None] | None = None, **kwargs):
        # include derived, read-only metric columns in the table
        cols = list(columns or ["field1", "field2", "field3", "field4", "field5", "field6", "field7", "gp", "cash_margin", "gp70"])
        # internal data columns include the hidden `id` followed by visible cols
        self._data_cols = ["id"] + cols
        # visible columns for the Treeview (do NOT include `id`)
        self._cols = cols

        # prepare heading labels corresponding to visible columns
        default_field_labels = ["Field 1", "Field 2", "Field 3", "Field 4", "Field 5", "Field 6", "Field 7", "GP", "CASH MARGIN", "WITH 70% GP"]
        provided_labels = list(labels or default_field_labels)
        heading_labels = provided_labels
        if len(heading_labels) < len(self._cols):
            heading_labels = heading_labels + self._cols[len(heading_labels):]
        self._labels = heading_labels

        # callback called when an inline edit is committed: (record_id, column, value)
        self._on_commit = on_commit

        super().__init__(parent, columns=self._cols, show="headings", **kwargs)
        for idx, c in enumerate(self._cols):
            heading_text = self._labels[idx] if idx < len(self._labels) else c
            # narrower columns for compact numeric fields (fields 3..7 + derived metrics)
            if c in ("field3", "field4", "field5", "field6", "field7", "gp", "cash_margin", "gp70"):
                col_width = 80
                col_anchor = "e"  # right-align numeric values
            elif c in ("field1", "field2"):
                col_width = 140
                col_anchor = "w"  # left-align text
            else:
                col_width = 120
                col_anchor = "w"
            # set both header and cell anchor so headers align with content
            self.heading(c, text=heading_text, anchor=col_anchor)
            self.column(c, width=col_width, anchor=col_anchor)

        # enable inline editing on double-click
        self.bind('<Double-1>', self._on_double_click)

    def update_column_labels(self, labels: Sequence[str]) -> None:
        """Update the visible column headings for the field columns.

        `labels` should be a sequence of labels corresponding to `field1`..`field7`.
        """
        for i, lbl in enumerate(labels):
            if i < len(self._cols):
                col = self._cols[i]
                self._labels[i] = lbl
                try:
                    self.heading(col, text=lbl)
                except Exception:
                    pass

    def copy_selected_id_to_clipboard(self) -> None:
        """Copy the currently-selected record id to the system clipboard.

        This uses the table's toplevel window for clipboard operations so tests
        can call it with a regular `tk.Tk()` root.
        """
        sel = self.get_selected_id()
        if not sel:
            return
        try:
            top = self.winfo_toplevel()
            top.clipboard_clear()
            top.clipboard_append(sel)
        except Exception:
            pass

    # ---- Inline cell editing -------------------------------------------------
    def _on_double_click(self, event) -> None:
        """Start inline edit for the clicked cell (row/column)."""
        try:
            row = self.identify_row(event.y)
            col_id = self.identify_column(event.x)  # returns like '#1'
            if not row or not col_id:
                return
            col_index = int(col_id.lstrip('#')) - 1
            col_name = self._cols[col_index]
            # do not allow editing of computed/read-only columns
            if col_name == 'field6':
                return
            self.start_cell_edit(row, col_name)
        except Exception:
            pass

    def start_cell_edit(self, iid: str, col: str) -> None:
        """Place an Entry widget over the given cell so it can be edited.

        The editor is available as `self._editor` for tests to interact with.
        """
        # ensure any previous editor is destroyed
        try:
            if getattr(self, '_editor', None):
                self._editor.destroy()
        except Exception:
            pass

        # don't allow editing of read-only column
        if col == 'field6':
            return

        # compute bbox and create an Entry overlay
        try:
            col_index = self._cols.index(col)
        except ValueError:
            return
        bbox = self.bbox(iid, column=col)
        # fallback: if bbox isn't available (headless/tests), place a small
        # editor inside the treeview — still allows programmatic testing.
        if not bbox:
            x, y, w, h = 2, 2, 120, 20
        else:
            x, y, w, h = bbox
        # current displayed value (may be formatted)
        cur = self.item(iid)['values'][col_index]
        # if this is a numeric/currency column, prefill editor with raw numeric text
        if col in ("field3", "field6", "field7") and isinstance(cur, str):
            s = cur.replace("£", "").replace(",", "").strip()
            # keep original if stripping fails
            try:
                # format as plain number (no trailing zeros problems)
                cur = str(float(s))
            except Exception:
                pass

        editor = ttk.Entry(self)
        try:
            editor.place(x=x, y=y, width=w, height=h)
        except Exception:
            # last-resort: pack into the treeview container (visible enough for tests)
            editor.pack()
        editor.insert(0, cur)
        editor.focus_set()
        editor.select_range(0, 'end')
        editor.bind('<Return>', lambda e: self._commit_edit())
        editor.bind('<Escape>', lambda e: self._cancel_edit())
        editor.bind('<FocusOut>', lambda e: self._cancel_edit())
        self._editor = editor
        self._editing = (iid, col)

    def _commit_edit(self, event=None) -> None:
        """Commit inline edit: call the commit callback (if provided) and remove editor."""
        try:
            if not getattr(self, '_editor', None) or not getattr(self, '_editing', None):
                return
            iid, col = self._editing
            new_val = self._editor.get()
            # destroy editor first to avoid lingering focus issues
            try:
                self._editor.destroy()
            except Exception:
                pass
            self._editor = None
            self._editing = None
            # callback to parent (GPDataApp) to validate + persist
            if callable(self._on_commit):
                try:
                    self._on_commit(iid, col, new_val)
                except Exception as exc:
                    # parent will show validation error; swallow here
                    print('commit callback error:', exc)
            else:
                # fallback: update displayed value only
                cur_vals = list(self.item(iid)['values'])
                idx = self._cols.index(col)
                cur_vals[idx] = new_val
                self.item(iid, values=cur_vals)
        except Exception:
            pass

    def _cancel_edit(self, event=None) -> None:
        try:
            if getattr(self, '_editor', None):
                self._editor.destroy()
        except Exception:
            pass
        self._editor = None
        self._editing = None

    def load(self, records: Sequence[Record]) -> None:
        self.delete(*self.get_children())
        for r in records:
            self.insert_record(r)

    def _format_display_value(self, col: str, val) -> str:
        """Return a UI-friendly string for a value in column `col`.

        - `field3`, `field6`, and `field7` are formatted as currency with 2 decimals.
        - Floats in other columns are trimmed of excessive precision.
        - None -> empty string.
        """
        if val is None:
            return ""
        # percentage for GP
        if col == 'gp':
            try:
                return f"{float(val) * 100:.2f}%"
            except Exception:
                return str(val)
        # currency-like columns
        if col in ("field3", "field6", "field7", "cash_margin", "gp70"):
            try:
                return f"\u00A3{float(val):.2f}"
            except Exception:
                return str(val)
        if isinstance(val, float):
            s = ("{:.6f}".format(val)).rstrip('0').rstrip('.')
            return s
        return str(val)

    def insert_record(self, record: Record):
        """Insert using record.id as the `iid` and only display visible fields.

        Display values are formatted via _format_display_value so numeric
        columns (Cost/field6) look consistent in the table.
        """
        values = [self._format_display_value(c, getattr(record, c)) for c in self._cols]
        return self.insert('', 'end', iid=record.id, values=values)

    def get_selected_id(self) -> str | None:
        sel = self.selection()
        if not sel:
            return None
        # selection item's iid is the record id
        return sel[0]

    def delete_selected(self) -> None:
        for iid in self.selection():
            self.delete(iid)


class GPDataApp(tk.Tk):
    def __init__(self, storage_path: Path | None = None):
        super().__init__()
        self.title('GP Data Manager')
        # increase width so all columns (including derived metrics) are visible
        self.geometry('1200x520')

        self.data_manager = DataManager(storage_path)
        # keep track of currently displayed records (for filtered export)
        self._displayed_records: list[Record] = []

        container = ttk.Frame(self)
        container.pack(fill='both', expand=True, padx=8, pady=8)

        left = ttk.Frame(container)
        left.pack(side='left', fill='y', padx=(0, 8))
        labels = load_labels()
        self.form = InputForm(left, labels=labels, on_rename=self.on_labels_changed, on_submit=self.on_add)
        self.form.pack(fill='y', expand=False)

        right = ttk.Frame(container)
        right.pack(side='left', fill='both', expand=True)
        self.table = RecordTable(right, labels=labels, on_commit=self._on_table_commit)
        self.table.pack(fill='both', expand=True)

        controls = ttk.Frame(self)
        controls.pack(fill='x', padx=8, pady=6)
        # left-side CRUD buttons
        ttk.Button(controls, text='Add', command=self.on_add).pack(side='left', padx=4)
        ttk.Button(controls, text='Edit selected', command=self.on_edit).pack(side='left', padx=4)
        ttk.Button(controls, text='Delete selected', command=self.on_delete).pack(side='left', padx=4)
        ttk.Button(controls, text='Rename fields', command=self.form.rename_fields).pack(side='left', padx=4)

        # right-side storage controls
        ttk.Button(controls, text='Backfill storage', command=self.on_backfill_csv).pack(side='right', padx=4)
        ttk.Button(controls, text='Manage backups', command=self.on_manage_backups).pack(side='right', padx=4)
        ttk.Button(controls, text='Restore backup', command=self.on_restore_backup).pack(side='right', padx=4)
        ttk.Button(controls, text='Export CSV', command=self.on_export).pack(side='right', padx=4)

        # search UI sits between left and right groups
        self._search_entry = ttk.Entry(controls, width=20)
        # perform search whenever the entry changes (typing/backspace)
        self._search_entry.bind('<KeyRelease>', lambda e: self.on_search())
        ttk.Button(controls, text='Search', command=self.on_search).pack(side='right', padx=4)
        ttk.Button(controls, text='Clear', command=self.on_clear_search).pack(side='right', padx=4)
        self._search_entry.pack(side='right', padx=4)

        # Row context menu (right-click) for convenience: Edit / Delete / Copy ID
        self.row_menu = tk.Menu(self, tearoff=0)
        self.row_menu.add_command(label='Edit', command=self.on_edit)
        self.row_menu.add_command(label='Delete', command=self.on_delete)
        self.row_menu.add_separator()
        self.row_menu.add_command(label='Copy ID', command=self._copy_selected_id_to_clipboard)
        # bind right-click on the table to show the menu and select the row under cursor
        self.table.bind('<Button-3>', self._on_row_right_click)

        self.load_records()

    def load_records(self) -> None:
        records = self.data_manager.load_all()
        # cache what we're showing so export can respect current filter
        self._displayed_records = records
        self.table.load(records)

    def on_search(self) -> None:
        """Filter table rows by type or name containing the query.

        If the query is empty we reload the full set.
        """
        q = self._search_entry.get().strip().lower()
        if not q:
            # reload everything and cache
            records = self.data_manager.load_all()
            self._displayed_records = records
            self.table.load(records)
            return
        records = self.data_manager.load_all()
        filtered = [r for r in records if (r.field1 or "").lower().find(q) != -1 or (r.field2 or "").lower().find(q) != -1]
        self._displayed_records = filtered
        self.table.load(filtered)

    def on_clear_search(self) -> None:
        self._search_entry.delete(0, 'end')
        self.load_records()

    def on_add(self) -> None:
        # ensure computed fields are up-to-date before creating Record
        try:
            self.form.recalc_field6()
        except Exception:
            pass
        data = self.form.get_values()
        try:
            rec = Record(**data)
        except Exception as exc:
            messagebox.showerror('Validation error', str(exc))
            return
        # create a timestamped backup before mutating the CSV (so user can undo)
        try:
            self.data_manager.create_timestamped_backup()
        except Exception:
            pass
        self.data_manager.save(rec)
        self.table.insert_record(rec)
        self.form.clear()

    def on_edit(self) -> None:
        sel_id = self.table.get_selected_id()
        if not sel_id:
            messagebox.showinfo('Select', 'Please select a record to edit.')
            return
        records = self.data_manager.load_all()
        record = next((r for r in records if r.id == sel_id), None)
        if not record:
            messagebox.showerror('Error', 'Record not found')
            return
        # populate form for editing
        self.form.set_values(record.to_dict())

        def apply_edit():
            # ensure computed fields are up-to-date before updating
            try:
                self.form.recalc_field6()
            except Exception:
                pass
            # gather values from the form and validate via Record
            values = self.form.get_values()
            try:
                updated = Record(id=record.id, created_at=record.created_at, **values)
            except Exception as exc:
                messagebox.showerror('Validation error', str(exc))
                return
            self.data_manager.update(record.id, updated)
            self.load_records()
            edit_win.destroy()

        edit_win = tk.Toplevel(self)
        edit_win.title('Edit record')
        ttk.Label(edit_win, text='Make changes in the main form then press Apply.').pack(padx=8, pady=8)
        ttk.Button(edit_win, text='Apply', command=apply_edit).pack(side='left', padx=8, pady=8)
        ttk.Button(edit_win, text='Cancel', command=edit_win.destroy).pack(side='left', padx=8, pady=8)

    def on_delete(self) -> None:
        sel_id = self.table.get_selected_id()
        if not sel_id:
            messagebox.showinfo('Select', 'Please select a record to delete.')
            return
        if messagebox.askyesno('Confirm', 'Delete selected record?'):
            self.data_manager.delete(sel_id)
            self.load_records()

    def on_export(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension='.csv', filetypes=[('CSV files', '*.csv')])
        if not path:
            return
        try:
            # if the table is filtered we only export what is visible
            if self._displayed_records:
                tmp = CSVDataManager(Path(path))
                tmp._write_all(self._displayed_records)
            else:
                self.data_manager.export_csv(Path(path))
            messagebox.showinfo('Export', f'Exported to {path}')
        except Exception as exc:
            messagebox.showerror('Export failed', str(exc))

    def on_backfill_csv(self) -> None:
        """Backfill storage with derived metric columns (creates a backup).

        For SQLite backend this is a no-op, but we still record a backup file.
        """
        if not messagebox.askyesno('Confirm', 'Backfill storage with derived metric columns? This will overwrite the storage and create a backup.'):
            return
        try:
            src = self.data_manager.path
            bak = src.with_name(src.name + '.bak')
            shutil.copyfile(str(src), str(bak))
            count = self.data_manager.backfill_derived()
            messagebox.showinfo('Backfill complete', f'Backfilled {count} rows; backup saved to {bak}')
        except Exception as exc:
            messagebox.showerror('Backfill failed', str(exc))

    def on_restore_backup(self) -> None:
        """Restore storage from the most recent `.bak` file. Creates a pre-restore backup."""
        bak = self.data_manager.path.with_name(self.data_manager.path.name + '.bak')
        if not bak.exists():
            messagebox.showinfo('Restore', 'No backup file found to restore.')
            return
        if not messagebox.askyesno('Confirm', f'Restore from backup ({bak})? This will overwrite the current storage and create a pre-restore backup.'):
            return
        try:
            pre = self.data_manager.restore_backup()
            # reload table from restored CSV
            self.load_records()
            messagebox.showinfo('Restore complete', f'Restored backup; pre-restore saved to {pre}')
        except Exception as exc:
            messagebox.showerror('Restore failed', str(exc))

    def on_manage_backups(self) -> None:
        """Open a dialog to preview, restore, and delete timestamped backups."""
        win = tk.Toplevel(self)
        win.title('Manage Backups')
        win.geometry('720x360')

        left = ttk.Frame(win)
        left.pack(side='left', fill='y', padx=8, pady=8)
        lb = tk.Listbox(left, width=48, height=18)
        lb.pack(side='top', fill='y', expand=True)

        info = ttk.Label(left, text='Select a backup to preview or restore')
        info.pack(side='top', pady=(6, 0))

        right = ttk.Frame(win)
        right.pack(side='left', fill='both', expand=True, padx=8, pady=8)
        preview = tk.Text(right, wrap='none', height=20)
        preview.pack(fill='both', expand=True)

        btn_frame = ttk.Frame(win)
        btn_frame.pack(fill='x', padx=8, pady=6)
        btn_restore = ttk.Button(btn_frame, text='Restore', state='disabled')
        btn_delete = ttk.Button(btn_frame, text='Delete', state='disabled')
        btn_close = ttk.Button(btn_frame, text='Close', command=win.destroy)
        btn_delete.pack(side='right', padx=4)
        btn_restore.pack(side='right', padx=4)
        btn_close.pack(side='right', padx=4)

        # populate listbox
        backups = self.data_manager.list_backups()
        for p in backups:
            lb.insert('end', p.name)

        def _refresh_list():
            lb.delete(0, 'end')
            for p in self.data_manager.list_backups():
                lb.insert('end', p.name)
            preview.delete('1.0', 'end')
            btn_restore.config(state='disabled')
            btn_delete.config(state='disabled')

        def _on_select(evt=None):
            sel = lb.curselection()
            if not sel:
                preview.delete('1.0', 'end')
                btn_restore.config(state='disabled')
                btn_delete.config(state='disabled')
                return
            idx = sel[0]
            name = lb.get(idx)
            path = (self.data_manager.path.parent / 'backups') / name
            # preview first 2000 chars of file
            try:
                s = path.read_text(encoding='utf-8')
                preview.delete('1.0', 'end')
                preview.insert('1.0', s[:2000])
            except Exception as exc:
                preview.delete('1.0', 'end')
                preview.insert('1.0', f'Unable to preview: {exc}')
            btn_restore.config(state='normal')
            btn_delete.config(state='normal')

        def _do_restore():
            sel = lb.curselection()
            if not sel:
                return
            name = lb.get(sel[0])
            path = (self.data_manager.path.parent / 'backups') / name
            if not messagebox.askyesno('Restore', f'Restore from {name}?'):
                return
            try:
                pre = self.data_manager.restore_from_backup(path)
                self.load_records()
                messagebox.showinfo('Restored', f'Restored {name}; pre-restore at {pre}')
                _refresh_list()
            except Exception as exc:
                messagebox.showerror('Restore failed', str(exc))

        def _do_delete():
            sel = lb.curselection()
            if not sel:
                return
            name = lb.get(sel[0])
            path = (self.data_manager.path.parent / 'backups') / name
            if not messagebox.askyesno('Delete', f'Delete backup {name}?'):
                return
            try:
                self.data_manager.delete_backup(path)
                _refresh_list()
            except Exception as exc:
                messagebox.showerror('Delete failed', str(exc))

        lb.bind('<<ListboxSelect>>', _on_select)
        btn_restore.config(command=_do_restore)
        btn_delete.config(command=_do_delete)
        # make dialog modal-ish by grabbing focus
        try:
            win.transient(self)
            win.grab_set()
        except Exception:
            pass
        return win
    def on_labels_changed(self, labels: Sequence[str]) -> None:
        """Called when the input-field labels are renamed in the form UI."""
        try:
            self.table.update_column_labels(labels)
        except Exception:
            pass

    def _on_table_commit(self, record_id: str, col: str, new_value: str) -> None:
        """Handle inline cell edit commits from the table.

        - Validate changes using `Record` so model rules apply.
        - Recompute `field6` when `field3` or `field5` change.
        - Persist using `DataManager.update` and refresh the table row.
        """
        try:
            records = self.data_manager.load_all()
            record = next((r for r in records if r.id == record_id), None)
            if record is None:
                messagebox.showerror('Error', 'Record not found')
                return

            data = record.to_dict()
            # accept the raw new_value (validators will coerce/catch errors)
            data[col] = new_value

            # if price/quantity change, ensure cost recalculated before validation
            if col in ('field3', 'field5'):
                # attempt to parse numeric inputs; leave to validator if not parseable
                try:
                    f3 = float(data.get('field3') or 0)
                    f5 = float(data.get('field5') or 0)
                    if f5:
                        data['field6'] = f3 / f5
                    else:
                        data['field6'] = None
                except Exception:
                    # leave field6 as-is; validation will raise if needed
                    pass

            try:
                updated = Record(**data)
            except Exception as exc:
                messagebox.showerror('Validation error', str(exc))
                return

            # create a timestamped backup before mutating the CSV so single-cell
            # inline edits are recoverable (row-level safety)
            try:
                self.data_manager.create_timestamped_backup()
            except Exception:
                pass

            self.data_manager.update(record_id, updated)
            self.load_records()
        except Exception as exc:
            messagebox.showerror('Error', str(exc))

    def _on_row_right_click(self, event) -> None:
        """Right-click on a table row: select the row under cursor and show menu."""
        try:
            row = self.table.identify_row(event.y)
            if row:
                self.table.selection_set(row)
                self.row_menu.post(event.x_root, event.y_root)
        except Exception:
            pass

    def _copy_selected_id_to_clipboard(self) -> None:
        # delegate to the table implementation (testable without creating a full
        # GPDataApp instance)
        try:
            self.table.copy_selected_id_to_clipboard()
        except Exception:
            pass

    def run(self) -> None:
        self.mainloop()
