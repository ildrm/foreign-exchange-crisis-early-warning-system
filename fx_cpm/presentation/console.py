"""Plain-text projection of an FX-CPM report."""

from __future__ import annotations

from typing import Any, Mapping


def _percent(value: Any) -> str:
    if not isinstance(value, int | float):
        return "not available"
    return f"{float(value):.1%}"


def render_console(report: Mapping[str, Any]) -> str:
    """Render a concise summary without changing scientific labels."""

    analysis = report.get("analysis") if isinstance(report.get("analysis"), Mapping) else {}
    country_names = [
        str(item.get("name", item.get("country_id", "Unknown")))
        for item in report.get("countries", [])
        if isinstance(item, Mapping)
    ]
    lines = [
        "FX-CPM — Foreign Exchange-Informed Crisis Probability Model",
        f"Mode: {analysis.get('report_mode', 'UNKNOWN')}",
        f"Countries: {', '.join(country_names) or 'not specified'}",
        f"Analysis date: {analysis.get('analysis_date', 'not available')}",
        "",
    ]
    summary = analysis.get("executive_summary")
    if summary:
        lines.extend((str(summary), ""))

    alerts = [item for item in report.get("alerts", []) if isinstance(item, Mapping)]
    active = [item for item in alerts if item.get("severity") != "NO_ALERT"]
    lines.append("Active warning center")
    if not active:
        lines.append("  No active risk warning. Evidence/model warnings may still apply.")
    for alert in active:
        estimate = alert.get("calibrated_probability")
        label = "probability"
        if estimate is None:
            estimate = alert.get("raw_estimate")
            label = "uncalibrated estimate"
        evidence = ", ".join(map(str, alert.get("evidence_alerts", []))) or "none"
        lines.append(
            f"  [{alert.get('severity', 'UNKNOWN')}] {alert.get('hazard', '?')} / "
            f"{alert.get('horizon', '?')}: {label} {_percent(estimate)}; "
            f"base {_percent(alert.get('base_rate'))}; evidence warnings: {evidence}"
        )

    limitation = analysis.get("major_limitation")
    if limitation:
        lines.extend(("", f"Major limitation: {limitation}"))
    lines.extend(
        (
            "",
            "Interpretation: This is a probabilistic research signal or explicitly uncalibrated "
            "estimate, not a declaration that any crisis will occur.",
        )
    )
    return "\n".join(lines) + "\n"


__all__ = ["render_console"]

