from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from types import MappingProxyType

from fx_cpm.presentation import render_html_report


def _research_report() -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "model_version": "fx-cpm-0.3.0",
        "methodology_version": "2026.08",
        "calibration_version": "iso-12m-v2",
        "alert_policy_version": "2.1",
        "analysis": {
            "analysis_date": "2026-08-26",
            "generated_at": "2026-08-27T09:00:00+03:30",
            "mode": "RESEARCH / VALIDATED",
        },
        "countries": [{"name": "Republic of Example", "iso3": "XMP"}],
        "hazards": [
            {
                "hazard": "currency_crisis",
                "supported_horizons": ["30d", "90d", "12m"],
            }
        ],
        "forecasts": [
            {
                "country": "Republic of Example",
                "hazard": "currency_crisis",
                "horizon": "30d",
                "raw_probability": 0.07,
                "calibrated_probability": 0.06,
                "calibrated": True,
                "calibration_validated": True,
                "base_rate": 0.025,
                "relative_risk": 2.4,
                "change_30d": 0.011,
                "historical_percentile": 82,
                "confidence": "MODERATE",
                "severity": "ELEVATED",
                "model_tier": "Tier 1",
                "ood_status": "in_domain",
                "lower_bound": 0.04,
                "upper_bound": 0.09,
                "contributors": [
                    {"name": "Exchange-market pressure", "contribution": 0.42},
                    {"name": "Export momentum", "contribution": -0.18},
                ],
            },
            {
                "country": "Republic of Example",
                "hazard": "currency_crisis",
                "horizon": "90d",
                "raw_probability": 0.13,
                "calibrated_probability": 0.11,
                "calibrated": True,
                "calibration_validated": True,
                "base_rate": 0.045,
                "confidence": "MODERATE",
                "severity": "ELEVATED",
                "lower_bound": 0.08,
                "upper_bound": 0.16,
            },
            {
                "country": "Republic of Example",
                "hazard": "currency_crisis",
                "horizon": "12m",
                "raw_probability": 0.28,
                "calibrated_probability": 0.24,
                "calibrated": True,
                "calibration_validated": True,
                "base_rate": 0.08,
                "confidence": "HIGH",
                "severity": "HIGH",
                "lower_bound": 0.18,
                "upper_bound": 0.31,
            },
        ],
        "alerts": [
            {
                "active": True,
                "country": "Republic of Example",
                "hazard": "currency_crisis",
                "horizon": "12m",
                "severity": "HIGH",
                "key_reason": "Exchange-market pressure remains unusually high.",
                "caveat": "Reserve observations are released with a six-week lag.",
                "calibrated": True,
                "calibration_validated": True,
            }
        ],
        "fx_stress": {
            "country": "Republic of Example",
            "spot_return": -0.031,
            "residual_stress": 1.7,
            "realized_volatility": 0.24,
            "emp": 1.34,
            "reserve_pressure": -0.018,
            "parallel_market_premium": None,
            "fx_stress_percentile": 0.91,
            "regime": "Managed float",
        },
        "macro_vulnerability": {
            "country": "Republic of Example",
            "vulnerability_score": 63,
            "credit_to_gdp": 71.4,
            "inflation": 0.19,
            "external_balance": -0.034,
            "reserves": 3.2,
            "political_structure": "Competitive executive constraints",
            "momentum": {"change_7d": 0.002, "change_30d": 0.011, "change_90d": 0.024},
        },
        "historical_timeline": {
            "points": [
                {"date": "2024-Q1", "risk_estimate": 0.08, "vintage_state": "true-vintage"},
                {"date": "2025-Q1", "risk_estimate": 0.14, "vintage_state": "true-vintage"},
                {"date": "2026-Q1", "risk_estimate": 0.21, "vintage_state": "true-vintage"},
            ],
            "events": [
                {
                    "onset_canonical": "2025-Q1",
                    "hazard_type": "inflation_crisis",
                    "label_confidence": "HIGH",
                }
            ],
        },
        "historical_analogues": [
            {
                "country": "Peerland",
                "period": "2018-Q3",
                "hazard": "currency_crisis",
                "similarity": 0.84,
                "outcome": "No crisis within 12 months",
                "evidence_quality": "HIGH",
            }
        ],
        "contributors": [
            {"name": "Exchange-market pressure", "contribution": 0.42},
            {"name": "Reserve deterioration", "contribution": 0.29},
            {"name": "Export momentum", "contribution": -0.18},
        ],
        "contagion": {
            "regional_state": "Elevated common-factor stress",
            "common_factor_stress": 1.2,
            "contagion_index": 0.44,
            "confidence": "MODERATE",
            "peers": [
                {
                    "country": "Peerland",
                    "region": "Example region",
                    "hazard": "currency_crisis",
                    "risk_estimate": 0.12,
                    "common_factor_stress": 1.2,
                    "channel": "Trade and bank funding",
                    "confidence": "MODERATE",
                }
            ],
        },
        "calibration": {
            "status": "validated",
            "validated": True,
            "brier_score": 0.082,
            "log_loss": 0.31,
            "pr_auc": 0.42,
            "base_rate": 0.08,
            "event_count": 27,
            "test_period": "2008–2025",
            "method": "Isotonic regression",
            "reliability_bins": [
                {"predicted": 0.04, "observed": 0.03, "count": 311},
                {"predicted": 0.12, "observed": 0.14, "count": 93},
                {"predicted": 0.25, "observed": 0.23, "count": 31},
            ],
        },
        "validation": {
            "calibration_validated": True,
            "status": "validated",
            "backtests": [
                {
                    "window": "2018–2025",
                    "crises_detected": 7,
                    "missed_events": 2,
                    "false_alerts": 5,
                    "warning_lead_time": "5.5 months",
                }
            ],
            "fx_ablation": {
                "with_fx": 0.42,
                "without_fx": 0.35,
                "metric": "PR-AUC",
                "test_period": "2018–2025",
            },
        },
        "data_quality": {
            "country": "Republic of Example",
            "score": 0.78,
            "coverage": 0.86,
            "freshness": "Mixed",
            "source_authority": "Mostly official",
            "source_disagreement": "One unresolved FX series",
            "historical_depth": "18 years",
            "vintage_quality": "Partial true-vintage",
        },
        "source_health": {"healthy": 14, "stale": 2, "failed": 1, "last_audit": "2026-08-27"},
        "methodology": {
            "summary": "Regime-aware discrete-time hazard ensemble with point-in-time features.",
            "event_target": "Currency-crisis onset within each disclosed horizon",
            "model": "Regularized survival model and tree challenger",
            "horizons": "30 days, 90 days and 12 months",
            "calibration": "Horizon-specific isotonic regression",
            "regime_adjustment": "Managed-float interaction terms",
            "alert_threshold": "Validated historical utility policy",
            "uncertainty": "Block-bootstrap confidence intervals",
            "point_in_time": "Release-date visibility with vintage selection",
        },
        "provenance": [
            {
                "source_name": "Example Central Bank",
                "series": "Official reserves",
                "period": "2026-06",
                "release_date": "2026-08-12",
                "retrieval_date": "2026-08-26",
                "vintage": "2026-08-12",
                "status": "available",
                "source_url": "https://data.example.test/reserves?id=1&format=csv",
                "license": "Open data terms",
            }
        ],
        "limitations": [
            "Reserve observations are released with a six-week lag.",
            "The calibration sample contains only 27 crisis onsets.",
        ],
    }


class _DocumentAudit(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.tables = 0
        self.captions = 0
        self.svgs = 0
        self.svg_titles = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if attributes.get("id"):
            self.ids.append(str(attributes["id"]))
        if tag == "table":
            self.tables += 1
        elif tag == "caption":
            self.captions += 1
        elif tag == "svg":
            self.svgs += 1
        elif tag == "title" and self.svgs:
            self.svg_titles += 1


def test_render_is_complete_self_contained_and_deterministic() -> None:
    report = MappingProxyType(_research_report())
    first = render_html_report(report)
    second = render_html_report(report)

    assert first == second
    assert first.startswith("<!doctype html>")
    assert first.rstrip().endswith("</html>")
    assert "<link" not in first
    assert not re.search(r'<(?:script|img|iframe)[^>]+src=["\']https?://', first)
    assert "@page { size: A4 landscape; margin: 10mm; }" in first
    assert "print-color-adjust: exact" in first
    assert ".screen-only, .js-only, .report-nav, .skip-link { display: none !important; }" in first
    assert ".report-footer { break-before: auto;" in first
    assert ".report-footer { break-before: page;" not in first
    assert '<script type="application/json" id="fx-cpm-report-data">' in first


def test_required_report_sections_and_signature_device_are_present() -> None:
    html = render_html_report(_research_report())

    expected = (
        "Executive crisis overview",
        "Active warning center",
        "Multi-hazard horizon matrix",
        "Probability / estimate term structure",
        "FX market stress",
        "Structural vulnerability &amp; risk momentum",
        "Historical timeline",
        "Historical analogues",
        "Predictive Contributors",
        "Regional / contagion context",
        "Calibration &amp; backtest",
        "Data quality",
        "Methodology summary",
        "Source / provenance appendix",
        "Limitations",
    )
    for label in expected:
        assert label in html
    assert "Evidence spine" in html
    assert "probabilistic early-warning" in html
    assert "not causes of crisis" in html


def test_accessible_static_charts_tables_and_landmarks() -> None:
    html = render_html_report(_research_report())
    audit = _DocumentAudit()
    audit.feed(html)

    assert '<a class="skip-link" href="#main-content">' in html
    assert '<main id="main-content" tabindex="-1">' in html
    assert 'aria-label="Report sections"' in html
    assert 'role="img"' in html
    assert "<desc" in html
    assert audit.svgs >= 5
    assert audit.tables >= 7
    assert audit.captions == audit.tables
    assert len(audit.ids) == len(set(audit.ids))


def test_uncalibrated_output_never_claims_probability_and_caps_severity() -> None:
    report = {
        "analysis": {"mode": "RESEARCH / UNCALIBRATED"},
        "countries": ["Example"],
        "forecasts": [
            {
                "country": "Example",
                "hazard": "currency_crisis",
                "horizon": "12m",
                "raw_probability": 0.41,
                "severity": "CRITICAL",
                "confidence": "LOW",
            }
        ],
        "alerts": [
            {
                "active": True,
                "country": "Example",
                "hazard": "currency_crisis",
                "horizon": "12m",
                "raw_probability": 0.41,
                "severity": "CRITICAL",
            }
        ],
    }
    html = render_html_report(report)

    assert "Uncalibrated risk estimate" in html
    assert "Watch — uncalibrated" in html
    assert "Requested CRITICAL; display capped" in html
    assert "Validated probability" not in html
    assert 'class="warning-card" data-risk="critical"' not in html


def test_report_strings_urls_and_embedded_json_are_safely_escaped() -> None:
    report = {
        "countries": ['<img src=x onerror="alert(1)">'],
        "limitations": ["</script><script>window.pwned=true</script>"],
        "provenance": [
            {
                "source_name": "A&B",
                "series": 'quote"series',
                "source_url": "javascript:alert(1)",
            }
        ],
    }
    html = render_html_report(report)

    assert "<img src=x" not in html
    assert "<script>window.pwned" not in html
    assert "&lt;img src=x" in html
    assert "javascript:alert(1) (link disabled)" in html
    match = re.search(
        r'<script type="application/json" id="fx-cpm-report-data">(.*?)</script>',
        html,
        re.DOTALL,
    )
    assert match
    embedded = match.group(1)
    assert "</script>" not in embedded.lower()
    decoded = json.loads(embedded)
    assert decoded == report


def test_missing_sections_remain_explicit_and_never_become_zero() -> None:
    html = render_html_report({})

    assert "Not available" in html
    assert "insufficient evidence" in html.lower()
    assert "Missing indicators are not treated as zero" in html
    assert "No explicit limitations were supplied" in html
    assert "0.0%" not in html


def test_render_rejects_non_mapping_payloads() -> None:
    try:
        render_html_report([])  # type: ignore[arg-type]
    except TypeError as error:
        assert str(error) == "report must be a mapping"
    else:
        raise AssertionError("render_html_report accepted a non-mapping payload")


def test_canonical_hazard_codes_map_to_exactly_eight_fixed_matrix_rows() -> None:
    codes = ("FX", "BANK", "SOV", "MON", "POL", "COUP", "CIV", "WAR")
    report = {
        "analysis": {"mode": "RESEARCH / UNCALIBRATED"},
        "forecasts": [
            {"hazard": code, "horizon": "12m", "raw_probability": 0.1 + index / 100}
            for index, code in enumerate(codes)
        ],
    }
    html = render_html_report(report)
    matrix = html.split('id="hazard-matrix"', 1)[1].split("</section>", 1)[0]

    assert matrix.count("<tbody>") == 1
    assert matrix.split("<tbody>", 1)[1].count("<tr>") == 8
    for label in (
        "Currency / balance-of-payments crisis",
        "Systemic banking crisis",
        "Sovereign distress / default crisis",
        "Monetary / inflation crisis",
        "Major political-instability crisis",
        "Coup / unconstitutional government-change risk",
        "Internal armed-conflict onset / escalation",
        "Interstate armed-conflict onset / escalation",
    ):
        assert matrix.count(label) == 1


def test_domain_not_assessed_and_evidence_alerts_are_audited_without_ood_claim() -> None:
    report = {
        "analysis": {"mode": "RESEARCH / UNCALIBRATED"},
        "alerts": [
            {
                "active": True,
                "country": "Example",
                "hazard": "FX",
                "horizon": "12m",
                "raw_estimate": 0.21,
                "severity": "WATCH_UNCALIBRATED",
                "ood_status": "NOT_ASSESSED",
                "evidence_alerts": ["CALIBRATION_WEAK"],
            }
        ],
    }
    html = render_html_report(report)

    assert "Domain not assessed" in html
    assert "CALIBRATION_WEAK" in html
    assert "Model out of domain" not in html
    assert 'class="warning-card" data-risk="out-of-domain"' not in html

    report["alerts"][0]["ood_status"] = "MODEL_OUT_OF_DOMAIN"  # type: ignore[index]
    out_of_domain_html = render_html_report(report)
    assert "Model out of domain" in out_of_domain_html
    assert 'class="warning-card" data-risk="out-of-domain"' in out_of_domain_html


def test_dense_screen_pacing_and_all_section_links_are_visible_in_wrapped_index() -> None:
    html = render_html_report(_research_report())
    navigation = html.split('<nav class="report-nav', 1)[1].split("</nav>", 1)[0]

    assert navigation.count("<li>") == 15
    assert 'href="#calibration"' in navigation
    assert 'href="#data-quality"' in navigation
    assert 'href="#sources"' in navigation
    assert 'href="#limitations"' in navigation
    assert "grid-template-columns: repeat(8, minmax(0, 1fr));" in html
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in html
    assert "white-space: normal;" in html
    assert "overflow-wrap: anywhere;" in html
    assert "padding: clamp(2.35rem, 4vw, 4.15rem) 0;" in html


def test_uncalibrated_no_alert_language_does_not_imply_safety_and_percentile_is_polished() -> None:
    report = {
        "analysis": {"mode": "RESEARCH / UNCALIBRATED"},
        "alerts": [
            {
                "active": True,
                "hazard": "CIV",
                "horizon": "12m",
                "raw_estimate": 0.014,
                "historical_percentile": 0.821,
                "severity": "NO_ALERT",
            }
        ],
    }
    html = render_html_report(report)

    assert "No operational alert — uncalibrated" in html
    assert "82.1 percentile" in html
    assert "82.1th" not in html


def test_embedded_timeline_onsets_use_deterministic_hazard_markers_and_legend() -> None:
    rows = [
        {"date": "2020-01", "estimate": 0.1, "hazard": "FX", "event_onset": True},
        {"date": "2020-02", "estimate": 0.2, "hazard": "BANK", "event_onset": True},
        {"date": "2020-03", "estimate": 0.3, "hazard": "SOV", "event_onset": True},
        {"date": "2020-04", "estimate": 0.4, "hazard": "POL", "event_onset": True},
        {"date": "2020-05", "estimate": 0.5, "hazard": "CIV", "event_onset": True},
    ]
    html = render_html_report({"historical_timeline": rows})

    for family in ("currency", "banking", "sovereign", "political", "conflict"):
        assert f'event-onset--{family}' in html
        assert f'event-marker--{family}' in html
    for label in ("Currency onset", "Banking onset", "Sovereign onset", "Political onset", "Conflict onset"):
        assert label in html
    assert "Documented event markers: currency 2020-01; banking 2020-02" in html
    assert html.count("Event onset embedded in the historical timeline") == 5
