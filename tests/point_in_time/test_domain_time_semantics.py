from datetime import date

import pytest

from fx_cpm.domain import (
    DomainValidationError,
    Frequency,
    MissingStatus,
    Observation,
    ProvenanceType,
    RevisionStatus,
    SourceType,
    VintageMode,
    audit_point_in_time,
    select_vintage,
    validate_chronological_split,
)


def observation(
    *,
    value: float,
    release_date: date,
    retrieval_date: date,
    vintage: str,
    revision_status: RevisionStatus,
) -> Observation:
    return Observation(
        feature_id="gdp_growth",
        country_id="X",
        currency_id=None,
        value=value,
        unit="percent",
        frequency=Frequency.ANNUAL,
        period_start=date(2019, 1, 1),
        period_end=date(2019, 12, 31),
        release_date=release_date,
        retrieval_date=retrieval_date,
        vintage=vintage,
        source_name="Statistical office",
        source_url="https://example.test/gdp",
        source_type=SourceType.OFFICIAL_STATISTICS,
        license="open",
        base_quality=0.9,
        revision_status=revision_status,
        provenance_type=ProvenanceType.TRUE_VINTAGE,
        status=MissingStatus.AVAILABLE,
    )


def test_true_vintage_reconstructed_and_revised_history_are_distinct() -> None:
    first = observation(
        value=1.0,
        release_date=date(2020, 2, 1),
        retrieval_date=date(2020, 2, 1),
        vintage="first",
        revision_status=RevisionStatus.FIRST_RELEASE,
    )
    known_revision_retrieved_late = observation(
        value=1.5,
        release_date=date(2020, 3, 1),
        retrieval_date=date(2021, 1, 1),
        vintage="revision-1",
        revision_status=RevisionStatus.REVISED,
    )
    future_final = observation(
        value=2.0,
        release_date=date(2021, 1, 1),
        retrieval_date=date(2021, 1, 1),
        vintage="final",
        revision_status=RevisionStatus.FINAL,
    )
    observations = (first, known_revision_retrieved_late, future_final)
    cutoff = date(2020, 6, 1)
    assert select_vintage(observations, analysis_date=cutoff, mode=VintageMode.TRUE_VINTAGE) is first
    assert select_vintage(
        observations,
        analysis_date=cutoff,
        mode=VintageMode.RECONSTRUCTED_POINT_IN_TIME,
    ) is known_revision_retrieved_late
    assert select_vintage(
        observations,
        analysis_date=cutoff,
        mode=VintageMode.REVISED_HISTORY_ONLY,
    ) is future_final


def test_release_and_retrieval_cutoffs_prevent_look_ahead() -> None:
    item = observation(
        value=1.5,
        release_date=date(2020, 3, 1),
        retrieval_date=date(2021, 1, 1),
        vintage="late-retrieval",
        revision_status=RevisionStatus.REVISED,
    )
    cutoff = date(2020, 6, 1)
    assert not item.is_visible_as_of(cutoff, mode=VintageMode.TRUE_VINTAGE)
    assert item.is_visible_as_of(cutoff, mode=VintageMode.RECONSTRUCTED_POINT_IN_TIME)
    issues = audit_point_in_time(
        (item,), analysis_date=cutoff, mode=VintageMode.TRUE_VINTAGE
    )
    assert issues[0].code == "LOOK_AHEAD_OBSERVATION"


def test_training_calibration_and_final_test_windows_cannot_overlap() -> None:
    validate_chronological_split(
        training_end=date(2010, 12, 31),
        calibration_start=date(2011, 1, 1),
        calibration_end=date(2015, 12, 31),
        test_start=date(2016, 1, 1),
    )
    with pytest.raises(DomainValidationError, match="training_end"):
        validate_chronological_split(
            training_end=date(2011, 1, 1),
            calibration_start=date(2011, 1, 1),
            calibration_end=date(2015, 12, 31),
            test_start=date(2016, 1, 1),
        )

