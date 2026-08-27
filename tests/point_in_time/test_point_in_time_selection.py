from __future__ import annotations

from datetime import date

from fx_cpm.application.point_in_time import PointInTimeSelector, VintageMode
from fx_cpm.application.provider import InMemoryProvider
from fx_cpm.domain.observations import Observation


def observation(
    *,
    feature: str = "reserves",
    period_end: date = date(2019, 12, 31),
    release: date,
    retrieval: date,
    vintage: str,
    value: float,
) -> Observation:
    return Observation(
        feature_id=feature,
        country_id="xx",
        currency_id="xxc",
        value=value,
        unit="usd",
        frequency="monthly",
        period_start=period_end.replace(day=1),
        period_end=period_end,
        release_date=release,
        retrieval_date=retrieval,
        vintage=vintage,
        source_name="test archive",
        source_url="https://example.test/data",
        source_type="official_statistics",
        license="CC-BY-4.0",
        base_quality=0.9,
        revision_status="first_release" if vintage == "2020-02-01" else "revised",
        provenance_type="raw",
        provider="fixture",
    )


def test_vintage_modes_are_distinct_and_revision_selection_has_no_lookahead() -> None:
    first = observation(
        release=date(2020, 2, 1),
        retrieval=date(2020, 2, 2),
        vintage="2020-02-01",
        value=10.0,
    )
    revised = observation(
        release=date(2020, 6, 1),
        retrieval=date(2020, 6, 2),
        vintage="2020-06-01",
        value=99.0,
    )
    selector = PointInTimeSelector()
    real_time = selector.select((first, revised), as_of=date(2020, 4, 1), mode=VintageMode.TRUE_VINTAGE)
    reconstructed = selector.select(
        (first, revised),
        as_of=date(2020, 4, 1),
        mode=VintageMode.RECONSTRUCTED_POINT_IN_TIME,
    )
    revised_history = selector.select(
        (first, revised),
        as_of=date(2020, 4, 1),
        mode=VintageMode.REVISED_HISTORY_ONLY,
    )

    assert tuple(item.value for item in real_time.observations) == (10.0,)
    assert tuple(item.value for item in reconstructed.observations) == (10.0,)
    assert tuple(item.value for item in revised_history.observations) == (99.0,)
    assert real_time.is_genuine_real_time
    assert not revised_history.leakage_safe
    assert real_time.reason_counts["not_yet_released"] == 1


def test_late_archive_retrieval_is_reconstructed_not_true_vintage() -> None:
    archived = observation(
        release=date(2020, 2, 1),
        retrieval=date(2024, 1, 1),
        vintage="2020-02-01",
        value=10.0,
    )
    selector = PointInTimeSelector()
    true = selector.select((archived,), as_of=date(2020, 3, 1), mode=VintageMode.TRUE_VINTAGE)
    reconstructed = selector.select(
        (archived,),
        as_of=date(2020, 3, 1),
        mode=VintageMode.RECONSTRUCTED_POINT_IN_TIME,
    )
    automatic = selector.select((archived,), as_of=date(2020, 3, 1), mode=VintageMode.AUTO)

    assert not true.observations
    assert true.reason_counts == {"not_yet_retrieved": 1}
    assert reconstructed.observations == (archived,)
    assert automatic.vintage_mode is VintageMode.RECONSTRUCTED_POINT_IN_TIME


def test_latest_per_series_does_not_replace_missing_with_zero() -> None:
    older = observation(
        period_end=date(2019, 11, 30),
        release=date(2019, 12, 15),
        retrieval=date(2019, 12, 16),
        vintage="2019-12-15",
        value=8.0,
    )
    latest = observation(
        period_end=date(2019, 12, 31),
        release=date(2020, 1, 15),
        retrieval=date(2020, 1, 16),
        vintage="2020-01-15",
        value=9.0,
    )
    selection = PointInTimeSelector().select(
        (older, latest),
        as_of=date(2020, 2, 1),
        latest_per_series=True,
    )
    assert selection.observations == (latest,)
    assert selection.reason_counts["older_period"] == 1


def test_in_memory_provider_returns_all_vintages_for_central_selection() -> None:
    first = observation(
        release=date(2020, 2, 1), retrieval=date(2020, 2, 2), vintage="2020-02-01", value=1.0
    )
    revised = observation(
        release=date(2020, 3, 1), retrieval=date(2020, 3, 2), vintage="2020-03-01", value=2.0
    )
    provider = InMemoryProvider(observations=[first, revised])

    assert provider.get_observations(country_id="xx", feature_ids=("reserves",)) == (first, revised)
    assert provider.get_observations(country_id="yy") == ()
