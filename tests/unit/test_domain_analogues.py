from datetime import date

import pytest

from fx_cpm.domain import (
    AnalogueQuery,
    AnalogueReferenceWindow,
    DomainValidationError,
    HistoricalState,
    find_historical_analogues,
)


def _state(
    country: str,
    observed_on: date,
    feature: float,
    global_value: float,
    *,
    regime: str = "managed_float",
    development: str = "emerging",
    coverage: float = 0.9,
    available_on: date | None = None,
) -> HistoricalState:
    return HistoricalState(
        country_code=country,
        observed_on=observed_on,
        available_on=available_on or observed_on,
        regime=regime,
        development_level=development,
        data_coverage=coverage,
        features={"emp": feature},
        global_state={"global_usd": global_value},
        outcomes={
            "crisis_occurred": country == "AA",
            "event_type": "currency_crisis" if country == "AA" else None,
            "time_to_event_days": 90 if country == "AA" else None,
        },
        context={"conditions": f"state for {country}"},
    )


def test_analogue_search_uses_only_supplied_past_visible_reference_window() -> None:
    history = (
        _state("AA", date(2018, 1, 1), 0.0, 0.0, coverage=0.95),
        _state("BB", date(2019, 1, 1), 2.0, 2.0),
        _state(
            "CC",
            date(2020, 1, 1),
            4.0,
            4.0,
            regime="peg",
            development="advanced",
            coverage=0.6,
        ),
        # Observed in-window but unavailable at the analysis date: excluded.
        _state(
            "DD",
            date(2019, 6, 1),
            1_000.0,
            1_000.0,
            available_on=date(2030, 1, 1),
        ),
        # A future outlier cannot enter either candidates or standardization.
        _state("ZZ", date(2035, 1, 1), 10_000.0, 10_000.0),
    )
    query = AnalogueQuery(
        country_code="TR",
        observed_on=date(2024, 1, 1),
        regime="managed_float",
        development_level="emerging",
        data_coverage=0.95,
        features={"emp": 0.2},
        global_state={"global_usd": 0.1},
    )

    result = find_historical_analogues(
        query=query,
        history=history,
        reference_window=AnalogueReferenceWindow(date(2018, 1, 1), date(2020, 12, 31)),
        as_of=date(2024, 1, 1),
        limit=3,
    )

    assert result.candidates_considered == 3
    assert result.feature_statistics[0].observations == 3
    assert result.feature_statistics[0].mean == pytest.approx(2.0)
    assert [match.country_code for match in result.matches][0] == "AA"
    assert {match.country_code for match in result.matches} == {"AA", "BB", "CC"}
    best = result.matches[0]
    assert best.outcomes["crisis_occurred"] is True
    assert best.outcomes["event_type"] == "currency_crisis"
    assert best.outcomes["time_to_event_days"] == 90
    assert best.feature_state["emp"] == 0.0
    assert best.global_state["global_usd"] == 0.0
    assert best.conditions_at_time["conditions"] == "state for AA"
    assert best.interpretation == "CONTEXTUAL_EVIDENCE_NOT_CAUSAL_PROOF"


def test_analogue_components_account_for_regime_development_and_coverage() -> None:
    query = AnalogueQuery(
        "TR",
        date(2024, 1, 1),
        "managed_float",
        "emerging",
        1.0,
        {"emp": 1.0},
        {"global_usd": 1.0},
    )
    result = find_historical_analogues(
        query=query,
        history=(
            _state("AA", date(2018, 1, 1), 1.0, 1.0, coverage=1.0),
            _state(
                "BB",
                date(2019, 1, 1),
                1.0,
                1.0,
                regime="peg",
                development="advanced",
                coverage=0.5,
            ),
        ),
        reference_window=AnalogueReferenceWindow(date(2018, 1, 1), date(2019, 12, 31)),
        as_of=date(2024, 1, 1),
    )

    exact, mismatch = result.matches
    assert exact.components.regime == 0.0
    assert exact.components.development_level == 0.0
    assert exact.components.data_coverage == 0.0
    assert mismatch.components.regime == 1.0
    assert mismatch.components.development_level == 1.0
    assert mismatch.components.data_coverage > 0.0
    assert exact.similarity_score > mismatch.similarity_score


def test_reference_window_must_be_strictly_historical() -> None:
    query = AnalogueQuery(
        "TR",
        date(2024, 1, 1),
        "float",
        "emerging",
        1.0,
        {"emp": 1.0},
        {"global_usd": 1.0},
    )
    with pytest.raises(DomainValidationError, match="must end before"):
        find_historical_analogues(
            query=query,
            history=(_state("AA", date(2024, 1, 1), 1.0, 1.0),),
            reference_window=AnalogueReferenceWindow(date(2024, 1, 1), date(2024, 1, 1)),
            as_of=date(2024, 1, 1),
        )
