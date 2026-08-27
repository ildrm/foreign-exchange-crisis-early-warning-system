"""Point-in-time observations, missingness, vintage, and provenance models."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import TypeVar

from .validation import (
    DomainValidationError,
    require_date,
    require_finite,
    require_non_empty,
    require_probability,
)


class ObservationFrequency(StrEnum):
    INTRADAY = "intraday"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"
    EVENT = "event"
    IRREGULAR = "irregular"


# Common concise name used by source adapters.
Frequency = ObservationFrequency


class MissingStatus(StrEnum):
    AVAILABLE = "available"
    STALE = "stale"
    MISSING = "missing"
    NOT_APPLICABLE = "not_applicable"
    UNRELIABLE = "unreliable"
    SOURCE_FAILURE = "source_failure"
    INSUFFICIENT_HISTORY = "insufficient_history"

    @property
    def has_observed_value(self) -> bool:
        return self in {MissingStatus.AVAILABLE, MissingStatus.STALE, MissingStatus.UNRELIABLE}


class RevisionStatus(StrEnum):
    FIRST_RELEASE = "first_release"
    REVISED = "revised"
    FINAL = "final"
    NOT_REVISED = "not_revised"
    UNKNOWN = "unknown"


class VintageMode(StrEnum):
    TRUE_VINTAGE = "true_vintage"
    RECONSTRUCTED_POINT_IN_TIME = "reconstructed_point_in_time"
    REVISED_HISTORY_ONLY = "revised_history_only"


class ProvenanceType(StrEnum):
    RAW = "raw"
    TRUE_VINTAGE = "true_vintage"
    RECONSTRUCTED = "reconstructed"
    DERIVED = "derived"
    IMPUTED = "imputed"
    MANUAL_RECONCILIATION = "manual_reconciliation"


class SourceType(StrEnum):
    OFFICIAL_STATISTICS = "official_statistics"
    CENTRAL_BANK = "central_bank"
    INTERNATIONAL_ORGANIZATION = "international_organization"
    ACADEMIC = "academic"
    MARKET = "market"
    COMMERCIAL = "commercial"
    NEWS = "news"
    MANUAL_ARCHIVE = "manual_archive"
    OTHER = "other"


class SourceAuthority(StrEnum):
    PRIMARY = "primary"
    AUTHORITATIVE_SECONDARY = "authoritative_secondary"
    SECONDARY = "secondary"
    UNVERIFIED = "unverified"


@dataclass(frozen=True, slots=True)
class TransformationStep:
    """One auditable step from source observations to a derived value."""

    operation: str
    input_observation_ids: tuple[str, ...]
    parameters: tuple[tuple[str, str], ...] = ()
    code_version: str = ""

    def __post_init__(self) -> None:
        require_non_empty(self.operation, "operation")
        if not self.input_observation_ids:
            raise DomainValidationError("input_observation_ids must not be empty")
        if any(not item.strip() for item in self.input_observation_ids):
            raise DomainValidationError("input observation identifiers must be non-empty")


@dataclass(frozen=True, slots=True)
class ImputationMetadata:
    """Explicit evidence retained whenever a missing value is imputed."""

    method: str
    original_status: MissingStatus
    uncertainty: float | None = None
    training_end_date: date | None = None

    def __post_init__(self) -> None:
        require_non_empty(self.method, "imputation method")
        if self.original_status.has_observed_value:
            raise DomainValidationError("original_status must describe missing, not observed, evidence")
        if self.uncertainty is not None:
            require_finite(self.uncertainty, "imputation uncertainty")
            if self.uncertainty < 0:
                raise DomainValidationError("imputation uncertainty cannot be negative")
        if self.training_end_date is not None:
            require_date(self.training_end_date, "imputation training_end_date")


_EnumT = TypeVar("_EnumT", bound=StrEnum)


def _coerce_enum(value: _EnumT | str, enum_type: type[_EnumT], field: str) -> _EnumT:
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(str(value).lower())
    except ValueError as exc:
        raise DomainValidationError(f"invalid {field}: {value!r}") from exc


@dataclass(frozen=True, slots=True)
class Observation:
    """An immutable, independently dated scientific observation.

    ``release_date`` and ``retrieval_date`` are intentionally distinct.  A
    reconstruction made today can be historically eligible by release date but
    is not a true-vintage observation that the system actually held at the time.
    """

    feature_id: str
    country_id: str
    currency_id: str | None
    value: float | None
    unit: str
    frequency: ObservationFrequency
    period_start: date
    period_end: date
    release_date: date
    retrieval_date: date
    vintage: str
    source_name: str
    source_url: str
    source_type: SourceType
    license: str
    base_quality: float
    revision_status: RevisionStatus
    provenance_type: ProvenanceType
    status: MissingStatus = MissingStatus.AVAILABLE
    observation_id: str | None = None
    provider: str | None = None
    source_authority: SourceAuthority = SourceAuthority.SECONDARY
    source_quality: float | None = None
    transformation_lineage: tuple[TransformationStep, ...] = ()
    imputation: ImputationMetadata | None = None

    def __post_init__(self) -> None:
        for field_name in ("feature_id", "country_id", "unit", "vintage", "source_name"):
            require_non_empty(getattr(self, field_name), field_name)
        if self.currency_id is not None:
            require_non_empty(self.currency_id, "currency_id")
        if not isinstance(self.frequency, ObservationFrequency):
            object.__setattr__(
                self,
                "frequency",
                _coerce_enum(self.frequency, ObservationFrequency, "frequency"),
            )
        for field_name, enum_type in (
            ("source_type", SourceType),
            ("revision_status", RevisionStatus),
            ("provenance_type", ProvenanceType),
            ("status", MissingStatus),
            ("source_authority", SourceAuthority),
        ):
            value = getattr(self, field_name)
            if not isinstance(value, enum_type):
                object.__setattr__(self, field_name, _coerce_enum(value, enum_type, field_name))
        for value, field_name in (
            (self.period_start, "period_start"),
            (self.period_end, "period_end"),
            (self.release_date, "release_date"),
            (self.retrieval_date, "retrieval_date"),
        ):
            require_date(value, field_name)
        if self.period_end < self.period_start:
            raise DomainValidationError("period_end must be on or after period_start")
        if self.release_date < self.period_start:
            raise DomainValidationError("release_date cannot precede period_start")
        if self.retrieval_date < self.release_date:
            raise DomainValidationError("retrieval_date cannot precede release_date")
        require_probability(self.base_quality, "base_quality")
        if self.source_quality is not None:
            require_probability(self.source_quality, "source_quality")
        if self.status.has_observed_value:
            if self.value is None:
                raise DomainValidationError(f"{self.status.value} observations require a value")
            require_finite(self.value, "value")
        elif self.value is not None:
            raise DomainValidationError(
                f"{self.status.value} observations must use value=None; missing is not zero"
            )
        if self.provenance_type is ProvenanceType.IMPUTED and self.imputation is None:
            raise DomainValidationError("imputed provenance requires imputation metadata")
        if self.imputation is not None and self.provenance_type is not ProvenanceType.IMPUTED:
            raise DomainValidationError("imputation metadata requires imputed provenance")
        if self.provenance_type is ProvenanceType.DERIVED and not self.transformation_lineage:
            raise DomainValidationError("derived observations require transformation lineage")

    @property
    def effective_source_quality(self) -> float:
        return self.source_quality if self.source_quality is not None else self.base_quality

    @property
    def was_imputed(self) -> bool:
        return self.imputation is not None

    @property
    def original_missing_status(self) -> MissingStatus | None:
        return self.imputation.original_status if self.imputation else None

    def is_visible_as_of(
        self,
        analysis_date: date,
        *,
        mode: VintageMode = VintageMode.TRUE_VINTAGE,
    ) -> bool:
        """Return whether this exact vintage is eligible under the selected mode.

        ``TRUE_VINTAGE`` requires both publication and actual retrieval by the
        cut-off. ``RECONSTRUCTED_POINT_IN_TIME`` uses known release dates but
        permits later retrieval. ``REVISED_HISTORY_ONLY`` deliberately admits a
        final/revised value for an already-ended period and must never be
        described as a real-time backtest.
        """

        require_date(analysis_date, "analysis_date")
        mode = _coerce_enum(mode, VintageMode, "vintage mode")
        if mode is VintageMode.TRUE_VINTAGE:
            return self.release_date <= analysis_date and self.retrieval_date <= analysis_date
        if mode is VintageMode.RECONSTRUCTED_POINT_IN_TIME:
            return self.release_date <= analysis_date
        return self.period_end <= analysis_date

    def is_usable(self, *, allow_stale: bool = False) -> bool:
        return self.status is MissingStatus.AVAILABLE or (
            allow_stale and self.status is MissingStatus.STALE
        )

    def age_days(self, analysis_date: date) -> int:
        require_date(analysis_date, "analysis_date")
        if analysis_date < self.period_end:
            raise DomainValidationError("analysis_date precedes the observation period")
        return (analysis_date - self.period_end).days

    @property
    def series_key(self) -> tuple[str, str, str | None, date, date]:
        return (
            self.feature_id,
            self.country_id,
            self.currency_id,
            self.period_start,
            self.period_end,
        )


def select_vintage(
    observations: Iterable[Observation],
    *,
    analysis_date: date,
    mode: VintageMode = VintageMode.TRUE_VINTAGE,
) -> Observation | None:
    """Select the latest eligible vintage for exactly one series-period key."""

    candidates = tuple(observations)
    if not candidates:
        return None
    keys = {item.series_key for item in candidates}
    if len(keys) != 1:
        raise DomainValidationError("select_vintage requires observations for one series-period key")
    eligible = [item for item in candidates if item.is_visible_as_of(analysis_date, mode=mode)]
    if not eligible:
        return None
    # Release/retrieval order is the scientific ordering.  The provider's
    # vintage string is only a deterministic final tie-breaker.
    return max(eligible, key=lambda item: (item.release_date, item.retrieval_date, item.vintage))


def select_observations_as_of(
    observations: Iterable[Observation],
    *,
    analysis_date: date,
    mode: VintageMode = VintageMode.TRUE_VINTAGE,
) -> tuple[Observation, ...]:
    """Select one eligible vintage per feature/country/currency/period."""

    grouped: dict[tuple[str, str, str | None, date, date], list[Observation]] = defaultdict(list)
    for observation in observations:
        grouped[observation.series_key].append(observation)
    selected = (
        select_vintage(group, analysis_date=analysis_date, mode=mode)
        for _, group in sorted(grouped.items(), key=lambda item: str(item[0]))
    )
    return tuple(item for item in selected if item is not None)

