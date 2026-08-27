"""Read-only country, currency, and time-varying regime registry."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import Mapping

from fx_cpm.domain.regimes import CountryCurrencyRegime, RegimeHistory
from fx_cpm.domain.validation import DomainValidationError

from .currencies import CurrencyDefinition, validate_currency_replacements
from .specifications import CountrySpecification


@dataclass(frozen=True, slots=True)
class CountryRegistry:
    countries: tuple[CountrySpecification, ...] = ()
    currencies: tuple[CurrencyDefinition, ...] = ()
    regimes: tuple[CountryCurrencyRegime, ...] = ()

    def __post_init__(self) -> None:
        country_ids = [item.country_id for item in self.countries]
        currency_ids = [item.currency_id for item in self.currencies]
        if len(set(country_ids)) != len(country_ids):
            raise DomainValidationError("country identifiers must be unique")
        validate_currency_replacements(self.currencies)
        known_countries = set(country_ids)
        known_currencies = set(currency_ids)
        for record in self.regimes:
            if record.country_id not in known_countries:
                raise DomainValidationError(f"regime references unknown country {record.country_id}")
            if record.currency_id not in known_currencies:
                raise DomainValidationError(f"regime references unknown currency {record.currency_id}")
            if record.anchor_currency_id and record.anchor_currency_id not in known_currencies:
                raise DomainValidationError(
                    f"regime references unknown anchor currency {record.anchor_currency_id}"
                )
        for country_id in known_countries:
            records = tuple(record for record in self.regimes if record.country_id == country_id)
            if records:
                RegimeHistory(country_id, records)

    @property
    def country_map(self) -> Mapping[str, CountrySpecification]:
        return MappingProxyType({item.country_id: item for item in self.countries})

    @property
    def currency_map(self) -> Mapping[str, CurrencyDefinition]:
        return MappingProxyType({item.currency_id: item for item in self.currencies})

    def country(self, country_id: str) -> CountrySpecification:
        try:
            return self.country_map[country_id]
        except KeyError as exc:
            raise DomainValidationError(f"unknown country: {country_id}") from exc

    def currency(self, currency_id: str) -> CurrencyDefinition:
        try:
            return self.currency_map[currency_id]
        except KeyError as exc:
            raise DomainValidationError(f"unknown currency: {currency_id}") from exc

    def regime_at(self, country_id: str, value: date) -> CountryCurrencyRegime | None:
        records = tuple(record for record in self.regimes if record.country_id == country_id)
        return RegimeHistory(country_id, records).at(value) if records else None

    def currency_at(self, country_id: str, value: date) -> CurrencyDefinition | None:
        regime = self.regime_at(country_id, value)
        return self.currency(regime.currency_id) if regime else None

