from __future__ import annotations

from copy import deepcopy

from fx_cpm.demo import build_demo_report
from fx_cpm.reporting import canonical_json, report_schema_path, validate_report


def test_demo_report_passes_standard_library_contract() -> None:
    issues = validate_report(build_demo_report(), use_jsonschema=False)
    assert [issue for issue in issues if issue.level == "ERROR"] == []


def test_canonical_json_is_deterministic() -> None:
    report = build_demo_report()
    assert canonical_json(report) == canonical_json(deepcopy(report))
    assert canonical_json(report).endswith("\n")


def test_canonical_schema_artifact_is_locatable() -> None:
    schema_path = report_schema_path()
    assert schema_path is not None
    assert schema_path.name == "report.schema.json"


def test_missing_evidence_cannot_carry_numeric_zero() -> None:
    report = build_demo_report()
    report["provenance"][1]["value"] = 0.0
    issues = validate_report(report, use_jsonschema=False)
    assert any(issue.code == "MISSING_IS_NOT_ZERO" for issue in issues)


def test_uncalibrated_forecast_cannot_issue_high_alert() -> None:
    report = build_demo_report()
    report["alerts"][0]["severity"] = "HIGH"
    issues = validate_report(report, use_jsonschema=False)
    assert any(issue.code == "SEVERE_ALERT_UNCALIBRATED" for issue in issues)


def test_uncalibrated_output_cannot_be_labelled_probability() -> None:
    report = build_demo_report()
    report["forecasts"][0]["display_label"] = "PROBABILITY"
    issues = validate_report(report, use_jsonschema=False)
    assert any(issue.code == "PROBABILITY_LANGUAGE_GATE" for issue in issues)


def test_forecast_status_cannot_bypass_report_level_calibration_gate() -> None:
    report = build_demo_report()
    forecast = report["forecasts"][0]
    forecast["calibrated_probability"] = forecast["raw_probability"]
    forecast["probability_status"] = "CALIBRATED_VALIDATED"
    forecast["display_label"] = "PROBABILITY"

    issues = validate_report(report, use_jsonschema=False)
    codes = {issue.code for issue in issues}

    assert "CALIBRATED_MODE_CONFLICT" in codes
    assert "CALIBRATION_EVIDENCE_MISSING" in codes
    assert "VALIDATION_EVIDENCE_MISSING" in codes
    assert "CALIBRATION_DOMAIN_UNSUPPORTED" in codes


def test_validated_probability_requires_uncertainty_and_training_cutoff() -> None:
    report = build_demo_report()
    forecast = report["forecasts"][0]
    forecast.update(
        calibrated_probability=forecast["raw_probability"],
        probability_status="CALIBRATED_VALIDATED",
        display_label="PROBABILITY",
        ood_status="IN_DOMAIN",
    )
    report["analysis"]["report_mode"] = "RESEARCH_CALIBRATED"
    report["calibration_version"] = "platt-1"
    report["calibration"].update(
        status="ACCEPTABLE",
        method="PLATT",
        calibration_period="2016-2020",
        event_count=12,
        brier_score=0.08,
        log_loss=0.31,
    )
    report["validation"].update(
        status="VALIDATED",
        chronological_split=True,
        final_test_untouched=True,
        alert_thresholds_backtested=True,
        metrics={"brier_score": 0.09, "log_loss": 0.33},
    )

    issues = validate_report(report, use_jsonschema=False)
    codes = {issue.code for issue in issues}

    assert "TRAINING_CUTOFF_MISSING" in codes
    assert "UNCERTAINTY_MISSING" not in codes

    forecast["training_end_date"] = "2020-12-31"
    errors = [
        issue for issue in validate_report(report, use_jsonschema=False) if issue.level == "ERROR"
    ]
    assert errors == []


def test_severe_alert_requires_threshold_evidence() -> None:
    report = build_demo_report()
    forecast = report["forecasts"][0]
    forecast.update(
        calibrated_probability=forecast["raw_probability"],
        probability_status="CALIBRATED_VALIDATED",
        display_label="PROBABILITY",
        ood_status="IN_DOMAIN",
        training_end_date="2020-12-31",
    )
    report["analysis"]["report_mode"] = "RESEARCH_CALIBRATED"
    report["calibration_version"] = "platt-1"
    report["calibration"].update(
        status="ACCEPTABLE",
        method="PLATT",
        calibration_period="2016-2020",
        event_count=12,
        brier_score=0.08,
        log_loss=0.31,
    )
    report["validation"].update(
        status="VALIDATED",
        chronological_split=True,
        final_test_untouched=True,
        alert_thresholds_backtested=True,
        metrics={"brier_score": 0.09, "log_loss": 0.33},
    )
    alert = report["alerts"][0]
    alert.update(severity="HIGH", calibration_status="ACCEPTABLE")

    issues = validate_report(report, use_jsonschema=False)
    assert any(issue.code == "ALERT_THRESHOLD_EVIDENCE_MISSING" for issue in issues)
