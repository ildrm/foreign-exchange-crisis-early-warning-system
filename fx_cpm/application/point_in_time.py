"""Point-in-time observation selection and vintage-quality labelling."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Iterable, Mapping


class VintageMode(str, Enum):
    """Scientific quality of a historical information set."""

    TRUE_VINTAGE = "TRUE_VINTAGE"
    RECONSTRUCTED_POINT_IN_TIME = "RECONSTRUCTED_POINT_IN_TIME"
    REVISED_HISTORY_ONLY = "REVISED_HISTORY_ONLY"
    AUTO = "AUTO"


@dataclass(frozen=True, slots=True)
class ExcludedObservation:
    observation: Any
    reason: str


@dataclass(frozen=True, slots=True)
class PointInTimeSelection:
    as_of: date
    vintage_mode: VintageMode
    observations: tuple[Any, ...]
    excluded: tuple[ExcludedObservation, ...]
    reason_counts: Mapping[str, int]

    @property
    def leakage_safe(self) -> bool:
        return self.vintage_mode is not VintageMode.REVISED_HISTORY_ONLY

    @property
    def is_genuine_real_time(self) -> bool:
        return self.vintage_mode is VintageMode.TRUE_VINTAGE


def _date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(getattr(value, "value", value)).strip()
    if not text:
        return None
    # ISO timestamps and ISO dates are the only unambiguous forms accepted.
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _mode(value: VintageMode | str) -> VintageMode:
    if isinstance(value, VintageMode):
        return value
    raw = str(getattr(value, "value", value)).upper()
    return VintageMode(raw)


def _series_period_key(observation: Any) -> tuple[Any, ...]:
    return (
        getattr(observation, "country_id", None),
        getattr(observation, "currency_id", None),
        getattr(observation, "feature_id", None),
        _date(getattr(observation, "period_start", None)),
        _date(getattr(observation, "period_end", None)),
        getattr(observation, "unit", None),
        getattr(observation, "frequency", None),
    )


def _series_key(observation: Any) -> tuple[Any, ...]:
    return (
        getattr(observation, "country_id", None),
        getattr(observation, "currency_id", None),
        getattr(observation, "feature_id", None),
        getattr(observation, "unit", None),
        getattr(observation, "frequency", None),
    )


def _version_order(observation: Any, position: int) -> tuple[Any, ...]:
    vintage = _date(getattr(observation, "vintage", None))
    release = _date(getattr(observation, "release_date", None))
    retrieval = _date(getattr(observation, "retrieval_date", None))
    period_end = _date(getattr(observation, "period_end", None))
    minimum = date.min
    return (vintage or minimum, release or minimum, retrieval or minimum, period_end or minimum, position)


class PointInTimeSelector:
    """Construct information sets without silently using future revisions.

    ``TRUE_VINTAGE`` requires both release and retrieval timestamps no later
    than the analysis date. ``RECONSTRUCTED_POINT_IN_TIME`` uses documented
    historical release/vintage dates even when the archive was retrieved later.
    ``REVISED_HISTORY_ONLY`` only enforces the economic-period boundary and is
    therefore explicitly unsuitable for a genuine real-time backtest.
    """

    def select(
        self,
        observations: Iterable[Any],
        *,
        as_of: date,
        mode: VintageMode | str = VintageMode.TRUE_VINTAGE,
        latest_per_series: bool = False,
    ) -> PointInTimeSelection:
        requested = _mode(mode)
        records = tuple(observations)
        effective = self._auto_mode(records, as_of) if requested is VintageMode.AUTO else requested
        visible: list[tuple[int, Any]] = []
        excluded: list[ExcludedObservation] = []

        for position, observation in enumerate(records):
            reason = self._exclusion_reason(observation, as_of, effective)
            if reason is None:
                visible.append((position, observation))
            else:
                excluded.append(ExcludedObservation(observation, reason))

        # Select the newest version that was available under the chosen semantics.
        versions: dict[tuple[Any, ...], tuple[int, Any]] = {}
        for position, observation in visible:
            key = _series_period_key(observation)
            current = versions.get(key)
            if current is None or _version_order(observation, position) > _version_order(current[1], current[0]):
                if current is not None:
                    excluded.append(ExcludedObservation(current[1], "superseded_vintage"))
                versions[key] = (position, observation)
            else:
                excluded.append(ExcludedObservation(observation, "superseded_vintage"))

        chosen = list(versions.values())
        if latest_per_series:
            latest: dict[tuple[Any, ...], tuple[int, Any]] = {}
            for position, observation in chosen:
                key = _series_key(observation)
                current = latest.get(key)
                if current is None or self._period_order(observation, position) > self._period_order(current[1], current[0]):
                    if current is not None:
                        excluded.append(ExcludedObservation(current[1], "older_period"))
                    latest[key] = (position, observation)
                else:
                    excluded.append(ExcludedObservation(observation, "older_period"))
            chosen = list(latest.values())

        chosen.sort(key=lambda item: item[0])
        counts = Counter(item.reason for item in excluded)
        return PointInTimeSelection(
            as_of=as_of,
            vintage_mode=effective,
            observations=tuple(item[1] for item in chosen),
            excluded=tuple(excluded),
            reason_counts=dict(sorted(counts.items())),
        )

    @staticmethod
    def _period_order(observation: Any, position: int) -> tuple[Any, ...]:
        minimum = date.min
        return (
            _date(getattr(observation, "period_end", None)) or minimum,
            _date(getattr(observation, "period_start", None)) or minimum,
            _version_order(observation, position),
        )

    @staticmethod
    def _auto_mode(observations: tuple[Any, ...], as_of: date) -> VintageMode:
        period_eligible = [
            observation
            for observation in observations
            if (_date(getattr(observation, "period_end", None)) or date.min) <= as_of
        ]
        if period_eligible and all(
            _date(getattr(item, "release_date", None)) is not None
            and _date(getattr(item, "release_date", None)) <= as_of
            and _date(getattr(item, "retrieval_date", None)) is not None
            and _date(getattr(item, "retrieval_date", None)) <= as_of
            for item in period_eligible
        ):
            return VintageMode.TRUE_VINTAGE
        if period_eligible and all(_date(getattr(item, "release_date", None)) is not None for item in period_eligible):
            return VintageMode.RECONSTRUCTED_POINT_IN_TIME
        return VintageMode.REVISED_HISTORY_ONLY

    @staticmethod
    def _exclusion_reason(observation: Any, as_of: date, mode: VintageMode) -> str | None:
        period_start = _date(getattr(observation, "period_start", None))
        period_end = _date(getattr(observation, "period_end", None))
        release = _date(getattr(observation, "release_date", None))
        retrieval = _date(getattr(observation, "retrieval_date", None))
        vintage = _date(getattr(observation, "vintage", None))

        boundary = period_end or period_start
        if boundary is None:
            return "missing_economic_period"
        if boundary > as_of:
            return "future_economic_period"

        if mode is VintageMode.REVISED_HISTORY_ONLY:
            return None
        if release is None:
            return "missing_release_date"
        if release > as_of:
            return "not_yet_released"
        if vintage is not None and vintage > as_of:
            return "future_vintage"
        if mode is VintageMode.TRUE_VINTAGE:
            if retrieval is None:
                return "missing_retrieval_date"
            if retrieval > as_of:
                return "not_yet_retrieved"
        return None


def select_point_in_time(
    observations: Iterable[Any],
    as_of: date,
    mode: VintageMode | str = VintageMode.TRUE_VINTAGE,
    *,
    latest_per_series: bool = False,
) -> PointInTimeSelection:
    """Functional convenience wrapper around :class:`PointInTimeSelector`."""

    return PointInTimeSelector().select(
        observations,
        as_of=as_of,
        mode=mode,
        latest_per_series=latest_per_series,
    )
