import pytest

from fx_cpm.domain import (
    DomainValidationError,
    HazardType,
    calculate_systemic_stress_index,
)


def test_systemic_stress_is_a_weighted_score_not_an_independence_probability() -> None:
    result = calculate_systemic_stress_index(
        {
            HazardType.FX: 80.0,
            HazardType.BANK: 40.0,
            HazardType.SOV: None,
        },
        weights={HazardType.FX: 2.0, HazardType.BANK: 1.0, HazardType.SOV: 1.0},
        minimum_coverage=0.7,
    )

    assert result.score == pytest.approx(200.0 / 3.0)
    assert result.coverage == pytest.approx(0.75)
    assert sum(item.index_points for item in result.contributions) == pytest.approx(result.score)
    assert result.missing_hazards == (HazardType.SOV,)
    assert result.elevated_hazards == (HazardType.FX,)
    assert result.label == "SYSTEMIC_STRESS_INDEX"
    assert result.is_probability is False
    assert "arithmetic mean" in result.methodology
    assert "no probability independence" in result.methodology


def test_systemic_stress_reports_unavailable_when_coverage_is_too_low() -> None:
    result = calculate_systemic_stress_index(
        {HazardType.FX: 100.0, HazardType.BANK: None, HazardType.SOV: None},
        minimum_coverage=0.5,
    )

    assert result.score is None
    assert result.coverage == pytest.approx(1.0 / 3.0)
    assert result.contributions == ()


def test_systemic_stress_validates_multi_hazard_0_to_100_inputs() -> None:
    with pytest.raises(DomainValidationError, match="at least two hazards"):
        calculate_systemic_stress_index({HazardType.FX: 50.0})
    with pytest.raises(DomainValidationError, match="between 0 and 100"):
        calculate_systemic_stress_index({HazardType.FX: 101.0, HazardType.BANK: 20.0})
