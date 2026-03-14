from datetime import datetime, timezone

import pytest

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
