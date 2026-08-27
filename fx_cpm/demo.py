"""Deterministic synthetic report data for documentation and pipeline testing.

Nothing in this module is empirical evidence about a real country. The named
countries make regime/currency rendering realistic while every value and event
is explicitly synthetic.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any, Iterable

HAZARDS: dict[str, dict[str, Any]] = {
    "FX": {
        "label": "Currency / balance-of-payments crisis",
        "horizons": ("90d", "180d", "12m", "24m"),
        "base": {"90d": 0.018, "180d": 0.034, "12m": 0.067, "24m": 0.118},
    },
    "BANK": {
        "label": "Systemic banking crisis",
        "horizons": ("12m", "24m", "36m"),
        "base": {"12m": 0.031, "24m": 0.059, "36m": 0.084},
    },
    "SOV": {
        "label": "Sovereign distress / default",
        "horizons": ("180d", "12m", "24m"),
        "base": {"180d": 0.012, "12m": 0.026, "24m": 0.049},
    },
    "MON": {
        "label": "Monetary / inflation crisis",
        "horizons": ("90d", "180d", "12m"),
        "base": {"90d": 0.021, "180d": 0.038, "12m": 0.071},
    },
    "POL": {
        "label": "Major political-instability crisis",
        "horizons": ("90d", "180d", "12m"),
        "base": {"90d": 0.015, "180d": 0.028, "12m": 0.052},
    },
    "COUP": {
        "label": "Coup / unconstitutional change",
        "horizons": ("90d", "180d", "12m"),
        "base": {"90d": 0.002, "180d": 0.004, "12m": 0.008},
    },
    "CIV": {
        "label": "Internal armed-conflict onset",
        "horizons": ("90d", "180d", "12m"),
        "base": {"90d": 0.004, "180d": 0.008, "12m": 0.016},
    },
    "WAR": {
        "label": "Interstate armed-conflict onset",
        "horizons": ("90d", "180d", "12m"),
        "base": {"90d": 0.001, "180d": 0.002, "12m": 0.004},
    },
}

COUNTRIES: dict[str, dict[str, Any]] = {
    "tr": {
        "country_id": "TR",
        "name": "Türkiye",
        "currency_id": "TRY",
        "regime": "MANAGED_FLOAT",
        "anchor_currency_id": "USD",
        "capital_controls": False,
        "multiple_rates": False,
        "multipliers": {"FX": 3.6, "BANK": 2.0, "SOV": 2.5, "MON": 3.1, "POL": 1.5},
        "coverage": 0.82,
    },
    "ar": {
        "country_id": "AR",
        "name": "Argentina",
        "currency_id": "ARS",
        "regime": "MULTIPLE_RATES_MANAGED",
        "anchor_currency_id": "USD",
        "capital_controls": True,
        "multiple_rates": True,
        "multipliers": {"FX": 4.4, "BANK": 2.3, "SOV": 3.8, "MON": 4.2, "POL": 1.4},
        "coverage": 0.74,
    },
    "br": {
        "country_id": "BR",
        "name": "Brazil",
        "currency_id": "BRL",
        "regime": "FREE_FLOAT",
        "anchor_currency_id": None,
        "capital_controls": False,
        "multiple_rates": False,
        "multipliers": {"FX": 1.4, "BANK": 1.2, "SOV": 1.3, "MON": 1.1, "POL": 1.0},
        "coverage": 0.88,
    },
}

_CONTRIBUTORS: dict[str, tuple[tuple[str, float], ...]] = {
    "FX": (
        ("Exchange-market pressure", 0.72),
        ("Residual FX depreciation", 0.48),
        ("Reserve adequacy deterioration", 0.36),
        ("Export momentum", -0.18),
    ),
    "BANK": (
        ("Real credit growth", 0.41),
        ("Bank funding pressure", 0.27),
        ("Yield-curve signal", -0.12),
    ),
    "SOV": (
        ("Foreign-currency debt burden", 0.44),
        ("Sovereign spread", 0.35),
        ("Primary-balance direction", -0.15),
    ),
    "MON": (
        ("Inflation acceleration", 0.61),
        ("Broad-money growth", 0.29),
        ("Real policy rate", -0.11),
    ),
    "POL": (
        ("Government-stability indicator", 0.21),
        ("Regional stress", 0.14),
        ("Institutional continuity", -0.20),
    ),
    "COUP": (("Recent unconstitutional-change history", 0.08), ("Institutional continuity", -0.23)),
    "CIV": (("Neighbor conflict exposure", 0.12), ("Recent domestic conflict", -0.16)),
    "WAR": (("Regional interstate tension", 0.10), ("Peaceful dyad history", -0.25)),
}


def _round_probability(value: float) -> float:
    return round(max(0.0001, min(0.95, value)), 4)


def _country(code: str) -> dict[str, Any]:
    normalized = code.strip().lower()
    if normalized not in COUNTRIES:
        raise ValueError(
            f"no bundled synthetic profile for country {code!r}; choose from {', '.join(COUNTRIES)}"
        )
    return dict(COUNTRIES[normalized])


def _hazard(code: str) -> tuple[str, dict[str, Any]]:
    normalized = code.strip().upper()
    aliases = {
        "CURRENCY": "FX",
        "BANKING": "BANK",
        "SOVEREIGN": "SOV",
        "MONETARY": "MON",
        "POLITICAL": "POL",
        "INTERNAL": "CIV",
        "INTERSTATE": "WAR",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in HAZARDS:
        raise ValueError(f"unknown hazard {code!r}; choose from {', '.join(HAZARDS)}")
    return normalized, HAZARDS[normalized]


def build_demo_report(
    country_codes: Iterable[str] = ("tr",),
    hazard_codes: Iterable[str] = tuple(HAZARDS),
    analysis_date: date = date(2024, 1, 31),
) -> dict[str, Any]:
    """Return a deterministic, schema-shaped, explicitly synthetic report."""

    countries = [_country(code) for code in country_codes]
    if not countries:
        raise ValueError("at least one country is required")
    selected_hazards = [_hazard(code) for code in hazard_codes]
    if not selected_hazards:
        raise ValueError("at least one hazard is required")

    forecasts: list[dict[str, Any]] = []
    alerts: list[dict[str, Any]] = []
    for country in countries:
        multipliers = country.pop("multipliers")
        for hazard_code, hazard in selected_hazards:
            multiplier = multipliers.get(hazard_code, 0.85)
            for order, horizon in enumerate(hazard["horizons"]):
                base_rate = hazard["base"][horizon]
                estimate = _round_probability(base_rate * multiplier)
                confidence = round(country["coverage"] * (0.91 - order * 0.025), 3)
                contributors = [
                    {
                        "feature": name,
                        "contribution": value,
                        "direction": "INCREASES_ESTIMATE" if value >= 0 else "DECREASES_ESTIMATE",
                        "available": True,
                    }
                    for name, value in _CONTRIBUTORS[hazard_code]
                    if value >= 0
                ]
                contrary = [
                    {
                        "feature": name,
                        "contribution": value,
                        "direction": "DECREASES_ESTIMATE",
                        "available": True,
                    }
                    for name, value in _CONTRIBUTORS[hazard_code]
                    if value < 0
                ]
                forecast = {
                    "country": country["name"],
                    "country_id": country["country_id"],
                    "hazard": hazard_code,
                    "analysis_date": analysis_date.isoformat(),
                    "horizon": horizon,
                    "raw_probability": estimate,
                    "calibrated_probability": None,
                    "probability_status": "UNCALIBRATED",
                    "display_label": "UNCALIBRATED_RISK_ESTIMATE",
                    "base_rate": base_rate,
                    "relative_risk": round(estimate / base_rate, 2),
                    "historical_percentile": min(0.98, round(0.48 + multiplier * 0.11, 3)),
                    "confidence": confidence,
                    "coverage": country["coverage"],
                    "uncertainty_low": _round_probability(estimate * 0.72),
                    "uncertainty_high": _round_probability(estimate * 1.34),
                    "model_version": "0.1.0-demo",
                    "calibration_version": "none",
                    "regime": country["regime"],
                    "training_end_date": None,
                    "model_tier": "MACRO_FINANCIAL",
                    "ood_status": "NOT_ASSESSED",
                    "momentum": {
                        "7d": round(0.001 * (order + 1), 4),
                        "30d": round(0.006 * multiplier / 2, 4),
                        "90d": round(0.014 * multiplier / 2, 4),
                    },
                    "contributors": contributors,
                    "contrary_evidence": contrary,
                }
                forecasts.append(forecast)
                if order == min(2, len(hazard["horizons"]) - 1):
                    severity = "WATCH_UNCALIBRATED" if multiplier >= 1.5 else "NO_ALERT"
                    alerts.append(
                        {
                            "country": country["name"],
                            "hazard": hazard_code,
                            "horizon": horizon,
                            "severity": severity,
                            "evidence_alerts": ["CALIBRATION_WEAK"],
                            "raw_estimate": estimate,
                            "calibrated_probability": None,
                            "base_rate": base_rate,
                            "relative_risk": round(estimate / base_rate, 2),
                            "historical_percentile": forecast["historical_percentile"],
                            "probability_change": forecast["momentum"]["30d"],
                            "evidence_confidence": confidence,
                            "data_coverage": country["coverage"],
                            "calibration_status": "NOT_FITTED",
                            "ood_status": "NOT_ASSESSED",
                            "fx_regime": country["regime"],
                            "trigger_threshold": None,
                            "threshold_methodology": None,
                            "key_reason": contributors[0]["feature"] if contributors else "No supported contributor",
                            "caveat": "Synthetic fixture; no empirical calibration or validated threshold.",
                            "first_seen": analysis_date.isoformat(),
                            "last_changed": analysis_date.isoformat(),
                        }
                    )

    leading = max(forecasts, key=lambda item: float(item["raw_probability"] or 0))
    generated_at = datetime.combine(analysis_date, time(12), tzinfo=timezone.utc)
    hazard_rows = [
        {
            "hazard_type": code,
            "label": definition["label"],
            "definition_version": "0.1.0",
            "supported_horizons": list(definition["horizons"]),
        }
        for code, definition in selected_hazards
    ]
    country_names = ", ".join(item["name"] for item in countries)

    return {
        "schema_version": "1.0.0",
        "model_version": "0.1.0-demo",
        "methodology_version": "0.1.0",
        "calibration_version": "none",
        "alert_policy_version": "0.1.0",
        "analysis": {
            "analysis_date": analysis_date.isoformat(),
            "generated_at": generated_at.isoformat().replace("+00:00", "Z"),
            "report_mode": "RESEARCH_UNCALIBRATED",
            "point_in_time_status": "RECONSTRUCTED_POINT_IN_TIME",
            "history_start": "2000-01-01",
            "web_accessed": False,
            "seed_used": True,
            "countries_label": country_names,
            "executive_summary": (
                f"In this synthetic pipeline demonstration, {leading['hazard']} at "
                f"{leading['horizon']} has the largest uncalibrated risk estimate "
                f"({leading['raw_probability']:.1%}). The historical comparison, changes, and "
                "contributors are fabricated fixtures used only to exercise report semantics."
            ),
            "major_limitation": (
                "No empirical training, held-out calibration, or validated alert threshold is "
                "attached; no value in this report is a current-country forecast."
            ),
        },
        "countries": countries,
        "hazards": hazard_rows,
        "forecasts": forecasts,
        "alerts": alerts,
        "fx_stress": {
            "status": "SYNTHETIC_FIXTURE",
            "country": countries[0]["name"],
            "regime": countries[0]["regime"],
            "percentile": 0.91,
            "measures": [
                {"name": "Spot depreciation (30d)", "value": 0.061, "unit": "%", "status": "AVAILABLE"},
                {"name": "Residual FX surprise", "value": 1.84, "unit": "z", "status": "AVAILABLE"},
                {"name": "Exchange-market pressure", "value": 2.16, "unit": "z", "status": "AVAILABLE"},
                {"name": "Reserve pressure", "value": -0.74, "unit": "z", "status": "AVAILABLE"},
                {"name": "Parallel-market premium", "value": None, "unit": "%", "status": "NOT_APPLICABLE"},
                {"name": "Option risk reversal", "value": None, "unit": "vol pts", "status": "MISSING"},
            ],
            "decomposition": [
                {"label": "Raw FX", "value": 0.62},
                {"label": "Reserve defense", "value": 0.38},
                {"label": "Rate defense", "value": 0.17},
                {"label": "Global factor", "value": -0.24},
                {"label": "Residual/local", "value": 0.53},
            ],
        },
        "macro_vulnerability": {
            "status": "SYNTHETIC_FIXTURE",
            "dimensions": [
                {"name": "External balance", "score": 0.68, "direction": "DETERIORATING"},
                {"name": "Reserve adequacy", "score": 0.73, "direction": "DETERIORATING"},
                {"name": "Credit cycle", "score": 0.49, "direction": "STABLE"},
                {"name": "Sovereign balance sheet", "score": 0.58, "direction": "DETERIORATING"},
                {"name": "Inflation pressure", "score": 0.77, "direction": "DETERIORATING"},
                {"name": "Political structure", "score": 0.41, "direction": "STABLE"},
            ],
        },
        "contagion": {
            "status": "SYNTHETIC_FIXTURE",
            "own_country_pressure": 0.69,
            "common_factor_pressure": 0.37,
            "network_pressure": 0.31,
            "peers": [
                {"country": "Synthetic peer A", "risk_index": 0.44, "channel": "trade"},
                {"country": "Synthetic peer B", "risk_index": 0.36, "channel": "common anchor"},
                {"country": "Synthetic peer C", "risk_index": 0.28, "channel": "banking claims"},
            ],
            "interpretation": "Network pressure is an association and is not evidence of direct contagion causation.",
        },
        "historical_analogues": [
            {
                "country": "Synthetic analogue A",
                "date": "2008-09-30",
                "similarity": 0.84,
                "outcome": "No qualifying onset within 12 months",
                "event_type": None,
                "time_to_event_days": None,
                "regime": "MANAGED_FLOAT",
                "coverage": 0.78,
            },
            {
                "country": "Synthetic analogue B",
                "date": "2013-06-30",
                "similarity": 0.79,
                "outcome": "Synthetic FX onset after 214 days",
                "event_type": "FX",
                "time_to_event_days": 214,
                "regime": "MANAGED_FLOAT",
                "coverage": 0.81,
            },
            {
                "country": "Synthetic analogue C",
                "date": "2018-08-31",
                "similarity": 0.74,
                "outcome": "Synthetic monetary onset after 301 days",
                "event_type": "MON",
                "time_to_event_days": 301,
                "regime": "CRAWLING_PEG",
                "coverage": 0.69,
            },
        ],
        "historical_timeline": [
            {"date": "2023-02-28", "hazard": "FX", "estimate": 0.12, "vintage_status": "RECONSTRUCTED"},
            {"date": "2023-05-31", "hazard": "FX", "estimate": 0.15, "vintage_status": "RECONSTRUCTED"},
            {"date": "2023-08-31", "hazard": "FX", "estimate": 0.18, "vintage_status": "RECONSTRUCTED"},
            {"date": "2023-11-30", "hazard": "FX", "estimate": 0.21, "vintage_status": "RECONSTRUCTED"},
            {"date": analysis_date.isoformat(), "hazard": "FX", "estimate": 0.241, "vintage_status": "RECONSTRUCTED"},
        ],
        "validation": {
            "status": "NOT_RUN",
            "chronological_split": False,
            "final_test_untouched": True,
            "metrics": {"average_precision": None, "brier_score": None, "log_loss": None},
            "fx_ablation": {"delta_average_precision": None, "delta_brier": None, "delta_log_loss": None},
            "test_window": None,
            "event_count": 0,
            "message": "Synthetic fixture: no empirical backtest has been run.",
        },
        "calibration": {
            "status": "NOT_FITTED",
            "method": None,
            "calibration_period": None,
            "event_count": 0,
            "brier_score": None,
            "log_loss": None,
            "slope": None,
            "intercept": None,
            "bins": [],
            "message": "Numerical outputs are uncalibrated research estimates, not probabilities.",
        },
        "data_quality": {
            "coverage": countries[0]["coverage"],
            "freshness": 0.79,
            "source_authority": 0.86,
            "source_disagreement": 0.18,
            "historical_depth": 0.66,
            "vintage_quality": 0.45,
            "overall": 0.69,
            "warnings": [
                "Synthetic records do not represent real source coverage.",
                "Historical values are labelled reconstructed, not true vintage.",
                "Modern option-market evidence is missing.",
            ],
        },
        "source_health": {
            "status": "DEMONSTRATION_ONLY",
            "healthy": 5,
            "stale": 1,
            "failed": 0,
            "items": [
                {"source": "Synthetic macro fixture", "status": "AVAILABLE"},
                {"source": "Synthetic market fixture", "status": "STALE"},
            ],
        },
        "limitations": [
            "Every numerical value and historical event in this example is synthetic.",
            "No empirical event labels, training, final test, calibration, or alert-threshold validation were used.",
            "Reconstructed point-in-time status is not a genuine real-time backtest.",
            "Parallel-rate and option evidence are unavailable or not applicable in the fixture.",
            "Hazards are dependent; no overall any-crisis probability is calculated.",
            "Predictive contributors are associations and are not causal findings.",
        ],
        "provenance": [
            {
                "feature_id": "demo.emp",
                "country_id": countries[0]["country_id"],
                "currency_id": countries[0]["currency_id"],
                "value": 2.16,
                "unit": "z",
                "frequency": "MONTHLY",
                "period_start": analysis_date.replace(day=1).isoformat(),
                "period_end": analysis_date.isoformat(),
                "release_date": analysis_date.isoformat(),
                "retrieval_date": analysis_date.isoformat(),
                "vintage": "synthetic-v1",
                "source_name": "FX-CPM synthetic fixture",
                "source_url": "https://example.invalid/fx-cpm/synthetic-fixture",
                "source_type": "SYNTHETIC",
                "provider": "FX-CPM",
                "source_authority": 0.0,
                "source_quality": 1.0,
                "license": "CC0-1.0 synthetic fixture",
                "revision_status": "FIXED",
                "provenance_type": "SYNTHETIC",
                "transformation_lineage": ["synthetic_spot", "synthetic_reserves", "emp_formula_v0.1.0"],
                "status": "AVAILABLE",
            },
            {
                "feature_id": "demo.option_risk_reversal",
                "country_id": countries[0]["country_id"],
                "currency_id": countries[0]["currency_id"],
                "value": None,
                "unit": "volatility points",
                "frequency": "DAILY",
                "period_start": analysis_date.isoformat(),
                "period_end": analysis_date.isoformat(),
                "release_date": analysis_date.isoformat(),
                "retrieval_date": analysis_date.isoformat(),
                "vintage": "synthetic-v1",
                "source_name": "FX-CPM synthetic fixture",
                "source_url": "https://example.invalid/fx-cpm/synthetic-fixture",
                "source_type": "SYNTHETIC",
                "provider": "FX-CPM",
                "source_authority": 0.0,
                "source_quality": 1.0,
                "license": "CC0-1.0 synthetic fixture",
                "revision_status": "FIXED",
                "provenance_type": "SYNTHETIC",
                "transformation_lineage": [],
                "status": "MISSING",
            },
        ],
    }


__all__ = ["COUNTRIES", "HAZARDS", "build_demo_report"]

