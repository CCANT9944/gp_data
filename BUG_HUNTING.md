# Bug Hunting Checklist

This file is a practical checklist for finding bugs in GP Data Manager before or after code changes.

## 1. Quick Start

Run the full test suite first:

```powershell
python -m pytest
```

If you changed only one area, also run a focused subset of tests for that feature.

## 2. High-Risk Areas

These parts of the program are most likely to hide regressions:

- form mode changes between new item and editing
- table selection changes
- unsaved-change warnings
- search and filtered save flows
- inline table editing
- backup create, preview, restore, and delete flows
- duplicate detection during add and edit
- export while a filter is active

## 3. Daily Manual Checklist

Use this after any UI or persistence change.

### Add and Edit Flow

1. Start the app with:

   ```powershell
   python main.py
   ```

2. Add a brand new item from a blank form.
3. Select that row in the table.
4. Confirm the edit banner switches from new item mode to editing mode.
5. Change one or more fields and save.
6. Confirm the saved values appear in the table and the form stays on the same record.

### Unsaved Changes Protection

1. Select a saved row.
2. Change a value but do not save.
3. Click a different row.
4. Confirm the discard warning appears.
5. Cancel the warning and make sure:
   - the original row stays selected
   - the unsaved value is still in the form
6. Repeat the same check with `New item`.

### Search Flow

1. Search by partial text.
2. Search by exact word.
3. Confirm `gin` does not wrongly keep `ginger beer` when exact gin matches exist.
4. Save an edit while filtered.
5. Confirm the row remains visible or hidden correctly based on the current filter.

### Duplicate Detection

1. Add a record with an existing `Type + Name`.
2. Confirm the duplicate warning appears.
3. Cancel and make sure no duplicate is saved.
4. Repeat during main-form edit.
5. Repeat during inline table edit.

### Delete Flow

1. Confirm `Delete selected` is disabled when nothing is selected.
2. Select a row and confirm the button enables.
3. Delete the row.
4. Confirm the table, form, and mode banner all reset correctly.

### Backup Flow

1. Create at least one backup.
2. Open `Manage backups`.
3. Preview the backup.
4. Delete one backup and confirm the list refreshes.
5. Restore a backup and confirm the table reloads with restored data.

### Export Flow

1. Export with no filter.
2. Export with a search filter active.
3. Confirm the CSV contains only the currently displayed rows when filtered.

## 4. Code Review Checklist

When reading code, pay extra attention to:

- broad `except Exception` blocks that hide real failures
- repeated `load_all()` calls in one workflow
- UI code that both updates widgets and enforces business rules
- duplicated logic between CSV and SQLite code paths
- any place where selection state, form state, and displayed rows can drift apart

## 5. Good Bug-Fix Workflow

When you find a bug:

1. Reproduce it manually.
2. Add or update a failing test.
3. Fix the code.
4. Run the focused test first.
5. Run the full suite.
6. Retest the manual workflow that originally failed.

## 6. Useful Commands

Run all tests:

```powershell
python -m pytest
```

Run one test file:

```powershell
python -m pytest tests/test_ui.py
```

Run tests matching a keyword:

```powershell
python -m pytest -k duplicate
```

Start the app manually:

```powershell
python main.py
```