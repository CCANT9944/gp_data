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
