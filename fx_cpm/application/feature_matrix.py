"""Leakage-resistant, dependency-free feature-matrix conventions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from math import isfinite, sqrt
from statistics import median
from typing import Any, Iterable, Mapping, Sequence


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


@dataclass(frozen=True, slots=True)
class FeatureSample:
    """One country/date modelling row before matrix encoding."""

    country_id: str
    analysis_date: date
    features: Mapping[str, float | None]
    target: int | None = None
    hazard: Any | None = None
    horizon: Any | None = None
    regime: Any | None = None
    cluster_id: str | None = None
    event_id: str | None = None
    event_date: date | None = None
    model_tier: Any | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.target not in (None, 0, 1):
            raise ValueError("target must be 0, 1, or None")


@dataclass(frozen=True, slots=True)
class FeatureMatrix:
    feature_names: tuple[str, ...]
    values: tuple[tuple[float, ...], ...]
    samples: tuple[FeatureSample, ...]

    @property
    def targets(self) -> tuple[int, ...] | None:
        if any(sample.target is None for sample in self.samples):
            return None
        return tuple(int(sample.target) for sample in self.samples if sample.target is not None)

    @property
    def shape(self) -> tuple[int, int]:
        return (len(self.values), len(self.feature_names))


@dataclass(slots=True)
class FeatureMatrixEncoder:
    """Median-impute and standardize using *training rows only*.

    Missing values are never converted to economic zero: each missing value is
    imputed with the training median and accompanied by an explicit missingness
    indicator.  Indicator columns are not standardized.
    """

    feature_names: Sequence[str] | None = None
    add_missing_indicators: bool = True
    standardize: bool = True
    _input_names: tuple[str, ...] = field(default=(), init=False, repr=False)
    _medians: tuple[float, ...] = field(default=(), init=False, repr=False)
    _means: tuple[float, ...] = field(default=(), init=False, repr=False)
    _scales: tuple[float, ...] = field(default=(), init=False, repr=False)
    _fitted: bool = field(default=False, init=False, repr=False)

    def fit(self, samples: Iterable[FeatureSample]) -> "FeatureMatrixEncoder":
        rows = tuple(samples)
        if not rows:
            raise ValueError("at least one training sample is required")
        if self.feature_names is None:
            names = tuple(sorted({name for sample in rows for name in sample.features}))
        else:
            names = tuple(dict.fromkeys(str(name) for name in self.feature_names))
        if not names:
            raise ValueError("at least one feature is required")

        medians: list[float] = []
        means: list[float] = []
        scales: list[float] = []
        for name in names:
            available = [
                value
                for sample in rows
                if (value := _number(sample.features.get(name))) is not None
            ]
            if not available:
                # A training-all-missing column contains no economic signal.
                # Zero is only a neutral transformed-space fill; the companion
                # indicator retains the fact that every original value was missing.
                imputation = 0.0
            else:
                imputation = float(median(available))
            completed = [
                value if (value := _number(sample.features.get(name))) is not None else imputation
                for sample in rows
            ]
            mean = sum(completed) / len(completed)
            variance = sum((value - mean) ** 2 for value in completed) / len(completed)
            medians.append(imputation)
            means.append(mean)
            scales.append(sqrt(variance) if variance > 1e-24 else 1.0)

        self._input_names = names
        self._medians = tuple(medians)
        self._means = tuple(means)
        self._scales = tuple(scales)
        self._fitted = True
        return self

    @property
    def fitted(self) -> bool:
        return self._fitted

    @property
    def output_feature_names(self) -> tuple[str, ...]:
        self._require_fitted()
        if not self.add_missing_indicators:
            return self._input_names
        return self._input_names + tuple(f"{name}__missing" for name in self._input_names)

    def transform(self, samples: Iterable[FeatureSample]) -> FeatureMatrix:
        self._require_fitted()
        rows = tuple(samples)
        matrix: list[tuple[float, ...]] = []
        for sample in rows:
            numeric: list[float] = []
            missing: list[float] = []
            for index, name in enumerate(self._input_names):
                value = _number(sample.features.get(name))
                is_missing = value is None
                completed = self._medians[index] if is_missing else value
                assert completed is not None
                if self.standardize:
                    completed = (completed - self._means[index]) / self._scales[index]
                numeric.append(completed)
                missing.append(1.0 if is_missing else 0.0)
            matrix.append(tuple(numeric + missing if self.add_missing_indicators else numeric))
        return FeatureMatrix(self.output_feature_names, tuple(matrix), rows)

    def fit_transform(self, samples: Iterable[FeatureSample]) -> FeatureMatrix:
        rows = tuple(samples)
        return self.fit(rows).transform(rows)

    def _require_fitted(self) -> None:
        if not self._fitted:
            raise RuntimeError("FeatureMatrixEncoder must be fitted on training data first")


def without_features(sample: FeatureSample, excluded: Iterable[str]) -> FeatureSample:
    """Copy a sample while removing named features (used for FX ablation)."""

    names = frozenset(excluded)
    return FeatureSample(
        country_id=sample.country_id,
        analysis_date=sample.analysis_date,
        features={key: value for key, value in sample.features.items() if key not in names},
        target=sample.target,
        hazard=sample.hazard,
        horizon=sample.horizon,
        regime=sample.regime,
        cluster_id=sample.cluster_id,
        event_id=sample.event_id,
        event_date=sample.event_date,
        model_tier=sample.model_tier,
        metadata=sample.metadata,
    )
