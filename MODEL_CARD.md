# FX-CPM Model Card

Model version: 0.1.0-research  
Methodology version: 0.1.0  
Taxonomy version: 0.1.0  
Last updated: 2026-08-27

## Summary

FX-CPM is a regime-aware research framework for estimating separate, horizon-specific risks of currency, systemic banking, sovereign, monetary/inflation, major political-instability, coup, internal armed-conflict, and interstate armed-conflict onset. It is designed to test whether foreign-exchange information adds out-of-sample predictive value beyond macro-financial and political information.

The 0.1.0 repository is a working scientific foundation and deterministic demonstration, not a released operational forecasting model. Bundled scores are labelled `UNCALIBRATED_RISK_ESTIMATE`; operational severe alerts are disabled. No current-country numerical output from the synthetic example should be used for decision-making.

> FX-CPM estimates probabilities from historical statistical relationships. It does not observe private intentions, classified information, future policy decisions or unforeseeable shocks.

## Intended uses

- reproducible methodological research and teaching;
- construction and audit of point-in-time macro-financial panels;
- historical crisis-label reconciliation;
- chronological model tournaments and calibration experiments;
- measurement of incremental FX information;
- generation of research dashboards with explicit uncertainty, coverage, and provenance;
- comparison of performance by country, regime, event cluster, era, and model tier.

## Non-intended uses

- deterministic prediction of crises, war, coups, or government intent;
- autonomous trading, lending, sanctions, military, migration/asylum, insurance, or public-safety decisions;
- inference about individuals or protected groups;
- replacing expert country analysis or authoritative event reporting;
- presenting revised-history results as real-time performance;
- publishing a numerical score as a probability without held-out calibration evidence;
- combining hazard estimates into `P(any crisis)` under an untested independence assumption.

## Supported targets and horizons

The software contracts represent all eight hazards. Initial candidate horizons are:

| Hazard | Candidate horizons | 0.1.0 validated probability? |
|---|---|---|
| Currency / balance-of-payments | 90d, 180d, 12m, 24m | No |
| Systemic banking | 12m, 24m, 36m | No |
| Sovereign distress/default | 180d, 12m, 24m | No |
| Monetary/inflation | 90d, 180d, 12m | No |
| Major political instability | 90d, 180d, 12m | No |
| Coup/unconstitutional change | 90d, 180d, 12m | No |
| Internal armed conflict | 90d, 180d, 12m | No |
| Interstate armed conflict | 90d, 180d, 12m | No |

Support becomes a model claim only after the event count and chronological evaluation are adequate for that hazard/horizon.

## Countries and periods

The architecture is country-extensible and distinguishes countries, currencies, regimes, anchors, and dated state/currency succession. Version 0.1.0 contains reference mappings and a synthetic reproducible example only; it does not claim validated support for any country.

The historical structural design targets approximately the 1920s to present where comparable data exist. The macro-financial tier is mostly post-1960/1970, and the modern market tier is generally post-1980/1990 depending on market. Earlier or lower-coverage observations select a lower tier rather than receiving invented modern features.

## Training data

No frozen empirical training dataset is distributed with 0.1.0. Candidate sources and license conditions are documented in `DATA_SOURCES.md`. A deployable artifact must record dataset digests, releases/vintages, label snapshot, training dates, countries, cluster exclusions, feature definitions, and license manifest. Synthetic demonstration rows are pipeline fixtures and are not training evidence.

## Model families

The tournament contract includes logistic and regularized logistic regression, discrete-time hazards, competing risks where appropriate, generalized additive models, gradient-boosted trees, a random-forest challenger, regime-interaction models, and calibrated ensembles. The reference code provides interpretable dependency-light baselines and evaluation primitives. A complex challenger is selected only if chronological held-out results justify it.

## Calibration

Calibration is horizon-specific and must use observations after model training but before final testing. The supported research process evaluates reliability, Brier score, log loss, intercept, slope, expected calibration error, event count, and score-domain support. Platt/logistic and monotone calibration are candidate methods. Calibration cannot be fitted or selected on final-test labels.

The 0.1.0 demonstration has status `NOT_FITTED`; its output must not be called a calibrated probability.

## Validation and current performance

Current empirical performance: **not established**. There are no release-quality Brier, log-loss, PR-AUC, false-alert, missed-event, or warning-lead-time claims in 0.1.0.

Before a future model is marked validated it must pass expanding chronological tests, country holdouts, crisis-cluster holdouts, regime holdouts, feature-era tests, calibration tests, and FX/no-FX ablation. Results must show event/base-rate counts and point-in-time status. Model selection and alert thresholds must precede the untouched final window.

## Known biases and limitations

- Crisis definitions and onset dates are contestable and historically revised.
- Data availability is systematically worse for poorer, closed, conflict-affected, sanctioned, and historical states; missingness is not random.
- Official exchange rates may conceal pressure under pegs, controls, or multiple-rate systems; parallel observations can be unsafe, sparse, or unrepresentative.
- Modern option, liquidity, CDS, and high-frequency series have short histories and restrictive licenses.
- Survivorship, boundary changes, currency unions, redenominations, and state succession can corrupt naive panels.
- Official macro data are revised and may have long or endogenous publication delays.
- Financial-market signals can reflect global risk, liquidity, sanctions, or positioning rather than country-specific fundamentals.
- Political and conflict labels reflect source definitions and measurement access; expert-coded variables carry uncertainty.
- Rare events create unstable calibration, subgroup performance, and threshold estimates.
- Closely related regional crises violate naive independence and can leak across folds.
- Structural breaks, novel policy tools, pandemics, wars, climate shocks, and regime transitions can put a case outside the training domain.
- Predictive contributors are associations, not identified causes.

## Geographic and regime limitations

Cross-country coefficients can overweight well-measured economies. Performance must be reported by region/development group without treating these categories as causal attributes. Fixed pegs, managed floats, currency boards, dollarization, monetary unions, capital controls, and parallel markets require different observable pressure channels. A model validated for liquid free floats is not presumed valid for a peg or currency union.

## Conflict-prediction and ethical interpretation

FX may enter political/conflict models only as one market-information channel alongside political, institutional, economic, regional, and conflict-history variables. Market movement cannot establish intent or preparations. Reports use restrained language such as “elevated model-estimated probability of armed-conflict onset,” never an allegation that a country intends to start a war.

False positives can stigmatize countries, amplify market stress, or be misused to justify harmful action; false negatives can create false reassurance. Therefore event estimates, evidence quality, model-domain warnings, base rates, uncertainty, and failure modes must remain visible together. Human review and independent evidence are required for consequential use.

## Monitoring

A future deployed model must monitor input distributions, missingness/freshness, calibration slope/intercept, reliability bins, alert burden, performance by tier/regime/geography, and source/parser health. Drift or a regime change creates a model-quality warning and can gate severity. Retraining or threshold changes increment the relevant version and preserve prior artifacts.

## Release gate

The word *probability* and operational `HIGH`/`CRITICAL` alerts are prohibited until labels are versioned, chronological separation is verified, held-out calibration is evaluated, Brier/log-loss and base rates are disclosed, thresholds are backtested, point-in-time limitations are documented, and this model card is updated with actual results.

