"""Schema-canonical report assembly and evidence-bound narrative generation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime, timezone
from enum import Enum
from statistics import mean
from typing import Any, Iterable, Mapping, Sequence

from .alert_service import AlertDecision
from .forecast_service import ForecastEstimate, horizon_days

REQUIRED_REPORT_SECTIONS = (
    "schema_version", "model_version", "methodology_version", "calibration_version",
    "alert_policy_version", "analysis", "countries", "hazards", "forecasts", "alerts",
    "fx_stress", "macro_vulnerability", "contagion", "historical_analogues", "validation",
    "calibration", "data_quality", "source_health", "limitations", "provenance",
)

_HAZARD_CODES = {
    "fx": "FX", "currency": "FX", "currency_crisis": "FX",
    "bank": "BANK", "banking": "BANK", "systemic_banking_crisis": "BANK",
    "sov": "SOV", "sovereign": "SOV", "sovereign_distress": "SOV",
    "mon": "MON", "monetary": "MON", "monetary_inflation_crisis": "MON",
    "pol": "POL", "political": "POL", "political_instability": "POL",
    "coup": "COUP", "civ": "CIV", "internal_conflict": "CIV",
    "war": "WAR", "interstate_conflict": "WAR",
}

_HAZARD_LABELS = {
    "FX": "Currency / balance-of-payments crisis",
    "BANK": "Systemic banking crisis",
    "SOV": "Sovereign distress / default",
    "MON": "Monetary / inflation crisis",
    "POL": "Major political-instability crisis",
    "COUP": "Coup / unconstitutional government change",
    "CIV": "Internal armed-conflict onset / escalation",
    "WAR": "Interstate armed-conflict onset / escalation",
}


def to_primitive(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if is_dataclass(value):
        return {key: to_primitive(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): to_primitive(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [to_primitive(item) for item in value]
    return str(value)


def _enum_text(value: Any) -> str:
    return str(getattr(value, "value", value))


def _hazard_code(value: Any) -> str:
    raw = _enum_text(value).strip()
    upper = raw.upper()
    if upper in _HAZARD_LABELS:
        return upper
    try:
        return _HAZARD_CODES[raw.lower()]
    except KeyError as exc:
        raise ValueError(f"hazard {value!r} is not in the canonical taxonomy") from exc


def _horizon_token(value: Any) -> str:
    label = getattr(value, "label", None)
    if label in {"30d", "90d", "180d", "12m", "24m", "36m"}:
        return str(label)
    days = horizon_days(value)
    try:
        return {30: "30d", 90: "90d", 180: "180d", 365: "12m", 730: "24m", 1095: "36m"}[days]
    except KeyError as exc:
        raise ValueError(f"horizon {value!r} is not canonical") from exc


def _point_in_time_status(value: Any) -> str:
    normalized = _enum_text(value).upper()
    if normalized not in {"TRUE_VINTAGE", "RECONSTRUCTED_POINT_IN_TIME", "REVISED_HISTORY_ONLY", "MIXED"}:
        raise ValueError(f"invalid point-in-time status: {value!r}")
    return normalized


@dataclass(frozen=True, slots=True)
class ReportVersions:
    schema: str = "1.0.0"
    model: str = "0.1.0-research"
    methodology: str = "0.1.0"
    calibration: str = "none"
    alert_policy: str = "0.1.0"


@dataclass(frozen=True, slots=True)
class ReportValidationIssue:
    path: str
    message: str


class ReportService:
    """Build the canonical object consumed identically by JSON and HTML."""

    def build(
        self,
        *,
        as_of: date,
        forecasts: Iterable[ForecastEstimate],
        alerts: Iterable[AlertDecision],
        versions: ReportVersions = ReportVersions(),
        point_in_time_mode: Any = "REVISED_HISTORY_ONLY",
        countries: Iterable[Any] | None = None,
        hazards: Iterable[Any] | None = None,
        generated_at: datetime | None = None,
        fx_stress: Any = None,
        macro_vulnerability: Any = None,
        contagion: Any = None,
        historical_analogues: Any = None,
        validation: Any = None,
        calibration: Any = None,
        data_quality: Any = None,
        source_health: Any = None,
        limitations: Iterable[str] = (),
        provenance: Any = None,
    ) -> dict[str, Any]:
        estimates = tuple(forecasts)
        decisions = tuple(alerts)
        generated = generated_at or datetime.now(timezone.utc)
        validation_row = self._validation(validation)
        calibration_row = self._calibration(calibration)
        calibrated_gate = self._calibrated_gate(estimates, versions, validation_row, calibration_row)
        report_mode = "RESEARCH_CALIBRATED" if calibrated_gate else "RESEARCH_UNCALIBRATED"
        country_rows = self._countries(countries, estimates)
        hazard_rows = self._hazards(hazards, estimates, versions.methodology)
        country_names = {row["country_id"]: row["name"] for row in country_rows}
        forecast_rows = tuple(
            self._forecast(item, country_names, versions, calibrated_gate) for item in estimates
        )
        alert_rows = tuple(self._alert(item, forecast_rows, country_names) for item in decisions)
        limitations_rows = tuple(dict.fromkeys(str(item) for item in limitations if str(item).strip()))
        if not calibrated_gate:
            limitation = "No validated calibration and final-test evidence authorizes operational probability claims."
            if limitation not in limitations_rows:
                limitations_rows += (limitation,)
        elif not limitations_rows:
            limitations_rows = (
                "Forecasts remain conditional on historical relationships and cannot anticipate unforeseeable shocks.",
            )
        summary = self.executive_summary(estimates, decisions, limitations_rows, calibrated_gate)
        return {
            "schema_version": versions.schema,
            "model_version": versions.model,
            "methodology_version": versions.methodology,
            "calibration_version": versions.calibration,
            "alert_policy_version": versions.alert_policy,
            "analysis": {
                "analysis_date": as_of.isoformat(),
                "generated_at": generated.isoformat().replace("+00:00", "Z"),
                "report_mode": report_mode,
                "point_in_time_status": _point_in_time_status(point_in_time_mode),
                "executive_summary": summary,
                "major_limitation": limitations_rows[0],
            },
            "countries": list(country_rows),
            "hazards": list(hazard_rows),
            "forecasts": list(forecast_rows),
            "alerts": list(alert_rows),
            "fx_stress": to_primitive(fx_stress if fx_stress is not None else {}),
            "macro_vulnerability": to_primitive(macro_vulnerability if macro_vulnerability is not None else {}),
            "contagion": to_primitive(contagion if contagion is not None else {}),
            "historical_analogues": to_primitive(historical_analogues if historical_analogues is not None else []),
            "validation": validation_row,
            "calibration": calibration_row,
            "data_quality": self._data_quality(data_quality, estimates, point_in_time_mode),
            "source_health": to_primitive(source_health if source_health is not None else {}),
            "limitations": list(limitations_rows),
            "provenance": self._provenance(tuple(provenance or ())),
        }

    @staticmethod
    def _calibrated_gate(
        estimates: Sequence[ForecastEstimate],
        versions: ReportVersions,
        validation: Mapping[str, Any],
        calibration: Mapping[str, Any],
    ) -> bool:
        metrics = validation.get("metrics") if isinstance(validation.get("metrics"), Mapping) else {}
        return bool(estimates) and all(
            item.output_label == "CALIBRATED_PROBABILITY"
            and item.calibration_in_domain
            and item.sensitivity_low is not None
            and item.sensitivity_high is not None
            for item in estimates
        ) and versions.calibration.lower() not in {"none", "unvalidated", ""} and all((
            calibration.get("status") == "ACCEPTABLE",
            calibration.get("method") not in (None, ""),
            calibration.get("calibration_period") not in (None, ""),
            isinstance(calibration.get("event_count"), int) and calibration.get("event_count", 0) > 0,
            calibration.get("brier_score") is not None,
            calibration.get("log_loss") is not None,
            validation.get("status") == "VALIDATED",
            validation.get("chronological_split") is True,
            validation.get("final_test_untouched") is True,
            validation.get("alert_thresholds_backtested") is True,
            metrics.get("brier_score") is not None,
            metrics.get("log_loss") is not None,
        ))

    @staticmethod
    def _countries(countries: Iterable[Any] | None, estimates: Sequence[ForecastEstimate]) -> tuple[dict[str, Any], ...]:
        supplied = tuple(countries or ())
        if not supplied:
            supplied = tuple(sorted({item.country_id for item in estimates}))
        rows = []
        for value in supplied:
            if isinstance(value, Mapping):
                country_id = str(value.get("country_id") or value.get("id") or value.get("name"))
                row = dict(to_primitive(value))
                row["country_id"] = country_id
                row["name"] = str(value.get("name") or country_id)
            else:
                country_id = str(getattr(value, "country_id", value))
                row = {
                    "country_id": country_id.upper(),
                    "name": str(getattr(value, "name", country_id.upper())),
                    "currency_id": getattr(value, "currency_id", None),
                    "regime": to_primitive(getattr(value, "regime", None)),
                }
            rows.append(row)
        return tuple(rows)

    @staticmethod
    def _hazards(hazards: Iterable[Any] | None, estimates: Sequence[ForecastEstimate], definition_version: str) -> tuple[dict[str, Any], ...]:
        supplied = tuple(hazards or (item.hazard for item in estimates))
        codes = tuple(dict.fromkeys(_hazard_code(item) for item in supplied))
        return tuple({
            "hazard_type": code,
            "label": _HAZARD_LABELS[code],
            "definition_version": definition_version,
            "supported_horizons": sorted(
                {_horizon_token(item.horizon) for item in estimates if _hazard_code(item.hazard) == code},
                key=lambda value: {"30d": 30, "90d": 90, "180d": 180, "12m": 365, "24m": 730, "36m": 1095}[value],
            ),
        } for code in codes)

    @staticmethod
    def _forecast(item: ForecastEstimate, countries: Mapping[str, str], versions: ReportVersions, calibrated_gate: bool) -> dict[str, Any]:
        validated = calibrated_gate and item.output_label == "CALIBRATED_PROBABILITY"
        weak = item.calibrated_probability is not None and not validated
        status = "CALIBRATED_VALIDATED" if validated else ("CALIBRATED_WEAK" if weak else "UNCALIBRATED")
        tier = _enum_text(item.model_tier).upper() if item.model_tier is not None else (
            "MODERN_MARKET_ENHANCED" if any(name.lower().startswith("fx") for name, _ in item.predictive_contributors) else "MACRO_FINANCIAL"
        )
        if tier not in {"HISTORICAL_STRUCTURAL", "MACRO_FINANCIAL", "MODERN_MARKET_ENHANCED"}:
            tier = "MACRO_FINANCIAL"
        contributors = [
            {"feature": name, "contribution": contribution, "direction": "INCREASES_ESTIMATE", "available": True}
            for name, contribution in item.predictive_contributors if contribution >= 0
        ]
        contrary = [
            {"feature": name, "contribution": contribution, "direction": "DECREASES_ESTIMATE", "available": True}
            for name, contribution in item.predictive_contributors if contribution < 0
        ]
        return {
            "country": countries.get(item.country_id, countries.get(item.country_id.upper(), item.country_id)),
            "country_id": item.country_id.upper(),
            "hazard": _hazard_code(item.hazard),
            "analysis_date": item.analysis_date.isoformat(),
            "horizon": _horizon_token(item.horizon),
            "raw_probability": item.raw_probability,
            "calibrated_probability": item.calibrated_probability,
            "probability_status": status,
            "display_label": "PROBABILITY" if validated else "UNCALIBRATED_RISK_ESTIMATE",
            "base_rate": item.base_rate,
            "relative_risk": item.relative_risk,
            "historical_percentile": None,
            "confidence": None,
            "coverage": item.data_coverage,
            "uncertainty_low": item.sensitivity_low,
            "uncertainty_high": item.sensitivity_high,
            "ensemble_dispersion": item.ensemble_dispersion,
            "model_version": item.model_version,
            "calibration_version": versions.calibration,
            "regime": _enum_text(getattr(item, "regime", "NOT_ASSESSED")),
            "training_end_date": item.training_end_date.isoformat(),
            "model_tier": tier,
            "ood_status": "IN_DOMAIN" if validated else "NOT_ASSESSED",
            "contributors": contributors,
            "contrary_evidence": contrary,
        }

    @staticmethod
    def _alert(item: AlertDecision, forecasts: Sequence[Mapping[str, Any]], countries: Mapping[str, str]) -> dict[str, Any]:
        country_id = item.country_id or next((str(row.get("country_id")) for row in forecasts if row.get("hazard") == _hazard_code(item.hazard) and row.get("horizon") == _horizon_token(item.horizon)), "UNKNOWN")
        match = next((row for row in forecasts if row.get("country_id") == country_id.upper() and row.get("hazard") == _hazard_code(item.hazard) and row.get("horizon") == _horizon_token(item.horizon)), None)
        severity = item.severity.value
        evidence = [warning.value for warning in item.evidence_warnings]
        if severity in {"ELEVATED", "HIGH", "CRITICAL"} and (match is None or match.get("probability_status") != "CALIBRATED_VALIDATED"):
            severity = "WATCH_UNCALIBRATED"
            if "CALIBRATION_WEAK" not in evidence:
                evidence.append("CALIBRATION_WEAK")
        return {
            "country": countries.get(country_id, countries.get(country_id.upper(), country_id)),
            "hazard": _hazard_code(item.hazard),
            "horizon": _horizon_token(item.horizon),
            "severity": severity,
            "evidence_alerts": evidence,
            "calibrated_probability": match.get("calibrated_probability") if match else None,
            "base_rate": item.historical_base_rate,
            "relative_risk": item.relative_risk,
            "historical_percentile": item.historical_percentile,
            "probability_change": item.probability_change_30d,
            "evidence_confidence": item.evidence_confidence,
            "data_coverage": item.data_coverage,
            "calibration_status": item.calibration_status,
            "ood_status": item.ood_status,
            "fx_regime": to_primitive(item.regime),
            "trigger_threshold": item.trigger_threshold,
            "threshold_methodology": item.threshold_methodology,
            "first_seen": item.state.first_seen.isoformat(),
            "last_changed": item.state.last_changed.isoformat(),
        }

    @staticmethod
    def _validation(value: Any) -> dict[str, Any]:
        row = dict(to_primitive(value)) if isinstance(value, Mapping) else {}
        row.setdefault("status", "NOT_RUN")
        row.setdefault("chronological_split", False)
        row.setdefault("final_test_untouched", False)
        return row

    @staticmethod
    def _calibration(value: Any) -> dict[str, Any]:
        row = dict(to_primitive(value)) if isinstance(value, Mapping) else {}
        row.setdefault("status", "NOT_FITTED")
        row.setdefault("method", None)
        row.setdefault("calibration_period", None)
        row.setdefault("event_count", 0)
        return row

    @staticmethod
    def _data_quality(value: Any, estimates: Sequence[ForecastEstimate], point_in_time_mode: Any) -> dict[str, Any]:
        supplied = dict(to_primitive(value)) if isinstance(value, Mapping) and "coverage" in value else {}
        supplied.setdefault("coverage", mean(item.data_coverage for item in estimates) if estimates else 0.0)
        supplied.setdefault("freshness", None)
        supplied.setdefault("source_authority", None)
        supplied.setdefault("vintage_quality", {"TRUE_VINTAGE": 1.0, "RECONSTRUCTED_POINT_IN_TIME": 0.7, "REVISED_HISTORY_ONLY": 0.3, "MIXED": 0.5}[_point_in_time_status(point_in_time_mode)])
        return supplied

    @staticmethod
    def _provenance(observations: Sequence[Any]) -> list[dict[str, Any]]:
        rows = []
        authority_scores = {"PRIMARY": 1.0, "AUTHORITATIVE_SECONDARY": 0.85, "SECONDARY": 0.65, "UNVERIFIED": 0.25}
        for item in observations:
            primitive = to_primitive(item)
            if not isinstance(primitive, Mapping):
                continue
            row = dict(primitive)
            authority = str(row.get("source_authority", "UNVERIFIED")).upper()
            row["source_authority"] = authority_scores.get(authority, row.get("source_authority") if isinstance(row.get("source_authority"), (int, float)) else 0.25)
            row["source_quality"] = row.get("source_quality") if row.get("source_quality") is not None else row.get("base_quality")
            row["provider"] = row.get("provider") or row.get("source_name")
            row["frequency"] = str(row.get("frequency", "")).lower()
            row["source_type"] = str(row.get("source_type", "")).lower()
            row["revision_status"] = str(row.get("revision_status", "")).lower()
            row["provenance_type"] = str(row.get("provenance_type", "")).lower()
            row["status"] = str(row.get("status", "MISSING")).upper()
            lineage = row.get("transformation_lineage") or ()
            row["transformation_lineage"] = [entry.get("operation", str(entry)) if isinstance(entry, Mapping) else str(entry) for entry in lineage]
            rows.append(row)
        return rows

    @staticmethod
    def executive_summary(forecasts: Iterable[ForecastEstimate], alerts: Iterable[AlertDecision], limitations: Iterable[str] = (), calibrated: bool = False) -> str:
        rows = tuple(forecasts)
        decisions = tuple(alerts)
        if not rows:
            return "No model estimate is available because the requested information set is insufficient."
        strongest = max(rows, key=lambda item: (item.displayed_probability, str(item.hazard), str(item.horizon)))
        hazard = _HAZARD_LABELS[_hazard_code(strongest.hazard)].lower()
        horizon = _horizon_token(strongest.horizon)
        if calibrated:
            opening = f"The calibrated model estimates a {strongest.displayed_probability:.1%} probability of {hazard} onset over {horizon}."
        else:
            opening = f"The research model reports an uncalibrated {strongest.displayed_probability:.1%} risk estimate for {hazard} over {horizon}; this is not an operational probability."
        pieces = [opening, f"The fitted-sample historical base rate is {strongest.base_rate:.1%}."]
        matched = next((item for item in decisions if _hazard_code(item.hazard) == _hazard_code(strongest.hazard) and _horizon_token(item.horizon) == horizon), None)
        if matched is not None:
            pieces.append(f"Evidence coverage is {matched.data_coverage:.0%}, assessed separately from event risk.")
        limitation = next(iter(limitations), None)
        if limitation:
            pieces.append(f"Key limitation: {limitation}")
        return " ".join(pieces)

    @staticmethod
    def validate(report: Mapping[str, Any]) -> tuple[ReportValidationIssue, ...]:
        from fx_cpm.reporting import validate_report

        return tuple(ReportValidationIssue(item.path, item.message) for item in validate_report(report, use_jsonschema=False))
