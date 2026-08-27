"""Small immutable value objects used across FX-CPM's domain."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from .validation import DomainValidationError, require_date, require_non_empty, require_probability


class ModelTier(StrEnum):
    HISTORICAL_STRUCTURAL = "historical_structural"
    MACRO_FINANCIAL = "macro_financial"
    MODERN_MARKET_ENHANCED = "modern_market_enhanced"


class OODStatus(StrEnum):
    IN_DOMAIN = "in_domain"
    NEAR_DOMAIN_BOUNDARY = "near_domain_boundary"
    OUT_OF_DOMAIN = "out_of_domain"
    UNKNOWN = "unknown"

    @property
    def strongly_out_of_domain(self) -> bool:
        return self is OODStatus.OUT_OF_DOMAIN


class ConfidenceBand(StrEnum):
    VERY_LOW = "very_low"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    VERY_HIGH = "very_high"

    @classmethod
    def from_score(cls, score: float) -> ConfidenceBand:
        require_probability(score, "confidence")
        if score < 0.2:
            return cls.VERY_LOW
        if score < 0.4:
            return cls.LOW
        if score < 0.7:
            return cls.MODERATE
        if score < 0.9:
            return cls.HIGH
        return cls.VERY_HIGH


@dataclass(frozen=True, slots=True)
class DateInterval:
    """A half-open calendar interval ``[effective_from, effective_to)``."""

    effective_from: date
    effective_to: date | None = None

    def __post_init__(self) -> None:
        require_date(self.effective_from, "effective_from")
        if self.effective_to is not None:
            require_date(self.effective_to, "effective_to")
            if self.effective_to <= self.effective_from:
                raise DomainValidationError("effective_to must be after effective_from")

    def contains(self, value: date) -> bool:
        require_date(value, "date")
        return self.effective_from <= value and (
            self.effective_to is None or value < self.effective_to
        )

    def overlaps(self, other: DateInterval) -> bool:
        self_end = self.effective_to or date.max
        other_end = other.effective_to or date.max
        return self.effective_from < other_end and other.effective_from < self_end


@dataclass(frozen=True, slots=True)
class Identifier:
    namespace: str
    value: str

    def __post_init__(self) -> None:
        require_non_empty(self.namespace, "namespace")
        require_non_empty(self.value, "value")

    def __str__(self) -> str:
        return f"{self.namespace}:{self.value}"
