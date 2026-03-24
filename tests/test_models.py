from datetime import datetime, timezone
import json

import pytest

from gp_data.formulas import get_active_formula_expressions, set_active_formula_expressions, validate_formula_expressions
from gp_data.models import Record, calculate_cash_margin, calculate_field6, calculate_gp, calculate_gp70


def test_record_roundtrip():
    changed_at = datetime.now(timezone.utc)
    r = Record(
        field1="Alpha",
        field2="Beta",
        field3="3.14",
        last_numeric_field="field7",
        last_numeric_from="1.50",
        last_numeric_to="2.50",
        last_numeric_changed_at=changed_at,
    )
    assert r.field3 == 3.14
    assert r.last_numeric_from == 1.5
    assert r.last_numeric_to == 2.5
    d = r.to_dict()
    r2 = Record.from_dict(d)
    assert r2.id == r.id
    assert r2.field1 == "Alpha"
    assert r2.last_numeric_field == "field7"
    assert r2.last_numeric_from == pytest.approx(1.5)
    assert r2.last_numeric_to == pytest.approx(2.5)


def test_calculation_helpers():
    # gp with valid inputs
    assert calculate_gp(2.0, 5.0) == pytest.approx(1 - (2.0 * 1.2) / 5.0)
    # gp when menu is zero or missing
    assert calculate_gp(2.0, 0) is None
    assert calculate_gp(None, 5.0) is None

    # cash margin
    assert calculate_cash_margin(2.0, 5.0) == pytest.approx(5.0 - (2.0 * 1.2))
    assert calculate_cash_margin(None, 5.0) is None

    # gp70
    assert calculate_gp70(3.0) == pytest.approx(3.0 * 100.0 / 30.0 * 1.2)
    assert calculate_gp70(None) is None


def test_calculate_field6_helper():
    assert calculate_field6(20, 5) == pytest.approx(4.0)
    assert calculate_field6("£20.00", "5") == pytest.approx(4.0)
    assert calculate_field6(20, 0) is None
    assert calculate_field6(20, "abc") is None
    assert calculate_field6("bad", 5) is None


def test_calculation_helpers_use_active_formula_expressions():
    set_active_formula_expressions(
        {
            "field6": "field3 / field5 * 2",
            "gp": "field6 / field7",
            "cash_margin": "field7 - field6",
            "gp70": "field6 * 2",
        }
    )

    assert get_active_formula_expressions()["gp70"] == "field6 * 2"
    assert calculate_field6(20, 5) == pytest.approx(8.0)
    assert calculate_gp(2.0, 5.0) == pytest.approx(0.4)
    assert calculate_cash_margin(2.0, 5.0) == pytest.approx(3.0)
    assert calculate_gp70(3.0) == pytest.approx(6.0)


def test_validate_formula_expressions_rejects_disallowed_field_names():
    with pytest.raises(ValueError, match="field3, field5"):
        validate_formula_expressions({"field6": "field7 / 2"})


def test_record_ignores_malformed_numeric_change_history_string():
    record = Record(field1="Alpha", numeric_change_history="{not-json")

    assert record.numeric_change_history == []


def test_record_to_dict_serializes_metrics_and_change_history():
    changed_at = datetime(2026, 3, 16, 12, 0, tzinfo=timezone.utc)
    record = Record(
        field1="alpha",
        field6="2.00",
        field7="5.00",
        last_numeric_changed_at=changed_at,
        numeric_change_history=[
            {
                "field_name": "field7",
                "from_value": 4.5,
                "to_value": 5.0,
                "changed_at": changed_at,
            }
        ],
    )

    data = record.to_dict()

    assert data["field1"] == "Alpha"
    assert datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")).tzinfo is not None
    assert datetime.fromisoformat(data["last_numeric_changed_at"].replace("Z", "+00:00")) == changed_at
    assert data["gp"] == pytest.approx(0.52)
    assert data["cash_margin"] == pytest.approx(2.6)
    assert data["gp70"] == pytest.approx(8.0)
    history = json.loads(data["numeric_change_history"])

    assert len(history) == 1
    assert history[0]["field_name"] == "field7"
    assert history[0]["from_value"] == 4.5
    assert history[0]["to_value"] == 5.0
    assert datetime.fromisoformat(history[0]["changed_at"].replace("Z", "+00:00")) == changed_at
