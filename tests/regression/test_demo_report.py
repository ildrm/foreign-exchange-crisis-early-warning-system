from __future__ import annotations

from datetime import date

from fx_cpm.demo import build_demo_report


def test_fixed_demo_shape_and_leading_estimate() -> None:
    report = build_demo_report(("tr",), ("FX", "BANK"), date(2024, 1, 31))
    assert report["schema_version"] == "1.0.0"
    assert len(report["countries"]) == 1
    assert len(report["forecasts"]) == 7
    assert len(report["alerts"]) == 2
    fx_12m = next(
        item
        for item in report["forecasts"]
        if item["hazard"] == "FX" and item["horizon"] == "12m"
    )
    assert fx_12m["raw_probability"] == 0.2412
    assert fx_12m["calibrated_probability"] is None
    assert fx_12m["display_label"] == "UNCALIBRATED_RISK_ESTIMATE"

