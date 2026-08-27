"""Country identities are separate from currencies and historical boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from fx_cpm.domain.entities import DateInterval
from fx_cpm.domain.taxonomy import HazardType
from fx_cpm.domain.validation import DomainValidationError, require_non_empty


@dataclass(frozen=True, slots=True)
class CountrySpecification:
    country_id: str
    name: str
    iso2: str | None = None
    iso3: str | None = None
    valid_from: date = date.min
    valid_to: date | None = None
    predecessor_ids: tuple[str, ...] = ()
    successor_ids: tuple[str, ...] = ()
    supported_hazards: tuple[HazardType, ...] = tuple(HazardType)
    source: str = ""

    def __post_init__(self) -> None:
        require_non_empty(self.country_id, "country_id")
        require_non_empty(self.name, "name")
        if self.iso2 is not None:
            iso2 = self.iso2.strip().upper()
            if len(iso2) != 2 or not iso2.isalpha():
                raise DomainValidationError("iso2 must contain two letters")
            object.__setattr__(self, "iso2", iso2)
        if self.iso3 is not None:
            iso3 = self.iso3.strip().upper()
            if len(iso3) != 3 or not iso3.isalpha():
                raise DomainValidationError("iso3 must contain three letters")
            object.__setattr__(self, "iso3", iso3)
        DateInterval(self.valid_from, self.valid_to)
        hazards = tuple(HazardType.parse(item) for item in self.supported_hazards)
        if len(set(hazards)) != len(hazards):
            raise DomainValidationError("supported_hazards must be unique")
        object.__setattr__(self, "supported_hazards", hazards)
        if self.country_id in self.predecessor_ids or self.country_id in self.successor_ids:
            raise DomainValidationError("a country cannot be its own predecessor or successor")

    def valid_on(self, value: date) -> bool:
        return DateInterval(self.valid_from, self.valid_to).contains(value)

    def supports(self, hazard: HazardType | str) -> bool:
        return HazardType.parse(hazard) in self.supported_hazards

