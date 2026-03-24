from __future__ import annotations

from collections.abc import Mapping, Sequence

from ..formulas import get_active_formula_expressions
from ..models import calculate_cash_margin, calculate_field6, calculate_gp, calculate_gp70

EMPTY_FORMULA_PANEL_TEXT = "Select a row to view calculations. The details panel updates below the main table."


def _field_label(field_name: str, labels: Sequence[str]) -> str:
    if field_name.startswith("field") and field_name[5:].isdigit():
        index = int(field_name[5:]) - 1
        if 0 <= index < len(labels):
            return labels[index]
    return field_name


def _expression_with_labels(expression: str, labels: Sequence[str]) -> str:
    rendered = str(expression)
    for field_name in ("field7", "field6", "field5", "field4", "field3", "field2", "field1"):
        rendered = rendered.replace(field_name, _field_label(field_name, labels))
    return rendered


def _coerce_optional_float(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.replace("£", "").replace(",", "").strip()
        if not normalized or normalized.upper() == "N/A":
            return None
        try:
            return float(normalized)
        except ValueError:
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_currency(value: float | None) -> str:
    if value is None:
        return "Not available"
    return f"£{value:.2f}"


def _format_percent(value: float | None) -> str:
    if value is None:
        return "Not available"
    return f"{value * 100:.2f}%"


def _has_meaningful_values(values: Mapping[str, object] | None) -> bool:
    if not values:
        return False
    for key in ("field1", "field2", "field3", "field5", "field6", "field7"):
        value = values.get(key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return True
    return False


def build_formula_settings_overview(labels: Sequence[str], formula_expressions: Mapping[str, str] | None = None) -> str:
    expressions = dict(formula_expressions or get_active_formula_expressions())

    return "\n".join(
        [
            "Current formulas",
            "",
            f"{_field_label('field6', labels)} = {_expression_with_labels(expressions['field6'], labels)}",
            f"GP = {_expression_with_labels(expressions['gp'], labels)}",
            f"Cash margin = {_expression_with_labels(expressions['cash_margin'], labels)}",
            f"WITH 70% GP = {_expression_with_labels(expressions['gp70'], labels)}",
            "",
            "Editable formulas use stable field names in the inputs: field3, field5, field6, field7.",
            "Allowed syntax: numbers, parentheses, and +, -, *, / operators.",
        ]
    )


def build_formula_panel_text(values: Mapping[str, object] | None, labels: Sequence[str]) -> str:
    if not _has_meaningful_values(values):
        return EMPTY_FORMULA_PANEL_TEXT

    expressions = get_active_formula_expressions()

    field3_label = _field_label("field3", labels)
    field5_label = _field_label("field5", labels)
    field6_label = _field_label("field6", labels)
    field7_label = _field_label("field7", labels)

    field3_value = values.get("field3") if values is not None else None
    field5_value = values.get("field5") if values is not None else None
    field6_value = calculate_field6(field3_value, field5_value)
    if field6_value is None and values is not None:
        field6_value = _coerce_optional_float(values.get("field6"))
    field7_value = _coerce_optional_float(values.get("field7") if values is not None else None)

    gp_value = calculate_gp(field6_value, field7_value)
    cash_margin_value = calculate_cash_margin(field6_value, field7_value)
    gp70_value = calculate_gp70(field6_value)

    lines = [
        "Selected row calculations",
        "",
        f"{field6_label}",
        f"Formula: {field6_label} = {_expression_with_labels(expressions['field6'], labels)}",
        f"Inputs: {field3_label} = {_format_currency(_coerce_optional_float(field3_value))}, {field5_label} = {field5_value or 'Not available'}",
        f"Result: {_format_currency(field6_value)}",
        "",
        "GP",
        f"Formula: GP = {_expression_with_labels(expressions['gp'], labels)}",
        f"Inputs: {field6_label} = {_format_currency(field6_value)}, {field7_label} = {_format_currency(field7_value)}",
        f"Result: {_format_percent(gp_value)}",
        "",
        "Cash margin",
        f"Formula: Cash margin = {_expression_with_labels(expressions['cash_margin'], labels)}",
        f"Inputs: {field6_label} = {_format_currency(field6_value)}, {field7_label} = {_format_currency(field7_value)}",
        f"Result: {_format_currency(cash_margin_value)}",
        "",
        "WITH 70% GP",
        f"Formula: WITH 70% GP = {_expression_with_labels(expressions['gp70'], labels)}",
        f"Input: {field6_label} = {_format_currency(field6_value)}",
        f"Result: {_format_currency(gp70_value)}",
    ]
    return "\n".join(lines)
