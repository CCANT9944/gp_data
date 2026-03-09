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
