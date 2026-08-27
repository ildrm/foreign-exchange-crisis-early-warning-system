"""Hazard-specific alert thresholds, evidence gates, and hysteresis."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from hashlib import sha256
from math import log
from typing import Any, Iterable


class RiskSeverity(str, Enum):
    NO_ALERT = "NO_ALERT"
    WATCH = "WATCH"
    WATCH_UNCALIBRATED = "WATCH_UNCALIBRATED"
    ELEVATED = "ELEVATED"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EvidenceWarning(str, Enum):
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    LOW_DATA_QUALITY = "LOW_DATA_QUALITY"
    STALE_DATA = "STALE_DATA"
    SOURCE_DISAGREEMENT = "SOURCE_DISAGREEMENT"
    MODEL_OUT_OF_DOMAIN = "MODEL_OUT_OF_DOMAIN"
    CALIBRATION_WEAK = "CALIBRATION_WEAK"
    MODEL_DRIFT = "MODEL_DRIFT"
    REGIME_CHANGE = "REGIME_CHANGE"
    DATA_PIPELINE_FAILURE = "DATA_PIPELINE_FAILURE"


_ORDER = {
    RiskSeverity.NO_ALERT: 0,
    RiskSeverity.WATCH: 1,
    RiskSeverity.WATCH_UNCALIBRATED: 1,
    RiskSeverity.ELEVATED: 2,
    RiskSeverity.HIGH: 3,
    RiskSeverity.CRITICAL: 4,
}


@dataclass(frozen=True, slots=True)
class AlertThresholds:
    watch: float
    elevated: float
    high: float
    critical: float
    watch_exit: float | None = None
    elevated_exit: float | None = None
    high_exit: float | None = None
    critical_exit: float | None = None

    def __post_init__(self) -> None:
        entries = (self.watch, self.elevated, self.high, self.critical)
        if any(value < 0.0 or value > 1.0 for value in entries):
            raise ValueError("alert thresholds must lie in [0, 1]")
        if tuple(sorted(entries)) != entries or len(set(entries)) != 4:
            raise ValueError("alert thresholds must be strictly increasing")
        for severity, exit_value in (
            (RiskSeverity.WATCH, self.watch_exit),
            (RiskSeverity.ELEVATED, self.elevated_exit),
            (RiskSeverity.HIGH, self.high_exit),
            (RiskSeverity.CRITICAL, self.critical_exit),
        ):
            if exit_value is not None and not 0.0 <= exit_value < self.enter(severity):
                raise ValueError("exit threshold must be lower than its entry threshold")

    def enter(self, severity: RiskSeverity) -> float:
        return {
            RiskSeverity.WATCH: self.watch,
            RiskSeverity.WATCH_UNCALIBRATED: self.watch,
            RiskSeverity.ELEVATED: self.elevated,
            RiskSeverity.HIGH: self.high,
            RiskSeverity.CRITICAL: self.critical,
            RiskSeverity.NO_ALERT: 0.0,
        }[severity]

    def exit(self, severity: RiskSeverity) -> float:
        explicit = {
            RiskSeverity.WATCH: self.watch_exit,
            RiskSeverity.WATCH_UNCALIBRATED: self.watch_exit,
            RiskSeverity.ELEVATED: self.elevated_exit,
            RiskSeverity.HIGH: self.high_exit,
            RiskSeverity.CRITICAL: self.critical_exit,
            RiskSeverity.NO_ALERT: 0.0,
        }[severity]
        return explicit if explicit is not None else self.enter(severity) * 0.9


@dataclass(frozen=True, slots=True)
class ThresholdValidationArtifact:
    """Content-addressed evidence that thresholds were historically validated."""

    hazard: Any
    horizon: Any
    validation_start: date
    validation_end: date
    event_count: int
    loss_utility_methodology: str
    policy_version: str
    artifact_digest: str
    calibration_version: str | None = None

    def __post_init__(self) -> None:
        if self.validation_end < self.validation_start:
            raise ValueError("threshold validation period is reversed")
        if isinstance(self.event_count, bool) or self.event_count < 1:
            raise ValueError("validated thresholds require positive event_count")
        if not self.loss_utility_methodology.strip() or not self.policy_version.strip():
            raise ValueError("loss/utility methodology and policy version are required")
        if self.artifact_digest != self.expected_digest():
            raise ValueError("threshold validation artifact digest does not match its contents")

    def expected_digest(self) -> str:
        payload = "|".join(
            (
                str(getattr(self.hazard, "value", self.hazard)),
                str(getattr(self.horizon, "value", self.horizon)),
                self.validation_start.isoformat(),
                self.validation_end.isoformat(),
                str(self.event_count),
                self.loss_utility_methodology,
                self.policy_version,
                self.calibration_version or "",
            )
        )
        return sha256(payload.encode("utf-8")).hexdigest()

    @classmethod
    def create(
        cls,
        *,
        hazard: Any,
        horizon: Any,
        validation_start: date,
        validation_end: date,
        event_count: int,
        loss_utility_methodology: str,
        policy_version: str,
        calibration_version: str | None = None,
    ) -> "ThresholdValidationArtifact":
        provisional = object.__new__(cls)
        values = {
            "hazard": hazard,
            "horizon": horizon,
            "validation_start": validation_start,
            "validation_end": validation_end,
            "event_count": event_count,
            "loss_utility_methodology": loss_utility_methodology,
            "policy_version": policy_version,
            "calibration_version": calibration_version,
        }
        for name, value in values.items():
            object.__setattr__(provisional, name, value)
        object.__setattr__(provisional, "artifact_digest", "")
        digest = provisional.expected_digest()
        return cls(artifact_digest=digest, **values)


@dataclass(frozen=True, slots=True)
class AlertPolicyConfig:
    hazard: Any
    horizon: Any
    thresholds: AlertThresholds
    methodology: str
    validation_artifact: ThresholdValidationArtifact | None = None
    minimum_coverage: float = 0.70
    minimum_data_quality: float = 0.60
    acceptable_calibration_statuses: tuple[str, ...] = ("ACCEPTABLE",)
    rapid_probability_change: float = 0.05
    rapid_log_odds_change: float = 0.50

    def __post_init__(self) -> None:
        if not self.methodology.strip():
            raise ValueError("threshold methodology is required")
        if not 0.0 <= self.minimum_coverage <= 1.0:
            raise ValueError("minimum coverage must lie in [0, 1]")
        if not 0.0 <= self.minimum_data_quality <= 1.0:
            raise ValueError("minimum data quality must lie in [0, 1]")
        if self.validation_artifact is not None:
            artifact = self.validation_artifact
            if _key(artifact.hazard, artifact.horizon) != _key(self.hazard, self.horizon):
                raise ValueError("threshold validation artifact does not match policy target")
            if artifact.loss_utility_methodology != self.methodology:
                raise ValueError("policy methodology differs from its validation artifact")

    @property
    def validated(self) -> bool:
        return self.validation_artifact is not None


@dataclass(frozen=True, slots=True)
class AlertState:
    severity: RiskSeverity
    first_seen: date
    last_changed: date
    last_escalated: date | None
    consecutive_observations: int
    peak_probability: float
    current_probability: float


@dataclass(frozen=True, slots=True)
class AlertDecision:
    hazard: Any
    horizon: Any
    analysis_date: date
    severity: RiskSeverity
    indicated_severity: RiskSeverity
    probability: float
    historical_base_rate: float
    relative_risk: float | None
    historical_percentile: float | None
    probability_change_7d: float | None
    probability_change_30d: float | None
    probability_change_90d: float | None
    log_odds_change_30d: float | None
    rapid_deterioration: bool
    evidence_confidence: float
    data_coverage: float
    data_quality: float
    calibration_status: str
    ood_status: str
    regime: Any | None
    trigger_threshold: float | None
    threshold_methodology: str
    evidence_warnings: tuple[EvidenceWarning, ...]
    primary_predictive_contributors: tuple[str, ...]
    contrary_evidence: tuple[str, ...]
    caveats: tuple[str, ...]
    interpretation: str
    state: AlertState
    country_id: str | None = None


def _key(hazard: Any, horizon: Any) -> tuple[str, str]:
    return (str(getattr(hazard, "value", hazard)), str(getattr(horizon, "value", horizon)))


def _logit(probability: float) -> float:
    clipped = min(max(probability, 1e-12), 1.0 - 1e-12)
    return log(clipped / (1.0 - clipped))


@dataclass(slots=True)
class AlertService:
    policies: dict[tuple[str, str], AlertPolicyConfig] = field(default_factory=dict)

    def register(self, policy: AlertPolicyConfig) -> None:
        self.policies[_key(policy.hazard, policy.horizon)] = policy

    def evaluate(
        self,
        *,
        hazard: Any,
        horizon: Any,
        analysis_date: date,
        probability: float,
        base_rate: float,
        coverage: float,
        data_quality: float,
        calibration_status: Any,
        ood_status: Any = "IN_DOMAIN",
        historical_percentile: float | None = None,
        evidence_confidence: float | None = None,
        regime: Any | None = None,
        probability_change_7d: float | None = None,
        probability_change_30d: float | None = None,
        probability_change_90d: float | None = None,
        stale_data: bool = False,
        source_disagreement: bool = False,
        source_failure: bool = False,
        model_drift: bool = False,
        regime_change: bool = False,
        calibration_in_domain: bool = True,
        contributors: Iterable[tuple[str, float]] = (),
        caveats: Iterable[str] = (),
        previous_state: AlertState | None = None,
        policy: AlertPolicyConfig | None = None,
        country_id: str | None = None,
    ) -> AlertDecision:
        if not 0.0 <= probability <= 1.0 or not 0.0 <= base_rate <= 1.0:
            raise ValueError("probability and base rate must lie in [0, 1]")
        if not 0.0 <= coverage <= 1.0 or not 0.0 <= data_quality <= 1.0:
            raise ValueError("coverage and data quality must lie in [0, 1]")
        selected = policy or self.policies.get(_key(hazard, horizon))
        if selected is None:
            raise KeyError(f"no alert policy for {hazard}/{horizon}")

        indicated = self._threshold_level(probability, selected.thresholds)
        indicated = self._apply_hysteresis(indicated, probability, selected.thresholds, previous_state)
        calibration = str(getattr(calibration_status, "value", calibration_status)).upper()
        ood = str(getattr(ood_status, "value", ood_status)).upper()
        warnings: list[EvidenceWarning] = []
        if coverage < selected.minimum_coverage:
            warnings.append(EvidenceWarning.INSUFFICIENT_EVIDENCE)
        if data_quality < selected.minimum_data_quality:
            warnings.append(EvidenceWarning.LOW_DATA_QUALITY)
        if stale_data:
            warnings.append(EvidenceWarning.STALE_DATA)
        if source_disagreement:
            warnings.append(EvidenceWarning.SOURCE_DISAGREEMENT)
        if source_failure:
            warnings.append(EvidenceWarning.DATA_PIPELINE_FAILURE)
        if calibration not in {value.upper() for value in selected.acceptable_calibration_statuses}:
            warnings.append(EvidenceWarning.CALIBRATION_WEAK)
        if ood not in {"IN_DOMAIN", "NONE", "FALSE"} or not calibration_in_domain:
            warnings.append(EvidenceWarning.MODEL_OUT_OF_DOMAIN)
        if model_drift:
            warnings.append(EvidenceWarning.MODEL_DRIFT)
        if regime_change:
            warnings.append(EvidenceWarning.REGIME_CHANGE)

        if not selected.validated:
            severity = RiskSeverity.WATCH_UNCALIBRATED if indicated is not RiskSeverity.NO_ALERT else RiskSeverity.NO_ALERT
        elif warnings and _ORDER[indicated] > _ORDER[RiskSeverity.WATCH]:
            # Preserve the numerical indication separately, but evidence gates
            # prevent a severe operational alert.
            severity = RiskSeverity.WATCH
        else:
            severity = indicated

        log_change = None
        if probability_change_30d is not None:
            previous_probability = min(max(probability - probability_change_30d, 0.0), 1.0)
            log_change = _logit(probability) - _logit(previous_probability)
        rapid = bool(
            probability_change_30d is not None
            and probability_change_30d >= selected.rapid_probability_change
            and log_change is not None
            and log_change >= selected.rapid_log_odds_change
        )
        state = self._next_state(severity, probability, analysis_date, previous_state)
        ranked = tuple(contributors)
        positive = tuple(name for name, value in sorted(ranked, key=lambda item: (-item[1], item[0])) if value > 0)[:5]
        negative = tuple(name for name, value in sorted(ranked, key=lambda item: (item[1], item[0])) if value < 0)[:5]
        combined_caveats = tuple(dict.fromkeys(str(item) for item in caveats if str(item).strip()))
        trigger = selected.thresholds.enter(indicated) if indicated is not RiskSeverity.NO_ALERT else None
        confidence = evidence_confidence if evidence_confidence is not None else coverage * data_quality
        return AlertDecision(
            hazard=hazard,
            horizon=horizon,
            analysis_date=analysis_date,
            severity=severity,
            indicated_severity=indicated,
            probability=probability,
            historical_base_rate=base_rate,
            relative_risk=probability / base_rate if base_rate > 0 else None,
            historical_percentile=historical_percentile,
            probability_change_7d=probability_change_7d,
            probability_change_30d=probability_change_30d,
            probability_change_90d=probability_change_90d,
            log_odds_change_30d=log_change,
            rapid_deterioration=rapid,
            evidence_confidence=min(max(confidence, 0.0), 1.0),
            data_coverage=coverage,
            data_quality=data_quality,
            calibration_status=calibration,
            ood_status=ood,
            regime=regime,
            trigger_threshold=trigger,
            threshold_methodology=selected.methodology,
            evidence_warnings=tuple(dict.fromkeys(warnings)),
            primary_predictive_contributors=positive,
            contrary_evidence=negative,
            caveats=combined_caveats,
            interpretation=self._interpretation(severity, hazard, horizon, warnings),
            state=state,
            country_id=country_id,
        )

    @staticmethod
    def _threshold_level(probability: float, thresholds: AlertThresholds) -> RiskSeverity:
        if probability >= thresholds.critical:
            return RiskSeverity.CRITICAL
        if probability >= thresholds.high:
            return RiskSeverity.HIGH
        if probability >= thresholds.elevated:
            return RiskSeverity.ELEVATED
        if probability >= thresholds.watch:
            return RiskSeverity.WATCH
        return RiskSeverity.NO_ALERT

    @staticmethod
    def _apply_hysteresis(
        indicated: RiskSeverity,
        probability: float,
        thresholds: AlertThresholds,
        previous: AlertState | None,
    ) -> RiskSeverity:
        if previous is None or previous.severity is RiskSeverity.WATCH_UNCALIBRATED:
            return indicated
        if _ORDER[indicated] >= _ORDER[previous.severity]:
            return indicated
        if probability >= thresholds.exit(previous.severity):
            return previous.severity
        return indicated

    @staticmethod
    def _next_state(
        severity: RiskSeverity,
        probability: float,
        analysis_date: date,
        previous: AlertState | None,
    ) -> AlertState:
        if previous is None:
            return AlertState(
                severity=severity,
                first_seen=analysis_date,
                last_changed=analysis_date,
                last_escalated=analysis_date if severity is not RiskSeverity.NO_ALERT else None,
                consecutive_observations=1,
                peak_probability=probability,
                current_probability=probability,
            )
        changed = severity is not previous.severity
        escalated = _ORDER[severity] > _ORDER[previous.severity]
        return AlertState(
            severity=severity,
            first_seen=previous.first_seen,
            last_changed=analysis_date if changed else previous.last_changed,
            last_escalated=analysis_date if escalated else previous.last_escalated,
            consecutive_observations=previous.consecutive_observations + 1 if not changed else 1,
            peak_probability=max(previous.peak_probability, probability),
            current_probability=probability,
        )

    @staticmethod
    def _interpretation(
        severity: RiskSeverity,
        hazard: Any,
        horizon: Any,
        warnings: Iterable[EvidenceWarning],
    ) -> str:
        target = str(getattr(hazard, "value", hazard)).replace("_", " ").lower()
        period = str(getattr(horizon, "value", horizon)).replace("_", " ").lower()
        if EvidenceWarning.INSUFFICIENT_EVIDENCE in warnings:
            return "Available observations do not meet the minimum evidence requirements for a reliable directional assessment."
        if EvidenceWarning.MODEL_OUT_OF_DOMAIN in warnings:
            return "Current conditions differ materially from the historical calibration domain; interpret the numerical estimate cautiously."
        if severity is RiskSeverity.WATCH_UNCALIBRATED:
            return f"Conditions for {target} over {period} are elevated, but operational thresholds or calibration have not been validated."
        if severity is RiskSeverity.CRITICAL:
            return f"The estimated probability of {target} onset over {period} crossed the highest validated threshold; this probabilistic warning does not imply certainty or imminence."
        if severity in {RiskSeverity.HIGH, RiskSeverity.ELEVATED}:
            return f"The calibrated model estimates elevated probability of {target} onset over {period}; this is a probabilistic early-warning signal."
        if severity is RiskSeverity.WATCH:
            return "Conditions have moved into an historically elevated range, but current evidence does not support a stronger warning."
        return f"The model estimate for {target} over {period} remains below the validated watch threshold."
