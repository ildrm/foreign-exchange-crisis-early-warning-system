"""Crisis-event labels with explicit onset-date uncertainty."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from .taxonomy import ForecastHorizon, HazardType
from .validation import (
    DomainValidationError,
    require_date,
    require_non_empty,
    require_probability,
)


class OnsetInterpretation(StrEnum):
    """How an uncertain onset range is converted into a binary horizon label."""

    CANONICAL = "canonical"
    POSSIBLE = "possible"
    CERTAIN = "certain"


@dataclass(frozen=True, slots=True)
class CrisisEvent:
    event_id: str
    country_id: str
    hazard_type: HazardType
    onset_min: date
    onset_canonical: date
    onset_max: date
    end_date: date | None
    severity: float
    source_ids: tuple[str, ...]
    source_agreement: float
    label_confidence: float
    notes: str = ""
    taxonomy_version: str = "0.1.0"
    is_escalation: bool = False

    def __post_init__(self) -> None:
        for value, field in (
            (self.event_id, "event_id"),
            (self.country_id, "country_id"),
            (self.taxonomy_version, "taxonomy_version"),
        ):
            require_non_empty(value, field)
        if not isinstance(self.hazard_type, HazardType):
            object.__setattr__(self, "hazard_type", HazardType.parse(self.hazard_type))
        for value, field in (
            (self.onset_min, "onset_min"),
            (self.onset_canonical, "onset_canonical"),
            (self.onset_max, "onset_max"),
        ):
            require_date(value, field)
        if not self.onset_min <= self.onset_canonical <= self.onset_max:
            raise DomainValidationError(
                "event onset must satisfy onset_min <= onset_canonical <= onset_max"
            )
        if self.end_date is not None:
            require_date(self.end_date, "end_date")
            if self.end_date < self.onset_max:
                raise DomainValidationError("end_date cannot precede the latest possible onset")
        require_probability(self.severity, "severity")
        require_probability(self.source_agreement, "source_agreement")
        require_probability(self.label_confidence, "label_confidence")
        if not self.source_ids or any(not source_id.strip() for source_id in self.source_ids):
            raise DomainValidationError("source_ids must contain non-empty identifiers")
        if len(set(self.source_ids)) != len(self.source_ids):
            raise DomainValidationError("source_ids must be unique")

    @property
    def onset_is_exact(self) -> bool:
        return self.onset_min == self.onset_canonical == self.onset_max

    @property
    def onset_uncertainty_days(self) -> int:
        return (self.onset_max - self.onset_min).days

    def onset_in_window(
        self,
        start_exclusive: date,
        end_inclusive: date,
        *,
        interpretation: OnsetInterpretation = OnsetInterpretation.CANONICAL,
    ) -> bool:
        """Evaluate event onset in the forecast interval ``(start, end]``."""

        require_date(start_exclusive, "start_exclusive")
        require_date(end_inclusive, "end_inclusive")
        if end_inclusive <= start_exclusive:
            raise DomainValidationError("forecast window must end after it starts")
        if not isinstance(interpretation, OnsetInterpretation):
            try:
                interpretation = OnsetInterpretation(str(interpretation).lower())
            except ValueError as exc:
                raise DomainValidationError(
                    f"invalid onset interpretation: {interpretation!r}"
                ) from exc
        if interpretation is OnsetInterpretation.CANONICAL:
            return start_exclusive < self.onset_canonical <= end_inclusive
        if interpretation is OnsetInterpretation.POSSIBLE:
            return self.onset_max > start_exclusive and self.onset_min <= end_inclusive
        return self.onset_min > start_exclusive and self.onset_max <= end_inclusive

    def active_on(self, value: date) -> bool:
        require_date(value, "date")
        return self.onset_canonical <= value and (self.end_date is None or value <= self.end_date)


def reconcile_onset_dates(
    dates: Sequence[date],
    *,
    canonical: date | None = None,
) -> tuple[date, date, date]:
    """Return ``(minimum, canonical, maximum)`` from independently sourced dates.

    When no canonical date is pre-specified, the upper median is used.  This is
    deterministic and keeps the full disagreement range visible; it is not a
    claim that the median source is uniquely correct.
    """

    if not dates:
        raise DomainValidationError("at least one onset date is required")
    ordered = sorted(require_date(value, "onset date") for value in dates)
    selected = canonical or ordered[len(ordered) // 2]
    require_date(selected, "canonical")
    if not ordered[0] <= selected <= ordered[-1]:
        raise DomainValidationError("canonical onset must lie inside the source date range")
    return ordered[0], selected, ordered[-1]


def events_in_horizon(
    events: Iterable[CrisisEvent],
    *,
    country_id: str,
    hazard_type: HazardType | str,
    analysis_date: date,
    horizon: ForecastHorizon | int | str,
    interpretation: OnsetInterpretation = OnsetInterpretation.CANONICAL,
) -> tuple[CrisisEvent, ...]:
    hazard = HazardType.parse(hazard_type)
    parsed_horizon = ForecastHorizon.parse(horizon)
    end_date = parsed_horizon.end_date(analysis_date)
    return tuple(
        event
        for event in events
        if event.country_id == country_id
        and event.hazard_type is hazard
        and event.onset_in_window(
            analysis_date,
            end_date,
            interpretation=interpretation,
        )
    )


def binary_horizon_label(
    events: Iterable[CrisisEvent],
    **kwargs: object,
) -> int:
    """Produce a deterministic 0/1 onset label using explicit event semantics."""

    return int(bool(events_in_horizon(events, **kwargs)))
