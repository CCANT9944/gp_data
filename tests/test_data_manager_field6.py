from pathlib import Path

from gp_data.data_manager import DataManager
from gp_data.models import Record


def test_field6_stored_as_numeric(tmp_path: Path):
    p = tmp_path / "data.db"
    dm = DataManager(p)

    # include field7 so derived metrics are non-empty
    r = Record(field1="one", field3=10, field5="4", field6=2.5, field7=10.0)
    dm.save(r)

    # loading should parse field6 as float and field1 normalized
    rows = dm.load_all()
    assert len(rows) == 1
    assert rows[0].field6 == 2.5
    assert rows[0].field1 == "One"


def test_loads_currency_string_in_csv(tmp_path: Path):
    p = tmp_path / "data.csv"
    import csv

    fieldnames = [
        "id",
        "field1",
        "field2",
        "field3",
        "field4",
        "field5",
        "field6",
        "gp",
        "cash_margin",
        "gp70",
        "created_at",
    ]

    # write a row where field6 is stored as a currency string (legacy); derived cols empty
    with p.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow({
            "id": "id1",
            "field1": "one",
            "field3": "",
            "field4": "10",
            "field5": "2",
            "field6": "\u00A32.50",
            # gp/cash_margin/gp70 left empty on purpose (legacy)
            "created_at": "2020-01-01T00:00:00Z",
        })

    dm = DataManager(p)
    records = dm.load_all()
    assert len(records) == 1
    assert records[0].field6 == 2.5
    # legacy CSV which contained lower-case field1 will be normalized by model
    assert records[0].field1 == "One"


def test_loads_currency_string_in_csv(tmp_path: Path):
    p = tmp_path / "data.csv"
    import csv

    fieldnames = [
        "id",
        "field1",
        "field2",
        "field3",
        "field4",
        "field5",
        "field6",
        "gp",
        "cash_margin",
        "gp70",
        "created_at",
    ]

    # write a row where field6 is stored as a currency string (legacy); derived cols empty
    with p.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow({
            "id": "id1",
            "field1": "one",
            "field3": "",
            "field4": "10",
            "field5": "2",
            "field6": "\u00A32.50",
            # gp/cash_margin/gp70 left empty on purpose (legacy)
            "created_at": "2020-01-01T00:00:00Z",
        })

    dm = DataManager(p)
    records = dm.load_all()
    assert len(records) == 1
    assert records[0].field6 == 2.5
    # legacy CSV which contained lower-case field1 will be normalized by model
    assert records[0].field1 == "One"

