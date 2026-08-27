"""Time-varying country/currency/regime mappings."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from .entities import DateInterval
from .validation import (
    DomainValidationError,
    ValidationIssue,
    ValidationSeverity,
    require_date,
    require_non_empty,
)


class RegimeType(StrEnum):
    GOLD_STANDARD = "gold_standard"
    CONVENTIONAL_FIXED_PEG = "conventional_fixed_peg"
    BRETTON_WOODS = "bretton_woods"
    CRAWLING_PEG = "crawling_peg"
    MANAGED_FLOAT = "managed_float"
    FREE_FLOAT = "free_float"
    CURRENCY_BOARD = "currency_board"
    DOLLARIZATION = "dollarization"
    CURRENCY_UNION = "currency_union"
    PARALLEL_MULTIPLE_RATES = "parallel_multiple_rates"
    OTHER = "other"
    UNKNOWN = "unknown"

    PEG = CONVENTIONAL_FIXED_PEG
    FIXED = CONVENTIONAL_FIXED_PEG
    FLOAT = FREE_FLOAT
    FLOATING = FREE_FLOAT
    MANAGED = MANAGED_FLOAT
    MULTIPLE_RATES = PARALLEL_MULTIPLE_RATES

    @classmethod
    def parse(cls, value: RegimeType | str) -> RegimeType:
        if isinstance(value, cls):
            return value
        normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "peg": cls.CONVENTIONAL_FIXED_PEG,
            "fixed": cls.CONVENTIONAL_FIXED_PEG,
            "fixed_peg": cls.CONVENTIONAL_FIXED_PEG,
            "conventional_fixed_peg": cls.CONVENTIONAL_FIXED_PEG,
            "bretton_woods": cls.BRETTON_WOODS,
            "crawling": cls.CRAWLING_PEG,
            "crawling_peg": cls.CRAWLING_PEG,
            "managed": cls.MANAGED_FLOAT,
            "managed_float": cls.MANAGED_FLOAT,
            "float": cls.FREE_FLOAT,
            "floating": cls.FREE_FLOAT,
            "free_float": cls.FREE_FLOAT,
            "currency_board": cls.CURRENCY_BOARD,
            "dollarized": cls.DOLLARIZATION,
            "dollarization": cls.DOLLARIZATION,
            "currency_union": cls.CURRENCY_UNION,
            "parallel": cls.PARALLEL_MULTIPLE_RATES,
            "multiple_rates": cls.PARALLEL_MULTIPLE_RATES,
            "parallel_multiple_rates": cls.PARALLEL_MULTIPLE_RATES,
            "gold": cls.GOLD_STANDARD,
            "gold_standard": cls.GOLD_STANDARD,
            "other": cls.OTHER,
            "unknown": cls.UNKNOWN,
        }
        try:
            return aliases[normalized]
        except KeyError as exc:
            raise DomainValidationError(f"unsupported FX regime: {value!r}") from exc


class RegimeFamily(StrEnum):
    COMMODITY_ANCHOR = "commodity_anchor"
    HARD_PEG = "hard_peg"
    MANAGED = "managed"
    FLOATING = "floating"
    MULTIPLE_MARKET = "multiple_market"
    UNKNOWN = "unknown"


class FXStressChannel(StrEnum):
    MARKET_RETURN = "market_return"
    EXCHANGE_MARKET_PRESSURE = "exchange_market_pressure"
    PARALLEL_MARKET = "parallel_market"
    MIXED = "mixed"
    UNKNOWN = "unknown"


def regime_family(regime_type: RegimeType | str) -> RegimeFamily:
    regime = RegimeType.parse(regime_type)
    if regime is RegimeType.GOLD_STANDARD:
        return RegimeFamily.COMMODITY_ANCHOR
    if regime in {
        RegimeType.CONVENTIONAL_FIXED_PEG,
        RegimeType.BRETTON_WOODS,
        RegimeType.CURRENCY_BOARD,
        RegimeType.DOLLARIZATION,
        RegimeType.CURRENCY_UNION,
    }:
        return RegimeFamily.HARD_PEG
    if regime in {RegimeType.CRAWLING_PEG, RegimeType.MANAGED_FLOAT}:
        return RegimeFamily.MANAGED
    if regime is RegimeType.FREE_FLOAT:
        return RegimeFamily.FLOATING
    if regime is RegimeType.PARALLEL_MULTIPLE_RATES:
        return RegimeFamily.MULTIPLE_MARKET
    return RegimeFamily.UNKNOWN


def preferred_stress_channel(regime_type: RegimeType | str, *, multiple_rates: bool = False) -> FXStressChannel:
    family = regime_family(regime_type)
    if multiple_rates or family is RegimeFamily.MULTIPLE_MARKET:
        return FXStressChannel.PARALLEL_MARKET
    if family in {RegimeFamily.HARD_PEG, RegimeFamily.COMMODITY_ANCHOR}:
        return FXStressChannel.EXCHANGE_MARKET_PRESSURE
    if family is RegimeFamily.MANAGED:
        return FXStressChannel.MIXED
    if family is RegimeFamily.FLOATING:
        return FXStressChannel.MARKET_RETURN
    return FXStressChannel.UNKNOWN


@dataclass(frozen=True, slots=True)
class CountryCurrencyRegime:
    """A half-open mapping from a country to currency and institutional regime."""

    country_id: str
    currency_id: str
    regime_type: RegimeType
    effective_from: date
    effective_to: date | None = None
    anchor_currency: str | None = None
    capital_controls: bool = False
    multiple_rates: bool = False
    source: str = ""
    currency_regime_id: str | None = None
    anchor_currency_id: str | None = None
    exchange_restrictions: bool = False

    def __post_init__(self) -> None:
        require_non_empty(self.country_id, "country_id")
        require_non_empty(self.currency_id, "currency_id")
        if not isinstance(self.regime_type, RegimeType):
            object.__setattr__(self, "regime_type", RegimeType.parse(self.regime_type))
        DateInterval(self.effective_from, self.effective_to)
        if self.currency_regime_id is not None:
            require_non_empty(self.currency_regime_id, "currency_regime_id")
        if self.anchor_currency is not None:
            require_non_empty(self.anchor_currency, "anchor_currency")
        if self.anchor_currency_id is not None:
            require_non_empty(self.anchor_currency_id, "anchor_currency_id")
        if (
            self.anchor_currency is not None
            and self.anchor_currency_id is not None
            and self.anchor_currency != self.anchor_currency_id
        ):
            raise DomainValidationError("anchor_currency and anchor_currency_id disagree")
        if self.anchor_currency is None and self.anchor_currency_id is not None:
            object.__setattr__(self, "anchor_currency", self.anchor_currency_id)
        elif self.anchor_currency_id is None and self.anchor_currency is not None:
            object.__setattr__(self, "anchor_currency_id", self.anchor_currency)

    @property
    def interval(self) -> DateInterval:
        return DateInterval(self.effective_from, self.effective_to)

    @property
    def family(self) -> RegimeFamily:
        return regime_family(self.regime_type)

    @property
    def stress_channel(self) -> FXStressChannel:
        return preferred_stress_channel(self.regime_type, multiple_rates=self.multiple_rates)

    def contains(self, value: date) -> bool:
        return self.interval.contains(value)


def regime_interval_issues(
    records: Iterable[CountryCurrencyRegime],
    *,
    require_contiguous: bool = False,
) -> tuple[ValidationIssue, ...]:
    """Audit overlap, duplicate IDs, and optional gaps independently by country."""

    grouped: dict[str, list[CountryCurrencyRegime]] = {}
    ids: set[str] = set()
    issues: list[ValidationIssue] = []
    for record in records:
        grouped.setdefault(record.country_id, []).append(record)
        if record.currency_regime_id:
            if record.currency_regime_id in ids:
                issues.append(
                    ValidationIssue(
                        code="DUPLICATE_REGIME_ID",
                        field="currency_regime_id",
                        message=f"duplicate regime identifier {record.currency_regime_id}",
                    )
                )
            ids.add(record.currency_regime_id)
    for country_id, country_records in grouped.items():
        ordered = sorted(country_records, key=lambda item: item.effective_from)
        for previous, current in zip(ordered, ordered[1:], strict=False):
            if previous.effective_to is None or current.effective_from < previous.effective_to:
                issues.append(
                    ValidationIssue(
                        code="OVERLAPPING_REGIMES",
                        field="effective_from",
                        message=(
                            f"{country_id} has overlapping regime mappings beginning "
                            f"{previous.effective_from} and {current.effective_from}"
                        ),
                    )
                )
            elif require_contiguous and current.effective_from > previous.effective_to:
                issues.append(
                    ValidationIssue(
                        code="REGIME_HISTORY_GAP",
                        field="effective_from",
                        severity=ValidationSeverity.WARNING,
                        message=(
                            f"{country_id} has no regime mapping from {previous.effective_to} "
                            f"to {current.effective_from}"
                        ),
                    )
                )
    return tuple(issues)


def validate_regime_intervals(
    records: Iterable[CountryCurrencyRegime],
    *,
    require_contiguous: bool = False,
) -> None:
    issues = regime_interval_issues(records, require_contiguous=require_contiguous)
    errors = [issue for issue in issues if issue.severity is ValidationSeverity.ERROR]
    if errors:
        raise DomainValidationError("; ".join(issue.message for issue in errors))


@dataclass(frozen=True, slots=True)
class RegimeHistory:
    country_id: str
    records: tuple[CountryCurrencyRegime, ...]
    require_contiguous: bool = False

    def __post_init__(self) -> None:
        require_non_empty(self.country_id, "country_id")
        if not self.records:
            raise DomainValidationError("regime history must contain at least one record")
        if any(record.country_id != self.country_id for record in self.records):
            raise DomainValidationError("all regime records must belong to the history country")
        ordered = tuple(sorted(self.records, key=lambda item: item.effective_from))
        object.__setattr__(self, "records", ordered)
        validate_regime_intervals(ordered, require_contiguous=self.require_contiguous)

    def at(self, value: date) -> CountryCurrencyRegime | None:
        require_date(value, "date")
        matches = [record for record in self.records if record.contains(value)]
        if len(matches) > 1:
            raise DomainValidationError("ambiguous overlapping regime mappings")
        return matches[0] if matches else None

    def require_at(self, value: date) -> CountryCurrencyRegime:
        result = self.at(value)
        if result is None:
            raise DomainValidationError(
                f"no regime mapping for {self.country_id} on {value.isoformat()}"
            )
        return result


def regimes_comparable(left: CountryCurrencyRegime, right: CountryCurrencyRegime) -> bool:
    """Conservative raw-FX comparability check; normalization may still be needed."""

    return left.family is right.family and left.multiple_rates == right.multiple_rates
