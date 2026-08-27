from datetime import date

import pytest

from fx_cpm.domain import (
    AlertMarker,
    AlertPolicy,
    AlertThresholds,
    CalibrationStatus,
    DomainValidationError,
    EvidenceAlert,
    ForecastHorizon,
    ForecastRecord,
    HazardProbabilityVector,
    HazardType,
    ModelTier,
    OODStatus,
    ProbabilityMomentum,
    RegimeType,
    RiskAlertLevel,
    build_alert_record,
    relative_risk,
    severity_with_hysteresis,
    validate_probability_term_structure,
)


def forecast(**overrides: object) -> ForecastRecord:
    values: dict[str, object] = {
        "country": "X",
        "hazard": HazardType.CURRENCY_CRISIS,
        "analysis_date": date(2024, 1, 31),
        "horizon": ForecastHorizon.MONTHS_12,
        "raw_probability": 0.31,
        "calibrated_probability": 0.30,
        "base_rate": 0.06,
        "historical_percentile": 96.0,
        "confidence": 0.86,
        "coverage": 0.9,
        "model_version": "model-1",
        "calibration_version": "cal-1",
        "regime": RegimeType.MANAGED_FLOAT,
        "training_end_date": date(2023, 12, 31),
        "model_tier": ModelTier.MODERN_MARKET_ENHANCED,
        "ood_status": OODStatus.IN_DOMAIN,
    }
    values.update(overrides)
    return ForecastRecord(**values)  # type: ignore[arg-type]


def thresholds(**overrides: object) -> AlertThresholds:
    values: dict[str, object] = {
        "hazard": HazardType.CURRENCY_CRISIS,
        "horizon": ForecastHorizon.MONTHS_12,
        "watch": 0.10,
        "elevated": 0.20,
        "high": 0.30,
        "critical": 0.50,
        "methodology": "validation utility with missed-event cost 5x false-alert cost",
        "validation_start": date(1990, 1, 1),
        "validation_end": date(2020, 12, 31),
        "event_count": 42,
        "exit_ratio": 0.8,
    }
    values.update(overrides)
    return AlertThresholds(**values)  # type: ignore[arg-type]


def test_forecast_computes_relative_risk_and_rejects_inconsistent_claims() -> None:
    item = forecast()
    assert item.reported_probability == 0.30
    assert item.relative_risk == pytest.approx(5.0)
    assert item.probability_label == "CALIBRATED_PROBABILITY"
    assert relative_risk(0.05, 0.005) == pytest.approx(10.0)
    with pytest.raises(DomainValidationError, match="inconsistent"):
        forecast(relative_risk=2.0)


def test_cumulative_term_structure_cannot_fall_with_horizon() -> None:
    short = forecast(horizon="90d", raw_probability=0.1, calibrated_probability=0.1)
    long = forecast(horizon="12m", raw_probability=0.2, calibrated_probability=0.2)
    validate_probability_term_structure((long, short))
    with pytest.raises(DomainValidationError, match="falls"):
        validate_probability_term_structure((short, forecast(horizon="12m", raw_probability=0.05, calibrated_probability=0.05)))


def test_hazard_vector_requires_all_eight_separate_probabilities() -> None:
    vector = HazardProbabilityVector({hazard: 0.01 for hazard in HazardType})
    assert len(vector.as_ordered_tuple()) == 8
    with pytest.raises(DomainValidationError, match="all eight"):
        HazardProbabilityVector({HazardType.CURRENCY_CRISIS: 0.1})


def test_hysteresis_uses_lower_exit_than_entry_threshold() -> None:
    policy_thresholds = thresholds()
    assert severity_with_hysteresis(0.25, policy_thresholds, previous_level=RiskAlertLevel.HIGH) is RiskAlertLevel.HIGH
    assert severity_with_hysteresis(0.23, policy_thresholds, previous_level=RiskAlertLevel.HIGH) is RiskAlertLevel.ELEVATED


def test_calibration_and_evidence_gates_cap_severe_alert_but_keep_estimate() -> None:
    item = forecast(coverage=0.4, ood_status=OODStatus.OUT_OF_DOMAIN)
    evaluation = AlertPolicy(thresholds()).evaluate(
        item,
        calibration_status=CalibrationStatus.WEAK,
        data_quality=0.5,
    )
    assert evaluation.proposed_level is RiskAlertLevel.HIGH
    assert evaluation.issued_level is RiskAlertLevel.WATCH
    assert EvidenceAlert.INSUFFICIENT_EVIDENCE in evaluation.evidence_alerts
    assert EvidenceAlert.LOW_DATA_QUALITY in evaluation.evidence_alerts
    assert EvidenceAlert.MODEL_OUT_OF_DOMAIN in evaluation.evidence_alerts
    assert EvidenceAlert.CALIBRATION_WEAK in evaluation.evidence_alerts
    assert item.reported_probability == 0.30


def test_critical_requires_calibration_and_validated_thresholds() -> None:
    critical = forecast(raw_probability=0.6, calibrated_probability=0.6)
    valid = AlertPolicy(thresholds()).evaluate(
        critical,
        calibration_status=CalibrationStatus.ACCEPTABLE,
        data_quality=0.9,
    )
    assert valid.issued_level is RiskAlertLevel.CRITICAL
    uncalibrated = forecast(
        raw_probability=0.6,
        calibrated_probability=None,
        calibration_version=None,
    )
    unvalidated = AlertPolicy(None).evaluate(
        uncalibrated,
        calibration_status=CalibrationStatus.UNCALIBRATED,
        data_quality=0.9,
    )
    assert unvalidated.issued_level is RiskAlertLevel.WATCH_UNCALIBRATED


def test_rapid_change_is_a_marker_not_an_absolute_severity_override() -> None:
    low = forecast(raw_probability=0.09, calibrated_probability=0.09, base_rate=0.06)
    momentum = ProbabilityMomentum.from_probabilities(0.09, previous_30d=0.03)
    evaluation = AlertPolicy(
        thresholds(), rapid_deterioration_threshold_30d=0.05
    ).evaluate(
        low,
        calibration_status=CalibrationStatus.ACCEPTABLE,
        data_quality=0.9,
        momentum=momentum,
    )
    assert evaluation.issued_level is RiskAlertLevel.NO_ALERT
    assert evaluation.markers == (AlertMarker.RAPID_DETERIORATION,)


def test_alert_record_tracks_persistence_peak_and_change_dates() -> None:
    item = forecast()
    policy = AlertPolicy(thresholds())
    evaluation = policy.evaluate(
        item,
        calibration_status=CalibrationStatus.ACCEPTABLE,
        data_quality=0.9,
    )
    first = build_alert_record(
        item,
        evaluation,
        calibration_status=CalibrationStatus.ACCEPTABLE,
        analysis_date=item.analysis_date,
    )
    next_date = date(2024, 2, 1)
    next_forecast = forecast(analysis_date=next_date, calibrated_probability=0.32, raw_probability=0.32)
    next_evaluation = policy.evaluate(
        next_forecast,
        calibration_status=CalibrationStatus.ACCEPTABLE,
        data_quality=0.9,
        previous_level=first.current_severity,
    )
    second = build_alert_record(
        next_forecast,
        next_evaluation,
        calibration_status=CalibrationStatus.ACCEPTABLE,
        analysis_date=next_date,
        previous=first,
    )
    assert second.first_seen_date == first.first_seen_date
    assert second.last_changed_date == first.last_changed_date
    assert second.consecutive_observations == 2
    assert second.peak_probability == pytest.approx(0.32)

