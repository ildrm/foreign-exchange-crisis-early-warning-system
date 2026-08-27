"""Canonical FX-CPM report serialization and semantic validation."""

from __future__ import annotations

import json
import math
import os
import sysconfig
import tempfile
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date
from enum import Enum
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "1.0.0"
REQUIRED_SECTIONS = (
    "schema_version",
    "model_version",
    "methodology_version",
    "calibration_version",
    "alert_policy_version",
    "analysis",
    "countries",
    "hazards",
    "forecasts",
    "alerts",
    "fx_stress",
    "macro_vulnerability",
    "contagion",
    "historical_analogues",
    "validation",
    "calibration",
    "data_quality",
    "source_health",
    "limitations",
    "provenance",
)


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """A deterministic structural or scientific-contract validation finding."""

    level: str
    path: str
    code: str
    message: str


class CanonicalJSONEncoder(json.JSONEncoder):
    """Encode immutable domain objects without weakening the JSON contract."""

    def default(self, obj: Any) -> Any:
        if is_dataclass(obj) and not isinstance(obj, type):
            return asdict(obj)
        if isinstance(obj, Enum):
            return obj.value
        if isinstance(obj, (date,)):
            return obj.isoformat()
        if isinstance(obj, Path):
            return str(obj)
        if isinstance(obj, set | frozenset):
            return sorted(obj)
        return super().default(obj)


def canonical_json(report: Mapping[str, Any], *, indent: int = 2) -> str:
    """Serialize a report deterministically with strict non-finite-number rejection."""

    return json.dumps(
        report,
        cls=CanonicalJSONEncoder,
        ensure_ascii=False,
        sort_keys=True,
        indent=indent,
        allow_nan=False,
    ) + "\n"


def load_report(path: str | Path) -> dict[str, Any]:
    """Load a canonical report object and reject non-object JSON."""

    report_path = Path(path)
    try:
        value = json.loads(report_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read report {report_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {report_path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("canonical report JSON must be an object")
    return value


def write_report(path: str | Path, report: Mapping[str, Any]) -> Path:
    """Atomically write canonical JSON when source and destination share a filesystem."""

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    data = canonical_json(report)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=str(output.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(output)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return output


def report_schema_path() -> Path | None:
    """Locate the canonical schema in a source checkout or installed wheel."""

    candidates = (
        Path(__file__).resolve().parent.parent / "schemas" / "report.schema.json",
        Path(sysconfig.get_path("data"))
        / "share"
        / "fx-cpm"
        / "schemas"
        / "report.schema.json",
    )
    local = next((candidate for candidate in candidates if candidate.is_file()), None)
    if local is not None:
        return local
    try:
        installed = distribution("fx-cpm").locate_file(
            "share/fx-cpm/schemas/report.schema.json"
        )
    except PackageNotFoundError:
        return None
    installed_path = Path(installed)
    return installed_path if installed_path.is_file() else None


def _number_in_unit_interval(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, int | float)
        and math.isfinite(float(value))
        and 0 <= float(value) <= 1
    )


def _as_sequence(value: Any) -> Sequence[Any] | None:
    return value if isinstance(value, list | tuple) else None


def _is_finite_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, int | float)
        and math.isfinite(float(value))
    )


def _validate_calibrated_claims(
    report: Mapping[str, Any],
    forecasts: Sequence[Any],
) -> list[ValidationIssue]:
    """Cross-check probability language against its report-level evidence.

    A forecast-local status flag is not evidence of calibration.  This gate
    deliberately requires the independently reported calibration, validation,
    taxonomy, point-in-time, and threshold artifacts before the canonical
    output may call a number a validated probability.
    """

    issues: list[ValidationIssue] = []
    analysis = report.get("analysis")
    analysis = analysis if isinstance(analysis, Mapping) else {}
    report_mode = analysis.get("report_mode")
    calibrated_mode = report_mode in {"RESEARCH_CALIBRATED", "VALIDATED_OPERATIONAL"}
    claimed: list[tuple[int, Mapping[str, Any]]] = [
        (index, forecast)
        for index, forecast in enumerate(forecasts)
        if isinstance(forecast, Mapping)
        and (
            forecast.get("probability_status") == "CALIBRATED_VALIDATED"
            or forecast.get("display_label") == "PROBABILITY"
        )
    ]
    if not calibrated_mode and not claimed:
        return issues

    if report_mode == "RESEARCH_UNCALIBRATED" and claimed:
        issues.append(
            ValidationIssue(
                "ERROR",
                "$.analysis.report_mode",
                "CALIBRATED_MODE_CONFLICT",
                "validated probability claims are forbidden in RESEARCH_UNCALIBRATED mode",
            )
        )
    if calibrated_mode and not claimed:
        issues.append(
            ValidationIssue(
                "ERROR",
                "$.forecasts",
                "CALIBRATED_FORECAST_MISSING",
                "a calibrated report mode requires at least one CALIBRATED_VALIDATED forecast",
            )
        )

    calibration = report.get("calibration")
    calibration = calibration if isinstance(calibration, Mapping) else {}
    calibration_requirements = (
        ("status", calibration.get("status") == "ACCEPTABLE", "must equal ACCEPTABLE"),
        ("method", calibration.get("method") not in (None, ""), "must name the fitted method"),
        (
            "calibration_period",
            calibration.get("calibration_period") not in (None, ""),
            "must disclose the held-out calibration period",
        ),
        (
            "event_count",
            isinstance(calibration.get("event_count"), int)
            and not isinstance(calibration.get("event_count"), bool)
            and int(calibration["event_count"]) > 0,
            "must be a positive integer",
        ),
        ("brier_score", _is_finite_number(calibration.get("brier_score")), "must be reported"),
        ("log_loss", _is_finite_number(calibration.get("log_loss")), "must be reported"),
    )
    for field, passed, message in calibration_requirements:
        if not passed:
            issues.append(
                ValidationIssue(
                    "ERROR",
                    f"$.calibration.{field}",
                    "CALIBRATION_EVIDENCE_MISSING",
                    message,
                )
            )

    calibration_version = str(report.get("calibration_version") or "").strip().casefold()
    if calibration_version in {"", "none", "not-fitted", "not_fitted", "unvalidated"}:
        issues.append(
            ValidationIssue(
                "ERROR",
                "$.calibration_version",
                "CALIBRATION_VERSION_MISSING",
                "validated probability claims require a fitted calibration artifact version",
            )
        )

    validation = report.get("validation")
    validation = validation if isinstance(validation, Mapping) else {}
    metrics = validation.get("metrics")
    metrics = metrics if isinstance(metrics, Mapping) else {}
    validation_requirements = (
        ("status", validation.get("status") == "VALIDATED", "must equal VALIDATED"),
        (
            "chronological_split",
            validation.get("chronological_split") is True,
            "must attest chronological separation",
        ),
        (
            "final_test_untouched",
            validation.get("final_test_untouched") is True,
            "must attest an untouched final test",
        ),
        (
            "alert_thresholds_backtested",
            validation.get("alert_thresholds_backtested") is True,
            "must attest hazard/horizon threshold backtesting",
        ),
    )
    for field, passed, message in validation_requirements:
        if not passed:
            issues.append(
                ValidationIssue(
                    "ERROR",
                    f"$.validation.{field}",
                    "VALIDATION_EVIDENCE_MISSING",
                    message,
                )
            )
    for field in ("brier_score", "log_loss"):
        if not _is_finite_number(metrics.get(field)):
            issues.append(
                ValidationIssue(
                    "ERROR",
                    f"$.validation.metrics.{field}",
                    "TEST_METRIC_MISSING",
                    "must be reported on held-out observations",
                )
            )

    hazard_versions = {
        item.get("hazard_type"): item.get("definition_version")
        for item in (_as_sequence(report.get("hazards")) or ())
        if isinstance(item, Mapping)
    }
    analysis_date = analysis.get("analysis_date")
    for index, forecast in claimed:
        path = f"$.forecasts[{index}]"
        hazard = forecast.get("hazard")
        if not hazard_versions.get(hazard):
            issues.append(
                ValidationIssue(
                    "ERROR",
                    f"{path}.hazard",
                    "TAXONOMY_VERSION_MISSING",
                    "the claimed hazard must reference a versioned report taxonomy",
                )
            )
        if forecast.get("base_rate") is None:
            issues.append(
                ValidationIssue(
                    "ERROR", f"{path}.base_rate", "BASE_RATE_MISSING", "must be disclosed"
                )
            )
        if forecast.get("ood_status") != "IN_DOMAIN":
            issues.append(
                ValidationIssue(
                    "ERROR",
                    f"{path}.ood_status",
                    "CALIBRATION_DOMAIN_UNSUPPORTED",
                    "validated probability language requires an IN_DOMAIN prediction",
                )
            )
        if not all(
            _number_in_unit_interval(forecast.get(field))
            for field in ("uncertainty_low", "uncertainty_high")
        ):
            issues.append(
                ValidationIssue(
                    "ERROR",
                    path,
                    "UNCERTAINTY_MISSING",
                    "validated probabilities require a disclosed bounded uncertainty interval",
                )
            )
        training_end = forecast.get("training_end_date")
        if not isinstance(training_end, str) or not training_end:
            issues.append(
                ValidationIssue(
                    "ERROR",
                    f"{path}.training_end_date",
                    "TRAINING_CUTOFF_MISSING",
                    "must disclose the model training cutoff",
                )
            )
        elif isinstance(analysis_date, str) and training_end > analysis_date:
            issues.append(
                ValidationIssue(
                    "ERROR",
                    f"{path}.training_end_date",
                    "TRAINING_AFTER_ANALYSIS",
                    "training cutoff cannot be after the analysis date",
                )
            )
    return issues


def validate_report(report: Mapping[str, Any], *, use_jsonschema: bool = True) -> list[ValidationIssue]:
    """Validate schema shape and scientific language/gating invariants.

    The standard-library checks always run. If ``jsonschema`` is installed,
    Draft 2020-12 validation is added without making it a runtime dependency.
    """

    issues: list[ValidationIssue] = []
    for key in REQUIRED_SECTIONS:
        if key not in report:
            issues.append(ValidationIssue("ERROR", "$", "MISSING_SECTION", key))
    if report.get("schema_version") != SCHEMA_VERSION:
        issues.append(
            ValidationIssue(
                "ERROR",
                "$.schema_version",
                "SCHEMA_VERSION",
                f"expected {SCHEMA_VERSION!r}",
            )
        )

    analysis = report.get("analysis")
    if not isinstance(analysis, Mapping):
        issues.append(ValidationIssue("ERROR", "$.analysis", "TYPE", "must be an object"))
    else:
        mode = analysis.get("report_mode")
        if mode not in {"RESEARCH_UNCALIBRATED", "RESEARCH_CALIBRATED", "VALIDATED_OPERATIONAL"}:
            issues.append(ValidationIssue("ERROR", "$.analysis.report_mode", "ENUM", str(mode)))

    forecasts = _as_sequence(report.get("forecasts"))
    if forecasts is None:
        issues.append(ValidationIssue("ERROR", "$.forecasts", "TYPE", "must be an array"))
        forecasts = ()
    for index, forecast in enumerate(forecasts):
        path = f"$.forecasts[{index}]"
        if not isinstance(forecast, Mapping):
            issues.append(ValidationIssue("ERROR", path, "TYPE", "must be an object"))
            continue
        for field in ("raw_probability", "calibrated_probability", "base_rate", "confidence", "coverage"):
            value = forecast.get(field)
            if value is not None and not _number_in_unit_interval(value):
                issues.append(
                    ValidationIssue("ERROR", f"{path}.{field}", "PROBABILITY_RANGE", repr(value))
                )
        low = forecast.get("uncertainty_low")
        high = forecast.get("uncertainty_high")
        center = forecast.get("calibrated_probability")
        if center is None:
            center = forecast.get("raw_probability")
        if low is not None and high is not None and center is not None:
            if not float(low) <= float(center) <= float(high):
                issues.append(
                    ValidationIssue(
                        "ERROR", path, "UNCERTAINTY_ORDER", "expected low <= estimate <= high"
                    )
                )
        status = forecast.get("probability_status")
        calibrated = forecast.get("calibrated_probability")
        label = forecast.get("display_label")
        if status == "CALIBRATED_VALIDATED" and calibrated is None:
            issues.append(
                ValidationIssue(
                    "ERROR", path, "CALIBRATION_VALUE_MISSING", "validated status needs a value"
                )
            )
        if status != "CALIBRATED_VALIDATED" and label == "PROBABILITY":
            issues.append(
                ValidationIssue(
                    "ERROR",
                    path,
                    "PROBABILITY_LANGUAGE_GATE",
                    "uncalibrated output cannot be labelled probability",
                )
            )
        base = forecast.get("base_rate")
        relative = forecast.get("relative_risk")
        estimate = calibrated if calibrated is not None else forecast.get("raw_probability")
        if base not in (None, 0) and estimate is not None and relative is not None:
            expected = float(estimate) / float(base)
            if not math.isclose(float(relative), expected, rel_tol=0.02, abs_tol=0.02):
                issues.append(
                    ValidationIssue(
                        "WARNING",
                        f"{path}.relative_risk",
                        "RELATIVE_RISK_MISMATCH",
                        f"reported={relative}, calculated={expected:.4g}",
                    )
                )

    issues.extend(_validate_calibrated_claims(report, forecasts))

    alerts = _as_sequence(report.get("alerts"))
    if alerts is None:
        issues.append(ValidationIssue("ERROR", "$.alerts", "TYPE", "must be an array"))
        alerts = ()
    forecast_status = {
        (item.get("country"), item.get("hazard"), item.get("horizon")): item.get(
            "probability_status"
        )
        for item in forecasts
        if isinstance(item, Mapping)
    }
    for index, alert in enumerate(alerts):
        path = f"$.alerts[{index}]"
        if not isinstance(alert, Mapping):
            issues.append(ValidationIssue("ERROR", path, "TYPE", "must be an object"))
            continue
        severity = alert.get("severity")
        key = (alert.get("country"), alert.get("hazard"), alert.get("horizon"))
        if severity in {"ELEVATED", "HIGH", "CRITICAL"} and forecast_status.get(key) != "CALIBRATED_VALIDATED":
            issues.append(
                ValidationIssue(
                    "ERROR",
                    f"{path}.severity",
                    "SEVERE_ALERT_UNCALIBRATED",
                    f"{severity} requires CALIBRATED_VALIDATED forecast",
                )
            )
        if severity == "CRITICAL" and alert.get("calibration_status") != "ACCEPTABLE":
            issues.append(
                ValidationIssue(
                    "ERROR",
                    path,
                    "CRITICAL_CALIBRATION_GATE",
                    "CRITICAL requires acceptable calibration",
                )
            )
        if severity in {"ELEVATED", "HIGH", "CRITICAL"}:
            if alert.get("trigger_threshold") is None or not alert.get("threshold_methodology"):
                issues.append(
                    ValidationIssue(
                        "ERROR",
                        path,
                        "ALERT_THRESHOLD_EVIDENCE_MISSING",
                        "severe alerts require a disclosed validated threshold and methodology",
                    )
                )

    provenance = _as_sequence(report.get("provenance"))
    if provenance is None:
        issues.append(ValidationIssue("ERROR", "$.provenance", "TYPE", "must be an array"))
        provenance = ()
    for index, observation in enumerate(provenance):
        if not isinstance(observation, Mapping):
            continue
        path = f"$.provenance[{index}]"
        status = observation.get("status")
        value = observation.get("value")
        if status in {"MISSING", "NOT_APPLICABLE", "SOURCE_FAILURE", "INSUFFICIENT_HISTORY"} and value is not None:
            issues.append(
                ValidationIssue(
                    "ERROR", path, "MISSING_IS_NOT_ZERO", f"status {status} must have null value"
                )
            )
        if status == "AVAILABLE" and value is None:
            issues.append(
                ValidationIssue("ERROR", path, "AVAILABLE_VALUE_MISSING", "available value is null")
            )

    if use_jsonschema:
        try:
            import jsonschema
        except ImportError:
            issues.append(
                ValidationIssue(
                    "ERROR",
                    "$",
                    "SCHEMA_VALIDATOR_UNAVAILABLE",
                    "jsonschema is required for canonical report validation",
                )
            )
        else:
            schema_path = report_schema_path()
            if schema_path is None:
                issues.append(
                    ValidationIssue(
                        "ERROR",
                        "$",
                        "SCHEMA_UNAVAILABLE",
                        "the packaged report.schema.json artifact could not be located",
                    )
                )
            else:
                schema = json.loads(schema_path.read_text(encoding="utf-8"))
                validator = jsonschema.Draft202012Validator(
                    schema, format_checker=jsonschema.FormatChecker()
                )
                for error in sorted(
                    validator.iter_errors(dict(report)),
                    key=lambda item: tuple(str(part) for part in item.path),
                ):
                    path = "$" + "".join(
                        f"[{part}]" if isinstance(part, int) else f".{part}" for part in error.path
                    )
                    issues.append(ValidationIssue("ERROR", path, "JSON_SCHEMA", error.message))
    return issues


__all__ = [
    "SCHEMA_VERSION",
    "ValidationIssue",
    "canonical_json",
    "load_report",
    "report_schema_path",
    "validate_report",
    "write_report",
]
