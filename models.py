from __future__ import annotations
from datetime import datetime
from typing import Optional
import uuid

from pydantic import BaseModel, Field, field_validator, ConfigDict


# helper functions are kept at module level so both the model and the UI can
# reuse the same business logic without duplicating formulas.  tests exercise
# these helpers directly.

def calculate_gp(cost: Optional[float], menu_price: Optional[float]) -> Optional[float]:
    """Return GP fraction (e.g. 0.52 == 52%) or ``None`` if not computable."""
    if cost is None or menu_price is None:
        return None
    try:
        if float(menu_price) == 0:
            return None
        return 1 - (float(cost) * 1.2) / float(menu_price)
    except Exception:
        return None


def calculate_cash_margin(cost: Optional[float], menu_price: Optional[float]) -> Optional[float]:
    """Return cash margin (MenuPrice - cost*1.2) or ``None`` if inputs missing."""
    if cost is None or menu_price is None:
        return None
    try:
        return float(menu_price) - (float(cost) * 1.2)
    except Exception:
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
    except Exception:
        return None



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
    created_at: datetime = Field(default_factory=lambda: datetime.now(__import__('datetime').timezone.utc))

    @field_validator("field1", mode="before")
    def _normalize_field1(cls, v):
        if v is None:
            return v
        s = str(v).strip()
        if s == "":
            return s
        # Title-case each word (e.g. "mary jane" -> "Mary Jane")
        return s.title()

    @field_validator("field2", mode="before")
    def _normalize_field2(cls, v):
        if v is None:
            return v
        s = str(v).strip()
        if s == "":
            return s
        # Title-case each word
        return s.title()

    @field_validator("field3", mode="before")
    def _parse_field3(cls, v):
        if v is None or v == "":
            return None
        # accept numeric, numeric strings, or currency-formatted strings (e.g. "£15.00")
        if isinstance(v, str):
            s = v.replace("£", "").replace(",", "").strip()
            if s == "" or s.upper() == "N/A":
                return None
            try:
                return float(s)
            except Exception:
                raise ValueError("field3 must be a number or empty")
        try:
            return float(v)
        except Exception:
            raise ValueError("field3 must be a number or empty")

    @field_validator("field6", mode="before")
    def _parse_field6(cls, v):
        if v is None or v == "":
            return None
        # accept numeric, numeric strings, or currency-formatted strings (e.g. "£2.50")
        if isinstance(v, str):
            s = v.replace("£", "").replace(",", "").strip()
            if s == "" or s.upper() == "N/A":
                return None
            try:
                return float(s)
            except Exception:
                raise ValueError("field6 must be a number or currency string")
        try:
            return float(v)
        except Exception:
            raise ValueError("field6 must be a number or empty")

    @field_validator("field7", mode="before")
    def _parse_field7(cls, v):
        if v is None or v == "":
            return None
        # accept numeric, numeric strings, or currency-formatted strings
        if isinstance(v, str):
            s = v.replace("£", "").replace(",", "").strip()
            if s == "" or s.upper() == "N/A":
                return None
            try:
                return float(s)
            except Exception:
                raise ValueError("field7 must be a number or currency string")
        try:
            return float(v)
        except Exception:
            raise ValueError("field7 must be a number or empty")

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
        d = self.model_dump()
        # include derived, read-only metrics so they can be exported to CSV
        try:
            d["gp"] = None if self.gp is None else float(self.gp)
        except Exception:
            d["gp"] = None
        try:
            d["cash_margin"] = None if self.cash_margin is None else float(self.cash_margin)
        except Exception:
            d["cash_margin"] = None
        try:
            d["gp70"] = None if self.gp70 is None else float(self.gp70)
        except Exception:
            d["gp70"] = None
        # ensure created_at is JSON-friendly (ISO string)
        ca = d.get("created_at")
        if isinstance(ca, datetime):
            d["created_at"] = ca.isoformat()
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Record":
        return cls.model_validate(data)
