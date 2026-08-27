"""Immutable historical currency definitions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from fx_cpm.domain.entities import DateInterval
from fx_cpm.domain.validation import DomainValidationError, require_non_empty


@dataclass(frozen=True, slots=True)
class CurrencyDefinition:
    currency_id: str
    name: str
    iso_code: str | None = None
    valid_from: date = date.min
    valid_to: date | None = None
    successor_currency_id: str | None = None
    union_currency: bool = False
    source: str = ""

    def __post_init__(self) -> None:
        require_non_empty(self.currency_id, "currency_id")
        require_non_empty(self.name, "name")
        if self.iso_code is not None:
            code = self.iso_code.strip().upper()
            if len(code) != 3 or not code.isalpha():
                raise DomainValidationError("iso_code must contain three letters")
            object.__setattr__(self, "iso_code", code)
        DateInterval(self.valid_from, self.valid_to)
        if self.successor_currency_id is not None:
            require_non_empty(self.successor_currency_id, "successor_currency_id")
            if self.successor_currency_id == self.currency_id:
                raise DomainValidationError("a currency cannot be its own successor")

    def valid_on(self, value: date) -> bool:
        return DateInterval(self.valid_from, self.valid_to).contains(value)


def validate_currency_replacements(currencies: tuple[CurrencyDefinition, ...]) -> None:
    by_id = {currency.currency_id: currency for currency in currencies}
    if len(by_id) != len(currencies):
        raise DomainValidationError("currency identifiers must be unique")
    for currency in currencies:
        successor_id = currency.successor_currency_id
        if successor_id is not None and successor_id not in by_id:
            raise DomainValidationError(
                f"unknown successor {successor_id!r} for currency {currency.currency_id!r}"
            )
        seen = {currency.currency_id}
        while successor_id is not None:
            if successor_id in seen:
                raise DomainValidationError("currency replacement graph contains a cycle")
            seen.add(successor_id)
            successor_id = by_id[successor_id].successor_currency_id

