# FX-CPM Crisis Taxonomy

Taxonomy version: 0.1.0  
Unit: country-time at risk  
Status: versioned research definition; source reconciliation is required before model training

## Shared event representation

Every event stores `onset_min`, `onset_canonical`, and `onset_max`, because public sources often disagree or provide only month/year precision. It also stores end date, severity, source identifiers, source agreement, label confidence, and notes. Dates use the Gregorian calendar; year-only sources map to January 1/July 1/December 31 bounds, not a fabricated exact onset.

Confidence is `HIGH` when at least two independent authoritative sources agree on category and materially overlap on onset; `MEDIUM` when one authoritative source with a documented method is available or dates differ within the accepted window; `LOW` when only secondary evidence exists or category/date disagreement remains. Low-confidence labels are excluded from primary training and may enter sensitivity tests.

An event is an onset only when the country was at risk immediately beforehand. Ongoing episodes are not relabeled every period. Each hazard has a quiet/recovery rule and an exclusion interval to prevent continuations from becoming negative controls. Source-coded labels and quantitative-rule labels are retained separately and reconciled; an indicator threshold never silently rewrites a documented historical event.

## Summary

| Code | Formal label | Primary frequency | Initial standard horizons | Principal label candidates |
|---|---|---:|---|---|
| `FX` | Currency / balance-of-payments crisis | monthly | 90d, 180d, 12m, 24m | IMF crisis databases; peer-reviewed EMP chronologies; central banks |
| `BANK` | Systemic banking crisis | monthly/annual | 12m, 24m, 36m | IMF Systemic Banking Crises Database |
| `SOV` | Sovereign distress/default crisis | daily/monthly | 180d, 12m, 24m | World Bank IDS; IMF; official creditor/debtor notices |
| `MON` | Monetary/inflation crisis | monthly | 90d, 180d, 12m | national statistics/central banks; IMF IFS |
| `POL` | Major political-instability crisis | monthly | 90d, 180d, 12m | V-Dem; constitutional/official records; curated event datasets |
| `COUP` | Coup or unconstitutional government change | daily/monthly | 90d, 180d, 12m | versioned academic coup datasets; official/constitutional records |
| `CIV` | Internal armed-conflict onset/escalation | daily/monthly | 90d, 180d, 12m | UCDP state-based conflict/onset data |
| `WAR` | Interstate armed-conflict onset/escalation | daily/monthly | 90d, 180d, 12m | UCDP/PRIO state-based conflict data |

Horizon support is provisional until event counts and release lags are evaluated. Daily precision does not imply that all predictors were available daily.

## FX — Currency / balance-of-payments crisis

**Definition.** A discrete episode of severe pressure on a country's currency arrangement, expressed through a sharp market/official depreciation, depletion of liquid reserves and exceptional interest-rate defense, forced regime/anchor change, suspension of convertibility, or a material parallel-market dislocation. Depreciation is not required under a successfully defended peg.

**Onset.** Earliest defensible date on which either (a) an authoritative chronology identifies a currency/balance-of-payments crisis or forced exchange-arrangement break, or (b) a predeclared regime-conditioned EMP rule crosses its extreme threshold and a second stress component confirms it. Thresholds are estimated from training history by regime; they are not hard-coded universally. A source-coded and EMP-derived onset within 90 days are one event.

**Continuation.** Months remain in episode while exchange restrictions, extraordinary defense, reserve loss, acute parallel premium, or stress above the continuation threshold persists.

**Termination/recovery.** Six consecutive months below the continuation threshold with no emergency exchange measure, or an authoritative source's later recovery date. The default new-onset washout is 12 months after termination; sensitivity tests use 6 and 24 months.

**Severity.** Ordinal combination of peak regime-conditioned EMP percentile, cumulative depreciation/parallel premium, reserve depletion, convertibility restriction, and regime break. Severity is not used to change the binary onset label unless a minimum two-component confirmation is met.

**Ambiguities and exclusions.** Planned redenominations without loss of value, movements caused purely by a reference-currency change, hyperinflationary arithmetic already inside an ongoing episode, illiquid quotes, and isolated data errors are excluded. Currency unions and dollarized countries can experience balance-of-payments/convertibility pressure but need applicable indicators; a nonexistent national bilateral spot rate is `NOT_APPLICABLE`, not zero.

## BANK — Systemic banking crisis

**Definition.** Significant signs of financial distress across material parts of the banking system accompanied by significant policy intervention, forced closures/mergers, deposit freezes, bank runs, or system-wide losses. A single idiosyncratic bank failure is insufficient unless it creates documented systemic impairment.

**Onset.** Canonical onset follows the earliest date in a versioned systemic-banking-crisis source, refined only by documented bank runs, closures, guarantees, or extraordinary intervention. The 2026 IMF update to the Laeven–Valencia database is the preferred initial backbone; its own borderline indicator is retained.

**Continuation.** The episode continues while systemic restructuring, blanket support, widespread insolvency, deposit restrictions, or emergency liquidity associated with the episode remains active.

**Termination/recovery.** Source-provided end date where available; otherwise the first year after core systemic interventions cease and banking intermediation resumes, with uncertainty bounds. New onsets require a documented distinct episode, not a new intervention in the same resolution cycle.

**Severity.** Uses source-coded systemic/borderline status and, secondarily, fiscal cost, output loss, affected asset share, and duration. Missing cost estimates do not imply low severity.

**Ambiguities and exclusions.** Non-systemic failures, market-price declines without system distress, and sovereign-directed bank recapitalization without bank distress are excluded. Sovereign-bank doom loops may create linked `BANK` and `SOV` events; both remain separate labels with shared-cluster identifiers.

## SOV — Sovereign distress/default crisis

**Definition.** Failure or coercive alteration of a sovereign debt obligation, or an officially documented state of severe debt distress involving arrears, default, restructuring, distressed exchange, standstill, or comparable loss to creditors. Market spread widening alone is a predictor, not an event.

**Onset.** Earliest missed contractual payment after any applicable grace period, announced standstill/moratorium, coercive/distressed exchange launch, or authoritative default date. For slow restructurings, `onset_min` may be the first missed payment and `onset_max` the formal restructuring/default announcement.

**Continuation.** Continues while arrears/default remain unresolved or the same restructuring process is active. Separate instruments involved in one negotiation are clustered into one episode.

**Termination/recovery.** Settlement/effective restructuring date and clearance of material arrears, with a 12-month post-resolution exclusion. Re-default on newly restructured debt is a new event only when contractually and historically distinct.

**Severity.** Domestic/external debt scope, affected principal, arrears duration, haircut/net-present-value loss, and official rating/source classifications where licensing permits.

**Ambiguities and exclusions.** Voluntary liability management at near-market terms, technical delays cured within a grace period, municipal/corporate defaults, and pure rating downgrades are excluded. Domestic-law restructurings are included when coercive and sovereign. Sanctions-blocked payments require adjudication rather than automatic labeling.

## MON — Monetary / inflation crisis

**Definition.** A discrete loss of domestic monetary-price stability evidenced by extreme and accelerating consumer-price inflation or a documented breakdown of the monetary unit. It is distinct from ordinary high inflation and from the currency-crisis target.

**Onset.** Primary rule: the first month in which year-over-year headline CPI is at least 40 percent *and* has risen by at least 20 percentage points over six months, confirmed in two consecutive releases. Hyperinflation onset (monthly inflation above 50 percent) also qualifies immediately. Country statistical breaks trigger review. These numeric rules are initial research conventions and must be sensitivity-tested at 30/50/100 percent annual thresholds.

**Continuation.** Continues while year-over-year inflation remains at least 30 percent, monthly hyperinflation persists, price measurement is suspended, or a currency replacement directly addressing monetary collapse is underway.

**Termination/recovery.** Twelve consecutive months below 20 percent year-over-year inflation and no hyperinflation reading. The wide hysteresis prevents one favorable base-effect month from ending an episode.

**Severity.** Peak monthly/annual inflation, episode duration, price-index reliability, currency replacement, and scale of real-money-balance erosion.

**Ambiguities and exclusions.** One-off price-level jumps from tax/statistical rebasing, wartime gaps without a reliable price index, asset-price inflation, and moderate target misses are excluded. Where official CPI is credibly suppressed or unavailable, alternative series may inform a low-confidence label but cannot silently substitute.

## POL — Major political-instability crisis

**Definition.** A major, observable disruption to ordinary national political authority that threatens or produces discontinuity in executive governance, constitutional order, or state control, but is not adequately represented solely by a coup or armed-conflict label.

**Onset.** Earliest documented date of one of: forced extra-constitutional executive removal not coded as a coup; dissolution/suspension of core constitutional institutions; sustained mass unrest with nationwide emergency measures and material governance disruption; collapse of central authority; or a versioned dataset's major adverse regime-transition event confirmed by contemporaneous authoritative evidence.

**Continuation.** Continues while exceptional suspension, central-authority vacuum, nationwide emergency repression/disruption, or unresolved executive discontinuity persists.

**Termination/recovery.** Restoration of a functioning nationally recognized executive and ordinary constitutional/administrative process for at least 90 days, or a documented transition to a new stable order. This is recovery from the event definition, not endorsement of the resulting regime.

**Severity.** Geographic reach, duration, institutional discontinuity, casualties where independently measured, and state-capacity impairment.

**Ambiguities and exclusions.** Routine elections, lawful cabinet turnover, peaceful constitutional succession, small/local protests, and model-inferred “instability” without a documented event are excluded. `POL` may overlap with `COUP` or `CIV`, but the label source and shared episode cluster must disclose dependence.

## COUP — Coup / unconstitutional government-change risk

**Definition.** An illegal and overt attempt by military personnel or other state elites to remove or displace the sitting national executive, plus successful unconstitutional changes that meet the source taxonomy. Attempts and successes are distinct severity fields, not different hazards.

**Onset.** First overt action directed at seizing/removing executive authority, using the event date in a versioned coup dataset and authoritative contemporaneous confirmation. Plot discovery without overt action is excluded from the primary label.

**Continuation.** A coup is generally a point-onset event. Immediate contestation, counter-coup, or consolidation is attached to the same episode for up to 30 days unless a source identifies a distinct attempt.

**Termination/recovery.** Resolution of the attempt (success/failure) and restoration or replacement of executive control. A 180-day exclusion prevents consolidation from being labeled as ordinary non-event exposure; distinct counter-coups remain linked events.

**Severity.** Attempted/successful, force used, fatalities where documented, executive displaced, and duration of contested control.

**Ambiguities and exclusions.** Constitutional impeachment, court-ordered removal under ordinary process, mass revolt without state-elite seizure, foreign invasion, assassination without a seizure attempt, rumors, and self-coups are separately coded. A self-coup may enter `COUP` only if the selected source taxonomy explicitly includes it; otherwise it enters `POL`.

## CIV — Internal armed-conflict onset or escalation

**Definition.** Organized armed force involving the government of a state and one or more internal opposition organizations over government or territory, meeting the selected UCDP state-based conflict threshold. Internationalized internal conflict remains `CIV` with an international-support attribute.

**Onset.** Primary onset is the first qualifying UCDP conflict year after at least two calendar years below the 25 battle-related-death threshold, with the date interval refined from georeferenced events when available. The annual threshold and date uncertainty are retained. An alternative escalation target begins when an existing low-intensity episode crosses a predeclared intensity threshold; onset and escalation are never mixed in one label.

**Continuation.** Continues while the dyad/conflict meets source activity rules. Temporary within-year lulls do not create repeated onsets.

**Termination/recovery.** Source termination date or two consecutive calendar years below the onset threshold. Recurrence definitions follow the chosen UCDP onset dataset and are versioned.

**Severity.** Battle-death best/low/high estimates, territorial spread, population displacement where sourced, and source intensity category.

**Ambiguities and exclusions.** Criminal violence without a political incompatibility, one-sided violence, non-state conflict without government participation, protests, and foreign interstate fighting are excluded from this target. They may be predictive features or separate research outcomes.

## WAR — Interstate armed-conflict onset or escalation

**Definition.** Organized armed force between two or more states over government, territory, or another documented incompatibility, meeting the selected UCDP/PRIO state-based threshold. The unit forecast is country involvement onset, with a shared war-cluster identifier.

**Onset.** Earliest qualifying armed-force event for each newly involved state, reconciled with the source's first active year and event data. In a continuing war, a new state's entry is an involvement onset for that state but remains part of the same cluster. Escalation of an existing conflict is a separate target.

**Continuation.** Continues while the interstate dyad is active under source rules. Ceasefires are not terminations unless source criteria are met.

**Termination/recovery.** Source-coded termination/peace or two consecutive inactive calendar years, depending on target dataset. Recurrence follows the source version.

**Severity.** Battle deaths, participating states, territorial scope, duration, and intensity category.

**Ambiguities and exclusions.** Militarized threats without qualifying force, covert activity without attributable state participation, accidental border incidents below threshold, colonial/internal conflicts, and unilateral attacks on non-state actors are excluded or assigned according to the source codebook. Forecasts describe onset probability; they do not infer a state's intent to start war.

## Cross-hazard clustering

Events may overlap without being merged. A single episode can carry a shared cluster identifier—for example, sovereign default during a banking crisis or currency collapse during political upheaval—so evaluation can hold out the entire cluster. FX-CPM never trains on one member of an unfolding cluster and describes prediction of another member as independent without disclosure.

## Label release and vintage policy

The source publication/release date determines when a label database could be used for training or retrospective evaluation. Event occurrence dates do not imply contemporaneous public coding. Every frozen label snapshot records dataset version, retrieval date, source license, reconciliation code version, and a digest. Corrections create a new snapshot; they do not overwrite prior labels.

No model may claim validated probabilities until a frozen label snapshot implements these definitions, ambiguous cases are adjudicated, and baseline prevalence is reported by hazard, horizon, era, model tier, and relevant regime.

