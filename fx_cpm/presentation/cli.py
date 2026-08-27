"""Command-line interface for reproducible FX-CPM research reports."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import traceback
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from fx_cpm.demo import COUNTRIES, HAZARDS, build_demo_report
from fx_cpm.presentation.console import render_console
from fx_cpm.provenance import audit_records
from fx_cpm.reporting import load_report, validate_report, write_report


def _csv(value: str) -> list[str]:
    items = [item.strip() for item in value.split(",") if item.strip()]
    if not items:
        raise argparse.ArgumentTypeError("provide at least one comma-separated value")
    return items


def _iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected an ISO date (YYYY-MM-DD)") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fx-cpm",
        description=(
            "Generate regime-aware multi-hazard research reports. The bundled data are "
            "synthetic and outputs remain uncalibrated unless a validated report is supplied."
        ),
    )
    parser.add_argument("--countries", type=_csv, help="country codes, e.g. tr,ar,br")
    parser.add_argument("--hazards", type=_csv, help="hazard codes, e.g. fx,banking,sovereign")
    parser.add_argument("--as-of", type=_iso_date, default=date(2024, 1, 31))
    parser.add_argument("--history-start", type=_iso_date)
    parser.add_argument("--no-web", action="store_true", help="disable all network-backed providers")
    parser.add_argument("--no-seed", action="store_true", help="do not use the synthetic fixture")
    parser.add_argument("--input-json", type=Path, help="load a complete canonical report")
    parser.add_argument(
        "--market-json",
        type=Path,
        help="augment the displayed fx_stress section; does not train or backtest a model",
    )
    parser.add_argument(
        "--event-database",
        type=Path,
        help="append report timeline context; does not create training labels or run a model",
    )
    parser.add_argument("--model-version", help="requested model artifact version")
    parser.add_argument("--calibration-version", help="requested calibration artifact version")
    parser.add_argument(
        "--backtest",
        nargs="?",
        const="all",
        metavar="HAZARD",
        help="run/record the deterministic synthetic pipeline backtest for a hazard",
    )
    parser.add_argument("--source-audit", action="store_true", help="audit provenance completeness")
    parser.add_argument("--validate", action="store_true", help="validate schema and scientific gates")
    parser.add_argument("--output", type=Path, help="write canonical JSON")
    parser.add_argument("--html", type=Path, help="write a self-contained HTML report")
    parser.add_argument("--pdf", type=Path, help="export PDF using the optional Playwright extra")
    parser.add_argument("--debug", action="store_true")
    parser.epilog = (
        f"Bundled synthetic countries: {', '.join(COUNTRIES)}. "
        f"Hazards: {', '.join(HAZARDS)}."
    )
    return parser


def _read_json(path: Path, expected: type) -> Any:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, expected):
        raise ValueError(f"{path} must contain a JSON {expected.__name__}")
    return payload


def _filter_loaded_report(
    report: dict[str, Any], countries: list[str] | None, hazards: list[str] | None
) -> dict[str, Any]:
    if countries:
        wanted = {item.casefold() for item in countries}
        selected_names = {
            str(item.get("name", ""))
            for item in report.get("countries", [])
            if isinstance(item, Mapping)
            and (
                str(item.get("country_id", "")).casefold() in wanted
                or str(item.get("name", "")).casefold() in wanted
            )
        }
        report["countries"] = [
            item
            for item in report.get("countries", [])
            if isinstance(item, Mapping) and str(item.get("name", "")) in selected_names
        ]
        report["forecasts"] = [
            item
            for item in report.get("forecasts", [])
            if isinstance(item, Mapping) and str(item.get("country", "")) in selected_names
        ]
        report["alerts"] = [
            item
            for item in report.get("alerts", [])
            if isinstance(item, Mapping) and str(item.get("country", "")) in selected_names
        ]
    if hazards:
        aliases = {"CURRENCY": "FX", "BANKING": "BANK", "SOVEREIGN": "SOV"}
        wanted_hazards = {aliases.get(item.upper(), item.upper()) for item in hazards}
        report["hazards"] = [
            item
            for item in report.get("hazards", [])
            if isinstance(item, Mapping) and item.get("hazard_type") in wanted_hazards
        ]
        report["forecasts"] = [
            item
            for item in report.get("forecasts", [])
            if isinstance(item, Mapping) and item.get("hazard") in wanted_hazards
        ]
        report["alerts"] = [
            item
            for item in report.get("alerts", [])
            if isinstance(item, Mapping) and item.get("hazard") in wanted_hazards
        ]
    return report


def _attach_inputs(report: dict[str, Any], market_json: Path | None, event_json: Path | None) -> None:
    if market_json:
        market = _read_json(market_json, dict)
        report["fx_stress"] = market
        report.setdefault("source_health", {})["market_json"] = str(market_json)
    if event_json:
        events = _read_json(event_json, list)
        for index, item in enumerate(events):
            if not isinstance(item, dict):
                raise ValueError(f"event database item {index} must be an object")
            if not {"date", "hazard"}.issubset(item):
                raise ValueError(f"event database item {index} needs date and hazard")
            entry = {
                "date": str(item["date"]),
                "hazard": str(item["hazard"]).upper(),
                "estimate": item.get("estimate"),
                "vintage_status": str(item.get("vintage_status", "EXTERNAL_NORMALIZED")),
                "event_onset": bool(item.get("event_onset", True)),
            }
            report.setdefault("historical_timeline", []).append(entry)


def _record_synthetic_backtest(report: dict[str, Any], hazard: str) -> None:
    selected = hazard.upper()
    if selected != "ALL" and selected not in HAZARDS:
        aliases = {"CURRENCY": "FX", "BANKING": "BANK", "SOVEREIGN": "SOV"}
        selected = aliases.get(selected, selected)
    if selected != "ALL" and selected not in HAZARDS:
        raise ValueError(f"unknown backtest hazard {hazard!r}")
    # Fixed outcomes/predictions exercise metric plumbing without implying empirical validity.
    outcomes = (0, 0, 1, 0, 0, 1, 0, 0, 0, 1, 0, 0)
    predictions = (0.04, 0.08, 0.42, 0.14, 0.11, 0.55, 0.09, 0.18, 0.07, 0.61, 0.13, 0.05)
    brier = sum((p - y) ** 2 for p, y in zip(predictions, outcomes, strict=True)) / len(outcomes)
    ranked = sorted(zip(predictions, outcomes, strict=True), reverse=True)
    positives = sum(outcomes)
    hits = 0
    ap = 0.0
    for rank, (_, outcome) in enumerate(ranked, start=1):
        if outcome:
            hits += 1
            ap += hits / rank
    report["validation"] = {
        "status": "RESEARCH_ONLY",
        "chronological_split": True,
        "final_test_untouched": True,
        "metrics": {"average_precision": round(ap / positives, 6), "brier_score": round(brier, 6), "log_loss": None},
        "fx_ablation": {"delta_average_precision": None, "delta_brier": None, "delta_log_loss": None},
        "test_window": "synthetic ordered fixture",
        "event_count": positives,
        "hazard": selected,
        "message": "Algorithm smoke test on fabricated ordered rows; this is not empirical performance.",
    }


def _audit_sources(report: Mapping[str, Any]) -> tuple[int, list[str]]:
    provenance = report.get("provenance", [])
    if not isinstance(provenance, list):
        return 1, ["provenance is not an array"]
    if not all(isinstance(record, Mapping) for record in provenance):
        return 1, ["every provenance item must be an object"]
    findings = audit_records(provenance)
    errors = [
        f"provenance[{item.record}] {item.code}: {item.message}"
        for item in findings
        if item.level == "ERROR"
    ]
    return len(errors), errors


def _build_report(args: argparse.Namespace) -> dict[str, Any]:
    if args.input_json:
        report = _filter_loaded_report(
            deepcopy(load_report(args.input_json)), args.countries, args.hazards
        )
    else:
        if args.no_seed:
            raise ValueError("--no-seed requires --input-json; no live data source is bundled")
        report = build_demo_report(
            args.countries or ["tr"], args.hazards or list(HAZARDS), args.as_of
        )
    analysis = report.setdefault("analysis", {})
    if args.history_start:
        analysis["history_start"] = args.history_start.isoformat()
    analysis["web_accessed"] = False
    if args.no_web:
        analysis["network_policy"] = "DISABLED_BY_USER"
    if args.model_version:
        report["model_version"] = args.model_version
        for forecast in report.get("forecasts", []):
            if isinstance(forecast, dict):
                forecast["model_version"] = args.model_version
    if args.calibration_version:
        report["calibration_version"] = args.calibration_version
        for forecast in report.get("forecasts", []):
            if isinstance(forecast, dict):
                forecast["calibration_version"] = args.calibration_version
    _attach_inputs(report, args.market_json, args.event_database)
    if args.backtest:
        _record_synthetic_backtest(report, args.backtest)
    return report


def _write_html(path: Path, report: Mapping[str, Any]) -> None:
    from fx_cpm.presentation.html_report import render_html_report

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html_report(report), encoding="utf-8", newline="\n")


def run(args: argparse.Namespace) -> int:
    report = _build_report(args)
    exit_code = 0
    if args.source_audit:
        count, messages = _audit_sources(report)
        for message in messages:
            print(f"SOURCE ERROR: {message}", file=sys.stderr)
        print(f"Source audit: {len(report.get('provenance', []))} record(s), {count} error(s)")
        exit_code = max(exit_code, int(count > 0))
    if args.validate:
        issues = validate_report(report)
        for issue in issues:
            stream = sys.stderr if issue.level == "ERROR" else sys.stdout
            print(f"{issue.level}: {issue.path} [{issue.code}] {issue.message}", file=stream)
        errors = sum(issue.level == "ERROR" for issue in issues)
        print(f"Validation: {errors} error(s), {len(issues) - errors} warning(s)")
        exit_code = max(exit_code, int(errors > 0))

    if args.output:
        write_report(args.output, report)
        print(f"Wrote JSON: {args.output}")
    if args.html:
        _write_html(args.html, report)
        print(f"Wrote HTML: {args.html}")
    if args.pdf:
        from fx_cpm.presentation.pdf import export_pdf

        if args.html:
            html_path = args.html
            export_pdf(html_path, args.pdf)
        else:
            with tempfile.TemporaryDirectory(prefix="fx-cpm-pdf-") as directory:
                html_path = Path(directory) / "report.html"
                _write_html(html_path, report)
                export_pdf(html_path, args.pdf)
        print(f"Wrote PDF: {args.pdf}")

    print(render_console(report), end="")
    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except (OSError, RuntimeError, ValueError) as exc:
        if args.debug:
            traceback.print_exc()
        else:
            print(f"fx-cpm: {exc}", file=sys.stderr)
        return 2


__all__ = ["build_parser", "main", "run"]
