from __future__ import annotations

from datetime import date, datetime, timezone

from fx_cpm.application.alert_service import (
    AlertPolicyConfig,
    AlertService,
    AlertThresholds,
    EvidenceWarning,
    RiskSeverity,
    ThresholdValidationArtifact,
)
from fx_cpm.application.feature_matrix import FeatureSample
from fx_cpm.application.forecast_service import ForecastService
from fx_cpm.application.report_service import (
    REQUIRED_REPORT_SECTIONS,
    ReportService,
    ReportVersions,
)


def policy(*, validated: bool = True) -> AlertPolicyConfig:
    methodology = "validation loss: missed event=5, false alert=1"
    artifact = (
        ThresholdValidationArtifact.create(
            hazard="fx",
            horizon="12m",
            validation_start=date(1990, 1, 1),
            validation_end=date(1999, 12, 31),
            event_count=12,
            loss_utility_methodology=methodology,
            policy_version="test-1.0",
            calibration_version="test-calibration",
        )
        if validated
        else None
    )
    return AlertPolicyConfig(
        hazard="fx",
        horizon="12m",
        thresholds=AlertThresholds(
            watch=0.10,
            elevated=0.20,
            high=0.30,
            critical=0.40,
            high_exit=0.27,
        ),
        methodology=methodology,
        validation_artifact=artifact,
    )


def test_alert_gates_keep_probability_visible_but_cap_operational_severity() -> None:
    service = AlertService()
    decision = service.evaluate(
        hazard="fx",
        horizon="12m",
        analysis_date=date(2024, 1, 1),
        probability=0.45,
        base_rate=0.05,
        coverage=0.4,
        data_quality=0.9,
        calibration_status="ACCEPTABLE",
        contributors=(("fx_emp", 1.2), ("exports", -0.4)),
        policy=policy(),
    )

    assert decision.probability == 0.45
    assert decision.indicated_severity is RiskSeverity.CRITICAL
    assert decision.severity is RiskSeverity.WATCH
    assert EvidenceWarning.INSUFFICIENT_EVIDENCE in decision.evidence_warnings
    assert decision.primary_predictive_contributors == ("fx_emp",)
    assert decision.contrary_evidence == ("exports",)


def test_unvalidated_policy_never_issues_severe_alert_and_hysteresis_prevents_flicker() -> None:
    service = AlertService()
    uncalibrated = service.evaluate(
        hazard="fx",
        horizon="12m",
        analysis_date=date(2024, 1, 1),
        probability=0.9,
        base_rate=0.05,
        coverage=1.0,
        data_quality=1.0,
        calibration_status="UNCALIBRATED",
        policy=policy(validated=False),
    )
    assert uncalibrated.severity is RiskSeverity.WATCH_UNCALIBRATED

    high = service.evaluate(
        hazard="fx",
        horizon="12m",
        analysis_date=date(2024, 2, 1),
        probability=0.31,
        base_rate=0.05,
        coverage=1.0,
        data_quality=1.0,
        calibration_status="ACCEPTABLE",
        policy=policy(),
    )
    still_high = service.evaluate(
        hazard="fx",
        horizon="12m",
        analysis_date=date(2024, 2, 2),
        probability=0.28,
        base_rate=0.05,
        coverage=1.0,
        data_quality=1.0,
        calibration_status="ACCEPTABLE",
        previous_state=high.state,
        policy=policy(),
    )
    assert high.severity is RiskSeverity.HIGH
    assert still_high.severity is RiskSeverity.HIGH


def test_report_is_versioned_deterministic_and_uses_probabilistic_language() -> None:
    training = tuple(
        FeatureSample("xx", date(2000 + index, 1, 1), {"fx_emp": float(index)}, index % 2, hazard="fx", horizon="12m")
        for index in range(8)
    )
    validation = tuple(
        FeatureSample("xx", date(2008 + index, 1, 1), {"fx_emp": float(index + 8)}, index % 2, hazard="fx", horizon="12m")
        for index in range(4)
    )
    forecast_service = ForecastService()
    forecast_service.fit(training, hazard="fx", horizon="12m", validation_samples=validation, final_test_start=date(2012, 1, 1))
    estimate = forecast_service.forecast(
        FeatureSample("xx", date(2012, 1, 1), {"fx_emp": 12.0}, hazard="fx", horizon="12m"),
        hazard="fx",
        horizon="12m",
    )
    alert_service = AlertService()
    decision = alert_service.evaluate(
        hazard="fx",
        horizon="12m",
        analysis_date=date(2012, 1, 1),
        probability=estimate.displayed_probability,
        base_rate=estimate.base_rate,
        coverage=1.0,
        data_quality=1.0,
        calibration_status="ACCEPTABLE",
        policy=policy(),
    )
    report_service = ReportService()
    kwargs = dict(
        as_of=date(2012, 1, 1),
        forecasts=(estimate,),
        alerts=(decision,),
        versions=ReportVersions(model="test-model"),
        generated_at=datetime(2012, 1, 2, tzinfo=timezone.utc),
    )
    first = report_service.build(**kwargs)
    second = report_service.build(**kwargs)

    assert first == second
    assert all(section in first for section in REQUIRED_REPORT_SECTIONS)
    assert "will occur" not in first["analysis"]["executive_summary"].lower()
    assert "risk estimate" in first["analysis"]["executive_summary"].lower()
