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
- Switching rows or returning to `New item` asks before discarding unsaved form changes.
- `Delete selected` is only active when a table row is selected.
- Add and edit flows warn when the same `Type + Name` already exists.
- The table shows the newest saved items first.
- Inline edits and form edits keep the edited row in place instead of moving it.
- Live search filters rows as you type.
- Search prefers exact whole-word matches when possible, so `gin` can match gin items without pulling in `ginger beer`.
- Click the `Type` column header to open a small filter menu listing the saved types, then use `Remove type filter` at the bottom to clear it.
- Click the `GP` column header to open a small menu with highlight presets, a custom threshold option, and a clear option.
- The GP highlight threshold is saved in your local `settings.json` and comes back after restart.
- The app warns at startup if the current storage file looks unreadable and points you toward backup restore or other recovery steps.
- Add, edit, and delete flows now ask before continuing if a safety backup cannot be created first.
- If renamed field labels cannot be saved or applied, the app shows an error and keeps the existing labels.
- If layout or GP highlight settings cannot be saved, the app warns that the current change may not still be there after restart.
- If an inline edit cannot be saved, the app shows an error and keeps the inline editor open with what you typed.
- If form submission fails unexpectedly, the app shows an error instead of silently dropping the submit action.
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
- `ui/record_actions.py`: record lookup and add/save/delete action flows
- `ui/view_helpers.py`: shared UI focus, recalc, and table-selection helpers
- `ui/`: the rest of the Tkinter application code
- `data_manager/`: CSV and SQLite persistence layer
- `models.py`: record model and calculated fields
- `settings.json`: local saved labels and table layout preferences
- `MANUAL.txt`: plain-language user guide
- `BUG_HUNTING.md`: manual and test checklist for finding regressions

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
- `settings.json` is intentionally ignored by Git so personal layout changes are not committed.
- Duplicate warnings are advisory: the GUI can still allow a duplicate if the user explicitly confirms it.
- Older duplicate rows already stored in the database are not merged automatically.
- In the GUI, restore is available from `Manage backups` rather than from a separate main-window restore button.
- The README is a technical overview. For normal day-to-day usage, see `MANUAL.txt`.