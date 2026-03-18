from pathlib import Path

from gp_data import settings


def test_save_and_load_labels(tmp_path: Path):
    p = tmp_path / "settings.json"
    labels = ["A", "B", "C", "D", "E", "F", "G"]
    settings.save_labels(labels, p)
    loaded = settings.load_labels(p)
    assert loaded == labels
    assert p.exists()


def test_load_defaults_when_missing(tmp_path: Path):
    p = tmp_path / "settings.json"
    loaded = settings.load_labels(p)
    assert loaded == ["Field 1", "Field 2", "Field 3", "Field 4", "Field 5", "Field 6", "Field 7"]


def test_save_and_load_column_order(tmp_path: Path):
    p = tmp_path / "settings.json"
    order = ["field3", "field1", "field2", "field7", "field6", "field4", "field5", "gp70", "gp", "cash_margin"]
    settings.save_column_order(order, p)
    loaded = settings.load_column_order(p)
    assert loaded == order


def test_load_settings_backfills_missing_columns(tmp_path: Path):
    p = tmp_path / "settings.json"
    settings.save_settings({"labels": ["A", "B", "C", "D", "E", "F", "G"], "column_order": ["field3", "field1"]}, p)
    loaded = settings.load_settings(p)
    assert loaded["column_order"][:2] == ["field3", "field1"]
    assert loaded["column_order"][-1] == "gp70"


def test_save_and_load_column_widths(tmp_path: Path):
    p = tmp_path / "settings.json"
    widths = {"field1": 220, "field3": 95, "gp": 110}
    settings.save_column_widths(widths, p)
    loaded = settings.load_column_widths(p)
    assert loaded["field1"] == 220
    assert loaded["field3"] == 95
    assert loaded["gp"] == 110
    assert loaded["field2"] == 140


def test_save_and_load_visible_columns(tmp_path: Path):
    p = tmp_path / "settings.json"
    visible = ["field1", "field3", "field7", "gp"]
    settings.save_visible_columns(visible, p)
    loaded = settings.load_visible_columns(p)
    assert loaded == visible


def test_save_and_load_gp_highlight_threshold(tmp_path: Path):
    p = tmp_path / "settings.json"

    settings.save_gp_highlight_threshold(60.0, p)

    assert settings.load_gp_highlight_threshold(p) == 60.0


def test_load_settings_defaults_on_malformed_json(tmp_path: Path):
    p = tmp_path / "settings.json"
    p.write_text("{not-json", encoding="utf-8")

    loaded = settings.load_settings(p)

    assert loaded["labels"] == settings.DEFAULT_LABELS
    assert loaded["column_order"] == settings.DEFAULT_COLUMN_ORDER


def test_load_settings_defaults_when_json_root_is_not_an_object(tmp_path: Path):
    p = tmp_path / "settings.json"
    p.write_text('["not", "an", "object"]', encoding="utf-8")

    loaded = settings.load_settings(p)

    assert loaded["column_widths"] == settings.DEFAULT_COLUMN_WIDTHS
    assert loaded["visible_columns"] == settings.DEFAULT_VISIBLE_COLUMNS


def test_load_settings_invalid_gp_highlight_threshold_defaults_to_none(tmp_path: Path):
    p = tmp_path / "settings.json"
    p.write_text('{"gp_highlight_threshold": 150}', encoding="utf-8")

    loaded = settings.load_settings(p)

    assert loaded["gp_highlight_threshold"] is None


def test_settings_store_save_normalizes_values_before_writing(tmp_path: Path):
    store = settings.SettingsStore(tmp_path / "settings.json")

    saved = store.save(
        {
            "labels": ["A", "B"],
            "column_order": ["field3", "field3", "field1", "bad"],
            "column_widths": {"field1": "210", "field2": 20, "bad": 999},
            "visible_columns": ["field7", "field7", "nope"],
            "gp_highlight_threshold": "61.5",
        }
    )

    assert saved.labels == ["A", "B", "Field 3", "Field 4", "Field 5", "Field 6", "Field 7"]
    assert saved.column_order[:2] == ["field3", "field1"]
    assert saved.column_widths["field1"] == 210
    assert saved.column_widths["field2"] == settings.DEFAULT_COLUMN_WIDTHS["field2"]
    assert saved.visible_columns == ["field7"]
    assert saved.gp_highlight_threshold == 61.5
    assert settings.load_settings(store.path)["visible_columns"] == ["field7"]


def test_settings_store_update_preserves_existing_keys(tmp_path: Path):
    store = settings.SettingsStore(tmp_path / "settings.json")
    store.save({
        "labels": ["Type", "Name", "Price", "Qty", "Units", "Cost", "Sale"],
        "column_order": settings.DEFAULT_COLUMN_ORDER,
        "column_widths": {"field1": 222},
        "visible_columns": ["field1", "field3"],
        "gp_highlight_threshold": 70.0,
    })

    updated = store.save_visible_columns(["field1", "field7", "gp"])

    assert updated.visible_columns == ["field1", "field7", "gp"]
    assert updated.labels[0] == "Type"
    assert updated.column_widths["field1"] == 222
    assert updated.gp_highlight_threshold == 70.0


def test_save_and_load_csv_preview_last_path(tmp_path: Path):
    p = tmp_path / "settings.json"

    settings.save_csv_preview_last_path(r"C:\data\sales.csv", p)

    assert settings.load_csv_preview_last_path(p) == r"C:\data\sales.csv"
    assert settings.load_csv_preview_recent_paths(p) == [r"C:\data\sales.csv"]


def test_save_and_load_csv_preview_recent_paths(tmp_path: Path):
    p = tmp_path / "settings.json"

    settings.save_csv_preview_recent_paths([r"C:\data\sales.csv", r"C:\data\stock.csv"], p)

    assert settings.load_csv_preview_recent_paths(p) == [r"C:\data\sales.csv", r"C:\data\stock.csv"]
    assert settings.load_csv_preview_last_path(p) == r"C:\data\sales.csv"


def test_save_and_load_csv_preview_visible_columns_for_path(tmp_path: Path):
    p = tmp_path / "settings.json"
    settings.save_csv_preview_recent_paths([r"C:\data\sales.csv", r"C:\data\stock.csv"], p)

    settings.save_csv_preview_visible_columns(r"C:\data\stock.csv", [0, 2, 4], p)

    assert settings.load_csv_preview_visible_columns(r"C:\data\stock.csv", p) == [0, 2, 4]
    assert settings.load_csv_preview_visible_columns(r"C:\data\sales.csv", p) is None


def test_save_and_load_csv_preview_visible_column_keys_for_path(tmp_path: Path):
    p = tmp_path / "settings.json"
    settings.save_csv_preview_recent_paths([r"C:\data\sales.csv", r"C:\data\stock.csv"], p)

    settings.save_csv_preview_visible_column_keys(r"C:\data\stock.csv", ["name#1", "quantity#1"], p)

    assert settings.load_csv_preview_visible_column_keys(r"C:\data\stock.csv", p) == ["name#1", "quantity#1"]
    assert settings.load_csv_preview_visible_column_keys(r"C:\data\sales.csv", p) is None


def test_save_and_load_csv_preview_sort_for_path(tmp_path: Path):
    p = tmp_path / "settings.json"
    settings.save_csv_preview_recent_paths([r"C:\data\sales.csv", r"C:\data\stock.csv"], p)

    settings.save_csv_preview_sort(r"C:\data\stock.csv", "quantity#1", descending=True, path=p)

    assert settings.load_csv_preview_sort(r"C:\data\stock.csv", p) == {
        "column_key": "quantity#1",
        "descending": True,
    }
    assert settings.load_csv_preview_sort(r"C:\data\sales.csv", p) is None

    settings.save_csv_preview_sort(r"C:\data\stock.csv", None, path=p)

    assert settings.load_csv_preview_sort(r"C:\data\stock.csv", p) is None


def test_save_and_load_csv_preview_state_for_path(tmp_path: Path):
    p = tmp_path / "settings.json"
    state = settings.CsvPreviewPathState(
        visible_columns=[0, 2],
        visible_column_keys=["name#1", "quantity#1"],
        sort_column_key="quantity#1",
        sort_descending=True,
    )

    settings.save_csv_preview_state(r"C:\data\stock.csv", state, p)

    loaded = settings.load_csv_preview_state(r"C:\data\stock.csv", p)

    assert loaded is not None
    assert loaded.visible_columns == [0, 2]
    assert loaded.visible_column_keys == ["name#1", "quantity#1"]
    assert loaded.sort_column_key == "quantity#1"
    assert loaded.sort_descending is True


def test_settings_store_preserves_csv_preview_last_path_during_other_updates(tmp_path: Path):
    store = settings.SettingsStore(tmp_path / "settings.json")
    store.save_csv_preview_last_path(r"C:\data\sales.csv")

    updated = store.save_visible_columns(["field1", "field2"])

    assert updated.csv_preview_last_path == r"C:\data\sales.csv"


def test_settings_store_remember_csv_preview_path_moves_path_to_front(tmp_path: Path):
    store = settings.SettingsStore(tmp_path / "settings.json")
    store.save_csv_preview_recent_paths([r"C:\data\sales.csv", r"C:\data\stock.csv"])

    updated = store.remember_csv_preview_path(r"C:\data\stock.csv")

    assert updated.csv_preview_last_path == r"C:\data\stock.csv"
    assert updated.csv_preview_recent_paths == [r"C:\data\stock.csv", r"C:\data\sales.csv"]


def test_load_settings_backfills_recent_csv_paths_from_legacy_last_path(tmp_path: Path):
    p = tmp_path / "settings.json"
    p.write_text('{"csv_preview_last_path": "C:\\\\data\\\\sales.csv"}', encoding="utf-8")

    loaded = settings.load_settings(p)

    assert loaded["csv_preview_last_path"] == r"C:\data\sales.csv"
    assert loaded["csv_preview_recent_paths"] == [r"C:\data\sales.csv"]
    assert loaded["csv_preview_visible_columns_by_path"] == {}
    assert loaded["csv_preview_visible_column_keys_by_path"] == {}
    assert loaded["csv_preview_sort_by_path"] == {}
