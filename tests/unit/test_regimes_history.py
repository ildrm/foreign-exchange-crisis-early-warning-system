from datetime import date

import pytest

from fx_cpm.countries import (
    CountryRegistry,
    CountrySpecification,
    CurrencyDefinition,
)
from fx_cpm.domain import (
    CountryCurrencyRegime,
    DomainValidationError,
    FXStressChannel,
    RegimeHistory,
    RegimeType,
    regimes_comparable,
    validate_regime_intervals,
)


def regime(**overrides: object) -> CountryCurrencyRegime:
    values: dict[str, object] = {
        "country_id": "X",
        "currency_id": "XCU",
        "currency_regime_id": "x-float",
        "regime_type": RegimeType.FREE_FLOAT,
        "effective_from": date(2000, 1, 1),
        "effective_to": None,
        "source": "versioned historical source",
    }
    values.update(overrides)
    return CountryCurrencyRegime(**values)  # type: ignore[arg-type]


def test_regime_intervals_are_half_open_at_transition() -> None:
    peg = regime(
        currency_regime_id="x-peg",
        regime_type=RegimeType.CONVENTIONAL_FIXED_PEG,
        anchor_currency="USD",
        effective_from=date(1990, 1, 1),
        effective_to=date(2000, 1, 1),
    )
    floating = regime()
    history = RegimeHistory("X", (floating, peg), require_contiguous=True)
    assert history.at(date(1999, 12, 31)) is peg
    assert history.at(date(2000, 1, 1)) is floating
    assert peg.stress_channel is FXStressChannel.EXCHANGE_MARKET_PRESSURE
    assert floating.stress_channel is FXStressChannel.MARKET_RETURN
    assert not regimes_comparable(peg, floating)


def test_overlapping_regimes_and_duplicate_mapping_ids_fail_validation() -> None:
    first = regime(effective_to=date(2010, 1, 1))
    overlap = regime(
        currency_regime_id="x-second",
        effective_from=date(2009, 1, 1),
    )
    with pytest.raises(DomainValidationError, match="overlapping"):
        validate_regime_intervals((first, overlap))
    duplicate = regime(effective_from=date(2010, 1, 1))
    with pytest.raises(DomainValidationError, match="duplicate"):
        validate_regime_intervals((first, duplicate))


def test_currency_union_dollarization_and_parallel_markets_are_explicit() -> None:
    euro_member = regime(
        country_id="EU_MEMBER",
        currency_id="EUR",
        currency_regime_id="eu-member-eur",
        regime_type=RegimeType.CURRENCY_UNION,
    )
    dollarized = regime(
        country_id="DOLLARIZED",
        currency_id="USD",
        currency_regime_id="dollarized-usd",
        regime_type=RegimeType.DOLLARIZATION,
        anchor_currency_id="USD",
    )
    parallel = regime(
        country_id="PARALLEL",
        currency_regime_id="parallel-xcu",
        regime_type=RegimeType.MANAGED_FLOAT,
        multiple_rates=True,
        capital_controls=True,
    )
    assert euro_member.country_id != euro_member.currency_id
    assert dollarized.country_id != dollarized.currency_id
    assert parallel.stress_channel is FXStressChannel.PARALLEL_MARKET
    assert dollarized.anchor_currency == dollarized.anchor_currency_id == "USD"


def test_registry_resolves_historical_currency_replacement_without_equating_country() -> None:
    registry = CountryRegistry(
        countries=(CountrySpecification("X", "Exampleland", iso2="EX", iso3="EXP"),),
        currencies=(
            CurrencyDefinition(
                "OLD",
                "Old unit",
                valid_from=date(1950, 1, 1),
                valid_to=date(2000, 1, 1),
                successor_currency_id="NEW",
            ),
            CurrencyDefinition("NEW", "New unit", valid_from=date(2000, 1, 1)),
        ),
        regimes=(
            regime(
                currency_id="OLD",
                currency_regime_id="old-regime",
                effective_from=date(1950, 1, 1),
                effective_to=date(2000, 1, 1),
            ),
            regime(currency_id="NEW", currency_regime_id="new-regime"),
        ),
    )
    assert registry.currency_at("X", date(1999, 12, 31)).currency_id == "OLD"
    assert registry.currency_at("X", date(2000, 1, 1)).currency_id == "NEW"

