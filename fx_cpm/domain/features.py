"""Central metadata and small deterministic formulas for model features."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping

from .observations import ObservationFrequency
from .regimes import RegimeType
from .taxonomy import HazardType
from .validation import (
    DomainValidationError,
    require_date,
    require_finite,
    require_non_empty,
)


class FeatureFamily(StrEnum):
    FX = "fx"
    MACRO = "macro"
    CREDIT = "credit"
    BANKING = "banking"
    SOVEREIGN = "sovereign"
    MARKET = "market"
    POLITICAL = "political"
    CONFLICT = "conflict"
    COMMODITY = "commodity"
    GLOBAL = "global"
    NETWORK = "network"
    REGIME = "regime"


class ExpectedRelationship(StrEnum):
    INCREASES_RISK = "increases_risk"
    DECREASES_RISK = "decreases_risk"
    NONLINEAR = "nonlinear"
    REGIME_DEPENDENT = "regime_dependent"
    UNKNOWN = "unknown"


class MissingDataPolicy(StrEnum):
    NO_IMPUTATION = "no_imputation"
    MODEL_NATIVE = "model_native"
    TRAINING_MEDIAN = "training_median"
    FORWARD_FILL_WITH_STALENESS_LIMIT = "forward_fill_with_staleness_limit"
    NOT_APPLICABLE_OUTSIDE_REGIME = "not_applicable_outside_regime"


@dataclass(frozen=True, slots=True)
class FeatureDefinition:
    """Versionable scientific contract for one feature.

    The formula is descriptive metadata; executable mathematics remains in
    named, tested domain functions rather than being evaluated from a string.
    """

    feature_id: str
    display_name: str
    family: FeatureFamily
    formula: str
    required_inputs: tuple[str, ...]
    frequency: ObservationFrequency
    transformations: tuple[str, ...]
    expected_relationship: ExpectedRelationship
    theoretical_rationale: str
    supported_hazards: tuple[HazardType, ...]
    valid_regimes: tuple[RegimeType, ...]
    historical_availability: date | None
    source_requirements: tuple[str, ...]
    missing_data_policy: MissingDataPolicy
    limitations: tuple[str, ...]
    unit: str = "dimensionless"
    definition_version: str = "0.1.0"

    def __post_init__(self) -> None:
        for field in (
            "feature_id",
            "display_name",
            "formula",
            "theoretical_rationale",
            "unit",
            "definition_version",
        ):
            require_non_empty(getattr(self, field), field)
        if not isinstance(self.family, FeatureFamily):
            try:
                object.__setattr__(self, "family", FeatureFamily(str(self.family).lower()))
            except ValueError as exc:
                raise DomainValidationError(f"invalid feature family: {self.family!r}") from exc
        if not isinstance(self.frequency, ObservationFrequency):
            try:
                object.__setattr__(
                    self, "frequency", ObservationFrequency(str(self.frequency).lower())
                )
            except ValueError as exc:
                raise DomainValidationError(f"invalid frequency: {self.frequency!r}") from exc
        if not isinstance(self.expected_relationship, ExpectedRelationship):
            try:
                object.__setattr__(
                    self,
                    "expected_relationship",
                    ExpectedRelationship(str(self.expected_relationship).lower()),
                )
            except ValueError as exc:
                raise DomainValidationError("invalid expected_relationship") from exc
        if not isinstance(self.missing_data_policy, MissingDataPolicy):
            try:
                object.__setattr__(
                    self,
                    "missing_data_policy",
                    MissingDataPolicy(str(self.missing_data_policy).lower()),
                )
            except ValueError as exc:
                raise DomainValidationError("invalid missing_data_policy") from exc
        hazards = tuple(HazardType.parse(item) for item in self.supported_hazards)
        regimes = tuple(RegimeType.parse(item) for item in self.valid_regimes)
        if not hazards:
            raise DomainValidationError("supported_hazards must not be empty")
        if not regimes:
            raise DomainValidationError("valid_regimes must not be empty")
        if len(set(hazards)) != len(hazards) or len(set(regimes)) != len(regimes):
            raise DomainValidationError("supported hazards and valid regimes must be unique")
        object.__setattr__(self, "supported_hazards", hazards)
        object.__setattr__(self, "valid_regimes", regimes)
        if self.historical_availability is not None:
            require_date(self.historical_availability, "historical_availability")
        if not self.source_requirements:
            raise DomainValidationError("source_requirements must not be empty")
        if not self.limitations:
            raise DomainValidationError("limitations must not be empty")

    def supports(self, hazard: HazardType | str, regime: RegimeType | str) -> bool:
        return (
            HazardType.parse(hazard) in self.supported_hazards
            and RegimeType.parse(regime) in self.valid_regimes
        )


def arithmetic_change(current: float, previous: float) -> float:
    return require_finite(current, "current") - require_finite(previous, "previous")


def percentage_change(current: float, previous: float, *, scale: float = 100.0) -> float:
    current = require_finite(current, "current")
    previous = require_finite(previous, "previous")
    scale = require_finite(scale, "scale")
    if previous == 0.0:
        raise DomainValidationError("percentage change is undefined from a zero denominator")
    return scale * (current / previous - 1.0)


def log_return(current: float, previous: float) -> float:
    current = require_finite(current, "current")
    previous = require_finite(previous, "previous")
    if current <= 0.0 or previous <= 0.0:
        raise DomainValidationError("log returns require strictly positive levels")
    return math.log(current / previous)


def acceleration(current_change: float, previous_change: float) -> float:
    return arithmetic_change(current_change, previous_change)


def rolling_mean(values: Sequence[float]) -> float:
    if not values:
        raise DomainValidationError("rolling mean requires at least one value")
    clean = tuple(require_finite(value, f"values[{index}]") for index, value in enumerate(values))
    return math.fsum(clean) / len(clean)


def drawdown(current: float, prior_peak: float) -> float:
    """Return fractional drawdown (zero at peak, negative below peak)."""

    current = require_finite(current, "current")
    prior_peak = require_finite(prior_peak, "prior_peak")
    if prior_peak <= 0:
        raise DomainValidationError("prior_peak must be positive")
    if current > prior_peak:
        return 0.0
    return current / prior_peak - 1.0


_ALL_REGIMES = tuple(RegimeType)
_FINANCIAL_HAZARDS = (
    HazardType.CURRENCY_CRISIS,
    HazardType.SYSTEMIC_BANKING_CRISIS,
    HazardType.SOVEREIGN_DISTRESS,
    HazardType.MONETARY_INFLATION_CRISIS,
)


CORE_FX_FEATURE_DEFINITIONS: Mapping[str, FeatureDefinition] = MappingProxyType(
    {
        "fx_spot_log_return": FeatureDefinition(
            feature_id="fx_spot_log_return",
            display_name="Spot FX log return",
            family=FeatureFamily.FX,
            formula="ln(S_t / S_{t-1}); S is local currency per anchor currency",
            required_inputs=("fx_spot_t", "fx_spot_t_minus_1"),
            frequency=ObservationFrequency.DAILY,
            transformations=("quote_normalization", "log_return"),
            expected_relationship=ExpectedRelationship.REGIME_DEPENDENT,
            theoretical_rationale=(
                "Depreciation can reveal market pressure under market-driven regimes but is not "
                "generic crisis evidence without regime and global-factor conditioning."
            ),
            supported_hazards=_FINANCIAL_HAZARDS,
            valid_regimes=_ALL_REGIMES,
            historical_availability=None,
            source_requirements=("point-in-time bid/offer-consistent spot rate",),
            missing_data_policy=MissingDataPolicy.NO_IMPUTATION,
            limitations=(
                "Official rates may not clear the market under controls or multiple rates.",
            ),
            unit="log return",
        ),
        "exchange_market_pressure": FeatureDefinition(
            feature_id="exchange_market_pressure",
            display_name="Exchange Market Pressure",
            family=FeatureFamily.FX,
            formula="w_s Z(Delta s) - w_r Z(Delta reserves) + w_i Z(Delta rate differential)",
            required_inputs=(
                "spot_depreciation_z",
                "reserve_growth_z",
                "rate_differential_change_z",
            ),
            frequency=ObservationFrequency.MONTHLY,
            transformations=("point_in_time_standardization", "documented_weighted_sum"),
            expected_relationship=ExpectedRelationship.INCREASES_RISK,
            theoretical_rationale=(
                "A defended peg can transmit currency pressure into reserve loss and interest-rate "
                "defense even while the official spot rate remains stable."
            ),
            supported_hazards=_FINANCIAL_HAZARDS,
            valid_regimes=_ALL_REGIMES,
            historical_availability=None,
            source_requirements=(
                "consistent FX quote convention",
                "point-in-time reserves",
                "domestic-anchor policy-rate differential",
            ),
            missing_data_policy=MissingDataPolicy.NO_IMPUTATION,
            limitations=(
                "Weighting and standardization windows materially affect comparability.",
                "Valuation changes can contaminate measured reserve growth.",
            ),
            unit="standard deviations",
        ),
        "parallel_market_premium": FeatureDefinition(
            feature_id="parallel_market_premium",
            display_name="Parallel-market FX premium",
            family=FeatureFamily.FX,
            formula="100 * (S_parallel / S_official - 1)",
            required_inputs=("parallel_fx_rate", "official_fx_rate"),
            frequency=ObservationFrequency.DAILY,
            transformations=("quote_and_timestamp_alignment", "ratio"),
            expected_relationship=ExpectedRelationship.INCREASES_RISK,
            theoretical_rationale=(
                "A widening gap can reveal rationing and devaluation pressure concealed by the "
                "official rate."
            ),
            supported_hazards=_FINANCIAL_HAZARDS,
            valid_regimes=(RegimeType.PARALLEL_MULTIPLE_RATES,),
            historical_availability=None,
            source_requirements=(
                "same-day identically quoted official and representative parallel rates",
            ),
            missing_data_policy=MissingDataPolicy.NOT_APPLICABLE_OUTSIDE_REGIME,
            limitations=(
                "Informal-market observations may be sparse, illegal, or unrepresentative.",
            ),
            unit="percent",
        ),
        "fx_surprise": FeatureDefinition(
            feature_id="fx_surprise",
            display_name="Residual FX stress",
            family=FeatureFamily.FX,
            formula="(r_i,t - E[r_i,t | global, regional, commodity, regime factors]) / sigma_i,t",
            required_inputs=("observed_fx_return", "expected_fx_return", "conditional_volatility"),
            frequency=ObservationFrequency.DAILY,
            transformations=("factor_residualization", "volatility_standardization"),
            expected_relationship=ExpectedRelationship.REGIME_DEPENDENT,
            theoretical_rationale=(
                "Residualization separates country-specific repricing from broad dollar, rates, "
                "risk-sentiment, commodity, and regional movements."
            ),
            supported_hazards=tuple(HazardType),
            valid_regimes=_ALL_REGIMES,
            historical_availability=None,
            source_requirements=(
                "factor model fitted only on information preceding the analysis date",
                "strictly positive conditional volatility estimate",
            ),
            missing_data_policy=MissingDataPolicy.NO_IMPUTATION,
            limitations=(
                "Residual stress is a predictive association, not evidence of political intent or causation.",
            ),
            unit="standard deviations",
        ),
    }
)


def feature_definition(feature_id: str) -> FeatureDefinition:
    try:
        return CORE_FX_FEATURE_DEFINITIONS[feature_id]
    except KeyError as exc:
        raise DomainValidationError(f"unknown core feature definition: {feature_id}") from exc
