# GP Data Manager

GP Data Manager is a small Python application for storing product or stock-style
records with both a Tkinter desktop UI and a command-line interface.

The current version uses SQLite by default, keeps timestamped backups, supports
live filtering, inline edits, persistent table layout preferences, and recent
numeric change history per item.

## Current Feature Set

### Storage

- SQLite is the default backend.
- Legacy CSV data can still be loaded and migrated.
- The storage layer auto-upgrades older databases when new columns are added.
- Timestamped backups are stored in `backups/`.

### Desktop UI

- Add records through the form on the left and press `Enter` in the last field to save.
- Clicking a table row loads that record into the main form for editing.
- Use `Save changes` to commit form edits, or press `Enter` in the last field while an item is loaded.
- The form shows a highlighted mode banner so edit mode stands out clearly from new-item mode.
- If the form has unsaved edits, the mode banner switches to an `UNSAVED CHANGES` state.
- Switching rows, returning to `New item`, deleting the selected row, or closing the window asks before discarding unsaved form changes.
- `Delete selected` is only active when a table row is selected.
- Add and edit flows warn when the same `Type + Name` already exists.
- The table shows the newest saved items first.
- Inline edits and form edits keep the edited row in place instead of moving it.
- Live search filters rows as you type.
- Search prefers exact whole-word matches when possible, so `gin` can match gin items without pulling in `ginger beer`.
- Click the `Type` column header to open a small filter menu listing the saved types, then use `Remove type filter` at the bottom to clear it.
- Click the `GP` column header to open a small menu with highlight presets, a custom threshold option, and a clear option.
- The GP highlight threshold is saved in your local `settings.json` and comes back after restart.
- `Open CSV` opens a separate read-only raw CSV viewer for the selected file.
- `Open CSV` now asks whether the file already has a header row; if it does not, the preview generates `Column 1`, `Column 2`, `Column 3`, and so on, and keeps the first row as data.
- `Last CSV` reopens the most recently viewed CSV from a remembered local path so you do not need to browse for the same file every time.
- `Recent CSVs` shows the latest remembered CSV files so you can jump back to more than one file without browsing again.
- Opening a CSV, combining sessions, and preparing analysis now show a centered processing dialog so long preview actions are clearly visible.
- The raw CSV viewer includes a global text search across all visible data, and it runs when you press `Enter` in the search box so you can finish typing first.
- The raw CSV viewer lets you choose which columns stay visible, and it remembers that choice per CSV path using column headers when possible so reordered files reopen more sensibly.
- Clicking a CSV preview column header opens a compact popup with a local search box, a scrollable value list, exact-value filtering for that column, and sort controls for that same column.
- The popup sorts text columns A-to-Z or Z-to-A and sorts numeric columns low-to-high or high-to-low using numeric order instead of text order.
- The raw CSV viewer remembers the active sort per CSV path and shows the current sort in the preview summary so you can see it without reopening the popup.
- The raw CSV viewer also shows a small header-mode label so you can see whether the file is using `Row 1` headers or generated column names.
- The raw CSV viewer includes an `Analyze` action that opens a separate analysis window for the current preview result, using only the rows that currently match the preview filters, the active combine-sessions state, and the columns that are still visible.
- The analysis window can show a summary table or bar and pie charts so you can inspect top visible values without exporting the CSV first; bar charts can show negative values, while pie charts only render positive values.
- `Save As CSV` creates a new CSV file from the current preview state, including the current search, exact column filter, combined rows, and visible columns, without changing the original imported file, and it defaults to your shared `Favorites/csv_exports` folder.
- The raw CSV viewer can also combine session-based rows, such as `Lunch` and `Dinner`, into one product row when the file has detectable session and quantity columns, including numeric export columns with generic names like `Textbox73`.
- For very large CSVs, the preview window opens from an initial sample first and only renders the first slice of matching rows so the window stays responsive, with a lower live row cap for very wide files to keep navigation smoother.
- Reopening the same unchanged CSV is faster because the preview data is reused while the app is still open.
- Reopening the same unchanged CSV after restarting the app is also faster because the preview can reuse persisted preview rows, and some moderate-sized files can also reuse a persisted full-row cache for follow-up searches.
- Repeated searches on larger CSVs are also faster when the viewer decides the file can fit a temporary in-memory search index safely, instead of rescanning the CSV every time.
- After the app has already resolved a large CSV once, reopening that same unchanged file is also faster after restart because the preview reuses a small sidecar metadata cache for row counts, encoding, and late columns.
- The app warns at startup if the current storage file looks unreadable and points you toward backup restore or other recovery steps.
- Add, edit, and delete flows now ask before continuing if a safety backup cannot be created first.
- If renamed field labels cannot be saved or applied, the app shows an error and keeps the existing labels.
- If layout or GP highlight settings cannot be saved, the app warns that the current change may not still be there after restart.
- If an inline edit cannot be saved, the app shows an error and keeps the inline editor open with what you typed.
- If form submission fails unexpectedly, the app shows an error instead of silently dropping the submit action.
- If you try to delete a selected row while the main form has unsaved edits, the app asks whether those form edits should be discarded first.
- If you confirm `Delete selected`, the row is removed and the form returns to new-item mode.
- Export writes the currently displayed rows.
- Restore from the UI is handled through `Manage backups`, which includes preview, restore, and delete operations.
- Table layout is customizable:
  - drag headers to reorder columns
  - resize columns and keep the new widths
  - hide/show columns from the `Columns` button
  - layout is remembered after restart
- The `Change history` box shows recent numeric changes for the selected item, and `View full history` opens the complete stored history for that row.

### Numeric Change Tracking

- Numeric change history is tracked per record.
- The app currently tracks numeric edits to the price-style fields:
  - `field3`
  - `field6`
  - `field7`
- The most recent entries are shown in the `Change history` box, newest first.
- Change history survives app restarts because it is saved in storage.

### Command-Line Interface

The CLI supports:

- `gui`
- `list`
- `add`
- `backup`
- `restore`
- `export`
- `migrate`
- `cleanup`

## Running the Program

From the `gp_data` directory:

```powershell
python main.py
```

This starts the graphical application.

To open the GUI explicitly:

```powershell
python main.py gui
```

## CLI Examples

List records:

```powershell
python main.py list
```

Add a record:

```powershell
python main.py add --field1 "Lager" --field2 "House" --field3 10 --field5 4 --field7 5.5
```

Create a timestamped backup:

```powershell
python main.py backup
```

Restore from the newest available backup:

```powershell
python main.py restore
```

Export to CSV:

```powershell
python main.py export exported.csv
```

Migrate legacy CSV data into SQLite:

```powershell
python main.py migrate old.csv data.db
```

Clean old legacy files:

```powershell
python main.py cleanup
```

## Files of Interest

- `main.py`: compatibility entrypoint
- `cli.py`: command-line logic
- `ui/app.py`: top-level Tkinter controller
- `ui/csv_preview/`: raw CSV preview package for loading and showing external CSV files in a separate window
- `ui/record_actions.py`: record lookup and add/save/delete action flows
- `ui/view_helpers.py`: shared UI focus, recalc, and table-selection helpers
- `ui/`: the rest of the Tkinter application code
- `data_manager/`: CSV and SQLite persistence layer
- `models.py`: record model and calculated fields
- `settings.json`: local saved labels and table layout preferences
- `MANUAL.txt`: plain-language user guide
- `BUG_HUNTING.md`: manual and test checklist for finding regressions

## CSV Preview Architecture

- `ui/csv_preview/loader.py`: loads CSV preview data, manages restart-safe preview sidecars, and can reuse persisted preview rows or persisted full-row caches for unchanged files.
- `ui/csv_preview/helpers.py`: holds pure preview helpers for column identity, numeric detection, row summaries, and sort/query formatting so those rules stay separate from Tk widget code.
- `ui/csv_preview/analysis.py`: builds analysis snapshots, numeric summaries, and top-value chart series from the current filtered preview rows.
- `ui/csv_preview/analysis_dialog.py`: owns the separate analysis dialog and its summary-table, bar-chart, and pie-chart views.
- `ui/csv_preview/pipeline.py`: owns preview search, filtering, sort, combine-session, and cache decisions that should stay independent from Tk widgets.
- `ui/csv_preview/popup_controller.py`: owns header popup and preview export behavior, including async distinct-value loading and exact-value filter application.
- `ui/csv_preview/refresh_controller.py`: owns metadata refresh, filtered refresh polling, loading placeholders, and header-filter prewarm orchestration for the preview table.
- `ui/csv_preview/dialog.py`: owns Tk window creation, view state, and Treeview rendering, while bridging to the extracted helper, pipeline, refresh, and popup-controller layers.

## Testing

Install dependencies and run:

```powershell
python -m pip install -r requirements.txt
python -m pytest
```

GUI-related tests skip automatically if Tk is not available in the current environment.

## Notes

- The app stores recent numeric change history, not a full unlimited audit log.
- Column order, visible columns, and widths are persisted in the local `settings.json` file.
- The last and recent CSV preview paths are persisted in `settings.json` for the `Last CSV` and `Recent CSVs` controls.
- CSV preview visible-column choices are also persisted in `settings.json` per CSV path, with header-aware restore for reordered files when possible.
- CSV preview header-row choices are also persisted in `settings.json` per CSV path, so `Last CSV` and `Recent CSVs` reopen with the same header mode.
- `settings.json` is intentionally ignored by Git so personal layout changes are not committed.
- Duplicate warnings are advisory: the GUI can still allow a duplicate if the user explicitly confirms it.
- Older duplicate rows already stored in the database are not merged automatically.
- In the GUI, restore is available from `Manage backups` rather than from a separate main-window restore button.
- The README is a technical overview. For normal day-to-day usage, see `MANUAL.txt`.