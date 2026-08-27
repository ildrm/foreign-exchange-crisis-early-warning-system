# ruff: noqa: F401
"""Public scientific-domain API for FX-CPM.

This package is deliberately dependency-free and has no filesystem, network,
CLI, or presentation imports.  All model mathematics can therefore be tested
offline.
"""

from .alerts import (
    AlertEvaluation,
    AlertMarker,
    AlertPolicy,
    AlertRecord,
    AlertSeverity,
    AlertThresholds,
    EvidenceAlert,
    ProbabilityMomentum,
    RiskAlertLevel,
    build_alert_record,
    severity_with_hysteresis,
)
from .analogues import (
    AnalogueDistanceComponents,
    AnalogueQuery,
    AnalogueReferenceWindow,
    AnalogueWeights,
    HistoricalAnalogue,
    HistoricalAnalogueSearch,
    HistoricalState,
    StandardizationStatistic,
    find_historical_analogues,
)
from .calibration import (
    CalibrationBin,
    CalibrationFit,
    CalibrationMethod,
    CalibrationRecord,
    CalibrationStatus,
    assess_calibration_status,
    beta_scale,
    binary_log_loss,
    brier_score,
    calibration_bins,
    calibration_intercept_slope,
    empirical_base_rate,
    expected_calibration_error,
    isotonic_scale,
    logistic,
    logit,
    platt_scale,
)
from .contagion import (
    CommonFactorPressureContribution,
    ContagionEdgeChannel,
    ContagionGraphSnapshot,
    DatedContagionEdge,
    DatedContagionGraph,
    NetworkPressureContribution,
    PressureDecomposition,
    decompose_contagion_pressure,
    graph_from_edges,
)
from .entities import ConfidenceBand, DateInterval, Identifier, ModelTier, OODStatus
from .events import (
    CrisisEvent,
    OnsetInterpretation,
    binary_horizon_label,
    events_in_horizon,
    reconcile_onset_dates,
)
from .features import (
    CORE_FX_FEATURE_DEFINITIONS,
    ExpectedRelationship,
    FeatureDefinition,
    FeatureFamily,
    MissingDataPolicy,
    acceleration,
    arithmetic_change,
    drawdown,
    feature_definition,
    log_return,
    percentage_change,
    rolling_mean,
)
from .global_factors import (
    FactorTrainingWindow,
    FXResidualEstimate,
    GlobalFactorModelFit,
    GlobalFactorObservation,
    fit_global_factor_model,
)
from .hazards import (
    ForecastRecord,
    HazardProbabilityVector,
    cumulative_probability_from_discrete_hazards,
    log_odds_change,
    probability_point_change,
    relative_risk,
    validate_probability_term_structure,
)
from .observations import (
    Frequency,
    ImputationMetadata,
    MissingStatus,
    Observation,
    ObservationFrequency,
    ProvenanceType,
    RevisionStatus,
    SourceAuthority,
    SourceType,
    TransformationStep,
    VintageMode,
    select_observations_as_of,
    select_vintage,
)
from .regimes import (
    CountryCurrencyRegime,
    FXStressChannel,
    RegimeFamily,
    RegimeHistory,
    RegimeType,
    preferred_stress_channel,
    regime_family,
    regime_interval_issues,
    regimes_comparable,
    validate_regime_intervals,
)
from .stress import (
    AggregateStress,
    EMPComponents,
    EMPWeights,
    aggregate_fx_stress,
    downside_volatility,
    exchange_market_pressure,
    expected_fx_return,
    fx_surprise,
    maximum_drawdown,
    parallel_market_premium,
    realized_volatility,
    residual_fx_return,
    residual_fx_stress,
    sample_standard_deviation,
    z_score,
)
from .systemic_stress import (
    SystemicStressContribution,
    SystemicStressIndex,
    calculate_systemic_stress_index,
)
from .taxonomy import (
    DEFAULT_HAZARD_TAXONOMY,
    TAXONOMY_VERSION,
    ForecastHorizon,
    HazardDefinition,
    HazardType,
    UnitOfAnalysis,
    hazard_definition,
    validate_complete_taxonomy,
)
from .validation import (
    DomainValidationError,
    ValidationIssue,
    ValidationSeverity,
    audit_point_in_time,
    ensure_no_point_in_time_issues,
    require_date_order,
    require_finite,
    require_non_empty,
    require_positive,
    require_probability,
    validate_chronological_split,
)

__all__ = [name for name in globals() if not name.startswith("_")]
