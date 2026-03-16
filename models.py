from __future__ import annotations
import json
from datetime import datetime, timezone
from typing import Optional
import uuid

from pydantic import BaseModel, Field, field_validator, ConfigDict


# helper functions are kept at module level so both the model and the UI can
# reuse the same business logic without duplicating formulas.  tests exercise
# these helpers directly.


def _normalize_title_text(value) -> Optional[str]:
    if value is None:
        return value
    normalized = str(value).strip()
    if normalized == "":
        return normalized
    return normalized.title()

def calculate_gp(cost: Optional[float], menu_price: Optional[float]) -> Optional[float]:
    """Return GP fraction (e.g. 0.52 == 52%) or ``None`` if not computable."""
    if cost is None or menu_price is None:
        return None
    try:
        if float(menu_price) == 0:
            return None
        return 1 - (float(cost) * 1.2) / float(menu_price)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def calculate_cash_margin(cost: Optional[float], menu_price: Optional[float]) -> Optional[float]:
    """Return cash margin (MenuPrice - cost*1.2) or ``None`` if inputs missing."""
    if cost is None or menu_price is None:
        return None
    try:
        return float(menu_price) - (float(cost) * 1.2)
    except (TypeError, ValueError):
        return None


def calculate_gp70(cost: Optional[float]) -> Optional[float]:
    """Return the custom 'WITH 70% GP' expression used in the UI.

    The formula may change in future; centralising it here keeps everything
    consistent.
    """
    if cost is None:
        return None
    try:
        return float(cost) * 100.0 / 30.0 * 1.2
    except (TypeError, ValueError):
        return None


def calculate_field6(total_value, units_in) -> Optional[float]:
    """Return the computed cost/unit value or ``None`` if not computable."""
    try:
        total = _parse_optional_float(total_value, "field3")
    except ValueError:
        return None
    if total is None:
        return None
    if units_in is None or units_in == "":
        return None
    try:
        units = float(str(units_in).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    if units == 0:
        return None
    return total / units


def _parse_optional_float(value, field_name: str) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        s = value.replace("£", "").replace(",", "").strip()
        if s == "" or s.upper() == "N/A":
            return None
        try:
            return float(s)
        except ValueError:
            raise ValueError(f"{field_name} must be a number or empty")
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a number or empty")


def _safe_export_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_numeric_change_history(value) -> list:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    if isinstance(value, list):
        return value
    return []


def _serialize_numeric_change_history(value) -> str:
    return json.dumps(value or [], ensure_ascii=False)


class NumericChange(BaseModel):
    field_name: str
    from_value: Optional[float] = None
    to_value: Optional[float] = None
    changed_at: datetime



class Record(BaseModel):
    """Pydantic v2-style Record model for the five input fields.

    - uses `model_config` (V2) instead of class Config
    - `field3` is validated/coerced via `@field_validator`
    - `to_dict` / `from_dict` delegate to `model_dump` / `model_validate` to
      avoid deprecated V1 APIs.
    """

    model_config = ConfigDict(from_attributes=True, extra='ignore')

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    field1: str = Field(..., min_length=1)
    field2: Optional[str] = None
    field3: Optional[float] = None
    field4: Optional[str] = None
    field5: Optional[str] = None
    field6: Optional[float] = None
    field7: Optional[float] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_numeric_field: Optional[str] = None
    last_numeric_from: Optional[float] = None
    last_numeric_to: Optional[float] = None
    last_numeric_changed_at: Optional[datetime] = None
    numeric_change_history: list[NumericChange] = Field(default_factory=list)

    @field_validator("field1", "field2", mode="before")
    def _normalize_title_fields(cls, v):
        return _normalize_title_text(v)

    @field_validator("field3", "field6", "field7", "last_numeric_from", "last_numeric_to", mode="before")
    def _parse_optional_float_fields(cls, v, info):
        return _parse_optional_float(v, info.field_name)

    @field_validator("numeric_change_history", mode="before")
    def _parse_numeric_change_history(cls, v):
        return _parse_numeric_change_history(v)

    @property
    def gp(self) -> float | None:
        """Computed GP % as a fraction (e.g. 0.52 == 52%)."""
        return calculate_gp(self.field6, self.field7)

    @property
    def cash_margin(self) -> float | None:
        """Computed cash margin (MenuPrice - cost*1.2)."""
        return calculate_cash_margin(self.field6, self.field7)

    @property
    def gp70(self) -> float | None:
        """Computed 'WITH 70% GP' value using shared formula."""
        return calculate_gp70(self.field6)

    def to_dict(self) -> dict:
        d = self.model_dump(mode="json")
        # include derived, read-only metrics so they can be exported to CSV
        d["gp"] = _safe_export_float(self.gp)
        d["cash_margin"] = _safe_export_float(self.cash_margin)
        d["gp70"] = _safe_export_float(self.gp70)
        d["numeric_change_history"] = _serialize_numeric_change_history(d.get("numeric_change_history"))
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Record":
        return cls.model_validate(data)
