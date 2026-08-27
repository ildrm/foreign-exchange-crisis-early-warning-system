# FX-CPM Alert Policy

Alert-policy version: 0.1.0  
Status: research defaults; no operational thresholds are bundled

## Purpose

Alerts summarize a validated hazard/horizon forecast under explicit evidence and model-quality gates. They do not assert that an event will occur, and they do not replace the underlying estimate, base rate, uncertainty, or evidence record.

The bundled example has no historically validated threshold artifact. Its maximum risk label is therefore `WATCH_UNCALIBRATED`, even when an uncalibrated estimate is numerically large.

## Two independent alert channels

Risk severity:

1. `NO_ALERT`
2. `WATCH`
3. `ELEVATED`
4. `HIGH`
5. `CRITICAL`
6. `WATCH_UNCALIBRATED` (research-only ceiling when probability/threshold validation is absent)

Evidence/model warnings:

- `INSUFFICIENT_EVIDENCE`
- `LOW_DATA_QUALITY`
- `STALE_DATA`
- `SOURCE_DISAGREEMENT`
- `MODEL_OUT_OF_DOMAIN`
- `CALIBRATION_WEAK`
- `MODEL_DRIFT`
- `REGIME_CHANGE`
- `DATA_PIPELINE_FAILURE`

These channels are displayed together but never collapsed. A high estimate with weak evidence remains visible as a high numerical estimate plus a quality warning; missing data do not make the estimate appear safe.

## Threshold artifacts

Thresholds are keyed by hazard, horizon, model tier, and policy version. A valid artifact records:

- four ordered entry thresholds and four lower exit thresholds;
- validation dates, countries, event clusters, and point-in-time status;
- historical base rate and number of events;
- probability calibration version and diagnostics;
- false-negative, false-positive, delay, and alert-burden costs;
- achieved recall, precision, false-alert rate, and median lead time;
- minimum evidence coverage/quality;
- artifact creator, timestamp, code version, and digest.

Threshold selection minimizes the predeclared validation loss described in `METHODOLOGY.md`. It is performed after model fitting and before the final test period. The final test set is used to report policy performance, never to tune thresholds. Thresholds are not transferred between hazards or horizons merely for visual consistency.

## Mandatory gates

`ELEVATED`, `HIGH`, and `CRITICAL` require all of the following:

1. the calibrated estimate crosses the relevant entry threshold;
2. calibration status is acceptable for that hazard/horizon;
3. evidence coverage and quality meet artifact minima;
4. the case is in domain or within an explicitly permitted boundary band;
5. the target is meaningful for the country and current currency regime;
6. no failed or stale single source is solely responsible for the crossing;
7. training, calibration, and alert-policy versions match;
8. the forecast is out of sample under the recorded deployment design.

Additional rules:

- `CRITICAL` requires a calibrated, validated probability and the strongest evidence gate. It is impossible for an uncalibrated artifact.
- When a validated threshold is missing, the ceiling is `WATCH_UNCALIBRATED`.
- When evidence is below the hard minimum, the risk value remains visible but the operational risk severity becomes `NO_ALERT` or `WATCH_UNCALIBRATED` and `INSUFFICIENT_EVIDENCE` is emitted.
- `MODEL_OUT_OF_DOMAIN` prevents `HIGH` and `CRITICAL`; the numerical output is retained with a caution.
- `CALIBRATION_WEAK` prevents `CRITICAL` and may prevent `HIGH` according to the artifact.
- A recent regime transition emits `REGIME_CHANGE` until the model's declared stabilization rule is satisfied.

## Hysteresis and persistence

Entry and exit thresholds differ: `exit < enter`. Escalation occurs on a qualifying current observation. De-escalation requires both the lower exit threshold and the artifact's persistence count, preventing alert flicker. A data outage cannot by itself de-escalate a risk alert; it freezes the last valid severity and adds a data-quality warning until the maximum stale interval is reached, after which the displayed state becomes insufficient evidence.

Each alert record retains:

- first observed date;
- last severity-change date;
- consecutive qualifying observations;
- current and peak estimate;
- entry/exit threshold used;
- threshold methodology and version;
- 7-, 30-, and 90-day estimate changes where supported;
- log-odds change for valid probabilities.

`RAPID_DETERIORATION` is a separate marker based on a validation-sample acceleration percentile. It does not override absolute probability, calibration, or evidence gates.

## Escalation and de-escalation language

### WATCH

> Conditions have moved into an historically elevated range, but current evidence does not support a stronger warning.

### ELEVATED

> The estimated probability is meaningfully above the validated historical baseline for this hazard and horizon.

### HIGH

> Multiple validated indicators and the calibrated forecasting model indicate substantially elevated risk within the specified horizon.

### CRITICAL

> The estimated probability has crossed the model's highest historically validated alert threshold with adequate calibration and evidence coverage. This remains a probabilistic warning and does not imply the event is certain or imminent.

### WATCH_UNCALIBRATED

> The research estimate is elevated, but operational probability thresholds have not been historically validated. No severe alert is issued.

### INSUFFICIENT_EVIDENCE

> Available observations do not meet the minimum evidence requirements for a reliable directional assessment.

### MODEL_OUT_OF_DOMAIN

> Current conditions differ materially from the historical observations used to train or calibrate this model. The numerical forecast should be interpreted cautiously.

## Display contract

Every active alert shows hazard, horizon, explicit severity text and symbol, estimate/probability label, base rate, relative risk, historical percentile, momentum, evidence confidence, coverage, calibration, out-of-domain status, regime, threshold, method, predictive contributors, contrary evidence, caveats, first seen, and last changed. Color is redundant encoding only.

Relative risk is omitted rather than reported as infinity when the relevant base rate is zero or unsupported. A lower-confidence estimate is never rounded to false precision.

## Governance

Any change to thresholds, costs, gates, persistence, or standard wording increments `alert_policy_version`. Retrospective comparisons must preserve the policy used at the time. Operational adoption additionally requires documented ownership, monitoring cadence, incident/data-outage handling, and a human review process; those organizational controls are outside this research release.

