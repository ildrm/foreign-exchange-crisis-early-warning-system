"""Hazard-specific alert thresholds, evidence gates, and hysteresis."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from .calibration import CalibrationStatus
from .entities import OODStatus
from .hazards import ForecastRecord, log_odds_change, relative_risk
from .regimes import RegimeType
from .taxonomy import ForecastHorizon, HazardType
from .validation import (
    DomainValidationError,
    require_date,
    require_finite,
    require_non_empty,
    require_probability,
)


class RiskAlertLevel(StrEnum):
    NO_ALERT = "NO_ALERT"
    WATCH_UNCALIBRATED = "WATCH_UNCALIBRATED"
    WATCH = "WATCH"
    ELEVATED = "ELEVATED"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    @property
    def rank(self) -> int:
        return {
            RiskAlertLevel.NO_ALERT: 0,
            RiskAlertLevel.WATCH_UNCALIBRATED: 1,
            RiskAlertLevel.WATCH: 1,
            RiskAlertLevel.ELEVATED: 2,
            RiskAlertLevel.HIGH: 3,
            RiskAlertLevel.CRITICAL: 4,
        }[self]

    @property
    def is_severe(self) -> bool:
        return self.rank >= RiskAlertLevel.ELEVATED.rank


class EvidenceAlert(StrEnum):
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    LOW_DATA_QUALITY = "LOW_DATA_QUALITY"
    STALE_DATA = "STALE_DATA"
    SOURCE_DISAGREEMENT = "SOURCE_DISAGREEMENT"
    MODEL_OUT_OF_DOMAIN = "MODEL_OUT_OF_DOMAIN"
    CALIBRATION_WEAK = "CALIBRATION_WEAK"
    MODEL_DRIFT = "MODEL_DRIFT"
    REGIME_CHANGE = "REGIME_CHANGE"
    DATA_PIPELINE_FAILURE = "DATA_PIPELINE_FAILURE"


class AlertMarker(StrEnum):
    RAPID_DETERIORATION = "RAPID_DETERIORATION"


# Compatibility name for report/application callers.
AlertSeverity = RiskAlertLevel


_VALIDATED_LEVELS = (
    RiskAlertLevel.WATCH,
    RiskAlertLevel.ELEVATED,
    RiskAlertLevel.HIGH,
    RiskAlertLevel.CRITICAL,
)


@dataclass(frozen=True, slots=True)
class AlertThresholds:
    """Validated entry thresholds for exactly one hazard and horizon."""

    hazard: HazardType
    horizon: ForecastHorizon
    watch: float
    elevated: float
    high: float
    critical: float
    methodology: str
    validation_start: date
    validation_end: date
    event_count: int
    policy_version: str = "0.1.0"
    exit_ratio: float = 0.85

    def __post_init__(self) -> None:
        if not isinstance(self.hazard, HazardType):
            object.__setattr__(self, "hazard", HazardType.parse(self.hazard))
        if not isinstance(self.horizon, ForecastHorizon):
            object.__setattr__(self, "horizon", ForecastHorizon.parse(self.horizon))
        values = tuple(
            require_probability(value, field)
            for value, field in (
                (self.watch, "watch threshold"),
                (self.elevated, "elevated threshold"),
                (self.high, "high threshold"),
                (self.critical, "critical threshold"),
            )
        )
        if any(right <= left for left, right in zip(values, values[1:], strict=False)):
            raise DomainValidationError("alert entry thresholds must be strictly increasing")
        require_non_empty(self.methodology, "threshold methodology")
        require_non_empty(self.policy_version, "policy_version")
        require_date(self.validation_start, "validation_start")
        require_date(self.validation_end, "validation_end")
        if self.validation_end < self.validation_start:
            raise DomainValidationError("threshold validation period is reversed")
        if isinstance(self.event_count, bool) or self.event_count < 1:
            raise DomainValidationError("validated thresholds require at least one event")
        exit_ratio = require_probability(self.exit_ratio, "exit_ratio")
        if exit_ratio <= 0.0 or exit_ratio >= 1.0:
            raise DomainValidationError("exit_ratio must lie strictly between zero and one")

    def entry_for(self, level: RiskAlertLevel) -> float | None:
        return {
            RiskAlertLevel.NO_ALERT: None,
            RiskAlertLevel.WATCH_UNCALIBRATED: self.watch,
            RiskAlertLevel.WATCH: self.watch,
            RiskAlertLevel.ELEVATED: self.elevated,
            RiskAlertLevel.HIGH: self.high,
            RiskAlertLevel.CRITICAL: self.critical,
        }[level]

    def exit_for(self, level: RiskAlertLevel) -> float | None:
        entry = self.entry_for(level)
        return None if entry is None else entry * self.exit_ratio


def _entry_severity(probability: float, thresholds: AlertThresholds) -> RiskAlertLevel:
    probability = require_probability(probability)
    if probability >= thresholds.critical:
        return RiskAlertLevel.CRITICAL
    if probability >= thresholds.high:
        return RiskAlertLevel.HIGH
    if probability >= thresholds.elevated:
        return RiskAlertLevel.ELEVATED
    if probability >= thresholds.watch:
        return RiskAlertLevel.WATCH
    return RiskAlertLevel.NO_ALERT


def severity_with_hysteresis(
    probability: float,
    thresholds: AlertThresholds,
    *,
    previous_level: RiskAlertLevel = RiskAlertLevel.NO_ALERT,
) -> RiskAlertLevel:
    """Apply higher entry than exit thresholds to prevent alert flicker."""

    probability = require_probability(probability)
    if not isinstance(previous_level, RiskAlertLevel):
        try:
            previous_level = RiskAlertLevel(str(previous_level).upper())
        except ValueError as exc:
            raise DomainValidationError(f"invalid previous alert level: {previous_level!r}") from exc
    candidate = _entry_severity(probability, thresholds)
    if previous_level is RiskAlertLevel.WATCH_UNCALIBRATED:
        previous_level = RiskAlertLevel.WATCH
    if candidate.rank >= previous_level.rank:
        return candidate
    exit_threshold = thresholds.exit_for(previous_level)
    if exit_threshold is not None and probability >= exit_threshold:
        return previous_level
    return candidate


@dataclass(frozen=True, slots=True)
class ProbabilityMomentum:
    delta_7d: float | None = None
    delta_30d: float | None = None
    delta_90d: float | None = None
    delta_12m: float | None = None
    delta_log_odds: float | None = None

    def __post_init__(self) -> None:
        for value, field in (
            (self.delta_7d, "delta_7d"),
            (self.delta_30d, "delta_30d"),
            (self.delta_90d, "delta_90d"),
            (self.delta_12m, "delta_12m"),
            (self.delta_log_odds, "delta_log_odds"),
        ):
            if value is not None:
                require_finite(value, field)

    @classmethod
    def from_probabilities(
        cls,
        current: float,
        *,
        previous_7d: float | None = None,
        previous_30d: float | None = None,
        previous_90d: float | None = None,
        previous_12m: float | None = None,
        log_odds_reference: float | None = None,
    ) -> ProbabilityMomentum:
        current = require_probability(current, "current")

        def change(previous: float | None, field: str) -> float | None:
            return (
                None
                if previous is None
                else current - require_probability(previous, field)
            )

        return cls(
            delta_7d=change(previous_7d, "previous_7d"),
            delta_30d=change(previous_30d, "previous_30d"),
            delta_90d=change(previous_90d, "previous_90d"),
            delta_12m=change(previous_12m, "previous_12m"),
            delta_log_odds=(
                None
                if log_odds_reference is None
                else log_odds_change(current, log_odds_reference)
            ),
        )


@dataclass(frozen=True, slots=True)
class AlertEvaluation:
    proposed_level: RiskAlertLevel
    issued_level: RiskAlertLevel
    evidence_alerts: tuple[EvidenceAlert, ...]
    markers: tuple[AlertMarker, ...]
    trigger_threshold: float | None
    threshold_methodology: str
    severe_gates_passed: bool
    gate_failures: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AlertPolicy:
    """One hazard/horizon operational policy with explicit decision gates."""

    thresholds: AlertThresholds | None
    minimum_coverage: float = 0.7
    minimum_data_quality: float = 0.7
    rapid_deterioration_threshold_30d: float | None = None
    policy_version: str = "0.1.0"

    def __post_init__(self) -> None:
        require_probability(self.minimum_coverage, "minimum_coverage")
        require_probability(self.minimum_data_quality, "minimum_data_quality")
        require_non_empty(self.policy_version, "policy_version")
        if self.rapid_deterioration_threshold_30d is not None:
            threshold = require_finite(
                self.rapid_deterioration_threshold_30d,
                "rapid_deterioration_threshold_30d",
            )
            if threshold <= 0.0:
                raise DomainValidationError(
                    "rapid deterioration threshold must be a positive validated change"
                )

    def evaluate(
        self,
        forecast: ForecastRecord,
        *,
        calibration_status: CalibrationStatus,
        data_quality: float,
        target_valid: bool = True,
        source_failure: bool = False,
        stale_source_only: bool = False,
        source_disagreement: bool = False,
        model_drift: bool = False,
        regime_change: bool = False,
        previous_level: RiskAlertLevel = RiskAlertLevel.NO_ALERT,
        momentum: ProbabilityMomentum | None = None,
    ) -> AlertEvaluation:
        if not isinstance(calibration_status, CalibrationStatus):
            try:
                calibration_status = CalibrationStatus(str(calibration_status).lower())
            except ValueError as exc:
                raise DomainValidationError("invalid calibration status") from exc
        data_quality = require_probability(data_quality, "data_quality")
        evidence: list[EvidenceAlert] = []
        failures: list[str] = []
        if forecast.coverage < self.minimum_coverage:
            evidence.append(EvidenceAlert.INSUFFICIENT_EVIDENCE)
            failures.append("coverage below policy minimum")
        if data_quality < self.minimum_data_quality:
            evidence.append(EvidenceAlert.LOW_DATA_QUALITY)
            failures.append("data quality below policy minimum")
        if stale_source_only:
            evidence.append(EvidenceAlert.STALE_DATA)
            failures.append("alert signal is driven solely by stale data")
        if source_failure:
            evidence.append(EvidenceAlert.DATA_PIPELINE_FAILURE)
            failures.append("a required source failed")
        if source_disagreement:
            evidence.append(EvidenceAlert.SOURCE_DISAGREEMENT)
        if forecast.ood_status is OODStatus.OUT_OF_DOMAIN:
            evidence.append(EvidenceAlert.MODEL_OUT_OF_DOMAIN)
            failures.append("forecast is strongly out of domain")
        if calibration_status is not CalibrationStatus.ACCEPTABLE:
            evidence.append(EvidenceAlert.CALIBRATION_WEAK)
            failures.append("calibration is not acceptable")
        if not forecast.is_calibrated:
            if EvidenceAlert.CALIBRATION_WEAK not in evidence:
                evidence.append(EvidenceAlert.CALIBRATION_WEAK)
            failures.append("forecast is uncalibrated")
        if not target_valid:
            evidence.append(EvidenceAlert.INSUFFICIENT_EVIDENCE)
            failures.append("target is not valid for the country/regime")
        if model_drift:
            evidence.append(EvidenceAlert.MODEL_DRIFT)
        if regime_change:
            evidence.append(EvidenceAlert.REGIME_CHANGE)

        if self.thresholds is None:
            # There is no defensible operational severity without validation.
            proposed = (
                RiskAlertLevel.WATCH_UNCALIBRATED
                if forecast.reported_probability > forecast.base_rate
                else RiskAlertLevel.NO_ALERT
            )
            issued = proposed
            failures.append("no historically validated alert thresholds")
            methodology = "UNVALIDATED: estimate compared with disclosed historical base rate"
            trigger = forecast.base_rate if proposed is not RiskAlertLevel.NO_ALERT else None
            severe_gates_passed = False
        else:
            if (
                self.thresholds.hazard is not forecast.hazard
                or self.thresholds.horizon is not forecast.horizon
            ):
                raise DomainValidationError("alert thresholds do not match forecast hazard/horizon")
            proposed = severity_with_hysteresis(
                forecast.reported_probability,
                self.thresholds,
                previous_level=previous_level,
            )
            severe_gates_passed = not failures
            if proposed.is_severe and not severe_gates_passed:
                issued = (
                    RiskAlertLevel.WATCH
                    if forecast.is_calibrated
                    else RiskAlertLevel.WATCH_UNCALIBRATED
                )
            elif proposed is RiskAlertLevel.WATCH and not forecast.is_calibrated:
                issued = RiskAlertLevel.WATCH_UNCALIBRATED
            else:
                issued = proposed
            trigger = self.thresholds.entry_for(proposed)
            methodology = self.thresholds.methodology

        markers: list[AlertMarker] = []
        if (
            momentum is not None
            and momentum.delta_30d is not None
            and self.rapid_deterioration_threshold_30d is not None
            and momentum.delta_30d >= self.rapid_deterioration_threshold_30d
        ):
            markers.append(AlertMarker.RAPID_DETERIORATION)
        return AlertEvaluation(
            proposed_level=proposed,
            issued_level=issued,
            evidence_alerts=tuple(dict.fromkeys(evidence)),
            markers=tuple(markers),
            trigger_threshold=trigger,
            threshold_methodology=methodology,
            severe_gates_passed=severe_gates_passed,
            gate_failures=tuple(dict.fromkeys(failures)),
        )


@dataclass(frozen=True, slots=True)
class AlertRecord:
    hazard: HazardType
    horizon: ForecastHorizon
    current_severity: RiskAlertLevel
    calibrated_probability: float | None
    historical_base_rate: float
    relative_risk: float
    historical_percentile: float | None
    probability_change: ProbabilityMomentum
    evidence_confidence: float
    data_coverage: float
    calibration_status: CalibrationStatus
    ood_status: OODStatus
    fx_regime: RegimeType
    trigger_threshold: float | None
    threshold_methodology: str
    first_seen_date: date
    last_changed_date: date
    primary_predictive_contributors: tuple[str, ...] = ()
    contrary_evidence: tuple[str, ...] = ()
    caveats: tuple[str, ...] = ()
    evidence_alerts: tuple[EvidenceAlert, ...] = ()
    markers: tuple[AlertMarker, ...] = ()
    consecutive_observations: int = 1
    peak_probability: float | None = None
    current_probability: float | None = None
    country: str | None = None
    alert_policy_version: str = "0.1.0"

    def __post_init__(self) -> None:
        if not isinstance(self.hazard, HazardType):
            object.__setattr__(self, "hazard", HazardType.parse(self.hazard))
        if not isinstance(self.horizon, ForecastHorizon):
            object.__setattr__(self, "horizon", ForecastHorizon.parse(self.horizon))
        if not isinstance(self.current_severity, RiskAlertLevel):
            object.__setattr__(
                self, "current_severity", RiskAlertLevel(str(self.current_severity).upper())
            )
        for field, enum_type in (
            ("calibration_status", CalibrationStatus),
            ("ood_status", OODStatus),
            ("fx_regime", RegimeType),
        ):
            value = getattr(self, field)
            if not isinstance(value, enum_type):
                try:
                    object.__setattr__(self, field, enum_type(str(value).lower()))
                except ValueError as exc:
                    raise DomainValidationError(f"invalid {field}: {value!r}") from exc
        if self.calibrated_probability is not None:
            require_probability(self.calibrated_probability, "calibrated_probability")
        base_rate = require_probability(self.historical_base_rate, "historical_base_rate")
        if base_rate == 0:
            raise DomainValidationError("historical_base_rate must be positive")
        reported = self.current_probability
        if reported is None:
            reported = self.calibrated_probability
            object.__setattr__(self, "current_probability", reported)
        if reported is not None:
            require_probability(reported, "current_probability")
            expected_rr = relative_risk(reported, base_rate)
            if not math.isclose(self.relative_risk, expected_rr, rel_tol=1e-9, abs_tol=1e-12):
                raise DomainValidationError("alert relative_risk is inconsistent")
        require_finite(self.relative_risk, "relative_risk")
        if self.historical_percentile is not None:
            percentile = require_finite(self.historical_percentile, "historical_percentile")
            if not 0 <= percentile <= 100:
                raise DomainValidationError("historical_percentile must lie between 0 and 100")
        require_probability(self.evidence_confidence, "evidence_confidence")
        require_probability(self.data_coverage, "data_coverage")
        if self.trigger_threshold is not None:
            require_probability(self.trigger_threshold, "trigger_threshold")
        require_non_empty(self.threshold_methodology, "threshold_methodology")
        require_date(self.first_seen_date, "first_seen_date")
        require_date(self.last_changed_date, "last_changed_date")
        if self.last_changed_date < self.first_seen_date:
            raise DomainValidationError("last_changed_date cannot precede first_seen_date")
        if isinstance(self.consecutive_observations, bool) or self.consecutive_observations < 1:
            raise DomainValidationError("consecutive_observations must be a positive integer")
        if self.peak_probability is not None:
            require_probability(self.peak_probability, "peak_probability")
            if reported is not None and self.peak_probability < reported:
                raise DomainValidationError("peak_probability cannot be below current_probability")
        if self.current_severity.is_severe and self.calibrated_probability is None:
            raise DomainValidationError("uncalibrated forecasts cannot issue severe alerts")
        object.__setattr__(
            self,
            "evidence_alerts",
            tuple(
                item if isinstance(item, EvidenceAlert) else EvidenceAlert(str(item).upper())
                for item in self.evidence_alerts
            ),
        )
        object.__setattr__(
            self,
            "markers",
            tuple(
                item if isinstance(item, AlertMarker) else AlertMarker(str(item).upper())
                for item in self.markers
            ),
        )
        require_non_empty(self.alert_policy_version, "alert_policy_version")


def build_alert_record(
    forecast: ForecastRecord,
    evaluation: AlertEvaluation,
    *,
    calibration_status: CalibrationStatus,
    analysis_date: date,
    momentum: ProbabilityMomentum | None = None,
    previous: AlertRecord | None = None,
    primary_predictive_contributors: tuple[str, ...] = (),
    contrary_evidence: tuple[str, ...] = (),
    caveats: tuple[str, ...] = (),
    alert_policy_version: str = "0.1.0",
) -> AlertRecord:
    """Create or advance an immutable alert-persistence record."""

    require_date(analysis_date, "analysis_date")
    if previous is not None:
        if previous.hazard is not forecast.hazard or previous.horizon is not forecast.horizon:
            raise DomainValidationError("previous alert does not match forecast hazard/horizon")
        if analysis_date < previous.last_changed_date:
            raise DomainValidationError("alert updates must be chronological")
    changed = previous is None or previous.current_severity is not evaluation.issued_level
    first_seen = previous.first_seen_date if previous else analysis_date
    last_changed = analysis_date if changed else previous.last_changed_date
    consecutive = 1 if changed else previous.consecutive_observations + 1
    current = forecast.reported_probability
    previous_peak = previous.peak_probability if previous else None
    peak = max(current, previous_peak) if previous_peak is not None else current
    merged_caveats = tuple(dict.fromkeys((*caveats, *evaluation.gate_failures)))
    return AlertRecord(
        hazard=forecast.hazard,
        horizon=forecast.horizon,
        current_severity=evaluation.issued_level,
        calibrated_probability=forecast.calibrated_probability,
        historical_base_rate=forecast.base_rate,
        relative_risk=forecast.relative_risk,
        historical_percentile=forecast.historical_percentile,
        probability_change=momentum or ProbabilityMomentum(),
        evidence_confidence=forecast.confidence,
        data_coverage=forecast.coverage,
        calibration_status=calibration_status,
        ood_status=forecast.ood_status,
        fx_regime=forecast.regime,
        trigger_threshold=evaluation.trigger_threshold,
        threshold_methodology=evaluation.threshold_methodology,
        first_seen_date=first_seen,
        last_changed_date=last_changed,
        primary_predictive_contributors=primary_predictive_contributors,
        contrary_evidence=contrary_evidence,
        caveats=merged_caveats,
        evidence_alerts=evaluation.evidence_alerts,
        markers=evaluation.markers,
        consecutive_observations=consecutive,
        peak_probability=peak,
        current_probability=current,
        country=forecast.country,
        alert_policy_version=alert_policy_version,
    )
