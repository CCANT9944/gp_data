from pathlib import Path
import warnings

import pytest

from gp_data.data_manager import DataManager
from gp_data.models import Record


def test_auto_migration_to_default(tmp_path: Path, monkeypatch, capsys):
    # prepare a legacy CSV at default location
    csv = tmp_path / "data.csv"
    csv.write_text("id,field1\n1,foo\n", encoding="utf-8")
    db = tmp_path / "data.db"

    # patch module constants so DataManager uses our temp paths
    import gp_data.data_manager as dm_mod
    monkeypatch.setattr(dm_mod, "DEFAULT_CSV", csv)
    monkeypatch.setattr(dm_mod, "DEFAULT_DB", db)

    # ensure no DB exists yet
    assert not db.exists()
    with pytest.warns(UserWarning, match="migrating"):
        dm = DataManager()
    # database is created and contains the record
    assert db.exists()
    rows = dm.load_all()
    assert rows and rows[0].field1.lower() == "foo"

    # simulate empty db scenario: close connection then wipe its contents
    if hasattr(dm._backend, '_reset_conn'):
        dm._backend._reset_conn()
    import sqlite3
    # remove all rows from the records table, leaving an empty DB file
    conn = sqlite3.connect(str(db))
    try:
        conn.execute("DELETE FROM records")
        conn.commit()
    finally:
        conn.close()
    # now CSV still present, should migrate again and repopulate DB
    with pytest.warns(UserWarning, match="migrating"):
        dm2 = DataManager()
    rows2 = dm2.load_all()
    assert rows2 and rows2[0].field1.lower() == "foo"


def test_default_data_manager_prefers_populated_db_over_legacy_csv(tmp_path: Path, monkeypatch):
    csv = tmp_path / "data.csv"
    csv.write_text("id,field1\n1,csv-row\n", encoding="utf-8")
    db = tmp_path / "data.db"

    seeded = DataManager(db)
    seeded.save(Record(field1="db row"))

    import gp_data.data_manager as dm_mod
    monkeypatch.setattr(dm_mod, "DEFAULT_CSV", csv)
    monkeypatch.setattr(dm_mod, "DEFAULT_DB", db)

    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        dm = DataManager()

    rows = dm.load_all()

    assert len(recorded) == 0
    assert rows and rows[0].field1.lower() == "db row"
