from pathlib import Path

import pytest

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
