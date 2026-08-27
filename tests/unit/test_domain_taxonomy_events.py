from datetime import date

import pytest

from fx_cpm.domain import (
    DEFAULT_HAZARD_TAXONOMY,
    CrisisEvent,
    DomainValidationError,
    ForecastHorizon,
    HazardType,
    OnsetInterpretation,
    binary_horizon_label,
    reconcile_onset_dates,
)


def event(**overrides: object) -> CrisisEvent:
    values: dict[str, object] = {
        "event_id": "evt-1",
        "country_id": "X",
        "hazard_type": HazardType.CURRENCY_CRISIS,
        "onset_min": date(2020, 3, 1),
        "onset_canonical": date(2020, 3, 5),
        "onset_max": date(2020, 3, 10),
        "end_date": date(2020, 6, 1),
        "severity": 0.8,
        "source_ids": ("source-a", "source-b"),
        "source_agreement": 0.7,
        "label_confidence": 0.8,
        "notes": "Sources disagree by nine days.",
    }
    values.update(overrides)
    return CrisisEvent(**values)  # type: ignore[arg-type]


def test_taxonomy_contains_eight_separate_fully_documented_hazards() -> None:
    assert len(HazardType) == 8
    assert set(DEFAULT_HAZARD_TAXONOMY) == set(HazardType)
    for hazard, definition in DEFAULT_HAZARD_TAXONOMY.items():
        assert definition.hazard_type is hazard
        assert definition.event_definition
        assert definition.onset_definition
        assert definition.continuation_definition
        assert definition.termination_definition
        assert definition.minimum_severity
        assert definition.label_sources
        assert definition.known_ambiguities
        assert definition.forecast_horizons
        assert definition.baseline_prevalence is None
        assert "Estimate separately" in definition.baseline_prevalence_note


def test_hazard_aliases_parse_without_merging_targets() -> None:
    assert HazardType.parse("currency") is HazardType.CURRENCY_CRISIS
    assert HazardType.parse("bank") is HazardType.SYSTEMIC_BANKING_CRISIS
    assert HazardType.parse("war") is HazardType.INTERSTATE_ARMED_CONFLICT
    assert len({HazardType.parse(item) for item in ("fx", "bank", "sov", "mon", "pol", "coup", "civ", "war")}) == 8


def test_uncertain_onset_supports_canonical_possible_and_certain_labels() -> None:
    item = event()
    assert item.onset_uncertainty_days == 9
    assert item.onset_in_window(date(2020, 3, 7), date(2020, 3, 20), interpretation=OnsetInterpretation.POSSIBLE)
    assert not item.onset_in_window(date(2020, 3, 7), date(2020, 3, 20), interpretation=OnsetInterpretation.CANONICAL)
    assert not item.onset_in_window(date(2020, 3, 7), date(2020, 3, 20), interpretation=OnsetInterpretation.CERTAIN)
    assert item.onset_in_window(date(2020, 2, 1), date(2020, 3, 31), interpretation=OnsetInterpretation.CERTAIN)


def test_forecast_interval_is_open_at_analysis_and_closed_at_horizon() -> None:
    analysis = date(2020, 1, 1)
    boundary = ForecastHorizon.DAYS_30.end_date(analysis)
    boundary_event = event(
        onset_min=boundary,
        onset_canonical=boundary,
        onset_max=boundary,
        end_date=None,
    )
    assert binary_horizon_label(
        [boundary_event],
        country_id="X",
        hazard_type="fx",
        analysis_date=analysis,
        horizon="30d",
    ) == 1
    same_day = event(
        onset_min=analysis,
        onset_canonical=analysis,
        onset_max=analysis,
        end_date=None,
    )
    assert binary_horizon_label(
        [same_day],
        country_id="X",
        hazard_type="fx",
        analysis_date=analysis,
        horizon="30d",
    ) == 0


def test_onset_range_and_source_ids_are_validated() -> None:
    with pytest.raises(DomainValidationError, match="onset_min"):
        event(onset_canonical=date(2020, 2, 1))
    with pytest.raises(DomainValidationError, match="unique"):
        event(source_ids=("same", "same"))
    assert reconcile_onset_dates(
        [date(2020, 3, 10), date(2020, 3, 1), date(2020, 3, 5)]
    ) == (date(2020, 3, 1), date(2020, 3, 5), date(2020, 3, 10))

