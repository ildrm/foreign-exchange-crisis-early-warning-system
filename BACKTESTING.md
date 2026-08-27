# FX-CPM Backtesting Protocol

Protocol version: 0.1.0  
Status: mandatory evaluation contract

## Objective

Backtesting estimates how a complete historical decision process would have behaved—not how well a model can fit revised history. Feature construction, imputation, scaling, feature selection, model fitting, calibration, ensembling, and alert-threshold selection all occur inside chronological folds.

## Forecast row and risk set

The row is country × forecast-origin × hazard × horizon. It is eligible only when:

- the country/target is applicable under the current regime;
- the country is not inside an ongoing episode or declared post-event exclusion period;
- the minimum structural inputs for the chosen tier exist;
- every included observation was public by the origin date under the recorded point-in-time policy.

The label is 1 when a qualified onset occurs in `(origin, origin + horizon]`. Onset-bound sensitivity is run for labels with uncertain dates. Overlapping horizons create correlated rows, so confidence procedures resample countries/event clusters or time blocks rather than assuming iid observations.

## Time split

Random train/test splitting is forbidden. A typical long-run expanding design is adapted to actual feature availability:

| Fold | Train | Calibration/threshold validation | Test |
|---|---|---|---|
| A | through 1969 | 1970–1979 | 1980–1989 |
| B | through 1989 | 1990–1999 | 2000–2007 |
| C | through 2007 | 2008–2012 | 2013–2019 |
| D | through 2019 | 2020–2022 | 2023–latest complete label window |

Dates move when the hazard or tier starts later. A test origin is included only when the full outcome horizon has elapsed and label collection is complete. The current partial year is not silently coded negative.

The workflow in each fold is:

1. freeze source/label snapshots and risk set;
2. fit preprocessing on train only;
3. fit all tournament models on train only;
4. produce untouched validation predictions;
5. select model/ensemble, calibration, and alert thresholds using validation only;
6. freeze artifacts;
7. predict test once;
8. report all prespecified metrics, including failures.

The final test window remains untouched until the research design is frozen. Repeatedly inspecting and tuning against it converts it into validation and requires a later test window.

## Point-in-time grades

Results are always stratified or labelled:

- `TRUE_VINTAGE`: historic releases and revisions are represented;
- `RECONSTRUCTED_POINT_IN_TIME`: release timing is reconstructed conservatively, but some values may be revised;
- `REVISED_HISTORY_ONLY`: current revised series are used;
- `MIXED`: components have different grades, with shares disclosed.

Only true-vintage results are called genuine real-time backtests. Revised-history tests remain useful research sensitivity checks.

## Leakage controls

- Rolling/z-score features use only data at or before each origin.
- Global/regional factors are estimated within the training window.
- Country peers and network edges are dated and lagged.
- Imputation values and missingness policies are fitted on train only.
- Label database publication after an origin is permitted for outcome evaluation, but not as an input feature.
- Observations revised after the origin are ineligible under true-vintage evaluation.
- Calibration and thresholds cannot see final-test labels.
- Rows from a single unfolding crisis cluster stay together in cluster tests.
- Hyperparameter/model selection occurs on validation, never test.

## Required holdouts

### Country holdout

Selected countries are removed from model fitting, preprocessing, and calibration. The test evaluates geographic transfer. Holdout groups should include different regions, income/development contexts, data qualities, and FX regimes. Results disclose when a held-out country lies outside training support.

### Crisis-cluster holdout

An entire connected episode—such as a regional currency crisis, global banking episode, sovereign-bank feedback cluster, or war—is removed from fitting and calibration. Cluster membership is declared before evaluation. This test prevents training on one member of an unfolding event and calling another an independent success.

### Regime holdout

Performance is reported for fixed/board, managed, floating, currency-union/dollarized, capital-control, and multiple-rate contexts. Where event counts allow, one regime class is held out entirely. Low counts produce `INSUFFICIENT_EVENTS`, not a precise metric.

### Feature-era/tier test

`HISTORICAL_STRUCTURAL`, `MACRO_FINANCIAL`, and `MODERN_MARKET_ENHANCED` results are evaluated independently. The modern tier is also compared over the same dates/countries as the structural tier so performance gain is not confused with an easier era/sample.

## FX ablation

Within identical folds and risk sets:

- `M0` uses all approved non-FX inputs;
- `M1` adds the declared FX feature family;
- optional sub-ablations add raw FX, EMP/defense, residual FX, derivatives, and liquidity in blocks.

Report paired differences for average precision, Brier, log loss, recall, false alerts, missed events, warning lead time, and calibration. For loss metrics, a negative `M1-M0` is better. Fold-/cluster-bootstrap intervals are required for inference; no-value and negative-value results remain prominent.

## Metrics

Every table begins with observations, countries, onsets, and unconditional base rate. Primary metrics:

- average precision / PR-AUC using the documented interpolation convention;
- Brier score and skill relative to a training-base-rate forecast;
- log loss with a fixed numeric clipping rule;
- calibration intercept, slope, reliability bins, and expected calibration error;
- recall at prespecified false-positive rates;
- precision at prespecified operational alert rates;
- missed-crisis and false-alert rates;
- mean and median warning lead time among detected events;
- fraction of crisis episodes with at least one warning;
- alert-days/months per country and explicit decision utility.

ROC-AUC is secondary. Ordinary accuracy is not a selection metric for rare events.

An “alert” is counted at the episode level for detection and at the country-origin level for burden; both denominators are shown. Multiple alerts before the same event do not become multiple true crises.

## Calibration evaluation

Reliability bins are based on validation declarations and applied unchanged to test where possible. Bins report mean prediction, observed rate, row count, and event count. Calibration diagnostics are not reported for bins with unusably small counts without a warning. Current estimates outside the validation score range receive an out-of-domain flag.

## Warning lead time

For a detected event, lead time is the interval from the first persistent alert crossing within the evaluation window to canonical onset. Sensitivity uses `onset_min`/`onset_max`. Alerts earlier than the declared maximum useful window are not credited indefinitely. Lead time is reported with detection rate; a model that alerts constantly cannot claim excellent warning simply from long lead times.

## Uncertainty and comparison

Resampling uses country and crisis-cluster blocks; time-block bootstrap is a sensitivity check. Every interval states what it represents. Statistical intervals do not absorb label ambiguity, vintage limitations, or source failure; these are reported separately. Model comparisons are paired on the same eligible origins.

## Reproducibility manifest

Each run records:

- code/model/methodology/taxonomy/calibration/alert-policy versions;
- dataset and label snapshot digests;
- point-in-time grade and release-lag assumptions;
- countries, hazards, horizons, tiers, folds, and exclusions;
- feature definitions/order and preprocessing;
- random seed and runtime version;
- predictions for every eligible row;
- calibration/threshold artifacts;
- metrics, warnings, and failed checks.

A fixed manifest, dataset snapshot, seed, and analysis date must reproduce deterministic models byte-for-byte where practical and numerically within declared tolerance otherwise.

## Release gate

A result cannot support calibrated-probability language unless chronological separation passes automated tests, calibration is held out, base rates and rare-event metrics are present, point-in-time grade is visible, threshold performance is backtested, and the model card contains the corresponding results. When event counts are too small, the correct result is `INSUFFICIENT_EVENTS`.

