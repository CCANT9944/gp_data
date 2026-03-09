# GP Data Manager

This project is a simple data management application written in Python. It
provides both a command-line interface and a Tkinter GUI for entering,
editing, searching, backing up, and exporting records.

## Background & Goals

The original implementation used a CSV file for persistence. During
development the user requested a "safer" way to store data which led to a
full redesign of the storage layer to use SQLite by default while providing
migration logic and backwards compatibility with existing CSV files.

Subsequent enhancements, summarized below, were built on top of the
refactored data manager and supported by an extensive pytest suite.

## Key Features

1. **Backend Abstraction**
   - `CSVDataManager` and `SQLiteDataManager` share the same interface.
   - `DataManager` wrapper detects existing CSV data, creates/opens the
     database and migrates records.  It also backs up the CSV file and
     automatically upgrades the backend.
   - Auto-migration on startup and a CLI `migrate` command are available.

2. **Command-Line Interface (`main.py`)**
   - CRUD operations (`add`, `list`, `edit`, `delete`).
   - `backup` and `restore` commands for file-based backups.
   - `export` command (now filters by search term when used from GUI).
   - `cleanup` command removes old backups to keep only the latest 10.
   - `migrate` command forces migration from CSV to SQLite.
   - Default storage paths automatically created in user data directory.

3. **Tkinter GUI (`ui.py`)**
   - Form for adding and editing entries.
   - Inline table display with column headers.
   - Live-search field: filtering occurs as you type or backspace.
   - Export button respects the current search filter.
   - Menu shortcuts for backup, restore, and migration.

4. **Backup Management**
   - Automatic backup on edits with timestamped files in `backups/`.
   - Backup rotation keeps the most recent 10, older ones are deleted.
   - GUI supports manual backup and restore operations.

5. **Testing Suite**
   - Over 40 pytest modules cover all functionality: data manager logic,
     CLI commands, GUI interactions, backup/restore, migration, search, and
     export behavior.
   - Tests use temporary directories and in-memory databases where
     appropriate.
   - GUI-related tests skip when a display is not available.

## Development History

1. **Initial Bug Fix**
   - Resolved a `NameError` in `main.py` by importing `DataManager` properly.

2. **CSV to SQLite Migration**
   - Added new `SQLiteDataManager` class and reorganized `data_manager.py` to
     support both backends.
   - Implemented detection of existing CSV data and automated migration.
   - Added CLI operations to trigger migration and clean up old backups.
   - Wrote tests to verify migration behavior and edge cases.

3. **CLI Enhancements**
   - Created `backup`, `restore`, `cleanup`, and `export` commands.
   - Added options for filtering and formatting.
   - Wrote numerous tests ensuring proper command output, error handling,
     and integration with the data manager.

4. **GUI Improvements**
   - Added live search field that filters table contents on key events.
   - Connected export button to use filtered results.
   - Backed GUI actions with tests that simulate user interactions.
   - Added menu shortcuts and confirmation dialogs for operations.

5. **Final Polish**
   - Implemented backup rotation and cleanup CLI.
   - Updated `.gitignore` to exclude `data.db`.
   - Added comprehensive documentation here and in code comments.

## Usage

### Command Line

```powershell
python main.py add "value1" "value2" ...   # add a record
python main.py list                          # list all records
python main.py edit 1 "new1" ...           # edit record #1
python main.py delete 1                      # delete record #1
python main.py backup                       # create CSV backup
python main.py restore backups/filename     # restore from backup
python main.py migrate                      # migrate CSV to SQLite
python main.py cleanup                     # remove old backups
```

### GUI

Run `python main.py gui` or simply `python main.py`.
- Use the search box to filter records live.
- Export will save the currently displayed records.
- Use the menu for backup/restore/migrate operations.

## Testing

Install test dependencies and run pytest from the project root:

```powershell
python -m pip install -r requirements.txt
python -m pytest -q
```

GUI tests are skipped if no display is available.

## Troubleshooting (Windows + PowerShell)

If `Activate.ps1` fails with exit code `1`, PowerShell script policy is often
the cause.

### 1) Allow local activation scripts (one-time)

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Close and reopen the terminal, then run:

```powershell
.\.venv\Scripts\Activate.ps1
```

### 2) Run without activating (works immediately)

You can always call the venv Python directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe main.py
```

### 3) Recreate venv if missing

From the `gp_data` directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

---

This README outlines the project's purpose, evolution, and how to use it.
Feel free to explore the source files and tests for deeper insight.