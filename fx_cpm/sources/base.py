"""Common contracts for macro, market, political, and historical adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Iterable, Mapping, Protocol, Sequence, runtime_checkable


@dataclass(frozen=True, slots=True)
class SourceDescriptor:
    source_id: str
    name: str
    provider: str
    url: str
    source_type: str
    authority: str
    license: str
    frequency: str
    revision_characteristics: str
    publication_lag: str
    historical_start: date | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        for field_name in ("source_id", "name", "provider", "url", "source_type", "license"):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} is required")


@dataclass(frozen=True, slots=True)
class SourceFetchResult:
    descriptor: SourceDescriptor
    observations: tuple[Any, ...]
    retrieved_at: datetime
    status: str = "AVAILABLE"
    warnings: tuple[str, ...] = ()


@runtime_checkable
class DataSource(Protocol):
    descriptor: SourceDescriptor

    def fetch(
        self,
        *,
        country_ids: Iterable[str] | None = None,
        start: date | None = None,
        end: date | None = None,
    ) -> SourceFetchResult: ...


class StaticSource:
    """Offline source retaining supplied immutable observation objects."""

    def __init__(self, descriptor: SourceDescriptor, observations: Sequence[Any]) -> None:
        self.descriptor = descriptor
        self._observations = tuple(observations)

    def fetch(
        self,
        *,
        country_ids: Iterable[str] | None = None,
        start: date | None = None,
        end: date | None = None,
    ) -> SourceFetchResult:
        countries = frozenset(country_ids) if country_ids is not None else None
        selected = []
        for observation in self._observations:
            if countries is not None and getattr(observation, "country_id", None) not in countries:
                continue
            period_start = getattr(observation, "period_start", None)
            period_end = getattr(observation, "period_end", None)
            if start is not None and period_end is not None and period_end < start:
                continue
            if end is not None and period_start is not None and period_start > end:
                continue
            selected.append(observation)
        return SourceFetchResult(self.descriptor, tuple(selected), datetime.now(timezone.utc))


def source_health(results: Iterable[SourceFetchResult]) -> Mapping[str, Any]:
    rows = tuple(results)
    failures = sum(result.status in {"SOURCE_FAILURE", "DATA_PIPELINE_FAILURE"} for result in rows)
    return {
        "source_count": len(rows),
        "available_count": len(rows) - failures,
        "failure_count": failures,
        "statuses": {result.descriptor.source_id: result.status for result in rows},
    }
