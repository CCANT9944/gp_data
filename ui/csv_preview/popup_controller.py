from __future__ import annotations

import queue
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .pipeline import _PreviewFilterState


@dataclass(frozen=True)
class _HeaderFilterOptionsResolvedUpdate:
    request_token: int
    column_index: int
    options: list[str]


@dataclass(frozen=True)
class _HeaderFilterOptionsErrorUpdate:
    request_token: int
    column_index: int
    error: Exception


_HeaderFilterOptionsMessage = _HeaderFilterOptionsResolvedUpdate | _HeaderFilterOptionsErrorUpdate


class _PreviewPopupExportControllerBase:
    def __init__(self, owner) -> None:
        self._owner = owner
        self._header_filter_popup_value = tk.StringVar(value="")
        self._header_filter_popup: tk.Toplevel | None = None
        self._header_filter_popup_column_index: int | None = None
        self._header_filter_popup_search_var: tk.StringVar | None = None
        self._header_filter_popup_listbox: tk.Listbox | None = None
        self._header_filter_popup_empty_var: tk.StringVar | None = None
        self._header_filter_popup_options: list[str] = []
        self._header_filter_popup_casefolded_options: list[str] = []
        self._header_filter_popup_filtered_options: list[str] = []
        self._header_filter_popup_loading = False
        self._header_filter_options_request_token = 0
        self._header_filter_options_queue: queue.Queue[_HeaderFilterOptionsMessage] = queue.Queue()
        self._header_filter_options_polling = False

    @property
    def popup(self) -> tk.Toplevel | None:
        return self._header_filter_popup

    def _popup_width(self) -> int:
        raise NotImplementedError

    def _popup_height(self) -> int:
        raise NotImplementedError

    def _popup_list_height(self) -> int:
        raise NotImplementedError

    def _prepare_export_directory(self, source_path: Path) -> Path:
        raise NotImplementedError

    def _default_export_path(self, source_path: Path) -> Path:
        raise NotImplementedError

    def _paths_match(self, first: Path, second: Path) -> bool:
        raise NotImplementedError

    def _write_export(self, dest_path: Path, headers: list[str], rows) -> None:
        raise NotImplementedError

    def _filter_label(self, header: str, index: int) -> str:
        raise NotImplementedError

    def _compact_filter_popup_label(self, value: str) -> str:
        raise NotImplementedError

    def _widget_descends_from(self, widget: tk.Misc | None, ancestor: tk.Misc | None) -> bool:
        raise NotImplementedError

    def export_current_view_as_csv(self) -> None:
        data = self._owner._data
        view_state = self._owner._view_state
        export_dir = self._prepare_export_directory(data.path)
        suggested_path = export_dir / self._default_export_path(data.path).name
        raw_path = filedialog.asksaveasfilename(
            title="Save CSV As",
            initialdir=str(export_dir),
            initialfile=suggested_path.name,
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not raw_path:
            return

        destination = Path(raw_path)
        if self._paths_match(destination, data.path):
            messagebox.showerror(
                "Save CSV As",
                "Choose a different destination file. The original CSV will not be modified.",
            )
            return

        headers = [data.headers[index] for index in view_state.visible_column_indices]
        rows = (
            tuple(row[index] for index in view_state.visible_column_indices)
            for row in self._owner._pipeline.iter_rows(self._owner._current_filter_state())
        )
        try:
            self._write_export(destination, headers, rows)
        except OSError as exc:
            messagebox.showerror("Save CSV As failed", f"Could not create the new CSV file.\n\nReason: {exc}")
            return

        messagebox.showinfo(
            "Save CSV As",
            f"Saved preview to {destination}.\n\nThe original CSV was not changed.",
        )

    def show_header_filter_popup(self, column_index: int, x_root: int, y_root: int) -> None:
        filter_state = self._owner._current_filter_state()
        options = self._owner._pipeline.cached_header_filter_options(filter_state, column_index)
        self.destroy_header_filter_popup()

        popup = tk.Toplevel(self._owner._win)
        popup.title(self._filter_label(self._owner._data.headers[column_index], column_index))
        popup.transient(self._owner._win)
        popup.resizable(False, False)

        screen_width = popup.winfo_screenwidth()
        screen_height = popup.winfo_screenheight()
        left = max(0, min(x_root, screen_width - self._popup_width()))
        top = max(0, min(y_root, screen_height - self._popup_height()))
        popup.geometry(f"{self._popup_width()}x{self._popup_height()}+{left}+{top}")

        self._header_filter_popup = popup
        self._header_filter_popup_column_index = column_index
        self._header_filter_popup_options = list(options or [])
        self._header_filter_popup_casefolded_options = [option.casefold() for option in self._header_filter_popup_options]
        self._header_filter_popup_filtered_options = []
        self._header_filter_popup_search_var = tk.StringVar(value="")
        self._header_filter_popup_empty_var = tk.StringVar(value="")
        self._header_filter_popup_loading = options is None

        container = ttk.Frame(popup, padding=8)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(2, weight=1)

        ttk.Label(container, text="Search").grid(row=0, column=0, sticky="w")
        search_entry = ttk.Entry(container, textvariable=self._header_filter_popup_search_var, width=28)
        search_entry.grid(row=1, column=0, sticky="ew", pady=(4, 8))

        list_frame = ttk.Frame(container)
        list_frame.grid(row=2, column=0, sticky="nsew")
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        listbox = tk.Listbox(list_frame, exportselection=False, height=self._popup_list_height())
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=listbox.yview)
        listbox.configure(yscrollcommand=scrollbar.set)
        listbox.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        self._header_filter_popup_listbox = listbox

        empty_label = ttk.Label(container, textvariable=self._header_filter_popup_empty_var, anchor="w")
        empty_label.grid(row=3, column=0, sticky="ew", pady=(6, 0))

        numeric_sort = self._owner._pipeline.is_numeric_sort_column(column_index)
        ascending_label = "Sort low to high" if numeric_sort else "Sort A to Z"
        descending_label = "Sort high to low" if numeric_sort else "Sort Z to A"

        sort_controls = ttk.Frame(container)
        sort_controls.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(
            sort_controls,
            text=ascending_label,
            command=lambda: self._owner.set_sort(column_index, descending=False),
        ).pack(side="left")
        ttk.Button(
            sort_controls,
            text=descending_label,
            command=lambda: self._owner.set_sort(column_index, descending=True),
        ).pack(side="left", padx=(6, 0))
        ttk.Button(sort_controls, text="Clear sort", command=self._owner.clear_sort).pack(side="right")

        button_row = ttk.Frame(container)
        button_row.grid(row=5, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(button_row, text="Clear filter", command=self._clear_header_filter_popup_filter).pack(side="right")
        ttk.Button(button_row, text="Apply", command=self._apply_selected_header_filter_option).pack(side="right", padx=(0, 6))

        if self._owner._view_state.header_filter_column_index != column_index:
            self._header_filter_popup_value.set("")

        popup.bind("<Destroy>", self._on_header_filter_popup_destroy, add="+")
        popup.bind("<Escape>", lambda _event: self.destroy_header_filter_popup(), add="+")
        widgets_for_focus = [popup, container, search_entry, listbox, empty_label, button_row, sort_controls]
        for widget in widgets_for_focus:
            widget.bind("<FocusOut>", self._schedule_header_filter_popup_focus_check, add="+")

        listbox.bind("<Double-Button-1>", self._on_header_filter_popup_listbox_activate, add="+")
        listbox.bind("<Return>", self._on_header_filter_popup_listbox_activate, add="+")
        search_entry.bind("<Return>", self._on_header_filter_popup_search_submit, add="+")

        self._header_filter_popup_search_var.trace_add("write", self._refresh_header_filter_popup_options)
        self._refresh_header_filter_popup_options()
        if options is None:
            self._start_header_filter_options_refresh(column_index, filter_state)
        search_entry.focus_set()

    def _start_header_filter_options_refresh(self, column_index: int, filter_state: _PreviewFilterState) -> None:
        self._header_filter_options_request_token += 1
        request_token = self._header_filter_options_request_token
        worker = threading.Thread(
            target=self._load_header_filter_options_in_background,
            args=(request_token, column_index, filter_state),
            daemon=True,
        )
        worker.start()
        if not self._header_filter_options_polling:
            self._header_filter_options_polling = True
            self._owner._win.after(25, self._poll_header_filter_options)

    def _load_header_filter_options_in_background(
        self,
        request_token: int,
        column_index: int,
        filter_state: _PreviewFilterState,
    ) -> None:
        try:
            options = self._owner._pipeline.resolve_header_filter_options(filter_state, column_index)
            self._header_filter_options_queue.put(
                _HeaderFilterOptionsResolvedUpdate(
                    request_token=request_token,
                    column_index=column_index,
                    options=options,
                )
            )
        except Exception as exc:
            self._header_filter_options_queue.put(
                _HeaderFilterOptionsErrorUpdate(
                    request_token=request_token,
                    column_index=column_index,
                    error=exc,
                )
            )

    def _poll_header_filter_options(self) -> None:
        if not self._owner._win.winfo_exists():
            return

        while True:
            try:
                message = self._header_filter_options_queue.get_nowait()
            except queue.Empty:
                break

            if message.request_token != self._header_filter_options_request_token:
                continue
            popup = self._header_filter_popup
            if popup is None or not popup.winfo_exists() or self._header_filter_popup_column_index != message.column_index:
                continue

            self._header_filter_popup_loading = False
            if isinstance(message, _HeaderFilterOptionsErrorUpdate):
                if self._header_filter_popup_empty_var is not None:
                    self._header_filter_popup_empty_var.set(f"Could not load values: {message.error}")
                continue

            self._header_filter_popup_options = list(message.options)
            self._header_filter_popup_casefolded_options = [option.casefold() for option in self._header_filter_popup_options]
            self._refresh_header_filter_popup_options()

        if self._header_filter_popup_loading or not self._header_filter_options_queue.empty():
            self._owner._win.after(25, self._poll_header_filter_options)
            return
        self._header_filter_options_polling = False

    def _refresh_header_filter_popup_options(self, *_args) -> None:
        listbox = self._header_filter_popup_listbox
        search_var = self._header_filter_popup_search_var
        empty_var = self._header_filter_popup_empty_var
        if listbox is None or search_var is None or empty_var is None:
            return

        if self._header_filter_popup_loading:
            self._header_filter_popup_filtered_options = []
            listbox.delete(0, "end")
            empty_var.set("Loading values...")
            return

        query = search_var.get().strip().casefold()
        if query:
            filtered_options = [
                option
                for option, casefolded_option in zip(
                    self._header_filter_popup_options,
                    self._header_filter_popup_casefolded_options,
                )
                if query in casefolded_option
            ]
        else:
            filtered_options = list(self._header_filter_popup_options)

        self._header_filter_popup_filtered_options = filtered_options
        listbox.delete(0, "end")
        for option in filtered_options:
            listbox.insert("end", "(blank)" if not option else self._compact_filter_popup_label(option))

        selected_value = self._header_filter_popup_value.get()
        if selected_value and selected_value in filtered_options:
            selected_index = filtered_options.index(selected_value)
            listbox.selection_set(selected_index)
            listbox.see(selected_index)

        if filtered_options:
            empty_var.set("")
        else:
            empty_var.set("No matching values" if query else "No values available")

    def _apply_selected_header_filter_option(self) -> None:
        column_index = self._header_filter_popup_column_index
        listbox = self._header_filter_popup_listbox
        if column_index is None or listbox is None:
            return
        selection = listbox.curselection()
        if not selection:
            return
        selected_index = selection[0]
        if selected_index < 0 or selected_index >= len(self._header_filter_popup_filtered_options):
            return
        self._owner.set_header_filter(column_index, self._header_filter_popup_filtered_options[selected_index])
        self.destroy_header_filter_popup()

    def _clear_header_filter_popup_filter(self) -> None:
        self._owner.clear_header_filter()

    def _on_header_filter_popup_listbox_activate(self, _event) -> str:
        self._apply_selected_header_filter_option()
        return "break"

    def _on_header_filter_popup_search_submit(self, _event) -> str:
        listbox = self._header_filter_popup_listbox
        if listbox is None:
            return "break"
        if not listbox.curselection() and self._header_filter_popup_filtered_options:
            listbox.selection_set(0)
            listbox.see(0)
        self._apply_selected_header_filter_option()
        return "break"

    def _schedule_header_filter_popup_focus_check(self, _event=None) -> None:
        if self._header_filter_popup is None:
            return
        self._owner._win.after_idle(self._close_header_filter_popup_if_focus_lost)

    def _close_header_filter_popup_if_focus_lost(self) -> None:
        popup = self._header_filter_popup
        if popup is None or not popup.winfo_exists():
            return
        focused_widget = popup.focus_get()
        if self._widget_descends_from(focused_widget, popup):
            return
        self.destroy_header_filter_popup()

    def _on_header_filter_popup_destroy(self, event) -> None:
        if event.widget != self._header_filter_popup:
            return
        self._header_filter_options_request_token += 1
        self._header_filter_popup = None
        self._header_filter_popup_column_index = None
        self._header_filter_popup_search_var = None
        self._header_filter_popup_listbox = None
        self._header_filter_popup_empty_var = None
        self._header_filter_popup_options = []
        self._header_filter_popup_casefolded_options = []
        self._header_filter_popup_filtered_options = []
        self._header_filter_popup_loading = False

    def destroy_header_filter_popup(self) -> None:
        popup = self._header_filter_popup
        if popup is None or not popup.winfo_exists():
            return
        popup.destroy()