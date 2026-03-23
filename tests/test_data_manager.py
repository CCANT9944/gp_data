from pathlib import Path

import pytest

from gp_data.data_manager import backends
from gp_data.data_manager import DataManager
from gp_data.models import Record


def test_data_manager_crud(tmp_path: Path):
    csv_path = tmp_path / "data.db"
    dm = DataManager(csv_path)

    assert dm.load_all() == []

    r = Record(field1="one", field2="two", field3=1.5)
    dm.save(r)

    rows = dm.load_all()
    assert len(rows) == 1
    # `field1` is normalized to start with a capital letter by the model
    assert rows[0].field1 == "One"

    r.field2 = "changed"
    dm.update(r.id, r)
    rows = dm.load_all()
    # field2 is normalized by the model on load
    assert rows[0].field2 == "Changed"

    dm.delete(r.id)
    assert dm.load_all() == []


def test_data_manager_tracks_last_numeric_change_in_csv(tmp_path: Path):
    csv_path = tmp_path / "data.csv"
    dm = DataManager(csv_path)

    record = Record(field1="one", field3=10.0, field6=2.0, field7=5.0)
    dm.save(record)

    updated = record.model_copy(update={"field3": 12.0})
    dm.update(record.id, updated)

    rows = dm.load_all()
    assert len(rows) == 1
    assert rows[0].last_numeric_field == "field3"
    assert rows[0].last_numeric_from == pytest.approx(10.0)
    assert rows[0].last_numeric_to == pytest.approx(12.0)
    assert rows[0].last_numeric_changed_at is not None
    assert len(rows[0].numeric_change_history) == 1

    updated_again = rows[0].model_copy(update={"field7": 7.5})
    dm.update(record.id, updated_again)

    rows = dm.load_all()
    assert len(rows[0].numeric_change_history) == 2
    assert rows[0].numeric_change_history[0].field_name == "field3"
    assert rows[0].numeric_change_history[1].field_name == "field7"


def test_data_manager_find_duplicate_record(tmp_path: Path):
    dm = DataManager(tmp_path / "data.db")

    first = Record(field1="soft drink", field2="tonic")
    second = Record(field1="spirit", field2="gin")
    dm.save(first)
    dm.save(second)

    duplicate = dm.find_duplicate_record(Record(field1="Soft Drink", field2="Tonic"))
    assert duplicate is not None
    assert duplicate.id == first.id

    same_record = dm.find_duplicate_record(Record(id=first.id, field1="Soft Drink", field2="Tonic"), exclude_id=first.id)
    assert same_record is None

    assert dm.duplicate_identity(Record(field1="  Soft Drink ", field2=" Tonic ")) == ("soft drink", "tonic")


def test_data_manager_can_detect_possible_duplicate_record(tmp_path: Path):
    dm = DataManager(tmp_path / "data.db")

    first = Record(field1="beer", field2="peroni")
    dm.save(first)

    possible = dm.find_possible_duplicate_record(Record(field1="Beer", field2="BTL Peroni"))

    assert possible is not None
    assert possible.id == first.id
    assert dm.possible_duplicate_identity(Record(field1="Beer", field2="BTL Peroni 330ml")) == ("beer", "peroni")
    assert dm.possible_duplicate_identity(Record(field1="Vermouth", field2="50ML Martini Rosso")) == ("vermouth", "martini rosso")
    assert dm.possible_duplicate_identity(Record(field1="Vermouth", field2="50 ML Martini Rosso")) == ("vermouth", "martini rosso")


def test_data_manager_can_detect_possible_duplicate_with_leading_measure(tmp_path: Path):
    dm = DataManager(tmp_path / "data.db")

    first = Record(field1="vermouth", field2="martini rosso")
    dm.save(first)

    possible = dm.find_possible_duplicate_record(Record(field1="Vermouth", field2="50ML Martini Rosso"))

    assert possible is not None
    assert possible.id == first.id


def test_data_manager_exposes_explicit_public_api(tmp_path: Path):
    dm = DataManager(tmp_path / "data.db")

    assert dm.path == tmp_path / "data.db"
    dm.ensure_storage()
    assert dm.load_all() == []

    dm.replace_all([Record(field1="replaced")])
    assert dm.load_all()[0].field1 == "Replaced"
    assert dm.storage_issue() is None

    with pytest.raises(AttributeError):
        getattr(dm, "missing_attribute")


def test_csv_data_manager_loads_records_with_custom_field_labels(tmp_path: Path, monkeypatch):
    csv_path = tmp_path / "data.csv"
    csv_path.write_text("Product,Category\nGin,Tonic\n", encoding="utf-8")
    monkeypatch.setattr(backends, "load_labels", lambda: ["Product", "Category", "Field 3", "Field 4", "Field 5", "Field 6", "Field 7"])

    dm = DataManager(csv_path)
    rows = dm.load_all()

    assert len(rows) == 1
    assert rows[0].field1 == "Gin"
    assert rows[0].field2 == "Tonic"
