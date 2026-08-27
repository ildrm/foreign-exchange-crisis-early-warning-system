import math

import pytest

from fx_cpm.domain import (
    CORE_FX_FEATURE_DEFINITIONS,
    DomainValidationError,
    EMPWeights,
    aggregate_fx_stress,
    downside_volatility,
    exchange_market_pressure,
    expected_fx_return,
    fx_surprise,
    maximum_drawdown,
    parallel_market_premium,
    realized_volatility,
)


def test_emp_sign_convention_and_documented_weights() -> None:
    # Depreciation, reserve loss, and rate defence all raise pressure.
    assert exchange_market_pressure(2.0, -1.0, 0.5) == pytest.approx(3.5)
    assert exchange_market_pressure(
        2.0,
        -1.0,
        0.5,
        weights=EMPWeights(2.0, 1.0, 1.0),
        normalize_weights=True,
    ) == pytest.approx(1.375)


def test_parallel_premium_and_factor_adjusted_surprise() -> None:
    assert parallel_market_premium(150.0, 100.0) == pytest.approx(50.0)
    expected = expected_fx_return(
        intercept=0.001,
        factor_values=(0.02, -0.01),
        coefficients=(0.5, 0.2),
    )
    assert expected == pytest.approx(0.009)
    assert fx_surprise(0.029, expected, 0.01) == pytest.approx(2.0)
    with pytest.raises(DomainValidationError, match="positive"):
        parallel_market_premium(100.0, 0.0)


def test_missing_stress_components_are_not_replaced_by_zero() -> None:
    partial = aggregate_fx_stress(
        {"emp": 2.0, "residual": None, "premium": 1.0},
        weights={"emp": 2.0, "residual": 1.0, "premium": 1.0},
        minimum_coverage=0.8,
    )
    assert partial.score is None
    assert partial.coverage == pytest.approx(0.75)
    assert partial.missing_components == ("residual",)
    available = aggregate_fx_stress(
        {"emp": 2.0, "residual": None, "premium": 1.0},
        weights={"emp": 2.0, "residual": 1.0, "premium": 1.0},
        minimum_coverage=0.7,
    )
    assert available.score == pytest.approx(5.0 / 3.0)
    assert available.label == "STRESS_SCORE"


def test_volatility_and_drawdown_formulas_are_deterministic() -> None:
    assert realized_volatility((-0.01, 0.01), annualization_periods=1) == pytest.approx(
        math.sqrt(0.0002)
    )
    assert downside_volatility((-0.02, 0.01), annualization_periods=1) == pytest.approx(
        math.sqrt(0.0002)
    )
    assert maximum_drawdown((100.0, 120.0, 90.0, 110.0)) == pytest.approx(0.25)


def test_core_fx_feature_definitions_keep_math_and_limitations_centralized() -> None:
    assert set(CORE_FX_FEATURE_DEFINITIONS) == {
        "fx_spot_log_return",
        "exchange_market_pressure",
        "parallel_market_premium",
        "fx_surprise",
    }
    for definition in CORE_FX_FEATURE_DEFINITIONS.values():
        assert definition.formula
        assert definition.required_inputs
        assert definition.source_requirements
        assert definition.limitations
        assert definition.supported_hazards
        assert definition.valid_regimes

