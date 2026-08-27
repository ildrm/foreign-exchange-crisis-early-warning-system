"""Auditable local CSV adapter with an injected immutable-record factory."""

from __future__ import annotations

import csv
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from fx_cpm.infrastructure.dates import parse_date
from fx_cpm.sources.base import SourceDescriptor, SourceFetchResult

ObservationFactory = Callable[[Mapping[str, str]], Any]


class CSVObservationSource:
    def __init__(
        self,
        path: str | Path,
        descriptor: SourceDescriptor,
        observation_factory: ObservationFactory,
    ) -> None:
        self.path = Path(path)
        self.descriptor = descriptor
        self.observation_factory = observation_factory

    def fetch(
        self,
        *,
        country_ids: Iterable[str] | None = None,
        start: date | None = None,
        end: date | None = None,
    ) -> SourceFetchResult:
        countries = frozenset(country_ids) if country_ids is not None else None
        observations = []
        with self.path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                raise ValueError("CSV source has no header")
            for line_number, row in enumerate(reader, start=2):
                country_id = row.get("country_id")
                if countries is not None and country_id not in countries:
                    continue
                try:
                    period_start = parse_date(row["period_start"])
                    period_end = parse_date(row["period_end"])
                except (KeyError, ValueError) as exc:
                    raise ValueError(f"invalid economic period at CSV line {line_number}") from exc
                if start is not None and period_end < start:
                    continue
                if end is not None and period_start > end:
                    continue
                observations.append(self.observation_factory(row))
        return SourceFetchResult(
            descriptor=self.descriptor,
            observations=tuple(observations),
            retrieved_at=datetime.now(timezone.utc),
        )
