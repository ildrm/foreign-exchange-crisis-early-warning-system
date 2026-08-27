from datetime import date

import pytest

from fx_cpm.domain import (
    CalibrationMethod,
    CalibrationRecord,
    CalibrationStatus,
    DomainValidationError,
    beta_scale,
    binary_log_loss,
    brier_score,
    calibration_bins,
    calibration_intercept_slope,
    expected_calibration_error,
    isotonic_scale,
    platt_scale,
)


def test_brier_log_loss_and_reliability_bins() -> None:
    probabilities = (0.1, 0.9)
    outcomes = (0, 1)
    assert brier_score(probabilities, outcomes) == pytest.approx(0.01)
    assert binary_log_loss(probabilities, outcomes) == pytest.approx(-__import__("math").log(0.9))
    bins = calibration_bins(probabilities, outcomes, n_bins=2)
    assert [item.count for item in bins] == [1, 1]
    assert expected_calibration_error(probabilities, outcomes, n_bins=2) == pytest.approx(0.1)


def test_calibration_transforms_are_real_probability_math() -> None:
    assert platt_scale(0.2, intercept=0.0, slope=1.0) == pytest.approx(0.2)
    assert beta_scale(0.2, a=1.0, b=-1.0, intercept=0.0) == pytest.approx(0.2)
    assert isotonic_scale(
        0.5,
        thresholds=(0.0, 0.4, 0.8, 1.0),
        calibrated_values=(0.0, 0.3, 0.9, 1.0),
    ) == pytest.approx(0.45)


def test_calibration_intercept_and_slope_recover_identity_mapping() -> None:
    probabilities = (0.2,) * 10 + (0.8,) * 10
    outcomes = (1, 1, 0, 0, 0, 0, 0, 0, 0, 0) + (1,) * 8 + (0, 0)
    fit = calibration_intercept_slope(probabilities, outcomes)
    assert fit.converged
    assert fit.intercept == pytest.approx(0.0, abs=1e-8)
    assert fit.slope == pytest.approx(1.0, abs=1e-8)


def test_calibration_record_keeps_period_domain_and_final_test_separate() -> None:
    record = CalibrationRecord(
        method=CalibrationMethod.PLATT,
        period_start=date(2010, 1, 1),
        period_end=date(2018, 12, 31),
        event_count=25,
        sample_count=200,
        brier_score=0.08,
        log_loss=0.3,
        expected_calibration_error=0.03,
        status=CalibrationStatus.ACCEPTABLE,
        domain_min=0.02,
        domain_max=0.65,
        test_window_start=date(2019, 1, 1),
        version="cal-1",
    )
    assert record.in_supported_domain(0.5)
    assert not record.in_supported_domain(0.8)
    with pytest.raises(DomainValidationError, match="precede"):
        CalibrationRecord(
            method=CalibrationMethod.PLATT,
            period_start=date(2010, 1, 1),
            period_end=date(2019, 1, 1),
            event_count=25,
            brier_score=0.08,
            log_loss=0.3,
            status=CalibrationStatus.ACCEPTABLE,
            test_window_start=date(2019, 1, 1),
        )

