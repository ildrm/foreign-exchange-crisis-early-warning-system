"""Offline, regime-aware foreign-exchange stress mathematics."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .validation import (
    DomainValidationError,
    require_finite,
    require_positive,
    require_probability,
)


def z_score(value: float, mean: float, standard_deviation: float) -> float:
    value = require_finite(value, "value")
    mean = require_finite(mean, "mean")
    standard_deviation = require_positive(standard_deviation, "standard_deviation")
    return (value - mean) / standard_deviation


def sample_standard_deviation(values: Sequence[float], *, ddof: int = 1) -> float:
    if isinstance(ddof, bool) or not isinstance(ddof, int) or ddof < 0:
        raise DomainValidationError("ddof must be a non-negative integer")
    clean = tuple(require_finite(value, f"values[{index}]") for index, value in enumerate(values))
    if len(clean) <= ddof:
        raise DomainValidationError("not enough observations for the selected ddof")
    mean = math.fsum(clean) / len(clean)
    variance = math.fsum((value - mean) ** 2 for value in clean) / (len(clean) - ddof)
    return math.sqrt(variance)


def realized_volatility(
    returns: Sequence[float],
    *,
    annualization_periods: float = 252.0,
    ddof: int = 1,
) -> float:
    annualization_periods = require_positive(annualization_periods, "annualization_periods")
    return sample_standard_deviation(returns, ddof=ddof) * math.sqrt(annualization_periods)


def downside_volatility(
    returns: Sequence[float],
    *,
    target: float = 0.0,
    annualization_periods: float = 252.0,
) -> float:
    """Annualized root mean squared shortfall below ``target``."""

    if not returns:
        raise DomainValidationError("downside volatility requires at least one return")
    target = require_finite(target, "target")
    annualization_periods = require_positive(annualization_periods, "annualization_periods")
    clean = tuple(require_finite(value, f"returns[{index}]") for index, value in enumerate(returns))
    semivariance = math.fsum(min(value - target, 0.0) ** 2 for value in clean) / len(clean)
    return math.sqrt(semivariance * annualization_periods)


def maximum_drawdown(levels: Sequence[float]) -> float:
    """Return the largest peak-to-trough loss as a non-negative fraction."""

    if not levels:
        raise DomainValidationError("maximum drawdown requires at least one level")
    clean = tuple(require_positive(value, f"levels[{index}]") for index, value in enumerate(levels))
    peak = clean[0]
    largest = 0.0
    for level in clean:
        peak = max(peak, level)
        largest = max(largest, 1.0 - level / peak)
    return largest


@dataclass(frozen=True, slots=True)
class EMPWeights:
    spot: float = 1.0
    reserves: float = 1.0
    interest_rate: float = 1.0

    def __post_init__(self) -> None:
        for value, field in (
            (self.spot, "spot weight"),
            (self.reserves, "reserves weight"),
            (self.interest_rate, "interest-rate weight"),
        ):
            require_positive(value, field, allow_zero=True)
        if self.spot + self.reserves + self.interest_rate == 0:
            raise DomainValidationError("at least one EMP weight must be positive")

    def normalized(self) -> EMPWeights:
        total = self.spot + self.reserves + self.interest_rate
        return EMPWeights(self.spot / total, self.reserves / total, self.interest_rate / total)


@dataclass(frozen=True, slots=True)
class EMPComponents:
    spot_depreciation_z: float
    reserve_growth_z: float
    rate_differential_change_z: float

    def __post_init__(self) -> None:
        for value, field in (
            (self.spot_depreciation_z, "spot_depreciation_z"),
            (self.reserve_growth_z, "reserve_growth_z"),
            (self.rate_differential_change_z, "rate_differential_change_z"),
        ):
            require_finite(value, field)


def exchange_market_pressure(
    spot_depreciation_z: float,
    reserve_growth_z: float,
    rate_differential_change_z: float,
    *,
    weights: EMPWeights | tuple[float, float, float] = EMPWeights(),
    normalize_weights: bool = False,
) -> float:
    """Compute ``w_s Z(ds) - w_r Z(dreserves) + w_i Z(di)``.

    The spot quote convention must be local currency per anchor currency, so a
    positive spot change is depreciation.  Reserve *growth* is passed in, hence
    the explicit minus sign makes reserve losses increase pressure.
    """

    if not isinstance(weights, EMPWeights):
        try:
            weights = EMPWeights(*weights)
        except (TypeError, ValueError) as exc:
            raise DomainValidationError("weights must contain spot, reserve, and rate weights") from exc
    if normalize_weights:
        weights = weights.normalized()
    components = EMPComponents(
        spot_depreciation_z,
        reserve_growth_z,
        rate_differential_change_z,
    )
    return (
        weights.spot * components.spot_depreciation_z
        - weights.reserves * components.reserve_growth_z
        + weights.interest_rate * components.rate_differential_change_z
    )


def parallel_market_premium(parallel_rate: float, official_rate: float) -> float:
    """Return ``100 * (parallel / official - 1)`` for identically quoted rates."""

    parallel_rate = require_positive(parallel_rate, "parallel_rate")
    official_rate = require_positive(official_rate, "official_rate")
    return 100.0 * (parallel_rate / official_rate - 1.0)


def expected_fx_return(
    *,
    intercept: float,
    factor_values: Sequence[float],
    coefficients: Sequence[float],
) -> float:
    """Evaluate a fitted linear global/regional factor component."""

    if len(factor_values) != len(coefficients):
        raise DomainValidationError("factor_values and coefficients must have equal length")
    result = require_finite(intercept, "intercept")
    for index, (factor, coefficient) in enumerate(zip(factor_values, coefficients, strict=True)):
        result += require_finite(factor, f"factor_values[{index}]") * require_finite(
            coefficient, f"coefficients[{index}]"
        )
    return result


def residual_fx_return(observed_return: float, expected_return: float) -> float:
    return require_finite(observed_return, "observed_return") - require_finite(
        expected_return, "expected_return"
    )


def fx_surprise(
    observed_return: float,
    expected_return: float,
    conditional_standard_deviation: float,
) -> float:
    """Standardized country-specific return residual."""

    sigma = require_positive(conditional_standard_deviation, "conditional_standard_deviation")
    return residual_fx_return(observed_return, expected_return) / sigma


# Scientific synonym used in reports and source adapters.
residual_fx_stress = fx_surprise


@dataclass(frozen=True, slots=True)
class AggregateStress:
    """A transparent non-probabilistic stress index result."""

    score: float | None
    coverage: float
    contributions: tuple[tuple[str, float], ...]
    missing_components: tuple[str, ...]
    label: str = "STRESS_SCORE"

    def __post_init__(self) -> None:
        if self.score is not None:
            require_finite(self.score, "score")
        require_probability(self.coverage, "coverage")
        if self.label not in {"STRESS_SCORE", "RISK_INDEX"}:
            raise DomainValidationError("aggregate FX stress cannot be labelled as a probability")


def aggregate_fx_stress(
    components: Mapping[str, float | None],
    *,
    weights: Mapping[str, float] | None = None,
    minimum_coverage: float = 0.5,
) -> AggregateStress:
    """Combine standardized stress components without treating missing as zero.

    Available weights are renormalized. ``coverage`` is the share of total
    configured absolute weight represented by observed components.
    """

    if not components:
        raise DomainValidationError("components must not be empty")
    require_probability(minimum_coverage, "minimum_coverage")
    configured = dict(weights or {name: 1.0 for name in components})
    if set(configured) != set(components):
        raise DomainValidationError("weights must have exactly the same keys as components")
    for name, weight in configured.items():
        require_finite(weight, f"weight[{name}]")
    total_weight = math.fsum(abs(weight) for weight in configured.values())
    if total_weight == 0:
        raise DomainValidationError("at least one aggregate stress weight must be non-zero")
    available: list[tuple[str, float, float]] = []
    missing: list[str] = []
    for name, value in components.items():
        if value is None:
            missing.append(name)
        else:
            available.append((name, require_finite(value, f"component[{name}]"), configured[name]))
    available_weight = math.fsum(abs(weight) for _, _, weight in available)
    coverage = available_weight / total_weight
    if not available or coverage < minimum_coverage or available_weight == 0:
        return AggregateStress(None, coverage, (), tuple(sorted(missing)))
    contributions = tuple(
        (name, value * weight / available_weight) for name, value, weight in sorted(available)
    )
    score = math.fsum(contribution for _, contribution in contributions)
    return AggregateStress(score, coverage, contributions, tuple(sorted(missing)))

