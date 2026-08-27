# FX-CPM

**Foreign Exchange–Informed Crisis Probability Model**

FX-CPM is a regime-aware, multi-hazard research system for point-in-time crisis early warning. It keeps currency, banking, sovereign, monetary, political-instability, coup, internal-conflict, and interstate-conflict hazards separate; evaluates whether FX information adds out-of-sample value; and couples every estimate with its horizon, base rate, calibration state, uncertainty, data coverage, model tier, and provenance.

> Forex is a potentially valuable crisis sensor, not a standalone oracle.

Version 0.1.0 is a working scientific foundation. The bundled example contains deliberately synthetic values and is always labelled **RESEARCH / UNCALIBRATED**. It is suitable for exercising the architecture, tests, JSON contract, and report—not for making claims about a real country.

## What works

- immutable observations with independent economic-period, release, retrieval, and vintage semantics;
- explicit missingness, imputation metadata, source authority/quality, and transformation lineage;
- versioned definitions for all eight crisis hazards and uncertain onset intervals;
- country/currency/regime histories covering pegs, floats, unions, dollarization, controls, parallel rates, and transitions;
- regime-aware FX mathematics: returns, volatility, drawdown, parallel premium, EMP, and residual FX surprise;
- interpretable dependency-light logistic, regularized-logistic, and discrete-time hazard baselines, plus a deterministic model-tournament surface;
- held-out calibration primitives and reliability/Brier/log-loss diagnostics;
- expanding chronological backtests, country/regime/event-cluster holdouts, rare-event metrics, warning lead time, and paired FX ablation;
- hazard/horizon-specific alert thresholds, calibration/evidence/OOD gates, momentum, and hysteresis;
- one canonical versioned JSON report and a professional self-contained responsive HTML view;
- optional A4-landscape Playwright PDF export with printed backgrounds;
- deterministic unit, point-in-time, backtest, integration, regression, and presentation tests.

No live dataset, API key, or licensed market feed is required to run the example.

## Install

Python 3.11 or newer is required.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

The runtime uses `jsonschema` so `--validate` always checks the published Draft 2020-12 contract. Development extras install `pytest`, `pytest-cov`, and `ruff`.

## Quick start

Print the fixed synthetic research summary:

```bash
python crisis_dashboard.py
```

Generate the reproducible canonical JSON and self-contained HTML example:

```bash
python crisis_dashboard.py \
  --countries tr \
  --as-of 2024-01-31 \
  --no-web \
  --event-database examples/normalized_events.json \
  --validate \
  --source-audit \
  --output output/json/example_report.json \
  --html output/html/example_report.html
```

The HTML opens directly from disk and makes calibration failure, evidence warnings, missing indicators, and synthetic status visible. JavaScript only progressively enhances navigation/sorting; the substantive report and inline SVG charts are server-rendered.

Other CLI examples:

```bash
python crisis_dashboard.py --countries tr,ar,br
python crisis_dashboard.py --hazards fx,banking,sovereign
python crisis_dashboard.py --countries tr --as-of 2024-01-31
python crisis_dashboard.py --backtest fx
python crisis_dashboard.py --input-json examples/example_report.json --validate
python crisis_dashboard.py --no-seed --input-json my_validated_report.json
python crisis_dashboard.py --market-json examples/normalized_market.json
python crisis_dashboard.py --event-database examples/normalized_events.json
python crisis_dashboard.py --html report.html --pdf report.pdf
```

`--market-json` and `--event-database` augment report sections only. They do not fit a model, create training labels, or turn the synthetic backtest into empirical research; production model input must flow through the point-in-time provider and suite interfaces.

`--backtest` runs an ordered synthetic algorithm smoke test unless an empirical pipeline is supplied; it explicitly reports `RESEARCH_ONLY` and never presents fixture metrics as model performance. `--no-seed` refuses to run without an input report, preventing accidental fabrication when users expect live data.

## PDF export

Install the optional browser dependency and Chromium once:

```bash
python -m pip install -e ".[pdf]"
python -m playwright install chromium
python scripts/export_pdf.py output/html/example_report.html output/pdf/example_report.pdf
```

The exporter uses A4 landscape, CSS page size, exact print colors, static chart content, and printed backgrounds.

## Normalized historical panel

`scripts/build_historical_panel.py` selects the eligible vintage for each series/period without look-ahead:

```bash
python scripts/build_historical_panel.py observations.csv \
  --as-of 2019-12-31 \
  --vintage-mode TRUE_VINTAGE \
  --output panel-2019.json
```

Input CSV columns are enforced by the script. `TRUE_VINTAGE` requires both release and retrieval by the cutoff; `RECONSTRUCTED_POINT_IN_TIME` permits later retrieval with known release timing; `REVISED_HISTORY_ONLY` admits revised history and is never described as a genuine real-time backtest.

Audit a generated report's provenance:

```bash
python scripts/source_audit.py output/json/example_report.json --strict
```

## Scientific contract

A number is called a probability only when the event target is versioned, predictions are out of sample, held-out calibration was evaluated, and the current score lies in a supported calibration domain. Otherwise it is an `UNCALIBRATED_RISK_ESTIMATE`, `RISK_INDEX`, or `INSUFFICIENT_EVIDENCE`.

Severe alerts require a validated, hazard- and horizon-specific threshold plus acceptable calibration, coverage, quality, regime applicability, and in-domain status. Without those artifacts the ceiling is `WATCH_UNCALIBRATED`. Missing data remain missing; evidence confidence is never substituted for event risk; predictive contributors are associations rather than causes.

See:

- [METHODOLOGY.md](METHODOLOGY.md) for formulas and model/evaluation logic;
- [CRISIS_TAXONOMY.md](CRISIS_TAXONOMY.md) for all eight event definitions;
- [ALERT_POLICY.md](ALERT_POLICY.md) for thresholds, evidence gates, and hysteresis;
- [BACKTESTING.md](BACKTESTING.md) for chronological and holdout protocols;
- [MODEL_CARD.md](MODEL_CARD.md) for intended use, non-use, bias, and current performance status;
- [DATA_SOURCES.md](DATA_SOURCES.md) for current access/license/revision review;
- [ARCHITECTURE.md](ARCHITECTURE.md) for dependency boundaries and extension rules.

## Repository layout

```text
fx_cpm/
├── domain/          # immutable science contracts and offline mathematics
├── application/     # point-in-time, model, calibration, backtest, alert, report services
├── sources/         # source boundaries and normalized adapters
├── countries/       # dated country/currency/regime reference records
├── infrastructure/  # replaceable HTTP/cache/parsing/JSON/date utilities
└── presentation/    # CLI, console, inline-SVG charts, self-contained HTML

schemas/report.schema.json
scripts/{build_historical_panel,source_audit,export_pdf,validate_project}.py
tests/{unit,point_in_time,backtests,integration,regression,presentation}/
examples/
output/{json,html,pdf}/
crisis_dashboard.py
```

Dependencies point inward. The domain package imports no HTTP, filesystem, CLI, HTML, or country-specific adapter. Presentation reads the same canonical report mapping emitted as JSON and does not calculate model features.

## Test and quality gates

```bash
ruff check .
pytest
python scripts/validate_project.py .
python crisis_dashboard.py --validate --source-audit
```

For coverage:

```bash
pytest --cov=fx_cpm --cov-report=term-missing
```

Release-quality calibrated claims additionally require frozen empirical labels/data, verified train/calibration/test separation, disclosed base rates and rare-event metrics, backtested alert thresholds, point-in-time limitations, and an updated model card. Version 0.1.0 intentionally does not claim those gates have passed.

## Adding real data or a model

1. Review the exact series license and revision behavior in `DATA_SOURCES.md`.
2. Convert provider output into immutable observations at the source boundary, retaining release/vintage/provenance.
3. Define feature mathematics and missing/regime policy in the domain layer.
4. Freeze a versioned event-label snapshot using `CRISIS_TAXONOMY.md`.
5. Run identical chronological folds with and without FX features.
6. Fit calibration and thresholds before the untouched final test window.
7. Publish predictions, metrics, base rates, failure modes, and artifact digests through the canonical schema.

Commercial market data and ambiguous-license datasets are intentionally not redistributed.

## License

Source code is available under the [MIT License](LICENSE). Data obtained through adapters retain their providers' licenses and terms; the software license does not grant rights to third-party data.
