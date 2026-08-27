"""Provider boundaries used by the application layer.

Providers return immutable domain records but deliberately do not decide what was
visible at a historical analysis date.  That decision belongs to
``PointInTimeSelector`` so that every adapter shares the same leakage rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from threading import RLock
from typing import Any, Iterable, Protocol, Sequence, runtime_checkable


def _as_date(value: Any) -> date | None:
    if value is None:
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


@runtime_checkable
class ObservationProvider(Protocol):
    """Read-only boundary for observations, events, and regime histories."""

    def get_observations(
        self,
        *,
        country_id: str | None = None,
        feature_ids: Iterable[str] | None = None,
        period_start: date | None = None,
        period_end: date | None = None,
    ) -> Sequence[Any]:
        """Return all matching vintages; point-in-time filtering happens later."""

    def get_events(
        self,
        *,
        country_id: str | None = None,
        hazard: Any | None = None,
    ) -> Sequence[Any]:
        """Return crisis-event records."""

    def get_regimes(
        self,
        *,
        country_id: str | None = None,
        as_of: date | None = None,
    ) -> Sequence[Any]:
        """Return country/currency regime records."""


@dataclass(slots=True)
class InMemoryProvider:
    """Deterministic provider for research fixtures and offline execution.

    Records are kept in insertion order and query results are returned as tuples.
    A lock makes mutation/query snapshots safe for simple threaded report runners.
    """

    observations: list[Any] = field(default_factory=list)
    events: list[Any] = field(default_factory=list)
    regimes: list[Any] = field(default_factory=list)
    _lock: RLock = field(default_factory=RLock, init=False, repr=False)

    def add_observation(self, observation: Any) -> None:
        with self._lock:
            self.observations.append(observation)

    def add_event(self, event: Any) -> None:
        with self._lock:
            self.events.append(event)

    def add_regime(self, regime: Any) -> None:
        with self._lock:
            self.regimes.append(regime)

    def get_observations(
        self,
        *,
        country_id: str | None = None,
        feature_ids: Iterable[str] | None = None,
        period_start: date | None = None,
        period_end: date | None = None,
    ) -> tuple[Any, ...]:
        requested = frozenset(feature_ids) if feature_ids is not None else None
        with self._lock:
            snapshot = tuple(self.observations)
        selected: list[Any] = []
        for observation in snapshot:
            if country_id is not None and getattr(observation, "country_id", None) != country_id:
                continue
            if requested is not None and getattr(observation, "feature_id", None) not in requested:
                continue
            obs_start = _as_date(getattr(observation, "period_start", None))
            obs_end = _as_date(getattr(observation, "period_end", None))
            if period_start is not None and obs_end is not None and obs_end < period_start:
                continue
            if period_end is not None and obs_start is not None and obs_start > period_end:
                continue
            selected.append(observation)
        return tuple(selected)

    # Adapter-friendly alias used by some source clients.
    fetch_observations = get_observations

    def get_events(
        self,
        *,
        country_id: str | None = None,
        hazard: Any | None = None,
    ) -> tuple[Any, ...]:
        with self._lock:
            snapshot = tuple(self.events)
        selected = []
        for event in snapshot:
            if country_id is not None and getattr(event, "country_id", None) != country_id:
                continue
            event_hazard = getattr(event, "hazard_type", getattr(event, "hazard", None))
            if hazard is not None and event_hazard != hazard:
                continue
            selected.append(event)
        return tuple(selected)

    def get_regimes(
        self,
        *,
        country_id: str | None = None,
        as_of: date | None = None,
    ) -> tuple[Any, ...]:
        with self._lock:
            snapshot = tuple(self.regimes)
        selected = []
        for regime in snapshot:
            if country_id is not None and getattr(regime, "country_id", None) != country_id:
                continue
            effective_from = _as_date(getattr(regime, "effective_from", None))
            effective_to = _as_date(getattr(regime, "effective_to", None))
            if as_of is not None:
                if effective_from is not None and effective_from > as_of:
                    continue
                if effective_to is not None and effective_to < as_of:
                    continue
            selected.append(regime)
        return tuple(selected)


@dataclass(frozen=True, slots=True)
class CompositeProvider:
    """Merge multiple read-only providers without hiding duplicate vintages."""

    providers: tuple[ObservationProvider, ...]

    def __init__(self, providers: Iterable[ObservationProvider]) -> None:
        object.__setattr__(self, "providers", tuple(providers))

    def get_observations(self, **filters: Any) -> tuple[Any, ...]:
        return tuple(item for provider in self.providers for item in provider.get_observations(**filters))

    fetch_observations = get_observations

    def get_events(self, **filters: Any) -> tuple[Any, ...]:
        return tuple(item for provider in self.providers for item in provider.get_events(**filters))

    def get_regimes(self, **filters: Any) -> tuple[Any, ...]:
        return tuple(item for provider in self.providers for item in provider.get_regimes(**filters))
