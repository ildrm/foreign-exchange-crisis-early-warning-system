# FX-CPM Methodology

Methodology version: 0.1.0  
Taxonomy dependency: 0.1.0  
Status: research foundation; bundled estimates are not validated operational probabilities

## 1. Estimand and information set

For country \(i\), analysis time \(t\), hazard \(k\), and horizon \(h\), the target is

\[
p_{i,t}^{(k,h)} = P\{T_i^{(k)} \in (t,t+h] \mid \mathcal F_t\}.
\]

The information set \(\mathcal F_t\) contains only observations whose release dates are on or before \(t\). The economic period, release date, vintage, and retrieval date are stored separately. A forecast record always identifies its hazard, horizon, training end, model tier, calibration version, base rate, coverage, and out-of-domain status.

FX-CPM estimates eight separate hazards: currency/balance-of-payments (`FX`), systemic banking (`BANK`), sovereign distress/default (`SOV`), monetary/inflation (`MON`), major political instability (`POL`), coup/unconstitutional change (`COUP`), internal armed conflict (`CIV`), and interstate armed conflict (`WAR`). It does not collapse them into one target.

## 2. Point-in-time panel

For an observation \(o\) to be visible at analysis date \(t\):

\[
visible(o,t) = 1[release\_date(o) \le t].
\]

If release time is unknown, the adapter must supply a documented conservative lag or mark the record unreliable. Among eligible revisions for the same feature/country/currency/period, the latest vintage actually available at \(t\) is selected. A current revised series without historic vintages is never silently treated as real-time data.

Backtests receive one of three labels:

- `TRUE_VINTAGE`: recorded historical releases/revisions are used;
- `RECONSTRUCTED_POINT_IN_TIME`: release lags are reconstructed but values may be revised;
- `REVISED_HISTORY_ONLY`: current revised history is used and the exercise is not described as real-time.

## 3. Feature definitions

All transformations are declared in domain feature definitions, never inside source adapters or renderers. Each definition includes inputs, formula, frequency, expected predictive association, rationale, hazards, valid regimes, historical availability, source requirements, missing policy, and limitations.

### 3.1 FX returns and stress

Rates are normalized as domestic currency units per unit of reference currency so a positive log return represents domestic depreciation:

\[
r_{i,t}=100[\log S_{i,t}-\log S_{i,t-1}].
\]

Over \(w\) observations:

\[
Dep_{i,t}^{(w)}=100[\log S_{i,t}-\log S_{i,t-w}],
\qquad
RV_{i,t}^{(w)}=\sqrt{a_w}\,sd(r_{i,t-w+1:t}),
\]

where \(a_w\) is an explicitly recorded annualization factor. Drawdown uses the log distance from the best exchange-rate level in the window after respecting quote direction. Downside volatility uses only depreciation-side innovations.

### 3.2 Exchange Market Pressure

For managed regimes, a stable official rate is not sufficient evidence of stability. The reference EMP is

\[
EMP_{i,t}=w_s Z_R(\Delta s_{i,t})-w_r Z_R(\Delta reserves_{i,t})
          +w_i Z_R(\Delta rateDifferential_{i,t}),
\]

where \(Z_R\) is a robust z-score estimated only from the training sample within a compatible regime and historical era. The default weights are inverse training-sample standard deviations normalized to sum to one; equal weights are a sensitivity challenger. Any missing component is reported and weights are renormalized only if the predeclared minimum-component rule is met.

For multiple-rate systems:

\[
ParallelPremium_{i,t}=100\left(S_{i,t}^{parallel}/S_{i,t}^{official}-1\right).
\]

Official and parallel quote definitions must share direction and unit before this calculation.

### 3.3 Abnormal FX movement

Local FX movement is separated from observable global pricing:

\[
r_{i,t}=\alpha_i+\beta_1 USD_t+\beta_2\Delta GlobalRates_t+
\beta_3 GlobalRisk_t+\beta_4 CommodityFactor_t+\beta_5 RegionalFX_t+\epsilon_{i,t}.
\]

Coefficients and residual scale are fitted within each training window. The surprise feature is

\[
FXSurprise_{i,t}=(r_{i,t}-\hat r_{i,t})/\hat\sigma_{i,t}.
\]

Raw depreciation and residual surprise remain separate features. The residual is a conditional market surprise, not proof of a domestic cause.

### 3.4 Structural features

Macro, credit, banking, sovereign, political, conflict, commodity, global, network, and regime families are stored separately. Stock/flow ratios use period-compatible denominators; growth rates record nominal/real and seasonal treatment; all rolling normalizers use past data only. A missing value remains missing. If a model supports imputation, it receives both the imputed value and a missingness indicator, with the method fitted on training data alone.

## 4. Regimes and historical comparability

A dated regime record maps `country_id` to `currency_id`, regime type, anchor, capital controls, and multiple-rate status over a closed-open interval `[effective_from, effective_to)`. Overlaps for a country are invalid. Currency succession, redenomination, unions, dollarization, and state succession are represented explicitly.

Standardization is conditional on compatible regimes and eras. A volatility observation under a free float is not ranked against a currency-board observation as if the policy mechanisms were identical. Regime interactions enter models either as indicators, interaction terms, or separately estimated challengers. Results are stratified into fixed, managed, floating, currency-union/dollarized, and multiple-rate environments.

## 5. Labels and horizons

Labels follow `CRISIS_TAXONOMY.md`. Onset may be an interval \([d_{min},d_{max}]\) with a canonical date, not a falsely exact point. For a forecast origin \(t\), a binary horizon label is 1 only when an eligible onset falls in \((t,t+h]\). Observations inside an ongoing event or a hazard-specific post-onset exclusion window are not treated as ordinary negative controls. Sensitivity tests repeat evaluation using onset bounds where ambiguity is material.

Supported horizons are hazard-specific selections from 30, 90, and 180 days and 12, 24, and 36 months. Cumulative horizon estimates should be nondecreasing; when independently fitted estimates cross, the report exposes the inconsistency or applies a validation-only monotonic projection that is identified in the artifact.

## 6. Model tournament

Every supported hazard/horizon begins with interpretable baselines:

\[
P(Y_{i,t}^{k,h}=1)=\sigma(\alpha_{k,h}+X_{i,t}'\beta_{k,h}),
\quad \sigma(z)=1/(1+e^{-z}).
\]

The tournament includes ordinary and regularized logistic regression, discrete-time hazard models, a competing-risk model when event definitions and sample size support it, generalized additive models, gradient-boosted trees, a random-forest challenger, regime interactions, and a calibrated stack. A challenger is admitted only after chronological out-of-sample improvement without unacceptable calibration or subgroup deterioration.

For discrete time, the conditional onset hazard is

\[
q_{i,t}^{k}=P(T_i^k=t\mid T_i^k\ge t, X_{i,t}),
\]

and cumulative risk over \(h\) periods is

\[
P(T_i^k\le t+h\mid T_i^k>t)=1-\prod_{u=1}^{h}(1-q_{i,t+u}^{k}).
\]

Competing-risk models estimate cause-specific hazards and account for removal from the risk set; FX-CPM does not compute an overall any-crisis probability by assuming hazard independence.

## 7. Incremental FX experiment

Each supported target is evaluated twice with identical folds and non-FX preprocessing:

\[
M_0=f(X_{nonFX}),\qquad M_1=f(X_{nonFX},X_{FX}).
\]

The reported \(\Delta_{FX}\) is `metric(M1) - metric(M0)` with the sign interpreted per metric. For losses such as Brier and log loss, negative deltas are improvements; for average precision and recall, positive deltas are improvements. Paired fold/bootstrap uncertainty is reported. “No meaningful incremental value” is an acceptable result.

## 8. Calibration

Calibration data must chronologically follow model training and precede the final test window. Supported mappings include Platt scaling,

\[
p_{cal}=\sigma(a+b\,logit(p_{raw})),
\]

and isotonic regression when the calibration sample is sufficiently large. The method, dates, event count, intercept, slope, reliability bins, Brier score, and log loss travel with the artifact. Horizon-specific calibration is preferred.

The Brier score and log loss are

\[
BS=N^{-1}\sum_j(p_j-y_j)^2,
\qquad
LL=-N^{-1}\sum_j[y_j\log p_j+(1-y_j)\log(1-p_j)].
\]

Calibration intercept and slope come from a logistic recalibration diagnostic on held-out predictions. A forecast outside the historical calibration score range is marked out of domain. Without evaluated calibration, output is an uncalibrated estimate and cannot produce a severe operational alert.

## 9. Uncertainty

Where sample size allows, country/event-cluster bootstrap refits produce a distribution of calibrated estimates. The reported lower and upper bounds are percentile model-uncertainty intervals; they are not called confidence intervals unless their statistical coverage has been established. Ensemble dispersion, calibration uncertainty, input-quality uncertainty, and sensitivity to event-onset bounds are retained separately rather than added into an opaque interval.

Evidence confidence is not event probability. The reference evidence score is a documented weighted geometric mean of coverage, freshness, source authority, vintage quality, and agreement, with a hard penalty for source failure and out-of-domain conditions. A low evidence score cannot lower the event estimate to make a country look safe; it creates a separate warning and gates alert severity.

## 10. Alerts

For hazard \(k\) and horizon \(h\), thresholds \(\theta^{watch},\ldots,\theta^{critical}\) are learned from a validation period under an explicit loss:

\[
L(\theta)=c_{FN}FN(\theta)+c_{FP}FP(\theta)+c_D Delay(\theta)+c_A AlertBurden(\theta).
\]

Thresholds are never universal across hazards. Relative risk is

\[
RR_{i,t}^{k,h}=p_{i,t}^{k,h}/\pi_{k,h},
\]

where \(\pi_{k,h}\) is the training/validation base rate for the same target and a comparable tier/regime population.

`HIGH` and `CRITICAL` require acceptable calibration, minimum coverage and quality, a valid target for the current regime, in-domain status, and no dependence on a failed/stale sole source. If thresholds are not validated, the maximum is `WATCH_UNCALIBRATED`. Evidence warnings remain visible beside risk severity.

Hysteresis uses an exit threshold below the entry threshold. Records retain first seen, last escalation, consecutive observations, peak estimate, and current estimate. Seven-, 30-, and 90-day changes and log-odds changes describe momentum; acceleration alone cannot turn a low absolute estimate into `CRITICAL`.

## 11. Historical analogues

Candidate states must be visible by the analysis date and fall inside an explicitly supplied reference window that ends before the query observation. Numeric feature and global-state distances use population means and standard deviations estimated only from that past reference window. Constant reference metrics use a disclosed unit scale. Regime and development-level mismatches are separate categorical penalties; data-coverage gaps and missing candidate metrics are separate penalties. The default aggregate distance is

\[
d(x,z)=\sum_g w_g d_g(x,z),
\qquad similarity=100/(1+d).
\]

The component weights and reference statistics travel with the search result. Analogue records disclose country/date, feature coverage, regime, global context, conditions at the time, subsequent outcome, event type, and time to event. The 0--100 similarity is not a probability. Analogues are contextual neighbors, not causal precedents.

## 12. Contagion

For channel \(c\) with lagged adjacency matrix \(W^{(c)}\), network pressure is

\[
NetworkPressure_{i,t}^{(c)}=\sum_{j\ne i}\tilde W_{ij}^{(c)}Risk_{j,t-1},
\]

with rows normalized over available, dated edges. Own risk, global/common-factor stress, regional stress, and channel-specific network pressure enter separately. Edges must be observable by the analysis date. Co-movement is described as association unless a separate identification design supports a causal claim.

### 12.1 Multi-hazard systemic stress

Each hazard may publish a separate descriptive stress score \(s_k\in[0,100]\). The non-probabilistic summary is an available-weight-renormalized arithmetic mean:

\[
SSI=\frac{\sum_k I_k w_k s_k}{\sum_k I_k w_k},
\qquad coverage=\frac{\sum_k I_k w_k}{\sum_k w_k}.
\]

Missing hazards reduce coverage and are not replaced with zero. The index is unavailable below its declared minimum coverage. It is not \(P(any\ crisis)\), and it never multiplies complements of separate hazard probabilities.

## 13. Evaluation and selection

All splits are chronological and preprocessing is fitted inside each training fold. Primary metrics are average precision/PR-AUC, Brier score, log loss, recall at fixed false-positive rate, precision at operational alert rate, missed-event rate, false-alert rate, warning lead time, and decision utility. ROC-AUC is secondary. Every result includes the unconditional base rate, event count, country count, period, tier, regime coverage, and point-in-time status.

Expanding-window, country holdout, event-cluster holdout, regime holdout, and feature-era tests are required before a validated claim. Calibration never sees final-test outcomes. Selection follows scientific validity, point-in-time integrity, calibration, provenance, interpretability, presentation, then convenience.

## 14. Interpretation

Coefficients, feature importance, SHAP values, residual stress, and analogue proximity are predictive associations. Reports use “predictive contributor” rather than “cause.” Political and military forecasts cannot infer intent from prices. FX is tested as one market-information channel; it is not treated as a standalone oracle.
