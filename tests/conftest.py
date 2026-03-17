import os
import tkinter as tk

import pytest

from gp_data.ui import GPDataApp


GUI_TEST_FILES = {
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


@pytest.fixture
def tk_root():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk not available in this environment")
    root.withdraw()
    try:
        yield root
    finally:
        try:
            if root.winfo_exists():
                root.destroy()
        except tk.TclError:
            pass


@pytest.fixture
def app_factory(tmp_path):
    apps: list[GPDataApp] = []

    def create_app(*, storage_path=None, withdraw=True, **kwargs):
        path = storage_path or (tmp_path / "data.db")
        try:
            app = GPDataApp(storage_path=path, **kwargs)
        except tk.TclError:
            pytest.skip("Tk not available in this environment")
        if withdraw:
            app.withdraw()
        apps.append(app)
        return app

    try:
        yield create_app
    finally:
        for app in reversed(apps):
            try:
                if app.winfo_exists():
                    app.destroy()
            except tk.TclError:
                pass