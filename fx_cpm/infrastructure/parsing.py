"""Conservative parsing helpers: missing text remains missing, never zero."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping

MISSING_MARKERS = frozenset({"", "na", "n/a", "nan", "null", "none", "..", "—", "-"})


def parse_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise ValueError("boolean is not a numeric observation")
    text = str(value).strip()
    if text.lower() in MISSING_MARKERS:
        return None
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    text = text.replace(",", "").replace("%", "").strip()
    try:
        parsed = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"invalid numeric value: {value!r}") from exc
    return -parsed if negative else parsed


def parse_float(value: Any, *, percent: bool = False) -> float | None:
    parsed = parse_decimal(value)
    if parsed is None:
        return None
    result = float(parsed)
    return result / 100.0 if percent else result


def require_columns(row: Mapping[str, Any], columns: Iterable[str]) -> None:
    missing = [column for column in columns if column not in row]
    if missing:
        raise ValueError("missing required columns: " + ", ".join(sorted(missing)))
