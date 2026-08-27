"""Forecast records and hazard-probability transformations."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from .calibration import logit
from .entities import ModelTier, OODStatus
from .regimes import RegimeType
from .taxonomy import ForecastHorizon, HazardType
from .validation import (
    DomainValidationError,
    require_date,
    require_finite,
    require_non_empty,
    require_probability,
)


def relative_risk(probability: float, base_rate: float) -> float:
    probability = require_probability(probability, "probability")
    base_rate = require_probability(base_rate, "base_rate")
    if base_rate == 0.0:
        raise DomainValidationError("relative risk is undefined when the historical base rate is zero")
    return probability / base_rate


def probability_point_change(current: float, previous: float) -> float:
    """Return an arithmetic probability change (multiply by 100 for pp display)."""

    return require_probability(current, "current") - require_probability(previous, "previous")


def log_odds_change(current: float, previous: float) -> float:
    return logit(current) - logit(previous)


def cumulative_probability_from_discrete_hazards(hazards: Sequence[float]) -> float:
    """Convert sequential same-event hazards to cumulative incidence.

    This survival identity is for time intervals of one hazard.  It must not be
    used to combine the eight dependent crisis families.
    """

    if not hazards:
        raise DomainValidationError("at least one discrete hazard is required")
    survival = 1.0
    for index, hazard in enumerate(hazards):
        survival *= 1.0 - require_probability(hazard, f"hazards[{index}]")
    return 1.0 - survival


@dataclass(frozen=True, slots=True, init=False)
class ForecastRecord:
    """One hazard/horizon forecast with evidence and calibration context.

    ``country`` is the canonical stored field.  The constructor also accepts
    ``country_id`` for source/service interoperability.
    """

    country: str
    hazard: HazardType
    analysis_date: date
    horizon: ForecastHorizon
    raw_probability: float
    calibrated_probability: float | None
    base_rate: float
    relative_risk: float
    historical_percentile: float | None
    confidence: float
    coverage: float
    model_version: str
    calibration_version: str | None
    regime: RegimeType
    training_end_date: date
    model_tier: ModelTier
    ood_status: OODStatus
    uncertainty_lower: float | None
    uncertainty_upper: float | None
    sensitivity_label: str | None

    def __init__(
        self,
        country: str | None = None,
        hazard: HazardType | str = HazardType.CURRENCY_CRISIS,
        analysis_date: date | None = None,
        horizon: ForecastHorizon | int | str = ForecastHorizon.MONTHS_12,
        raw_probability: float = 0.0,
        calibrated_probability: float | None = None,
        base_rate: float = 0.01,
        relative_risk: float | None = None,
        historical_percentile: float | None = None,
        confidence: float = 0.0,
        coverage: float = 0.0,
        model_version: str = "unversioned",
        calibration_version: str | None = None,
        regime: RegimeType | str = RegimeType.UNKNOWN,
        training_end_date: date | None = None,
        model_tier: ModelTier | str = ModelTier.HISTORICAL_STRUCTURAL,
        ood_status: OODStatus | str = OODStatus.UNKNOWN,
        *,
        country_id: str | None = None,
        uncertainty_lower: float | None = None,
        uncertainty_upper: float | None = None,
        sensitivity_label: str | None = None,
    ) -> None:
        selected_country = country if country is not None else country_id
        if country is not None and country_id is not None and country != country_id:
            raise DomainValidationError("country and country_id disagree")
        if selected_country is None:
            raise DomainValidationError("country or country_id is required")
        if analysis_date is None:
            raise DomainValidationError("analysis_date is required")
        if training_end_date is None:
            raise DomainValidationError("training_end_date is required")
        parsed_hazard = HazardType.parse(hazard)
        parsed_horizon = ForecastHorizon.parse(horizon)
        parsed_regime = RegimeType.parse(regime)
        try:
            parsed_tier = model_tier if isinstance(model_tier, ModelTier) else ModelTier(str(model_tier).lower())
            parsed_ood = ood_status if isinstance(ood_status, OODStatus) else OODStatus(str(ood_status).lower())
        except ValueError as exc:
            raise DomainValidationError("invalid model tier or OOD status") from exc
        raw = require_probability(raw_probability, "raw_probability")
        calibrated = (
            None
            if calibrated_probability is None
            else require_probability(calibrated_probability, "calibrated_probability")
        )
        base = require_probability(base_rate, "base_rate")
        if base == 0.0:
            raise DomainValidationError("base_rate must be positive for relative-risk reporting")
        reported = calibrated if calibrated is not None else raw
        computed_rr = relative_risk if relative_risk is not None else reported / base
        computed_rr = require_finite(computed_rr, "relative_risk")
        if computed_rr < 0:
            raise DomainValidationError("relative_risk cannot be negative")
        if not math.isclose(computed_rr, reported / base, rel_tol=1e-9, abs_tol=1e-12):
            raise DomainValidationError("relative_risk is inconsistent with probability/base_rate")
        if historical_percentile is not None:
            percentile = require_finite(historical_percentile, "historical_percentile")
            if not 0.0 <= percentile <= 100.0:
                raise DomainValidationError("historical_percentile must lie between 0 and 100")
        require_probability(confidence, "confidence")
        require_probability(coverage, "coverage")
        require_date(analysis_date, "analysis_date")
        require_date(training_end_date, "training_end_date")
        if training_end_date > analysis_date:
            raise DomainValidationError("training_end_date cannot follow analysis_date")
        require_non_empty(selected_country, "country")
        require_non_empty(model_version, "model_version")
        if calibration_version is not None:
            require_non_empty(calibration_version, "calibration_version")
        if calibrated is not None and calibration_version is None:
            raise DomainValidationError("calibrated_probability requires calibration_version")
        if (uncertainty_lower is None) ^ (uncertainty_upper is None):
            raise DomainValidationError("uncertainty bounds must be supplied together")
        if uncertainty_lower is not None and uncertainty_upper is not None:
            lower = require_probability(uncertainty_lower, "uncertainty_lower")
            upper = require_probability(uncertainty_upper, "uncertainty_upper")
            if not lower <= reported <= upper:
                raise DomainValidationError(
                    "uncertainty bounds must contain the reported probability"
                )
        for field, value in (
            ("country", selected_country),
            ("hazard", parsed_hazard),
            ("analysis_date", analysis_date),
            ("horizon", parsed_horizon),
            ("raw_probability", raw),
            ("calibrated_probability", calibrated),
            ("base_rate", base),
            ("relative_risk", computed_rr),
            ("historical_percentile", historical_percentile),
            ("confidence", float(confidence)),
            ("coverage", float(coverage)),
            ("model_version", model_version),
            ("calibration_version", calibration_version),
            ("regime", parsed_regime),
            ("training_end_date", training_end_date),
            ("model_tier", parsed_tier),
            ("ood_status", parsed_ood),
            ("uncertainty_lower", uncertainty_lower),
            ("uncertainty_upper", uncertainty_upper),
            ("sensitivity_label", sensitivity_label),
        ):
            object.__setattr__(self, field, value)

    @property
    def country_id(self) -> str:
        return self.country

    @property
    def reported_probability(self) -> float:
        return (
            self.calibrated_probability
            if self.calibrated_probability is not None
            else self.raw_probability
        )

    @property
    def is_calibrated(self) -> bool:
        return self.calibrated_probability is not None

    @property
    def probability_label(self) -> str:
        return "CALIBRATED_PROBABILITY" if self.is_calibrated else "UNCALIBRATED_RISK_ESTIMATE"


def validate_probability_term_structure(records: Iterable[ForecastRecord]) -> None:
    """Require cumulative probabilities to be monotone across increasing horizons."""

    records = tuple(records)
    if not records:
        raise DomainValidationError("term structure must contain at least one forecast")
    identity = {(item.country, item.hazard, item.analysis_date) for item in records}
    if len(identity) != 1:
        raise DomainValidationError("term structure records must share country, hazard, and date")
    ordered = sorted(records, key=lambda item: item.horizon.days)
    if len({item.horizon for item in ordered}) != len(ordered):
        raise DomainValidationError("term structure contains duplicate horizons")
    for shorter, longer in zip(ordered, ordered[1:], strict=False):
        if longer.reported_probability + 1e-12 < shorter.reported_probability:
            raise DomainValidationError(
                f"cumulative probability falls from {shorter.horizon.label} to {longer.horizon.label}"
            )


@dataclass(frozen=True, slots=True)
class HazardProbabilityVector:
    """The eight separate probabilities; this is not an any-crisis probability."""

    probabilities: Mapping[HazardType, float]

    def __post_init__(self) -> None:
        parsed = {HazardType.parse(hazard): value for hazard, value in self.probabilities.items()}
        missing = set(HazardType) - set(parsed)
        if missing or len(parsed) != len(HazardType):
            raise DomainValidationError(
                f"hazard vector must contain all eight hazards; missing={sorted(item.code for item in missing)}"
            )
        clean = {
            hazard: require_probability(probability, f"probability[{hazard.value}]")
            for hazard, probability in parsed.items()
        }
        from types import MappingProxyType

        object.__setattr__(self, "probabilities", MappingProxyType(clean))

    def __getitem__(self, hazard: HazardType | str) -> float:
        return self.probabilities[HazardType.parse(hazard)]

    def as_ordered_tuple(self) -> tuple[float, ...]:
        return tuple(self.probabilities[hazard] for hazard in HazardType)
