from pathlib import Path

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
