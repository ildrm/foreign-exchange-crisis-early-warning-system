#!/usr/bin/env python3
"""Build an auditable point-in-time observation panel from normalized CSV."""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from fx_cpm.application.point_in_time import PointInTimeSelector, VintageMode
from fx_cpm.domain.observations import (
    MissingStatus,
    Observation,
    ObservationFrequency,
    ProvenanceType,
    RevisionStatus,
    SourceAuthority,
    SourceType,
)
from fx_cpm.infrastructure.json_io import write_json

REQUIRED_COLUMNS = {
    "feature_id",
    "country_id",
    "value",
    "unit",
    "frequency",
    "period_start",
    "period_end",
    "release_date",
    "retrieval_date",
    "vintage",
    "source_name",
    "source_url",
    "source_type",
    "license",
    "base_quality",
    "revision_status",
    "provenance_type",
    "status",
}


def _date(value: str, field: str, line: int) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"line {line}: {field} must be YYYY-MM-DD") from exc


def _optional(value: str | None) -> str | None:
    normalized = (value or "").strip()
    return normalized or None


def _observation(row: dict[str, str], line: int) -> Observation:
    status = MissingStatus(row["status"].strip().lower())
    raw_value = row.get("value", "").strip()
    value = None if not raw_value else float(raw_value)
    return Observation(
        observation_id=_optional(row.get("observation_id")),
        feature_id=row["feature_id"].strip(),
        country_id=row["country_id"].strip(),
        currency_id=_optional(row.get("currency_id")),
        value=value,
        unit=row["unit"].strip(),
        frequency=ObservationFrequency(row["frequency"].strip().lower()),
        period_start=_date(row["period_start"], "period_start", line),
        period_end=_date(row["period_end"], "period_end", line),
        release_date=_date(row["release_date"], "release_date", line),
        retrieval_date=_date(row["retrieval_date"], "retrieval_date", line),
        vintage=row["vintage"].strip(),
        source_name=row["source_name"].strip(),
        source_url=row["source_url"].strip(),
        source_type=SourceType(row["source_type"].strip().lower()),
        license=row["license"].strip(),
        base_quality=float(row["base_quality"]),
        revision_status=RevisionStatus(row["revision_status"].strip().lower()),
        provenance_type=ProvenanceType(row["provenance_type"].strip().lower()),
        status=status,
        provider=_optional(row.get("provider")),
        source_authority=SourceAuthority(
            (row.get("source_authority") or SourceAuthority.SECONDARY.value).strip().lower()
        ),
        source_quality=(
            float(row["source_quality"])
            if _optional(row.get("source_quality")) is not None
            else None
        ),
    )


def read_observations(paths: Iterable[Path]) -> tuple[Observation, ...]:
    observations: list[Observation] = []
    for path in paths:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            columns = set(reader.fieldnames or ())
            missing = sorted(REQUIRED_COLUMNS - columns)
            if missing:
                raise ValueError(f"{path}: missing columns: {', '.join(missing)}")
            for line, row in enumerate(reader, start=2):
                try:
                    observations.append(_observation(row, line))
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError(f"{path}:{line}: {exc}") from exc
    return tuple(observations)


def _primitive_observation(item: Observation) -> dict[str, Any]:
    raw = asdict(item)
    raw["frequency"] = item.frequency.value
    raw["source_type"] = item.source_type.value
    raw["revision_status"] = item.revision_status.value
    raw["provenance_type"] = item.provenance_type.value
    raw["status"] = item.status.value
    raw["source_authority"] = item.source_authority.value
    for field in ("period_start", "period_end", "release_date", "retrieval_date"):
        raw[field] = getattr(item, field).isoformat()
    return raw


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Select one eligible vintage per normalized observation period."
    )
    parser.add_argument("inputs", type=Path, nargs="+", help="normalized CSV input(s)")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--as-of", type=date.fromisoformat, required=True)
    parser.add_argument(
        "--vintage-mode",
        choices=[item.value for item in VintageMode],
        default=VintageMode.TRUE_VINTAGE.value,
    )
    parser.add_argument(
        "--latest-per-series",
        action="store_true",
        help="retain only the newest eligible period for each feature/country/currency",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        observations = read_observations(args.inputs)
        selection = PointInTimeSelector().select(
            observations,
            as_of=args.as_of,
            mode=VintageMode(args.vintage_mode),
            latest_per_series=args.latest_per_series,
        )
        payload = {
            "panel_version": "1.0.0",
            "as_of": args.as_of.isoformat(),
            "vintage_mode": selection.vintage_mode.value,
            "genuine_real_time": selection.is_genuine_real_time,
            "input_records": len(observations),
            "selected_records": len(selection.observations),
            "exclusion_counts": dict(selection.reason_counts),
            "observations": [_primitive_observation(item) for item in selection.observations],
        }
        write_json(args.output, payload)
    except (OSError, ValueError) as exc:
        print(f"historical panel build failed: {exc}", file=sys.stderr)
        return 2
    print(
        f"Wrote {args.output}: {len(selection.observations)}/{len(observations)} observations "
        f"({selection.vintage_mode.value})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

