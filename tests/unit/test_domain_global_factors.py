from datetime import date, timedelta

import pytest

from fx_cpm.domain import (
    DomainValidationError,
    FactorTrainingWindow,
    GlobalFactorObservation,
    fit_global_factor_model,
)


def _observation(day: int, usd: float, risk: float, noise: float = 0.0) -> GlobalFactorObservation:
    observed_on = date(2020, 1, 1) + timedelta(days=day)
    return GlobalFactorObservation(
        observed_on=observed_on,
        available_on=observed_on,
        fx_return=0.01 + 0.5 * usd - 0.25 * risk + noise,
        factors={"global_usd": usd, "global_risk": risk},
    )


def test_global_factor_fit_ignores_rows_outside_or_unavailable_in_training_window() -> None:
    training = (
        _observation(0, -2.0, 0.0, 0.01),
        _observation(1, -1.0, 1.0, -0.01),
        _observation(2, 0.0, -1.0, 0.02),
        _observation(3, 1.0, 2.0, -0.02),
        _observation(4, 2.0, -2.0, 0.01),
        _observation(5, 3.0, 1.0, -0.01),
    )
    delayed = GlobalFactorObservation(
        observed_on=date(2020, 1, 3),
        available_on=date(2020, 2, 1),
        fx_return=999.0,
        factors={"global_usd": 0.0, "global_risk": 0.0},
    )
    future = GlobalFactorObservation(
        observed_on=date(2030, 1, 1),
        available_on=date(2030, 1, 1),
        fx_return=-999.0,
        factors={"global_usd": 999.0, "global_risk": 999.0},
    )
    window = FactorTrainingWindow(date(2020, 1, 1), date(2020, 1, 6))
    baseline = fit_global_factor_model(
        training,
        factor_names=("global_usd", "global_risk"),
        training_window=window,
        as_of=date(2020, 2, 2),
    )
    guarded = fit_global_factor_model(
        (*training, delayed, future),
        factor_names=("global_usd", "global_risk"),
        training_window=window,
        as_of=date(2020, 2, 2),
    )

    assert guarded.intercept == pytest.approx(baseline.intercept)
    assert dict(guarded.coefficients) == pytest.approx(dict(baseline.coefficients))
    assert guarded.residual_standard_deviation == pytest.approx(
        baseline.residual_standard_deviation
    )
    assert guarded.n_observations == 6
    assert guarded.ignored_observations == 2
    assert max(guarded.training_observation_dates) == date(2020, 1, 6)
    assert guarded.latest_training_availability <= guarded.training_window.end


def test_fx_residual_estimate_uses_fitted_training_parameters_and_scale() -> None:
    training = tuple(
        _observation(day, usd, risk, noise)
        for day, (usd, risk, noise) in enumerate(
            (
                (-2.0, 0.0, 0.01),
                (-1.0, 1.0, -0.01),
                (0.0, -1.0, 0.02),
                (1.0, 2.0, -0.02),
                (2.0, -2.0, 0.01),
                (3.0, 1.0, -0.01),
            )
        )
    )
    fit = fit_global_factor_model(
        training,
        factor_names=("global_usd", "global_risk"),
        training_window=FactorTrainingWindow(date(2020, 1, 1), date(2020, 1, 6)),
        as_of=date(2020, 1, 6),
    )
    target = GlobalFactorObservation(
        observed_on=date(2020, 1, 7),
        available_on=date(2020, 1, 7),
        fx_return=0.40,
        factors={"global_usd": 0.2, "global_risk": -0.1},
    )

    estimate = fit.estimate(target, as_of=date(2020, 1, 7))

    assert estimate.residual_return == pytest.approx(
        target.fx_return - estimate.expected_global_factor_return
    )
    assert estimate.standardized_residual == pytest.approx(
        estimate.residual_return / fit.residual_standard_deviation
    )
    assert estimate.training_window_end < estimate.observed_on
    assert estimate.interpretation == "COUNTRY_SPECIFIC_RESIDUAL_NOT_CAUSAL_EFFECT"


def test_global_factor_scoring_blocks_future_observations() -> None:
    noises = (0.01, -0.02, 0.015, -0.005, 0.02, -0.01)
    training = tuple(
        _observation(day, float(day), float(day % 2), noises[day]) for day in range(6)
    )
    fit = fit_global_factor_model(
        training,
        factor_names=("global_usd", "global_risk"),
        training_window=FactorTrainingWindow(date(2020, 1, 1), date(2020, 1, 6)),
        as_of=date(2020, 1, 6),
    )
    target = _observation(10, 1.0, 1.0)

    with pytest.raises(DomainValidationError, match="not visible as_of"):
        fit.estimate(target, as_of=date(2020, 1, 7))
