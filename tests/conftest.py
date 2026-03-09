import os

import pytest


GUI_TEST_FILES = {
    "test_backfill.py",
    "test_edit_commit.py",
    "test_enter_submit.py",
    "test_field1_capitalize.py",
    "test_field1_titlecase_extra.py",
    "test_inline_table_edit.py",
    "test_input_navigation.py",
    "test_manage_backups_gui.py",
    "test_metrics.py",
    "test_restore.py",
    "test_search_ui.py",
    "test_table_display_format.py",
    "test_ui.py",
}


def _running_in_ci() -> bool:
    return os.getenv("GITHUB_ACTIONS") == "true" or os.getenv("CI") == "true"


def pytest_collection_modifyitems(config, items):
    if not _running_in_ci():
        return
    skip_gui = pytest.mark.skip(reason="GUI tests are skipped on CI")
    for item in items:
        if item.fspath.basename in GUI_TEST_FILES:
            item.add_marker(skip_gui)