"""Validation primitives shared by the scientific domain.

The domain raises :class:`DomainValidationError` at construction time.  This
keeps invalid probabilities, impossible date ranges, and look-ahead data from
travelling deeper into the application layer.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .observations import Observation, VintageMode


class DomainValidationError(ValueError):
    """Raised when a scientific-domain invariant is violated."""


class ValidationSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """A machine-readable validation result for non-throwing audits."""

    code: str
    message: str
    severity: ValidationSeverity = ValidationSeverity.ERROR
    field: str | None = None


def require_non_empty(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DomainValidationError(f"{field} must be a non-empty string")
    return value


def require_finite(value: float, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DomainValidationError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise DomainValidationError(f"{field} must be finite")
    return result


def require_probability(value: float, field: str = "probability") -> float:
    result = require_finite(value, field)
    if not 0.0 <= result <= 1.0:
        raise DomainValidationError(f"{field} must be between 0 and 1 inclusive")
    return result


def require_positive(value: float, field: str, *, allow_zero: bool = False) -> float:
    result = require_finite(value, field)
    if result < 0.0 or (result == 0.0 and not allow_zero):
        qualifier = "non-negative" if allow_zero else "positive"
        raise DomainValidationError(f"{field} must be {qualifier}")
    return result


def require_date(value: date, field: str) -> date:
    # datetime subclasses date but carries a time-zone-sensitive meaning.  The
    # scientific contracts in this package deliberately use calendar dates.
    if type(value) is not date:
        raise DomainValidationError(f"{field} must be a datetime.date")
    return value


def require_date_order(
    start: date,
    end: date,
    *,
    start_field: str = "start",
    end_field: str = "end",
    allow_equal: bool = True,
) -> None:
    require_date(start, start_field)
    require_date(end, end_field)
    valid = start <= end if allow_equal else start < end
    if not valid:
        operator = "on or before" if allow_equal else "before"
        raise DomainValidationError(f"{start_field} must be {operator} {end_field}")


def require_probability_sequence(
    values: Sequence[float], *, field: str = "probabilities"
) -> tuple[float, ...]:
    if not values:
        raise DomainValidationError(f"{field} must not be empty")
    return tuple(require_probability(value, f"{field}[{index}]") for index, value in enumerate(values))


def validate_chronological_split(
    *,
    training_end: date,
    calibration_start: date,
    calibration_end: date,
    test_start: date,
) -> None:
    """Enforce disjoint chronological training, calibration, and test windows."""

    for value, field in (
        (training_end, "training_end"),
        (calibration_start, "calibration_start"),
        (calibration_end, "calibration_end"),
        (test_start, "test_start"),
    ):
        require_date(value, field)
    if not training_end < calibration_start <= calibration_end < test_start:
        raise DomainValidationError(
            "expected training_end < calibration_start <= calibration_end < test_start"
        )


def audit_point_in_time(
    observations: Iterable[Observation],
    *,
    analysis_date: date,
    mode: VintageMode,
) -> tuple[ValidationIssue, ...]:
    """Return visibility issues without mutating or silently dropping data."""

    require_date(analysis_date, "analysis_date")
    issues: list[ValidationIssue] = []
    for observation in observations:
        if not observation.is_visible_as_of(analysis_date, mode=mode):
            issues.append(
                ValidationIssue(
                    code="LOOK_AHEAD_OBSERVATION",
                    field="release_date",
                    message=(
                        f"{observation.feature_id} for {observation.period_end.isoformat()} "
                        f"was not visible on {analysis_date.isoformat()} in {mode.value} mode"
                    ),
                )
            )
    return tuple(issues)


def ensure_no_point_in_time_issues(
    observations: Iterable[Observation],
    *,
    analysis_date: date,
    mode: VintageMode,
) -> None:
    issues = audit_point_in_time(observations, analysis_date=analysis_date, mode=mode)
    if issues:
        raise DomainValidationError("; ".join(issue.message for issue in issues))


def enum_value(value: Any) -> Any:
    """Return a JSON-friendly enum value while leaving other objects unchanged."""

    return getattr(value, "value", value)

