"""Leakage-safe historical analogue search for contextual interpretation."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import TypeAlias

from .validation import (
    DomainValidationError,
    require_date,
    require_finite,
    require_non_empty,
    require_positive,
    require_probability,
)

ContextValue: TypeAlias = str | int | float | bool | None


def _freeze_numeric_mapping(
    values: Mapping[str, float | None], field: str
) -> Mapping[str, float | None]:
    frozen: dict[str, float | None] = {}
    for raw_name, value in values.items():
        name = require_non_empty(raw_name, f"{field} key").strip()
        if name in frozen:
            raise DomainValidationError(f"duplicate {field} key: {name}")
        frozen[name] = None if value is None else require_finite(value, f"{field}[{name}]")
    return MappingProxyType(frozen)


def _freeze_context_mapping(
    values: Mapping[str, ContextValue], field: str
) -> Mapping[str, ContextValue]:
    frozen: dict[str, ContextValue] = {}
    for raw_name, value in values.items():
        name = require_non_empty(raw_name, f"{field} key").strip()
        if not isinstance(value, (str, int, float, bool, type(None))):
            raise DomainValidationError(f"{field}[{name}] must be a scalar context value")
        if isinstance(value, float):
            require_finite(value, f"{field}[{name}]")
        frozen[name] = value
    return MappingProxyType(frozen)


@dataclass(frozen=True, slots=True)
class AnalogueReferenceWindow:
    """Inclusive historical window used both for candidates and standardization."""

    start: date
    end: date

    def __post_init__(self) -> None:
        require_date(self.start, "reference_window.start")
        require_date(self.end, "reference_window.end")
        if self.end < self.start:
            raise DomainValidationError("reference window end must be on or after start")

    def contains(self, value: date) -> bool:
        require_date(value, "date")
        return self.start <= value <= self.end


@dataclass(frozen=True, slots=True)
class HistoricalState:
    """A dated country state, its later outcome, and contemporaneous context."""

    country_code: str
    observed_on: date
    available_on: date
    regime: str
    development_level: str
    data_coverage: float
    features: Mapping[str, float | None]
    global_state: Mapping[str, float | None]
    outcomes: Mapping[str, ContextValue]
    context: Mapping[str, ContextValue]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "country_code",
            require_non_empty(self.country_code, "country_code").strip().upper(),
        )
        require_date(self.observed_on, "observed_on")
        require_date(self.available_on, "available_on")
        if self.available_on < self.observed_on:
            raise DomainValidationError("available_on cannot precede observed_on")
        object.__setattr__(self, "regime", require_non_empty(self.regime, "regime").strip())
        object.__setattr__(
            self,
            "development_level",
            require_non_empty(self.development_level, "development_level").strip(),
        )
        object.__setattr__(
            self, "data_coverage", require_probability(self.data_coverage, "data_coverage")
        )
        object.__setattr__(self, "features", _freeze_numeric_mapping(self.features, "features"))
        object.__setattr__(
            self, "global_state", _freeze_numeric_mapping(self.global_state, "global_state")
        )
        object.__setattr__(self, "outcomes", _freeze_context_mapping(self.outcomes, "outcomes"))
        object.__setattr__(self, "context", _freeze_context_mapping(self.context, "context"))


@dataclass(frozen=True, slots=True)
class AnalogueQuery:
    country_code: str
    observed_on: date
    regime: str
    development_level: str
    data_coverage: float
    features: Mapping[str, float | None]
    global_state: Mapping[str, float | None]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "country_code",
            require_non_empty(self.country_code, "country_code").strip().upper(),
        )
        require_date(self.observed_on, "observed_on")
        object.__setattr__(self, "regime", require_non_empty(self.regime, "regime").strip())
        object.__setattr__(
            self,
            "development_level",
            require_non_empty(self.development_level, "development_level").strip(),
        )
        object.__setattr__(
            self, "data_coverage", require_probability(self.data_coverage, "data_coverage")
        )
        object.__setattr__(self, "features", _freeze_numeric_mapping(self.features, "features"))
        object.__setattr__(
            self, "global_state", _freeze_numeric_mapping(self.global_state, "global_state")
        )
        if not self.features:
            raise DomainValidationError("analogue query features must not be empty")
        if not any(value is not None for value in self.features.values()):
            raise DomainValidationError("analogue query needs at least one observed feature")
        if not self.global_state or not any(
            value is not None for value in self.global_state.values()
        ):
            raise DomainValidationError("analogue query needs observed global-state metrics")


@dataclass(frozen=True, slots=True)
class AnalogueWeights:
    feature_state: float = 0.45
    global_state: float = 0.20
    regime: float = 0.15
    development_level: float = 0.10
    data_coverage: float = 0.10

    def __post_init__(self) -> None:
        for field in (
            "feature_state",
            "global_state",
            "regime",
            "development_level",
            "data_coverage",
        ):
            require_positive(getattr(self, field), field, allow_zero=True)
        if self.total == 0.0:
            raise DomainValidationError("at least one analogue weight must be positive")

    @property
    def total(self) -> float:
        return (
            self.feature_state
            + self.global_state
            + self.regime
            + self.development_level
            + self.data_coverage
        )


@dataclass(frozen=True, slots=True)
class StandardizationStatistic:
    name: str
    mean: float
    standard_deviation: float
    observations: int
    constant_in_reference: bool


@dataclass(frozen=True, slots=True)
class AnalogueDistanceComponents:
    feature_state: float
    global_state: float
    regime: float
    development_level: float
    data_coverage: float


@dataclass(frozen=True, slots=True)
class HistoricalAnalogue:
    country_code: str
    observed_on: date
    similarity_score: float
    distance: float
    components: AnalogueDistanceComponents
    feature_state: Mapping[str, float | None]
    global_state: Mapping[str, float | None]
    conditions_at_time: Mapping[str, ContextValue]
    outcomes: Mapping[str, ContextValue]
    regime: str
    development_level: str
    data_coverage: float
    interpretation: str = "CONTEXTUAL_EVIDENCE_NOT_CAUSAL_PROOF"
    is_probability: bool = False

    def __post_init__(self) -> None:
        score = require_finite(self.similarity_score, "similarity_score")
        if not 0.0 <= score <= 100.0:
            raise DomainValidationError("similarity_score must be between 0 and 100")
        require_positive(self.distance, "distance", allow_zero=True)
        object.__setattr__(
            self, "feature_state", _freeze_numeric_mapping(self.feature_state, "feature_state")
        )
        object.__setattr__(
            self, "global_state", _freeze_numeric_mapping(self.global_state, "global_state")
        )
        object.__setattr__(
            self,
            "conditions_at_time",
            _freeze_context_mapping(self.conditions_at_time, "conditions_at_time"),
        )
        object.__setattr__(
            self, "outcomes", _freeze_context_mapping(self.outcomes, "outcomes")
        )
        if self.is_probability:
            raise DomainValidationError("analogue similarity must not be labelled as probability")


@dataclass(frozen=True, slots=True)
class HistoricalAnalogueSearch:
    as_of: date
    query_date: date
    reference_window: AnalogueReferenceWindow
    feature_statistics: tuple[StandardizationStatistic, ...]
    global_statistics: tuple[StandardizationStatistic, ...]
    matches: tuple[HistoricalAnalogue, ...]
    candidates_considered: int
    standardization_method: str = (
        "population mean and standard deviation from point-in-time-visible observations "
        "inside the supplied past reference window; constant metrics use unit scale"
    )
    similarity_method: str = "100 / (1 + weighted component distance); not a probability"
    interpretation: str = "CONTEXTUAL_EVIDENCE_NOT_CAUSAL_PROOF"


def _standardization_statistics(
    states: Sequence[HistoricalState],
    names: Sequence[str],
    *,
    field: str,
) -> tuple[StandardizationStatistic, ...]:
    statistics: list[StandardizationStatistic] = []
    for name in names:
        values = tuple(
            value
            for state in states
            if (value := getattr(state, field).get(name)) is not None
        )
        if not values:
            raise DomainValidationError(
                f"reference window has no observed values for {field}[{name}]"
            )
        mean = math.fsum(values) / len(values)
        variance = math.fsum((value - mean) ** 2 for value in values) / len(values)
        raw_scale = math.sqrt(variance)
        constant = raw_scale <= 1e-12
        statistics.append(
            StandardizationStatistic(
                name=name,
                mean=mean,
                standard_deviation=1.0 if constant else raw_scale,
                observations=len(values),
                constant_in_reference=constant,
            )
        )
    return tuple(statistics)


def _standardized_distance(
    query: Mapping[str, float | None],
    candidate: Mapping[str, float | None],
    statistics: Sequence[StandardizationStatistic],
    *,
    missing_penalty: float,
) -> float:
    observed_query = tuple(stat for stat in statistics if query.get(stat.name) is not None)
    if not observed_query:
        return 1.0
    squared: list[float] = []
    missing = 0
    for statistic in observed_query:
        query_value = query[statistic.name]
        candidate_value = candidate.get(statistic.name)
        if candidate_value is None:
            missing += 1
            continue
        squared.append(
            ((query_value - candidate_value) / statistic.standard_deviation) ** 2
        )
    base_distance = math.sqrt(math.fsum(squared) / len(squared)) if squared else 0.0
    return base_distance + missing_penalty * missing / len(observed_query)


def find_historical_analogues(
    *,
    query: AnalogueQuery,
    history: Sequence[HistoricalState],
    reference_window: AnalogueReferenceWindow,
    as_of: date,
    limit: int = 5,
    weights: AnalogueWeights = AnalogueWeights(),
    missing_metric_penalty: float = 1.0,
) -> HistoricalAnalogueSearch:
    """Rank past states using statistics fitted only within ``reference_window``.

    The result is a transparent contextual similarity score, not a probability
    and not evidence that a matching historical state caused a later outcome.
    """

    require_date(as_of, "as_of")
    if query.observed_on > as_of:
        raise DomainValidationError("analogue query observation cannot be after as_of")
    if reference_window.end >= query.observed_on:
        raise DomainValidationError("reference window must end before the query observation")
    if reference_window.end > as_of:
        raise DomainValidationError("reference window cannot end after as_of")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise DomainValidationError("limit must be a positive integer")
    missing_metric_penalty = require_positive(
        missing_metric_penalty, "missing_metric_penalty", allow_zero=True
    )
    eligible = tuple(
        state
        for state in history
        if reference_window.contains(state.observed_on)
        and state.observed_on <= as_of
        and state.available_on <= as_of
    )
    if not eligible:
        raise DomainValidationError("no point-in-time-visible states in the reference window")
    feature_names = tuple(sorted(query.features))
    global_names = tuple(sorted(query.global_state))
    feature_statistics = _standardization_statistics(
        eligible, feature_names, field="features"
    )
    global_statistics = _standardization_statistics(
        eligible, global_names, field="global_state"
    )
    normalized = AnalogueWeights(
        feature_state=weights.feature_state / weights.total,
        global_state=weights.global_state / weights.total,
        regime=weights.regime / weights.total,
        development_level=weights.development_level / weights.total,
        data_coverage=weights.data_coverage / weights.total,
    )
    matches: list[HistoricalAnalogue] = []
    for candidate in eligible:
        feature_distance = _standardized_distance(
            query.features,
            candidate.features,
            feature_statistics,
            missing_penalty=missing_metric_penalty,
        )
        global_distance = _standardized_distance(
            query.global_state,
            candidate.global_state,
            global_statistics,
            missing_penalty=missing_metric_penalty,
        )
        regime_distance = 0.0 if candidate.regime == query.regime else 1.0
        development_distance = (
            0.0 if candidate.development_level == query.development_level else 1.0
        )
        coverage_distance = 0.5 * abs(query.data_coverage - candidate.data_coverage) + 0.5 * (
            1.0 - candidate.data_coverage
        )
        components = AnalogueDistanceComponents(
            feature_state=feature_distance,
            global_state=global_distance,
            regime=regime_distance,
            development_level=development_distance,
            data_coverage=coverage_distance,
        )
        distance = (
            normalized.feature_state * components.feature_state
            + normalized.global_state * components.global_state
            + normalized.regime * components.regime
            + normalized.development_level * components.development_level
            + normalized.data_coverage * components.data_coverage
        )
        matches.append(
            HistoricalAnalogue(
                country_code=candidate.country_code,
                observed_on=candidate.observed_on,
                similarity_score=100.0 / (1.0 + distance),
                distance=distance,
                components=components,
                feature_state=candidate.features,
                global_state=candidate.global_state,
                conditions_at_time=candidate.context,
                outcomes=candidate.outcomes,
                regime=candidate.regime,
                development_level=candidate.development_level,
                data_coverage=candidate.data_coverage,
            )
        )
    matches.sort(key=lambda match: (-match.similarity_score, match.observed_on, match.country_code))
    return HistoricalAnalogueSearch(
        as_of=as_of,
        query_date=query.observed_on,
        reference_window=reference_window,
        feature_statistics=feature_statistics,
        global_statistics=global_statistics,
        matches=tuple(matches[:limit]),
        candidates_considered=len(eligible),
    )
