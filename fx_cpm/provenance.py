"""Shared, status-aware provenance audit for reports and command-line tools."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

REQUIRED_VALUES = (
    "feature_id",
    "country_id",
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
    "provider",
    "source_authority",
    "source_quality",
    "license",
    "revision_status",
    "provenance_type",
    "status",
)
REQUIRED_KEYS = ("currency_id", "value", "transformation_lineage")


@dataclass(frozen=True, slots=True)
class Finding:
    level: str
    code: str
    record: int
    message: str


def _parse_date(value: Any, field: str, index: int, findings: list[Finding]) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        findings.append(Finding("ERROR", "INVALID_DATE", index, f"{field} is not ISO date"))
        return None


def audit_records(records: Sequence[Mapping[str, Any]]) -> list[Finding]:
    """Return deterministic provenance findings without treating missing as zero."""

    findings: list[Finding] = []
    identities: set[tuple[Any, ...]] = set()
    for index, record in enumerate(records):
        for field in REQUIRED_VALUES:
            if record.get(field) in (None, "", []):
                findings.append(Finding("ERROR", "MISSING_REQUIRED", index, field))
        for field in REQUIRED_KEYS:
            if field not in record:
                findings.append(Finding("ERROR", "MISSING_REQUIRED_KEY", index, field))

        period_start = _parse_date(record.get("period_start"), "period_start", index, findings)
        period_end = _parse_date(record.get("period_end"), "period_end", index, findings)
        release = _parse_date(record.get("release_date"), "release_date", index, findings)
        retrieval = _parse_date(record.get("retrieval_date"), "retrieval_date", index, findings)
        if period_start and period_end and period_start > period_end:
            findings.append(Finding("ERROR", "INVERTED_PERIOD", index, "period_start > period_end"))
        if period_end and release and release < period_end:
            findings.append(
                Finding(
                    "WARNING",
                    "RELEASE_BEFORE_PERIOD_END",
                    index,
                    "verify release semantics; release_date precedes period_end",
                )
            )
        if release and retrieval and retrieval < release:
            findings.append(
                Finding("ERROR", "RETRIEVED_BEFORE_RELEASE", index, "retrieval < release")
            )

        source_url = record.get("source_url")
        if source_url:
            parsed = urlparse(str(source_url))
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                findings.append(Finding("ERROR", "INVALID_SOURCE_URL", index, str(source_url)))

        status = str(record.get("status", "")).upper()
        value = record.get("value")
        if status in {"MISSING", "SOURCE_FAILURE", "NOT_APPLICABLE", "INSUFFICIENT_HISTORY"}:
            if value is not None:
                findings.append(
                    Finding(
                        "ERROR",
                        "MISSING_HAS_VALUE",
                        index,
                        f"status={status} but value is present",
                    )
                )
        elif status in {"AVAILABLE", "STALE", "UNRELIABLE"} and value is None:
            findings.append(Finding("ERROR", "OBSERVED_WITHOUT_VALUE", index, "value is null"))

        provenance_type = str(record.get("provenance_type", "")).upper()
        if provenance_type == "DERIVED" and not record.get("transformation_lineage"):
            findings.append(
                Finding(
                    "ERROR",
                    "DERIVED_WITHOUT_LINEAGE",
                    index,
                    "derived observations require transformation_lineage",
                )
            )

        authority = record.get("source_authority")
        quality = record.get("source_quality")
        for field, score in (("source_authority", authority), ("source_quality", quality)):
            if isinstance(score, bool) or not isinstance(score, int | float) or not 0 <= score <= 1:
                findings.append(
                    Finding("ERROR", "INVALID_QUALITY_SCORE", index, f"{field} must lie in [0, 1]")
                )

        identity = (
            record.get("feature_id"),
            record.get("country_id"),
            record.get("currency_id"),
            record.get("period_start"),
            record.get("period_end"),
            record.get("vintage"),
            record.get("source_name"),
        )
        if identity in identities:
            findings.append(Finding("WARNING", "DUPLICATE_IDENTITY", index, repr(identity)))
        identities.add(identity)
    return findings


__all__ = ["Finding", "audit_records"]
