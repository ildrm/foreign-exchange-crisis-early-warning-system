"""Training, prediction, and probability term-structure orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from math import sqrt
from typing import Any, Iterable, Mapping

from .calibration_service import (
    CalibrationEvaluation,
    CalibrationQuality,
    CalibrationService,
    FittedCalibration,
)
from .feature_matrix import FeatureMatrixEncoder, FeatureSample
from .models import LogisticRegression, RegularizedLogisticRegression


def _value(value: Any) -> str:
    return str(getattr(value, "value", value))


def horizon_days(horizon: Any) -> int:
    """Map standard horizon enums/labels to an ordering in days."""

    explicit = getattr(horizon, "days", None)
    if explicit is not None:
        return int(explicit)
    if isinstance(horizon, int):
        return horizon
    text = _value(horizon).strip().lower().replace("_", "")
    aliases = {
        "30d": 30,
        "30days": 30,
        "90d": 90,
        "90days": 90,
        "180d": 180,
        "180days": 180,
        "12m": 365,
        "12months": 365,
        "1y": 365,
        "24m": 730,
        "24months": 730,
        "2y": 730,
        "36m": 1095,
        "36months": 1095,
        "3y": 1095,
    }
    if text in aliases:
        return aliases[text]
    if text.endswith("d") and text[:-1].isdigit():
        return int(text[:-1])
    raise ValueError(f"unsupported forecast horizon: {horizon!r}")


@dataclass(frozen=True, slots=True)
class ModelKey:
    hazard: str
    horizon: str

    @classmethod
    def from_values(cls, hazard: Any, horizon: Any) -> "ModelKey":
        return cls(_value(hazard), _value(horizon))


@dataclass(frozen=True, slots=True)
class ModelFitSummary:
    key: ModelKey
    model_version: str
    training_start: date
    training_end: date
    observation_count: int
    event_count: int
    base_rate: float
    feature_names: tuple[str, ...]
    converged: bool
    calibration: CalibrationEvaluation | None


@dataclass(frozen=True, slots=True)
class ForecastEstimate:
    country_id: str
    hazard: Any
    horizon: Any
    analysis_date: date
    raw_probability: float
    calibrated_probability: float | None
    output_label: str
    base_rate: float
    relative_risk: float | None
    data_coverage: float
    calibration_quality: str
    calibration_in_domain: bool
    model_version: str
    training_end_date: date
    model_tier: Any | None
    regime: Any | None
    predictive_contributors: tuple[tuple[str, float], ...]
    sensitivity_low: float | None = None
    sensitivity_high: float | None = None
    ensemble_dispersion: float | None = None

    @property
    def displayed_probability(self) -> float:
        return self.calibrated_probability if self.calibrated_probability is not None else self.raw_probability


@dataclass(frozen=True, slots=True)
class TermStructurePoint:
    horizon: Any
    horizon_days: int
    estimate: ForecastEstimate
    monotonic_probability: float
    adjusted_for_monotonicity: bool


@dataclass(slots=True)
class _FittedModel:
    key: ModelKey
    hazard: Any
    horizon: Any
    encoder: FeatureMatrixEncoder
    model: LogisticRegression
    model_version: str
    training_start: date
    training_end: date
    base_rate: float
    calibration: FittedCalibration | None = None


@dataclass(slots=True)
class ForecastService:
    """Manage separate horizon/hazard statistical baselines."""

    calibration_service: CalibrationService = field(default_factory=CalibrationService)
    _models: dict[ModelKey, _FittedModel] = field(default_factory=dict, init=False, repr=False)

    def fit(
        self,
        samples: Iterable[FeatureSample],
        *,
        hazard: Any,
        horizon: Any,
        model_version: str = "logit-1.0",
        regularized: bool = True,
        l2: float = 1.0,
        class_weight: str | None = None,
        validation_samples: Iterable[FeatureSample] = (),
        calibration_evaluation_samples: Iterable[FeatureSample] = (),
        calibration_method: str = "platt",
        final_test_start: date | None = None,
    ) -> ModelFitSummary:
        training = tuple(samples)
        validation = tuple(validation_samples)
        calibration_evaluation = tuple(calibration_evaluation_samples)
        if not training:
            raise ValueError("training samples are required")
        if any(sample.target is None for sample in training):
            raise ValueError("every training sample needs a target")
        if any(ModelKey.from_values(sample.hazard, sample.horizon) != ModelKey.from_values(hazard, horizon) for sample in training if sample.hazard is not None and sample.horizon is not None):
            raise ValueError("training samples mix hazard/horizon targets")
        training_end = max(sample.analysis_date for sample in training)
        training_start = min(sample.analysis_date for sample in training)
        if validation and min(sample.analysis_date for sample in validation) <= training_end:
            raise ValueError("validation samples must follow the model-training period")
        if validation and any(sample.target is None for sample in validation):
            raise ValueError("every calibration sample needs a target")
        if calibration_evaluation and not validation:
            raise ValueError("calibration evaluation requires a preceding calibration fit partition")
        if calibration_evaluation and any(sample.target is None for sample in calibration_evaluation):
            raise ValueError("every calibration-evaluation sample needs a target")

        encoder = FeatureMatrixEncoder()
        matrix = encoder.fit_transform(training)
        targets = matrix.targets
        assert targets is not None
        model: LogisticRegression
        if regularized:
            model = RegularizedLogisticRegression(l2=l2, class_weight=class_weight)
        else:
            model = LogisticRegression(l2=0.0, class_weight=class_weight)
        model.fit(matrix.values, targets)

        fitted_calibration = None
        if validation:
            validation_matrix = encoder.transform(validation)
            validation_targets = validation_matrix.targets
            assert validation_targets is not None
            raw = model.predict_proba(validation_matrix.values)
            evaluation_matrix = encoder.transform(calibration_evaluation) if calibration_evaluation else None
            evaluation_targets = evaluation_matrix.targets if evaluation_matrix is not None else None
            fitted_calibration = self.calibration_service.fit(
                raw,
                validation_targets,
                method=calibration_method,
                validation_dates=(sample.analysis_date for sample in validation),
                final_test_start=final_test_start,
                evaluation_probabilities=(
                    model.predict_proba(evaluation_matrix.values) if evaluation_matrix is not None else None
                ),
                evaluation_labels=evaluation_targets,
                evaluation_dates=(
                    tuple(sample.analysis_date for sample in calibration_evaluation)
                    if calibration_evaluation
                    else None
                ),
            )

        key = ModelKey.from_values(hazard, horizon)
        base_rate = sum(targets) / len(targets)
        self._models[key] = _FittedModel(
            key=key,
            hazard=hazard,
            horizon=horizon,
            encoder=encoder,
            model=model,
            model_version=model_version,
            training_start=training_start,
            training_end=training_end,
            base_rate=base_rate,
            calibration=fitted_calibration,
        )
        return ModelFitSummary(
            key=key,
            model_version=model_version,
            training_start=training_start,
            training_end=training_end,
            observation_count=len(training),
            event_count=sum(targets),
            base_rate=base_rate,
            feature_names=matrix.feature_names,
            converged=model.converged_,
            calibration=fitted_calibration.evaluation if fitted_calibration else None,
        )

    def forecast(
        self,
        sample: FeatureSample,
        *,
        hazard: Any,
        horizon: Any,
        sensitivity_interval: tuple[float, float] | None = None,
        ensemble_probabilities: Iterable[float] = (),
    ) -> ForecastEstimate:
        key = ModelKey.from_values(hazard, horizon)
        fitted = self._models.get(key)
        if fitted is None:
            raise KeyError(f"no fitted model for {key.hazard}/{key.horizon}")
        if sample.analysis_date <= fitted.training_end:
            # Forecasting inside the training period is allowed for diagnostics but
            # must never masquerade as an out-of-sample result.  Refuse by default.
            raise ValueError("forecast analysis date must follow the training period")
        matrix = fitted.encoder.transform((sample,))
        raw = fitted.model.predict_proba(matrix.values)[0]
        calibrated: float | None = None
        quality = CalibrationQuality.UNCALIBRATED.value
        in_domain = False
        if fitted.calibration is not None:
            calibrated = fitted.calibration.calibrator.transform((raw,))[0]
            quality = fitted.calibration.evaluation.quality.value
            in_domain = fitted.calibration.evaluation.in_supported_domain(raw)
        displayed = calibrated if calibrated is not None else raw
        relative = displayed / fitted.base_rate if fitted.base_rate > 0 else None
        present = sum(sample.features.get(name) is not None for name in fitted.encoder._input_names)
        coverage = present / len(fitted.encoder._input_names) if fitted.encoder._input_names else 0.0
        contributions = fitted.model.contributions(matrix.values[0])
        ranked = tuple(
            sorted(
                zip(matrix.feature_names, contributions),
                key=lambda item: (-abs(item[1]), item[0]),
            )
        )
        label = (
            "CALIBRATED_PROBABILITY"
            if calibrated is not None and quality == CalibrationQuality.ACCEPTABLE.value
            else "UNCALIBRATED_RISK_ESTIMATE"
        )
        ensemble = tuple(float(value) for value in ensemble_probabilities)
        if any(value < 0.0 or value > 1.0 for value in ensemble):
            raise ValueError("ensemble probabilities must lie in [0, 1]")
        low = high = None
        if sensitivity_interval is not None:
            low, high = (float(sensitivity_interval[0]), float(sensitivity_interval[1]))
            if not 0.0 <= low <= high <= 1.0:
                raise ValueError("sensitivity interval must be ordered within [0, 1]")
        elif ensemble:
            low, high = min(ensemble), max(ensemble)
        dispersion = None
        if ensemble:
            ensemble_mean = sum(ensemble) / len(ensemble)
            dispersion = sqrt(sum((value - ensemble_mean) ** 2 for value in ensemble) / len(ensemble))
        return ForecastEstimate(
            country_id=sample.country_id,
            hazard=hazard,
            horizon=horizon,
            analysis_date=sample.analysis_date,
            raw_probability=raw,
            calibrated_probability=calibrated,
            output_label=label,
            base_rate=fitted.base_rate,
            relative_risk=relative,
            data_coverage=coverage,
            calibration_quality=quality,
            calibration_in_domain=in_domain,
            model_version=fitted.model_version,
            training_end_date=fitted.training_end,
            model_tier=sample.model_tier,
            regime=sample.regime,
            predictive_contributors=ranked,
            sensitivity_low=low,
            sensitivity_high=high,
            ensemble_dispersion=dispersion,
        )

    def term_structure(
        self,
        sample: FeatureSample,
        *,
        hazard: Any,
        horizons: Iterable[Any],
        enforce_monotonicity: bool = True,
    ) -> tuple[TermStructurePoint, ...]:
        ordered = sorted(tuple(horizons), key=horizon_days)
        previous = 0.0
        result = []
        for horizon in ordered:
            estimate = self.forecast(sample, hazard=hazard, horizon=horizon)
            value = estimate.displayed_probability
            monotonic = max(previous, value) if enforce_monotonicity else value
            result.append(
                TermStructurePoint(
                    horizon=horizon,
                    horizon_days=horizon_days(horizon),
                    estimate=estimate,
                    monotonic_probability=monotonic,
                    adjusted_for_monotonicity=monotonic > value + 1e-15,
                )
            )
            previous = monotonic
        return tuple(result)

    def fitted_models(self) -> Mapping[ModelKey, ModelFitSummary]:
        return {
            key: ModelFitSummary(
                key=key,
                model_version=item.model_version,
                training_start=item.training_start,
                training_end=item.training_end,
                observation_count=0,
                event_count=0,
                base_rate=item.base_rate,
                feature_names=item.encoder.output_feature_names,
                converged=item.model.converged_,
                calibration=item.calibration.evaluation if item.calibration else None,
            )
            for key, item in self._models.items()
        }
