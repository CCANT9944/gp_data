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
- Loading a selected row with long names or longer numeric change history now keeps the left-side form layout stable instead of shifting the input fields.
- Switching rows, returning to `New item`, deleting the selected row, or closing the window asks before discarding unsaved form changes.
- `Delete selected` is only active when a table row is selected.
- Add and edit flows warn when the same `Type + Name` already exists.
- The table shows the newest saved items first.
- Inline edits and form edits keep the edited row in place instead of moving it.
- Inline edits to `field3` or `field5` also recalculate `field6` before saving, the same way the main form does.
- Live search filters rows as you type.
- Search prefers exact whole-word matches when possible, so `gin` can match gin items without pulling in `ginger beer`.
- Click the `Type` column header to open a small filter menu listing the saved types, click one to filter the table, use `Edit type...` to choose an existing source type from a list and rename it across all matching saved records, and use `Remove type filter` at the bottom to clear the filter again.
- If `Edit type...` renames a type to one that already exists, the app asks before merging those matching records into the existing target type.
- Click the `GP` column header to open a small menu with highlight presets, a custom threshold option, and a clear option.
- The GP highlight threshold is saved in your local `settings.json` and comes back after restart.
- `Formula settings` lets you edit the calculation formulas using safe field names with simple `+`, `-`, `*`, `/`, and parentheses syntax, and it also lets you show or hide the inline calculation details panel below the main table.
- When a row is selected, the inline calculation details panel explains `field6`, `GP`, `Cash margin`, and `WITH 70% GP` using the current field labels and row values.
- `Open CSV` opens a separate raw CSV viewer for the selected file.
- `Open CSV` now asks whether the file already has a header row; if it does not, the preview generates `Column 1`, `Column 2`, `Column 3`, and so on, and keeps the first row as data.
- `Last CSV` reopens the most recently viewed CSV from a remembered local path so you do not need to browse for the same file every time.
- `Recent CSVs` shows the latest remembered CSV files so you can jump back to more than one file without browsing again.
- If the current data file has prior import history for that same CSV path, reopening it now shows an inline notice in the preview so you can avoid accidentally importing the same source again.
- CSVs with prior import history are also marked with a compact `[*]` marker in the `Last CSV` button state and in the `Recent CSVs` menu so you can spot them before reopening, even when only part of the file was imported earlier.
- Inside the CSV preview, rows that already match saved items are highlighted so you can review row-by-row what is already in the current data file before starting the import review.
- Opening a CSV, combining sessions, and preparing analysis now show a centered processing dialog so long preview actions are clearly visible.
- The raw CSV viewer includes a global text search across all visible data, and it runs when you press `Enter` in the search box so you can finish typing first.
- The raw CSV viewer lets you choose which columns stay visible, and it remembers that choice per CSV path using column headers when possible so reordered files reopen more sensibly.
- Reopening a CSV with remembered preview state is also faster because the viewer restores the saved visible columns immediately and finishes the heavier initial row refresh right after the window appears.
- Clicking a CSV preview column header opens a compact popup with a local search box, a scrollable value list, exact-value filtering for that column, and sort controls for that same column.
- The popup sorts text columns A-to-Z or Z-to-A and sorts numeric columns low-to-high or high-to-low using numeric order instead of text order.
- The raw CSV viewer remembers the active sort per CSV path and shows the current sort in the preview summary so you can see it without reopening the popup.
- The raw CSV viewer also shows a small header-mode label so you can see whether the file is using `Row 1` headers or generated column names.
- The raw CSV viewer includes `Preview` and `Analysis` workspace buttons, and `Analysis` switches the same preview window into an analysis workspace for the current preview result, using only the rows that currently match the preview filters, the active combine-sessions state, and the columns that are still visible.
- The raw CSV viewer also includes an `Import Filtered Rows` button. If you have selected preview rows, the import uses those selected rows first; otherwise it uses the full current filtered result.
- Import opens a mapping step and then a review table before saving anything into the main app data.
- The mapping step treats buying price and selling price separately, so a `Selling Price` CSV column does not auto-fill the buying-price field by default.
- The review table lets you include or exclude rows, edit mapped values, import only rows that validate successfully, and overwrite a matched saved row when you explicitly choose that path.
- The review table also lets you intentionally keep an advisory possible-duplicate saved-data match as a new row, so amber duplicate warnings do not force an overwrite.
- The review table separates saved-data matches from import-batch conflicts, so statuses that mention another included import row refer to the current CSV selection rather than the main database.
- Import-batch possible-duplicate checks now keep size markers such as `125ml`, `175ml`, and `250ml` distinct from each other, while saved-data possible matches can still ignore size and format tokens when looking for an overwrite candidate.
- When a row is blocked by another included import row, the selected-row panel shows exactly which earlier import row it conflicts with and includes a short summary of that blocking row.
- If one imported row has several possible saved matches, the review table lets you choose which saved row should be overwritten instead of silently picking one.
- The import summary reports how many rows were imported and how many duplicate or invalid rows were skipped.
- The analysis workspace can show a summary table, bar chart, pie chart, or histogram so you can inspect top visible values and numeric spread without exporting the CSV first; bar charts can show negative values, while pie charts only render positive values.
- Bar charts in the analysis workspace can be limited to `All`, `First 5`, `First 10`, `First 20`, `Last 5`, `Last 10`, or `Last 20` items, and can be switched between vertical and horizontal layouts.
- Switching back to `Preview` keeps the same CSV window open, and returning to `Analysis` reuses the last analysis snapshot when the preview filters and visible columns have not changed.
- That reuse keeps the underlying analysis data fast to reopen, but the analysis controls themselves still reopen at their default state, so the selected chart type, chosen label/value columns, bar range, orientation, histogram bins, and hidden-bar choices are not yet remembered.
- Histogram mode uses a numeric value column, defaults to an `Auto` bin choice based on the current data spread, still lets you choose a fixed bin count manually, shows short helper text explaining what bins mean, and includes an `Explain histogram` button that opens a detailed in-app tutorial popup.
- Histogram bins that contain outlier values are highlighted in red so unusual values stand out more clearly.
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
- Restore from the UI is handled through `Manage backups`, which includes preview, restore, and delete operations for backups created for the current storage file.
- Table layout is customizable:
  - drag the whole header left or right to reorder columns
  - drag the divider line between two headers to resize columns and keep the new widths
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
- `ui/app.py`: top-level Tkinter shell and composition root, with phased startup, startup settings reuse for recent-CSV initialization, and public callbacks kept stable for tests and callers
- `ui/app_layout.py`: main-window widget, menu, and processing-status construction extracted from `ui/app.py`
- `ui/app_csv_preview_controller.py`: remembered CSV path, header-mode, and preview-launch actions
- `ui/app_formula_display_controller.py`: formula settings dialog and inline calculation-details panel visibility
- `ui/app_storage_controller.py`: export and manage-backups actions
- `ui/app_form_mode_controller.py`: form-mode banner and edit/new-item button-state logic
- `ui/app_table_display_controller.py`: type filter, bulk type rename, GP highlight, column labels, and column-visibility controls
- `ui/app_record_controllers.py`: record list refresh/selection flow plus add/edit/save/delete form actions
- `ui/formula_explanation.py`: text rendering for the read-only formula overview dialog and selected-row calculation details panel
- `ui/record_actions.py`: record lookup and add/save/delete flows, plus inline table-edit save logic
- `ui/csv_preview/`: raw CSV preview package split into loader, dialog, controller, helper, state, and analysis modules
- `ui/view_helpers.py`: shared UI focus, recalc, table-selection, and processing-dialog helpers
- `ui/`: the rest of the Tkinter application code
- `data_manager/`: CSV and SQLite persistence layer
- `models.py`: record model and calculated fields
- `settings.py`: public settings facade used by the app and tests
- `settings_store.py`: settings persistence and per-CSV remembered state storage
- `settings_normalization.py`: settings normalization and backfill rules for old or partial settings data
- `settings_types.py`: immutable settings dataclasses
- `settings_defaults.py`: default labels, layout, and preview-setting constants
- `settings_facade.py`: module-level compatibility wrappers behind the public `settings.py` API
- `settings.json`: local saved labels, layout preferences, GP highlight preference, and remembered CSV preview state
- `MANUAL.txt`: plain-language user guide
- `BUG_HUNTING.md`: manual and test checklist for finding regressions

## CSV Preview Architecture

- `ui/csv_preview/loader.py`: loads CSV preview data, manages restart-safe preview sidecars, and can reuse persisted preview rows or persisted full-row caches for unchanged files.
- `ui/csv_preview/helpers.py`: holds pure preview helpers for column identity, numeric detection, row summaries, and sort/query formatting so those rules stay separate from Tk widget code.
- `ui/csv_preview/analysis.py`: builds analysis snapshots, numeric summaries, top-value chart series, histogram bin series, automatic bin sizing, and outlier-bin detection from the current filtered preview rows.
- `ui/csv_preview/analysis_dialog.py`: builds the reusable CSV analysis view used both for the embedded preview analysis workspace and for the compatibility standalone analysis dialog, including the summary-table, bar-chart, pie-chart, histogram, bar-range, bar-orientation, and histogram-bin controls.
- `ui/csv_preview/analysis_launcher.py`: prepares filtered analysis snapshots in the background and hands the snapshot back to the preview workflow when it is ready.
- `ui/csv_preview/dialog_support.py`: holds generic Treeview, export-path, and widget helpers used by the preview window.
- `ui/csv_preview/pipeline.py`: owns preview search, filtering, sort, combine-session, and cache decisions that should stay independent from Tk widgets.
- `ui/csv_preview/preview_pipeline.py`: provides the dialog-facing preview pipeline class while still routing runtime hooks through the dialog module for test and compatibility stability.
- `ui/csv_preview/runtime_hooks.py`: centralizes the preview runtime hook assignment for the dialog-facing pipeline and view state while letting `dialog.py` keep late-bound compatibility wrappers.
- `ui/csv_preview/preview_settings.py`: restores remembered preview columns and sort per CSV path from one loaded settings snapshot and builds the save callbacks used by the preview window.
- `ui/csv_preview/preview_state.py`: holds the preview summary and view-state dataclasses used by the table controller.
- `ui/csv_preview/popup_controller.py`: owns header popup and preview export behavior, including async distinct-value loading and exact-value filter application.
- `ui/csv_preview/refresh_controller.py`: owns metadata refresh, filtered refresh polling, loading placeholders, and header-filter prewarm orchestration for the preview table.
- `ui/csv_preview/row_combiner.py`: owns combined-session row iteration and pre-header-filter row generation for the preview pipeline.
- `ui/csv_preview/table_controller.py`: owns the preview table controller and popup-export adapter used by the dialog.
- `ui/csv_preview/table_helpers.py`: owns the column chooser dialog, visible-column manager, chunked Treeview row renderer, and the no-op heading/display-column update skips used to keep preview refreshes lighter.
- `ui/csv_preview/dialog.py`: remains the public preview entrypoint and compatibility surface, while also owning the `Preview` / `Analysis` workspace switching, same-state analysis snapshot reuse, immediate remembered-column restore, and idle-deferred first refresh used by the raw CSV viewer.
- The dialog currently reuses the last analysis snapshot for the same preview state, but it rebuilds the analysis widgets when you return to `Analysis`, so chart-control selections still reset to their defaults.

## Main App Architecture

- `ui/app.py` is now mainly a wiring layer for the root window, phased startup, startup settings reuse, and public callbacks.
- `ui/app_layout.py` owns the main-window widget, menu, and processing-status assembly so `GPDataApp` can stay focused on runtime wiring.
- `ui/app_layout.py` also freezes the left form pane at its initial natural width so edit-mode banner changes do not repack the form while rows are loaded.
- Main-window behaviors are split into small focused controllers so backup/export, CSV preview launch, table display state, form-mode state, and record list/form actions are easier to reason about independently.
- `RecordActions.save_inline_edit(...)` now owns inline table-edit save behavior so form saves and inline saves share the same record-action layer.
- The compatibility re-export shims in `ui/app_controllers.py` and `ui/app_display_controllers.py` exist to keep imports stable while the concrete code lives in narrower modules.

## Settings Architecture

- `settings.py` remains the public module that callers import from.
- `settings_store.py` owns reading, writing, and updating saved settings.
- `settings_store.py` also keeps per-storage CSV import markers so reopening a previously imported CSV can warn before you import it again.
- `settings_normalization.py` owns defaults, normalization, and backfill rules so malformed or older settings still load safely.
- `settings_facade.py` provides the module-level `load_*` and `save_*` helper bindings without putting that boilerplate back into `settings.py`.
- `settings.SettingsStore` still resolves its default path through `settings.DEFAULT_PATH`, which keeps tests and UI flows compatible when that default path is monkeypatched.

## Testing

Install dependencies and run:

```powershell
python -m pip install -r requirements.txt
python -m pytest
```

GUI-related tests skip automatically if Tk is not available in the current environment.
The UI packages also lazy-load GUI entry points so non-GUI imports and CLI tests can still collect in environments where `tkinter` is missing.

## Notes

- The app stores recent numeric change history, not a full unlimited audit log.
- Column order, visible columns, and widths are persisted in the local `settings.json` file.
- The last and recent CSV preview paths are persisted in `settings.json` for the `Last CSV` and `Recent CSVs` controls.
- CSV preview visible-column choices are also persisted in `settings.json` per CSV path, with header-aware restore for reordered files when possible.
- CSV preview header-row choices are also persisted in `settings.json` per CSV path, so `Last CSV` and `Recent CSVs` reopen with the same header mode.
- `settings.json` is intentionally ignored by Git so personal layout changes are not committed.
- Duplicate warnings are advisory: the GUI can still allow a duplicate if the user explicitly confirms it.
- Older duplicate rows already stored in the database are not merged automatically.
- In the GUI, restore is available from `Manage backups` rather than from a separate main-window restore button, and those actions are limited to backups that belong to the current storage file.
- The README is a technical overview. For normal day-to-day usage, see `MANUAL.txt`.