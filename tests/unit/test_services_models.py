from __future__ import annotations

from datetime import date

import pytest

from fx_cpm.application.calibration_service import (
    CalibrationQuality,
    CalibrationService,
    IsotonicCalibrator,
)
from fx_cpm.application.feature_matrix import FeatureMatrixEncoder, FeatureSample
from fx_cpm.application.models import (
    REQUIRED_MODEL_FAMILIES,
    CalibratedStackingModel,
    CompetingRiskHazardModel,
    DiscreteTimeHazardModel,
    LogisticRegression,
    ModelTournament,
    RegimeInteractionLogisticModel,
    RegularizedLogisticRegression,
)


def sample(day: int, *, x: float | None, other: float | None, target: int) -> FeatureSample:
    return FeatureSample("xx", date(2000, 1, day), {"x": x, "other": other}, target)


def test_feature_encoder_preserves_missingness_and_fits_only_on_training_rows() -> None:
    training = (
        sample(1, x=10.0, other=2.0, target=0),
        sample(2, x=None, other=4.0, target=1),
        sample(3, x=30.0, other=6.0, target=1),
    )
    encoder = FeatureMatrixEncoder().fit(training)
    before = encoder.transform((sample(4, x=None, other=1_000_000.0, target=0),))
    after = encoder.transform((sample(5, x=None, other=-1_000_000.0, target=0),))

    x_index = before.feature_names.index("x")
    missing_index = before.feature_names.index("x__missing")
    assert before.values[0][x_index] == pytest.approx(0.0)  # training median equals training mean
    assert after.values[0][x_index] == pytest.approx(before.values[0][x_index])
    assert before.values[0][missing_index] == 1.0
    assert training[1].features["x"] is None  # source evidence was not overwritten with zero


def test_logistic_baselines_are_deterministic_and_regularization_shrinks() -> None:
    features = tuple((float(value),) for value in range(-4, 5))
    labels = tuple(int(value > 0) for value in range(-4, 5))
    first = LogisticRegression(max_iterations=300).fit(features, labels)
    second = LogisticRegression(max_iterations=300).fit(features, labels)
    regularized = RegularizedLogisticRegression(l2=2.0).fit(features, labels)

    assert first.coefficients_ == second.coefficients_
    assert first.intercept_ == second.intercept_
    predictions = first.predict_proba(((-2.0,), (0.0,), (2.0,)))
    assert predictions[0] < predictions[1] < predictions[2]
    assert abs(regularized.coefficients_[0]) < abs(first.coefficients_[0])


def test_one_class_logistic_window_returns_smoothed_base_rate() -> None:
    model = LogisticRegression().fit(((0.0,), (1.0,), (2.0,)), (0, 0, 0))
    predictions = model.predict_proba(((100.0,), (-100.0,)))
    assert predictions[0] == pytest.approx(predictions[1])
    assert 0.0 < predictions[0] < 0.5


def test_discrete_time_hazard_is_a_monotone_cumulative_term_structure() -> None:
    features = ((-1.0,), (-1.0,), (0.0,), (0.0,), (1.0,), (1.0,))
    intervals = (1, 2, 1, 2, 1, 2)
    events = (0, 0, 0, 1, 1, 1)
    model = DiscreteTimeHazardModel(interval_edges=(1, 2, 4), l2=0.5).fit(features, events, intervals)
    term = model.term_structure((0.25,), (1, 2, 4))

    assert 0.0 <= term[1] <= term[2] <= term[4] <= 1.0


def test_calibration_is_deterministic_monotone_and_cannot_see_final_test() -> None:
    raw = (0.05, 0.10, 0.20, 0.30, 0.60, 0.80, 0.90, 0.95)
    labels = (0, 0, 0, 1, 0, 1, 1, 1)
    dates = tuple(date(2010, month, 1) for month in range(1, 9))
    service = CalibrationService(minimum_events=2)
    fitted = service.fit(raw, labels, method="platt", validation_dates=dates, final_test_start=date(2011, 1, 1))

    assert fitted.calibrator.transform(raw) == fitted.calibrator.transform(raw)
    assert fitted.evaluation.quality is CalibrationQuality.NOT_ASSESSED
    with pytest.raises(ValueError, match="precede"):
        service.fit(raw, labels, validation_dates=dates, final_test_start=date(2010, 8, 1))

    isotonic = IsotonicCalibrator().fit((0.1, 0.2, 0.3, 0.4), (0, 1, 0, 1))
    transformed = isotonic.transform((0.1, 0.2, 0.3, 0.4))
    assert transformed == tuple(sorted(transformed))

    assessed = service.fit(
        raw[:4],
        labels[:4],
        validation_dates=dates[:4],
        evaluation_probabilities=raw[4:],
        evaluation_labels=labels[4:],
        evaluation_dates=dates[4:],
        final_test_start=date(2011, 1, 1),
    )
    assert assessed.evaluation.quality is not CalibrationQuality.NOT_ASSESSED
    assert assessed.evaluation.evaluation_start == dates[4]


def test_generic_binary_tournament_is_deterministic_on_chronological_holdout() -> None:
    train_x = tuple((float(index % 5), float(index // 5)) for index in range(30))
    train_y = tuple(int((row[0] > 2) ^ (row[1] > 2)) for row in train_x)
    test_x = tuple((float(index % 5), float(index // 5)) for index in range(30, 40))
    test_y = tuple(int((row[0] > 2) ^ (row[1] > 2)) for row in test_x)
    train_dates = tuple(date(2000, 1, 1).replace(year=2000 + index) for index in range(30))
    test_dates = tuple(date(2030, 1, 1).replace(year=2030 + index) for index in range(10))

    first = ModelTournament().evaluate(
        train_x, train_y, test_x, test_y, train_dates=train_dates, test_dates=test_dates
    )
    second = ModelTournament().evaluate(
        train_x, train_y, test_x, test_y, train_dates=train_dates, test_dates=test_dates
    )

    assert first == second
    assert {item.name for item in first.scores} == {
        "logistic",
        "regularized_logistic",
        "gam",
        "gradient_boosted_trees",
        "random_forest",
    }
    assert len(REQUIRED_MODEL_FAMILIES) == 9
    assert {item.name for item in REQUIRED_MODEL_FAMILIES} >= {
        "discrete_time_hazard",
        "competing_risk",
        "regime_interaction",
        "calibrated_ensemble_stack",
    }
    assert all(item.evaluation_contract for item in REQUIRED_MODEL_FAMILIES)
    with pytest.raises(ValueError, match="strictly follow"):
        ModelTournament().evaluate(
            train_x,
            train_y,
            test_x,
            test_y,
            train_dates=test_dates + train_dates[:20],
            test_dates=test_dates,
        )


def test_regime_competing_risk_and_heldout_stack_adapters_are_operational() -> None:
    features = ((-1.0,), (-0.5,), (0.5,), (1.0,), (-1.0,), (-0.5,), (0.5,), (1.0,))
    labels = (0, 0, 1, 1, 1, 1, 0, 0)
    regimes = ("float",) * 4 + ("peg",) * 4
    regime_model = RegimeInteractionLogisticModel(l2=0.2).fit(features, labels, regimes)
    probabilities = regime_model.predict_proba(((0.8,), (0.8,)), ("float", "peg"))
    assert probabilities[0] > probabilities[1]

    competing = CompetingRiskHazardModel(("fx", "bank"), interval_edges=(1, 2), l2=0.5)
    competing.fit(features, (None, None, "fx", "fx", "bank", "bank", None, None), (1, 2, 1, 2, 1, 2, 1, 2))
    term = competing.term_structure((0.2,), (1, 2, 3))
    assert term[1]["fx"] <= term[2]["fx"] <= term[3]["fx"]
    assert sum(term[3].values()) <= 1.0 + 1e-12

    stack = CalibratedStackingModel().fit(
        ((0.1, 0.2), (0.2, 0.3), (0.7, 0.6), (0.8, 0.9)),
        (0, 0, 1, 1),
        validation_dates=(date(2020, 1, 1), date(2020, 2, 1), date(2020, 3, 1), date(2020, 4, 1)),
        final_test_start=date(2020, 5, 1),
    )
    assert stack.predict_proba(((0.15, 0.2),))[0] < stack.predict_proba(((0.85, 0.8),))[0]
