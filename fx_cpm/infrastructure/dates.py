"""Strict date helpers shared by adapters and launchers."""

from __future__ import annotations

import calendar
from datetime import date, datetime, timezone
from typing import Any


def parse_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        raise ValueError("date value is empty")
    try:
        return date.fromisoformat(text[:10])
    except ValueError as exc:
        raise ValueError(f"invalid ISO date: {value!r}") from exc


def parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        result = value
    else:
        text = str(value).strip().replace("Z", "+00:00")
        try:
            result = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(f"invalid ISO timestamp: {value!r}") from exc
    return result if result.tzinfo is not None else result.replace(tzinfo=timezone.utc)


def add_months(value: date, months: int) -> date:
    index = value.year * 12 + value.month - 1 + months
    year, zero_based_month = divmod(index, 12)
    month = zero_based_month + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def horizon_end(analysis_date: date, horizon: Any) -> date:
    raw = str(getattr(horizon, "value", horizon)).strip().lower().replace("_", "")
    aliases = {"30d": 30, "90d": 90, "180d": 180}
    if raw in aliases:
        from datetime import timedelta

        return analysis_date + timedelta(days=aliases[raw])
    month_aliases = {"12m": 12, "24m": 24, "36m": 36, "1y": 12, "2y": 24, "3y": 36}
    if raw in month_aliases:
        return add_months(analysis_date, month_aliases[raw])
    raise ValueError(f"unsupported horizon: {horizon!r}")


def contains(start: date, end: date | None, value: date) -> bool:
    return start <= value and (end is None or value <= end)
