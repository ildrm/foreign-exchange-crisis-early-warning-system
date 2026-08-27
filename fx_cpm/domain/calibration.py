"""Dependency-free probability calibration records and evaluation math."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from .taxonomy import ForecastHorizon, HazardType
from .validation import (
    DomainValidationError,
    require_date,
    require_finite,
    require_non_empty,
    require_probability,
)


class CalibrationMethod(StrEnum):
    NONE = "none"
    PLATT = "platt"
    LOGISTIC = "platt"
    ISOTONIC = "isotonic"
    BETA = "beta"
    HORIZON_SPECIFIC = "horizon_specific"


class CalibrationStatus(StrEnum):
    ACCEPTABLE = "acceptable"
    WEAK = "weak"
    INSUFFICIENT_EVENTS = "insufficient_events"
    UNCALIBRATED = "uncalibrated"
    FAILED = "failed"

    @property
    def permits_severe_alert(self) -> bool:
        return self is CalibrationStatus.ACCEPTABLE


def _validated_pairs(
    probabilities: Sequence[float], outcomes: Sequence[int | bool]
) -> tuple[tuple[float, ...], tuple[int, ...]]:
    if len(probabilities) != len(outcomes):
        raise DomainValidationError("probabilities and outcomes must have equal length")
    if not probabilities:
        raise DomainValidationError("at least one prediction is required")
    clean_probabilities = tuple(
        require_probability(value, f"probabilities[{index}]")
        for index, value in enumerate(probabilities)
    )
    clean_outcomes: list[int] = []
    for index, value in enumerate(outcomes):
        if value not in (0, 1, False, True):
            raise DomainValidationError(f"outcomes[{index}] must be binary")
        clean_outcomes.append(int(value))
    return clean_probabilities, tuple(clean_outcomes)


def empirical_base_rate(outcomes: Sequence[int | bool]) -> float:
    if not outcomes:
        raise DomainValidationError("base rate requires at least one outcome")
    clean: list[int] = []
    for index, value in enumerate(outcomes):
        if value not in (0, 1, False, True):
            raise DomainValidationError(f"outcomes[{index}] must be binary")
        clean.append(int(value))
    return math.fsum(clean) / len(clean)


def brier_score(probabilities: Sequence[float], outcomes: Sequence[int | bool]) -> float:
    probabilities, outcomes = _validated_pairs(probabilities, outcomes)
    return math.fsum((probability - outcome) ** 2 for probability, outcome in zip(probabilities, outcomes, strict=True)) / len(probabilities)


def binary_log_loss(
    probabilities: Sequence[float],
    outcomes: Sequence[int | bool],
    *,
    epsilon: float = 1e-15,
) -> float:
    probabilities, outcomes = _validated_pairs(probabilities, outcomes)
    epsilon = require_probability(epsilon, "epsilon")
    if epsilon <= 0.0 or epsilon >= 0.5:
        raise DomainValidationError("epsilon must lie strictly between 0 and 0.5")
    total = 0.0
    for probability, outcome in zip(probabilities, outcomes, strict=True):
        clipped = min(max(probability, epsilon), 1.0 - epsilon)
        total -= outcome * math.log(clipped) + (1 - outcome) * math.log1p(-clipped)
    return total / len(probabilities)


# Familiar metric alias.
log_loss = binary_log_loss


@dataclass(frozen=True, slots=True)
class CalibrationBin:
    lower_bound: float
    upper_bound: float
    count: int
    mean_prediction: float | None
    observed_frequency: float | None

    def __post_init__(self) -> None:
        require_probability(self.lower_bound, "lower_bound")
        require_probability(self.upper_bound, "upper_bound")
        if self.upper_bound <= self.lower_bound:
            raise DomainValidationError("calibration bin bounds must increase")
        if self.count < 0:
            raise DomainValidationError("calibration bin count cannot be negative")
        if self.count == 0 and (
            self.mean_prediction is not None or self.observed_frequency is not None
        ):
            raise DomainValidationError("empty bins cannot have means or frequencies")
        if self.count > 0:
            if self.mean_prediction is None or self.observed_frequency is None:
                raise DomainValidationError("non-empty bins require means and frequencies")
            require_probability(self.mean_prediction, "mean_prediction")
            require_probability(self.observed_frequency, "observed_frequency")


def calibration_bins(
    probabilities: Sequence[float],
    outcomes: Sequence[int | bool],
    *,
    n_bins: int = 10,
) -> tuple[CalibrationBin, ...]:
    probabilities, outcomes = _validated_pairs(probabilities, outcomes)
    if isinstance(n_bins, bool) or not isinstance(n_bins, int) or n_bins < 2:
        raise DomainValidationError("n_bins must be an integer of at least two")
    members: list[list[tuple[float, int]]] = [[] for _ in range(n_bins)]
    for probability, outcome in zip(probabilities, outcomes, strict=True):
        # p=1 belongs in the final bin rather than an out-of-range bin.
        index = min(int(probability * n_bins), n_bins - 1)
        members[index].append((probability, outcome))
    result: list[CalibrationBin] = []
    for index, values in enumerate(members):
        lower = index / n_bins
        upper = (index + 1) / n_bins
        if not values:
            result.append(CalibrationBin(lower, upper, 0, None, None))
            continue
        count = len(values)
        result.append(
            CalibrationBin(
                lower,
                upper,
                count,
                math.fsum(item[0] for item in values) / count,
                math.fsum(item[1] for item in values) / count,
            )
        )
    return tuple(result)


def expected_calibration_error(
    probabilities: Sequence[float],
    outcomes: Sequence[int | bool],
    *,
    n_bins: int = 10,
) -> float:
    bins = calibration_bins(probabilities, outcomes, n_bins=n_bins)
    total = sum(item.count for item in bins)
    return math.fsum(
        (item.count / total) * abs(item.mean_prediction - item.observed_frequency)
        for item in bins
        if item.count and item.mean_prediction is not None and item.observed_frequency is not None
    )


def _clip_probability(probability: float, epsilon: float = 1e-12) -> float:
    probability = require_probability(probability)
    return min(max(probability, epsilon), 1.0 - epsilon)


def logit(probability: float) -> float:
    probability = _clip_probability(probability)
    return math.log(probability) - math.log1p(-probability)


def logistic(value: float) -> float:
    value = require_finite(value, "log_odds")
    if value >= 0:
        inverse = math.exp(-value)
        return 1.0 / (1.0 + inverse)
    exponential = math.exp(value)
    return exponential / (1.0 + exponential)


def platt_scale(raw_probability: float, *, intercept: float, slope: float) -> float:
    """Apply logistic calibration to the raw probability's log odds."""

    intercept = require_finite(intercept, "intercept")
    slope = require_finite(slope, "slope")
    return logistic(intercept + slope * logit(raw_probability))


def beta_scale(raw_probability: float, *, a: float, b: float, intercept: float) -> float:
    """Apply beta calibration ``logit(q)=a log(p)+b log(1-p)+c``."""

    probability = _clip_probability(raw_probability)
    a = require_finite(a, "a")
    b = require_finite(b, "b")
    intercept = require_finite(intercept, "intercept")
    return logistic(a * math.log(probability) + b * math.log1p(-probability) + intercept)


def isotonic_scale(
    raw_probability: float,
    *,
    thresholds: Sequence[float],
    calibrated_values: Sequence[float],
) -> float:
    """Monotone piecewise-linear interpolation over fitted isotonic knots."""

    probability = require_probability(raw_probability, "raw_probability")
    if len(thresholds) != len(calibrated_values) or not thresholds:
        raise DomainValidationError("isotonic knots and values must be non-empty and equally sized")
    knots = tuple(require_probability(value, "threshold") for value in thresholds)
    values = tuple(require_probability(value, "calibrated value") for value in calibrated_values)
    if any(right <= left for left, right in zip(knots, knots[1:], strict=False)):
        raise DomainValidationError("isotonic thresholds must be strictly increasing")
    if any(right < left for left, right in zip(values, values[1:], strict=False)):
        raise DomainValidationError("isotonic calibrated values must be non-decreasing")
    if probability <= knots[0]:
        return values[0]
    if probability >= knots[-1]:
        return values[-1]
    for left_index, (left, right) in enumerate(zip(knots, knots[1:], strict=False)):
        if left <= probability <= right:
            fraction = (probability - left) / (right - left)
            return values[left_index] + fraction * (values[left_index + 1] - values[left_index])
    raise AssertionError("validated probability must lie in an isotonic interval")


@dataclass(frozen=True, slots=True)
class CalibrationFit:
    intercept: float
    slope: float
    converged: bool
    iterations: int


def calibration_intercept_slope(
    probabilities: Sequence[float],
    outcomes: Sequence[int | bool],
    *,
    tolerance: float = 1e-10,
    max_iterations: int = 100,
) -> CalibrationFit:
    """Fit ``outcome ~ intercept + slope * logit(probability)`` by Newton updates."""

    probabilities, outcomes = _validated_pairs(probabilities, outcomes)
    if len(set(outcomes)) < 2:
        raise DomainValidationError("calibration fit requires both event and non-event outcomes")
    if isinstance(max_iterations, bool) or not isinstance(max_iterations, int) or max_iterations < 1:
        raise DomainValidationError("max_iterations must be a positive integer")
    tolerance = require_finite(tolerance, "tolerance")
    if tolerance <= 0:
        raise DomainValidationError("tolerance must be positive")
    predictors = tuple(logit(value) for value in probabilities)
    if max(predictors) - min(predictors) <= 1e-14:
        raise DomainValidationError("calibration slope is unidentified for constant predictions")
    base_rate = math.fsum(outcomes) / len(outcomes)
    intercept = logit(base_rate)
    slope = 0.0
    for iteration in range(1, max_iterations + 1):
        fitted = tuple(logistic(intercept + slope * predictor) for predictor in predictors)
        gradient_0 = math.fsum(outcome - value for outcome, value in zip(outcomes, fitted, strict=True))
        gradient_1 = math.fsum(
            (outcome - value) * predictor
            for outcome, value, predictor in zip(outcomes, fitted, predictors, strict=True)
        )
        weights = tuple(max(value * (1.0 - value), 1e-15) for value in fitted)
        info_00 = math.fsum(weights)
        info_01 = math.fsum(weight * predictor for weight, predictor in zip(weights, predictors, strict=True))
        info_11 = math.fsum(
            weight * predictor * predictor
            for weight, predictor in zip(weights, predictors, strict=True)
        )
        determinant = info_00 * info_11 - info_01 * info_01
        if abs(determinant) <= 1e-18:
            raise DomainValidationError("calibration fit information matrix is singular")
        delta_intercept = (info_11 * gradient_0 - info_01 * gradient_1) / determinant
        delta_slope = (-info_01 * gradient_0 + info_00 * gradient_1) / determinant
        intercept += delta_intercept
        slope += delta_slope
        if max(abs(delta_intercept), abs(delta_slope)) < tolerance:
            return CalibrationFit(intercept, slope, True, iteration)
    return CalibrationFit(intercept, slope, False, max_iterations)


@dataclass(frozen=True, slots=True)
class CalibrationRecord:
    method: CalibrationMethod
    period_start: date
    period_end: date
    event_count: int
    brier_score: float
    log_loss: float
    status: CalibrationStatus
    domain_min: float = 0.0
    domain_max: float = 1.0
    sample_count: int | None = None
    expected_calibration_error: float | None = None
    calibration_intercept: float | None = None
    calibration_slope: float | None = None
    hazard: HazardType | None = None
    horizon: ForecastHorizon | None = None
    version: str = "unversioned"
    test_window_start: date | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.method, CalibrationMethod):
            try:
                object.__setattr__(self, "method", CalibrationMethod(str(self.method).lower()))
            except ValueError as exc:
                raise DomainValidationError(f"invalid calibration method: {self.method!r}") from exc
        if not isinstance(self.status, CalibrationStatus):
            try:
                object.__setattr__(self, "status", CalibrationStatus(str(self.status).lower()))
            except ValueError as exc:
                raise DomainValidationError(f"invalid calibration status: {self.status!r}") from exc
        require_date(self.period_start, "period_start")
        require_date(self.period_end, "period_end")
        if self.period_end < self.period_start:
            raise DomainValidationError("calibration period ends before it starts")
        if isinstance(self.event_count, bool) or self.event_count < 0:
            raise DomainValidationError("event_count must be a non-negative integer")
        require_probability(self.brier_score, "brier_score")
        require_finite(self.log_loss, "log_loss")
        if self.log_loss < 0:
            raise DomainValidationError("log_loss cannot be negative")
        require_probability(self.domain_min, "domain_min")
        require_probability(self.domain_max, "domain_max")
        if self.domain_max < self.domain_min:
            raise DomainValidationError("calibration domain bounds are reversed")
        if self.sample_count is not None:
            if isinstance(self.sample_count, bool) or self.sample_count < 1:
                raise DomainValidationError("sample_count must be a positive integer")
            if self.event_count > self.sample_count:
                raise DomainValidationError("event_count cannot exceed sample_count")
        if self.expected_calibration_error is not None:
            require_probability(self.expected_calibration_error, "expected_calibration_error")
        for value, field in (
            (self.calibration_intercept, "calibration_intercept"),
            (self.calibration_slope, "calibration_slope"),
        ):
            if value is not None:
                require_finite(value, field)
        if self.hazard is not None and not isinstance(self.hazard, HazardType):
            object.__setattr__(self, "hazard", HazardType.parse(self.hazard))
        if self.horizon is not None and not isinstance(self.horizon, ForecastHorizon):
            object.__setattr__(self, "horizon", ForecastHorizon.parse(self.horizon))
        require_non_empty(self.version, "calibration version")
        if self.test_window_start is not None:
            require_date(self.test_window_start, "test_window_start")
            if self.test_window_start <= self.period_end:
                raise DomainValidationError(
                    "calibration period must precede the final test window"
                )
        if self.method is CalibrationMethod.NONE and self.status is CalibrationStatus.ACCEPTABLE:
            raise DomainValidationError("an uncalibrated method cannot have acceptable status")

    @property
    def calibration_period(self) -> tuple[date, date]:
        return self.period_start, self.period_end

    def in_supported_domain(self, raw_probability: float) -> bool:
        probability = require_probability(raw_probability, "raw_probability")
        return self.domain_min <= probability <= self.domain_max


def assess_calibration_status(
    *,
    event_count: int,
    ece: float,
    minimum_events: int = 20,
    maximum_acceptable_ece: float = 0.05,
) -> CalibrationStatus:
    if isinstance(event_count, bool) or event_count < 0:
        raise DomainValidationError("event_count must be a non-negative integer")
    if event_count < minimum_events:
        return CalibrationStatus.INSUFFICIENT_EVENTS
    require_probability(ece, "ece")
    require_probability(maximum_acceptable_ece, "maximum_acceptable_ece")
    return (
        CalibrationStatus.ACCEPTABLE
        if ece <= maximum_acceptable_ece
        else CalibrationStatus.WEAK
    )

