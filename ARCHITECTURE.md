# FX-CPM Architecture

Version: 0.1.0  
Status: research foundation

FX-CPM separates scientific definitions from data access and presentation. The dependency rule is strict: dependencies point inward, and the domain layer is executable without a network, filesystem, HTML renderer, or country adapter.

```text
presentation / scripts
          |
      application
       /       \
sources     infrastructure
       \       /
          domain  <--- countries (reference data only)
```

## Package map

- `fx_cpm.domain` contains immutable records, event semantics, feature mathematics, regime-independent validation, calibration primitives, and alert policy types.
- `fx_cpm.countries` contains country, currency, and dated regime reference records. A country is never treated as synonymous with a currency.
- `fx_cpm.application` coordinates point-in-time reads, feature assembly, model fitting, calibration, chronological evaluation, alert gating, and canonical report construction.
- `fx_cpm.sources` defines source-facing adapters. Raw provider responses are converted into domain observations at this boundary; provider-specific fields cannot leak into model mathematics.
- `fx_cpm.infrastructure` supplies replaceable HTTP, cache, date, JSON, and parsing utilities. The core system works without these facilities.
- `fx_cpm.presentation` turns one canonical report mapping into JSON, console, and self-contained HTML views. Renderers do not calculate model features or alter scientific results.
- `schemas/report.schema.json` is the versioned machine-readable public contract.

## Direction of control

The command-line entry point builds a provider, applies an analysis-date cutoff, selects a model tier, produces estimates, applies calibration only when a fitted calibration artifact is valid, gates alerts, and constructs one report object. JSON is serialized directly from that object; HTML consumes the same object. This prevents a visually convenient renderer from changing a value or silently replacing missing data with zero.

```text
raw records
    -> source adapter
    -> immutable observations + provenance
    -> point-in-time snapshot
    -> feature definitions
    -> hazard model
    -> optional held-out calibration
    -> forecast record + uncertainty
    -> evidence/alert gates
    -> canonical report
    -> JSON / HTML / console / PDF
```

## Scientific boundaries

### Observation time

Four times are deliberately distinct:

1. `period_start` and `period_end`: when the measured phenomenon occurred;
2. `release_date`: when the value became public;
3. `vintage`: which revision was observed;
4. `retrieval_date`: when FX-CPM acquired that record.

The point-in-time service first rejects releases after the analysis date, then chooses the latest eligible vintage according to the requested policy. `retrieval_date` is an audit attribute, not a substitute for release time. Where historic vintages do not exist, the service labels the snapshot `RECONSTRUCTED_POINT_IN_TIME` or `REVISED_HISTORY_ONLY`; it does not claim a genuine real-time backtest.

### Missingness

An observation has both a value and an evidence status. `MISSING`, `NOT_APPLICABLE`, `SOURCE_FAILURE`, and `INSUFFICIENT_HISTORY` are not numeric values. Imputers must retain the original status, identify the method, and expose an uncertainty or missingness indicator to the model.

### Probability boundary

Raw model output is stored separately from calibrated output. Presentation code may use the word *probability* only when all of the following are true:

- a versioned target definition and historical label set exist;
- the estimate is genuinely out of sample;
- calibration was fitted before the final test window;
- calibration metrics and base rate are recorded;
- the current case is inside the supported calibration domain.

Otherwise the public label is `UNCALIBRATED_RISK_ESTIMATE`, `RISK_INDEX`, or `INSUFFICIENT_EVIDENCE`. The bundled demonstration is intentionally uncalibrated.

## Model tiers

- `HISTORICAL_STRUCTURAL` uses long-run, slow-moving, regime-aware variables and is designed for sparse historic panels.
- `MACRO_FINANCIAL` adds higher-frequency macro, credit, banking, and sovereign variables.
- `MODERN_MARKET_ENHANCED` adds daily FX, forwards/options where licensed, cross-asset prices, and modern liquidity measures.

Tier selection is explicit. A missing modern-market variable does not invalidate a historical row; it lowers coverage and selects an appropriate tier. Performance and confidence are reported per tier.

## Model artifacts

A deployable artifact should be content-addressed and contain:

- model and feature-definition versions;
- hazard, horizon, and tier;
- training interval and country/event-cluster exclusions;
- fitted coefficients or tree serialization;
- feature ordering, normalization, and missingness policy;
- label taxonomy version;
- calibration artifact and calibration interval;
- validation metrics, base rate, and threshold policy version;
- seed and software version.

The reference implementation keeps artifacts serializable with standard Python structures. Production storage can replace the JSON layer without changing domain types.

## Contagion boundary

Contagion is a directed, channel-specific graph. Own-country features, common/global factors, and neighbor/network pressure remain separate model inputs. An edge may represent trade, banking claims, a common anchor, geography, migration, or conflict exposure. The graph yields predictive associations; it does not establish transmission causality.

## Security and reliability

- Network access is opt-in; `--no-web` is a supported offline mode.
- Source URLs are provenance, never executable content.
- HTML escapes all data-derived text and embeds no remote resource.
- JSON writes are atomic where the operating system permits.
- Cached records include retrieval time, source identity, and a content digest.
- No credential is required by the bundled example. Future adapters must obtain secrets outside source control.

## Extension rules

To add a feature, define its mathematics and metadata in `domain/features.py`, add an adapter that produces required raw observations, and test point-in-time visibility and missingness. To add a model, implement the application model protocol and join the chronological tournament; do not change report semantics. To add a hazard, first version its taxonomy and label resolver, then add horizons, backtests, calibration, and a hazard-specific alert policy.

## Deliberate non-goals in 0.1.0

The foundation does not ship licensed market data, claim a validated operational forecasting model, infer private political intent, or combine hazard probabilities under an independence assumption. Those omissions are scientific safeguards, not hidden gaps.

