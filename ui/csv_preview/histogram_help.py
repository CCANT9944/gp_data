from __future__ import annotations

import tkinter as tk
from tkinter import ttk


HISTOGRAM_HELP_WINDOW_WIDTH = 760
HISTOGRAM_HELP_WINDOW_HEIGHT = 560


def _histogram_help_text(
    *,
    value_column_label: str,
    bin_label: str,
    row_count: int,
    filtering_active: bool,
    combine_sessions: bool,
) -> str:
    row_scope = "filtered rows" if filtering_active else "preview rows"
    combine_scope = "on" if combine_sessions else "off"
    return (
        "Histogram tutorial\n"
        "==================\n\n"
        "What this chart uses\n"
        "- Value column: "
        f"{value_column_label}\n"
        "- Row scope: "
        f"{row_count} {row_scope}\n"
        "- Combine sessions: "
        f"{combine_scope}\n"
        "- Bins: "
        f"{bin_label}\n\n"
        "How to read the chart\n"
        "- The x-axis shows value ranges, called bins.\n"
        "- The y-axis shows how many rows fall into each value range.\n"
        "- The number above each bar is the row count for that range.\n"
        "- Blue bins show the main distribution.\n"
        "- Red bins contain outlier values.\n\n"
        "Important: what this chart does not do\n"
        "- Histogram counts rows in value ranges.\n"
        "- Histogram does not sum values by item, category, or session.\n"
        "- Histogram ignores the label column entirely.\n\n"
        "Example with net item total\n"
        "If the visible values are 2.10, 2.40, 2.90, 5.20, 5.60, and 11.00, a histogram might show:\n"
        "- 2 to 4 = 3 rows\n"
        "- 4 to 6 = 2 rows\n"
        "- 6 to 8 = 0 rows\n"
        "- 8 to 11 = 1 row\n\n"
        "That means most rows are in the lower ranges. It does not mean the first bar sums to 3 or 7.40.\n\n"
        "When to use histogram\n"
        "- Use it to see spread, clusters, gaps, and unusual values.\n"
        "- Use it when you want to know whether most rows are low, medium, or high values.\n\n"
        "When to use bar chart instead\n"
        "- Use Bar chart if you want total net by item.\n"
        "- Use Bar chart if you want total value by category or session.\n"
        "- Bar chart groups by a label. Histogram does not.\n"
    )


def open_histogram_help_dialog(
    parent: tk.Misc,
    *,
    value_column_label: str,
    bin_label: str,
    row_count: int,
    filtering_active: bool,
    combine_sessions: bool,
) -> tk.Toplevel:
    win = tk.Toplevel(parent)
    win.title("How Histogram Works")
    win.geometry(f"{HISTOGRAM_HELP_WINDOW_WIDTH}x{HISTOGRAM_HELP_WINDOW_HEIGHT}")
    win.transient(parent.winfo_toplevel())

    container = ttk.Frame(win, padding=10)
    container.pack(fill="both", expand=True)
    container.columnconfigure(0, weight=1)
    container.rowconfigure(1, weight=1)

    ttk.Label(
        container,
        text="Histogram Help",
        font=("Segoe UI", 12, "bold"),
        anchor="w",
    ).grid(row=0, column=0, sticky="ew", pady=(0, 8))

    text_frame = ttk.Frame(container)
    text_frame.grid(row=1, column=0, sticky="nsew")
    text_frame.columnconfigure(0, weight=1)
    text_frame.rowconfigure(0, weight=1)

    scrollbar = ttk.Scrollbar(text_frame, orient="vertical")
    text = tk.Text(
        text_frame,
        wrap="word",
        yscrollcommand=scrollbar.set,
        relief="flat",
        borderwidth=0,
        font=("Segoe UI", 10),
        padx=4,
        pady=4,
    )
    scrollbar.configure(command=text.yview)
    text.grid(row=0, column=0, sticky="nsew")
    scrollbar.grid(row=0, column=1, sticky="ns")

    text.insert(
        "1.0",
        _histogram_help_text(
            value_column_label=value_column_label,
            bin_label=bin_label,
            row_count=row_count,
            filtering_active=filtering_active,
            combine_sessions=combine_sessions,
        ),
    )
    text.configure(state="disabled")

    button_row = ttk.Frame(container)
    button_row.grid(row=2, column=0, sticky="ew", pady=(10, 0))
    ttk.Button(button_row, text="Close", command=win.destroy).pack(side="right")

    return win