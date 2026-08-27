"""Training-window-only global-factor adjustment for FX returns."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType

from .validation import (
    DomainValidationError,
    require_date,
    require_finite,
    require_non_empty,
    require_positive,
)


def _freeze_factors(values: Mapping[str, float]) -> Mapping[str, float]:
    frozen: dict[str, float] = {}
    for raw_name, value in values.items():
        name = require_non_empty(raw_name, "factor name").strip()
        frozen[name] = require_finite(value, f"factors[{name}]")
    return MappingProxyType(frozen)


@dataclass(frozen=True, slots=True)
class GlobalFactorObservation:
    observed_on: date
    available_on: date
    fx_return: float
    factors: Mapping[str, float]

    def __post_init__(self) -> None:
        require_date(self.observed_on, "observed_on")
        require_date(self.available_on, "available_on")
        if self.available_on < self.observed_on:
            raise DomainValidationError("available_on cannot precede observed_on")
        object.__setattr__(self, "fx_return", require_finite(self.fx_return, "fx_return"))
        object.__setattr__(self, "factors", _freeze_factors(self.factors))


@dataclass(frozen=True, slots=True)
class FactorTrainingWindow:
    start: date
    end: date

    def __post_init__(self) -> None:
        require_date(self.start, "training_window.start")
        require_date(self.end, "training_window.end")
        if self.end < self.start:
            raise DomainValidationError("training window end must be on or after start")

    def contains(self, value: date) -> bool:
        require_date(value, "date")
        return self.start <= value <= self.end


@dataclass(frozen=True, slots=True)
class FXResidualEstimate:
    observed_on: date
    observed_return: float
    expected_global_factor_return: float
    residual_return: float
    standardized_residual: float
    training_window_end: date
    interpretation: str = "COUNTRY_SPECIFIC_RESIDUAL_NOT_CAUSAL_EFFECT"


@dataclass(frozen=True, slots=True)
class GlobalFactorModelFit:
    """Auditable linear fit whose parameters use only its training window."""

    factor_names: tuple[str, ...]
    intercept: float
    coefficients: Mapping[str, float]
    residual_standard_deviation: float
    training_window: FactorTrainingWindow
    as_of: date
    training_observation_dates: tuple[date, ...]
    latest_training_availability: date
    ignored_observations: int
    ridge_penalty: float

    def __post_init__(self) -> None:
        if not self.factor_names or len(set(self.factor_names)) != len(self.factor_names):
            raise DomainValidationError("factor_names must be non-empty and unique")
        for name in self.factor_names:
            require_non_empty(name, "factor_name")
        object.__setattr__(self, "intercept", require_finite(self.intercept, "intercept"))
        if set(self.coefficients) != set(self.factor_names):
            raise DomainValidationError("coefficients must exactly match factor_names")
        coefficients = {
            name: require_finite(self.coefficients[name], f"coefficients[{name}]")
            for name in self.factor_names
        }
        object.__setattr__(self, "coefficients", MappingProxyType(coefficients))
        object.__setattr__(
            self,
            "residual_standard_deviation",
            require_positive(
                self.residual_standard_deviation, "residual_standard_deviation"
            ),
        )
        require_date(self.as_of, "as_of")
        if self.training_window.end > self.as_of:
            raise DomainValidationError("training window cannot end after as_of")
        if not self.training_observation_dates:
            raise DomainValidationError("training_observation_dates must not be empty")
        if tuple(sorted(self.training_observation_dates)) != self.training_observation_dates:
            raise DomainValidationError("training_observation_dates must be chronological")
        if any(
            not self.training_window.contains(observed_on)
            for observed_on in self.training_observation_dates
        ):
            raise DomainValidationError("training observation lies outside the training window")
        require_date(self.latest_training_availability, "latest_training_availability")
        if self.latest_training_availability > self.training_window.end:
            raise DomainValidationError(
                "training data availability cannot be after the training window"
            )
        if self.ignored_observations < 0:
            raise DomainValidationError("ignored_observations cannot be negative")
        require_positive(self.ridge_penalty, "ridge_penalty", allow_zero=True)

    @property
    def n_observations(self) -> int:
        return len(self.training_observation_dates)

    def expected_return(self, factors: Mapping[str, float]) -> float:
        if set(factors) != set(self.factor_names):
            raise DomainValidationError("scoring factors must exactly match fitted factor_names")
        return self.intercept + math.fsum(
            self.coefficients[name] * require_finite(factors[name], f"factors[{name}]")
            for name in self.factor_names
        )

    def estimate(
        self, observation: GlobalFactorObservation, *, as_of: date
    ) -> FXResidualEstimate:
        require_date(as_of, "as_of")
        if as_of < self.as_of:
            raise DomainValidationError("cannot use a fitted model before its as_of date")
        if observation.observed_on > as_of or observation.available_on > as_of:
            raise DomainValidationError("cannot score an FX observation not visible as_of")
        expected = self.expected_return(observation.factors)
        residual = observation.fx_return - expected
        return FXResidualEstimate(
            observed_on=observation.observed_on,
            observed_return=observation.fx_return,
            expected_global_factor_return=expected,
            residual_return=residual,
            standardized_residual=residual / self.residual_standard_deviation,
            training_window_end=self.training_window.end,
        )


def _solve_linear_system(matrix: list[list[float]], vector: list[float]) -> tuple[float, ...]:
    """Solve a small dense system with deterministic partial-pivot elimination."""

    size = len(vector)
    augmented = [row[:] + [vector[index]] for index, row in enumerate(matrix)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) <= 1e-12:
            raise DomainValidationError(
                "global-factor design is singular; remove collinear factors or add ridge_penalty"
            )
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        pivot_value = augmented[column][column]
        augmented[column] = [value / pivot_value for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            multiplier = augmented[row][column]
            if multiplier == 0.0:
                continue
            augmented[row] = [
                current - multiplier * pivot_current
                for current, pivot_current in zip(
                    augmented[row], augmented[column], strict=True
                )
            ]
    return tuple(augmented[row][-1] for row in range(size))


def fit_global_factor_model(
    observations: Sequence[GlobalFactorObservation],
    *,
    factor_names: Sequence[str],
    training_window: FactorTrainingWindow,
    as_of: date,
    ridge_penalty: float = 0.0,
) -> GlobalFactorModelFit:
    """Fit an intercept and factor loadings using only visible training rows.

    Rows outside the explicit training window, or unavailable by the training
    window end, are counted as ignored and cannot affect coefficients or
    residual scale.  ``as_of`` must be no earlier than that cutoff.
    """

    require_date(as_of, "as_of")
    if training_window.end > as_of:
        raise DomainValidationError("training window cannot end after as_of")
    names = tuple(require_non_empty(name, "factor_name").strip() for name in factor_names)
    if not names or len(set(names)) != len(names):
        raise DomainValidationError("factor_names must be non-empty and unique")
    ridge_penalty = require_positive(ridge_penalty, "ridge_penalty", allow_zero=True)
    eligible = tuple(
        sorted(
            (
                observation
                for observation in observations
                if training_window.contains(observation.observed_on)
                and observation.available_on <= training_window.end
            ),
            key=lambda observation: (observation.observed_on, observation.available_on),
        )
    )
    parameter_count = len(names) + 1
    if len(eligible) <= parameter_count:
        raise DomainValidationError(
            "global-factor fit requires more visible training rows than parameters"
        )
    rows: list[tuple[float, ...]] = []
    targets: list[float] = []
    for observation in eligible:
        if set(observation.factors) != set(names):
            missing = set(names) - set(observation.factors)
            extra = set(observation.factors) - set(names)
            raise DomainValidationError(
                "training factors must exactly match factor_names; "
                f"missing={sorted(missing)}, extra={sorted(extra)}"
            )
        rows.append((1.0, *(observation.factors[name] for name in names)))
        targets.append(observation.fx_return)
    gram = [[0.0 for _ in range(parameter_count)] for _ in range(parameter_count)]
    moment = [0.0 for _ in range(parameter_count)]
    for row, target in zip(rows, targets, strict=True):
        for left in range(parameter_count):
            moment[left] += row[left] * target
            for right in range(parameter_count):
                gram[left][right] += row[left] * row[right]
    for index in range(1, parameter_count):
        gram[index][index] += ridge_penalty
    fitted = _solve_linear_system(gram, moment)
    residuals = tuple(
        target - math.fsum(coefficient * value for coefficient, value in zip(fitted, row))
        for row, target in zip(rows, targets, strict=True)
    )
    degrees_of_freedom = len(residuals) - parameter_count
    residual_scale = math.sqrt(
        math.fsum(residual * residual for residual in residuals) / degrees_of_freedom
    )
    if residual_scale <= 1e-12:
        raise DomainValidationError(
            "training residual scale is zero; standardized FX residual is undefined"
        )
    return GlobalFactorModelFit(
        factor_names=names,
        intercept=fitted[0],
        coefficients={name: fitted[index + 1] for index, name in enumerate(names)},
        residual_standard_deviation=residual_scale,
        training_window=training_window,
        as_of=as_of,
        training_observation_dates=tuple(item.observed_on for item in eligible),
        latest_training_availability=max(item.available_on for item in eligible),
        ignored_observations=len(observations) - len(eligible),
        ridge_penalty=ridge_penalty,
    )
