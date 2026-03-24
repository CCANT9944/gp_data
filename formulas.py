from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Mapping


DEFAULT_FORMULA_EXPRESSIONS: dict[str, str] = {
    "field6": "field3 / field5",
    "gp": "1 - (field6 * 1.2) / field7",
    "cash_margin": "field7 - (field6 * 1.2)",
    "gp70": "field6 * 100 / 30 * 1.2",
}

FORMULA_DISPLAY_NAMES: dict[str, str] = {
    "field6": "Field 6",
    "gp": "GP",
    "cash_margin": "Cash margin",
    "gp70": "WITH 70% GP",
}

ALLOWED_FORMULA_VARIABLES: dict[str, frozenset[str]] = {
    "field6": frozenset({"field3", "field5"}),
    "gp": frozenset({"field6", "field7"}),
    "cash_margin": frozenset({"field6", "field7"}),
    "gp70": frozenset({"field6"}),
}


@dataclass(frozen=True)
class _CompiledFormula:
    key: str
    expression: str
    referenced_names: frozenset[str]
    code: object


class FormulaValidationError(ValueError):
    pass


def _formula_label(formula_key: str) -> str:
    return FORMULA_DISPLAY_NAMES.get(formula_key, formula_key)


def _validate_expression_node(node: ast.AST, formula_key: str, referenced_names: set[str]) -> None:
    if isinstance(node, ast.Expression):
        _validate_expression_node(node.body, formula_key, referenced_names)
        return
    if isinstance(node, ast.BinOp):
        if not isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            raise FormulaValidationError(f"{_formula_label(formula_key)} formula only supports +, -, *, and / operators.")
        _validate_expression_node(node.left, formula_key, referenced_names)
        _validate_expression_node(node.right, formula_key, referenced_names)
        return
    if isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, (ast.UAdd, ast.USub)):
            raise FormulaValidationError(f"{_formula_label(formula_key)} formula only supports unary + and - operators.")
        _validate_expression_node(node.operand, formula_key, referenced_names)
        return
    if isinstance(node, ast.Name):
        allowed_names = ALLOWED_FORMULA_VARIABLES[formula_key]
        if node.id not in allowed_names:
            allowed_description = ", ".join(sorted(allowed_names))
            raise FormulaValidationError(
                f"{_formula_label(formula_key)} formula can only use these field names: {allowed_description}."
            )
        referenced_names.add(node.id)
        return
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return
    raise FormulaValidationError(
        f"{_formula_label(formula_key)} formula can only use numbers, field names, parentheses, and +, -, *, / operators."
    )


def _compile_formula(formula_key: str, expression: str) -> _CompiledFormula:
    normalized_expression = str(expression).strip()
    if formula_key not in DEFAULT_FORMULA_EXPRESSIONS:
        raise FormulaValidationError(f"Unknown formula key: {formula_key}")
    if not normalized_expression:
        raise FormulaValidationError(f"{_formula_label(formula_key)} formula cannot be empty.")

    try:
        parsed = ast.parse(normalized_expression, mode="eval")
    except SyntaxError as exc:
        raise FormulaValidationError(f"{_formula_label(formula_key)} formula is not valid syntax.") from exc

    referenced_names: set[str] = set()
    _validate_expression_node(parsed, formula_key, referenced_names)
    code = compile(parsed, f"<{formula_key}_formula>", "eval")
    return _CompiledFormula(
        key=formula_key,
        expression=normalized_expression,
        referenced_names=frozenset(referenced_names),
        code=code,
    )


def validate_formula_expressions(raw_expressions: Mapping[str, object] | None) -> dict[str, str]:
    source = raw_expressions if isinstance(raw_expressions, Mapping) else {}
    validated: dict[str, str] = {}
    for formula_key, default_expression in DEFAULT_FORMULA_EXPRESSIONS.items():
        raw_value = source.get(formula_key, default_expression)
        compiled = _compile_formula(formula_key, str(raw_value).strip() if raw_value is not None else "")
        validated[formula_key] = compiled.expression
    return validated


def normalized_formula_expressions(raw_expressions: Mapping[str, object] | None) -> dict[str, str]:
    source = raw_expressions if isinstance(raw_expressions, Mapping) else {}
    normalized: dict[str, str] = {}
    for formula_key, default_expression in DEFAULT_FORMULA_EXPRESSIONS.items():
        raw_value = source.get(formula_key, default_expression)
        candidate = str(raw_value).strip() if raw_value is not None else ""
        try:
            normalized[formula_key] = _compile_formula(formula_key, candidate).expression
        except FormulaValidationError:
            normalized[formula_key] = default_expression
    return normalized


def _compile_formula_expressions(expressions: Mapping[str, object] | None) -> dict[str, _CompiledFormula]:
    validated = validate_formula_expressions(expressions)
    return {
        formula_key: _compile_formula(formula_key, expression)
        for formula_key, expression in validated.items()
    }


_ACTIVE_FORMULAS: dict[str, _CompiledFormula] = _compile_formula_expressions(DEFAULT_FORMULA_EXPRESSIONS)


def get_active_formula_expressions() -> dict[str, str]:
    return {formula_key: compiled.expression for formula_key, compiled in _ACTIVE_FORMULAS.items()}


def set_active_formula_expressions(expressions: Mapping[str, object] | None) -> dict[str, str]:
    global _ACTIVE_FORMULAS
    compiled = _compile_formula_expressions(expressions)
    _ACTIVE_FORMULAS = compiled
    return get_active_formula_expressions()


def reset_active_formula_expressions() -> None:
    set_active_formula_expressions(DEFAULT_FORMULA_EXPRESSIONS)


def evaluate_formula(formula_key: str, values: Mapping[str, object]) -> float | None:
    compiled = _ACTIVE_FORMULAS.get(formula_key)
    if compiled is None:
        return None

    resolved_values: dict[str, float] = {}
    for name in compiled.referenced_names:
        raw_value = values.get(name)
        if raw_value is None:
            return None
        try:
            resolved_values[name] = float(raw_value)
        except (TypeError, ValueError):
            return None

    try:
        result = eval(compiled.code, {"__builtins__": {}}, resolved_values)
    except (ArithmeticError, NameError, SyntaxError, TypeError, ValueError):
        return None

    try:
        return float(result)
    except (TypeError, ValueError):
        return None