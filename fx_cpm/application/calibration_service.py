"""Probability calibration fitted only on pre-test validation predictions."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from enum import Enum
from math import log
from typing import Iterable, Protocol, Sequence, runtime_checkable

from .models import LogisticRegression, logit

_EPSILON = 1e-12


class CalibrationQuality(str, Enum):
    ACCEPTABLE = "ACCEPTABLE"
    WEAK = "WEAK"
    INSUFFICIENT_EVENTS = "INSUFFICIENT_EVENTS"
    NOT_ASSESSED = "NOT_ASSESSED"
    UNCALIBRATED = "UNCALIBRATED"


@runtime_checkable
class ProbabilityCalibrator(Protocol):
    method: str

    def fit(self, probabilities: Iterable[float], labels: Iterable[int]) -> "ProbabilityCalibrator": ...

    def transform(self, probabilities: Iterable[float]) -> tuple[float, ...]: ...


def _validate(probabilities: Iterable[float], labels: Iterable[int] | None = None) -> tuple[tuple[float, ...], tuple[int, ...] | None]:
    values = tuple(float(value) for value in probabilities)
    if any(value < 0.0 or value > 1.0 for value in values):
        raise ValueError("probabilities must lie in [0, 1]")
    if labels is None:
        return values, None
    targets = tuple(int(value) for value in labels)
    if len(values) != len(targets):
        raise ValueError("probabilities and labels must align")
    if any(target not in (0, 1) for target in targets):
        raise ValueError("labels must be binary")
    return values, targets


@dataclass(slots=True)
class IdentityCalibrator:
    method: str = "none"

    def fit(self, probabilities: Iterable[float], labels: Iterable[int]) -> "IdentityCalibrator":
        _validate(probabilities, labels)
        return self

    def transform(self, probabilities: Iterable[float]) -> tuple[float, ...]:
        values, _ = _validate(probabilities)
        return values


@dataclass(slots=True)
class PlattCalibrator:
    """Logistic calibration on the log odds of raw probabilities."""

    l2: float = 1e-6
    method: str = "platt"
    _model: LogisticRegression | None = None
    _constant: float | None = None

    def fit(self, probabilities: Iterable[float], labels: Iterable[int]) -> "PlattCalibrator":
        values, targets = _validate(probabilities, labels)
        assert targets is not None
        if not values:
            raise ValueError("calibration requires validation observations")
        if len(set(targets)) < 2:
            self._constant = (sum(targets) + 0.5) / (len(targets) + 1.0)
            self._model = None
            return self
        self._constant = None
        self._model = LogisticRegression(l2=self.l2, max_iterations=250)
        self._model.fit(((logit(value),) for value in values), targets)
        return self

    def transform(self, probabilities: Iterable[float]) -> tuple[float, ...]:
        values, _ = _validate(probabilities)
        if self._constant is not None:
            return tuple(self._constant for _ in values)
        if self._model is None:
            raise RuntimeError("calibrator is not fitted")
        return self._model.predict_proba((logit(value),) for value in values)


@dataclass(slots=True)
class IsotonicCalibrator:
    """Monotone piecewise-constant calibration via pair-adjacent violators."""

    method: str = "isotonic"
    thresholds_: tuple[float, ...] = ()
    values_: tuple[float, ...] = ()

    def fit(self, probabilities: Iterable[float], labels: Iterable[int]) -> "IsotonicCalibrator":
        scores, targets = _validate(probabilities, labels)
        assert targets is not None
        if not scores:
            raise ValueError("calibration requires validation observations")
        grouped: list[list[float]] = []  # [mean score, successes, weight]
        for score, target in sorted(zip(scores, targets), key=lambda item: item[0]):
            if grouped and score == grouped[-1][0]:
                grouped[-1][1] += target
                grouped[-1][2] += 1.0
            else:
                grouped.append([score, float(target), 1.0])

        blocks: list[list[float]] = []  # [weighted score, successes, weight]
        for score, successes, weight in grouped:
            blocks.append([score * weight, successes, weight])
            while len(blocks) >= 2:
                left = blocks[-2][1] / blocks[-2][2]
                right = blocks[-1][1] / blocks[-1][2]
                if left <= right:
                    break
                newer = blocks.pop()
                older = blocks.pop()
                blocks.append([older[0] + newer[0], older[1] + newer[1], older[2] + newer[2]])

        self.thresholds_ = tuple(block[0] / block[2] for block in blocks)
        # Mild Jeffreys smoothing prevents exact 0/1 probabilities and infinite log loss.
        self.values_ = tuple((block[1] + 0.5) / (block[2] + 1.0) for block in blocks)
        return self

    def transform(self, probabilities: Iterable[float]) -> tuple[float, ...]:
        scores, _ = _validate(probabilities)
        if not self.thresholds_:
            raise RuntimeError("calibrator is not fitted")
        result = []
        for score in scores:
            index = min(range(len(self.thresholds_)), key=lambda item: (abs(self.thresholds_[item] - score), item))
            # At a boundary, interpolate between adjacent monotone blocks.  Away
            # from boundaries the nearest fitted block is deliberately constant.
            result.append(self.values_[index])
        return tuple(result)


@dataclass(frozen=True, slots=True)
class ReliabilityBin:
    lower: float
    upper: float
    count: int
    mean_prediction: float | None
    event_rate: float | None


@dataclass(frozen=True, slots=True)
class CalibrationEvaluation:
    method: str
    quality: CalibrationQuality
    observation_count: int
    event_count: int
    brier_score: float | None
    log_loss: float | None
    expected_calibration_error: float | None
    calibration_intercept: float | None
    calibration_slope: float | None
    reliability: tuple[ReliabilityBin, ...]
    validation_start: date | None
    validation_end: date | None
    evaluation_start: date | None
    evaluation_end: date | None
    supported_probability_min: float | None
    supported_probability_max: float | None

    def in_supported_domain(self, raw_probability: float) -> bool:
        if self.supported_probability_min is None or self.supported_probability_max is None:
            return False
        return self.supported_probability_min <= raw_probability <= self.supported_probability_max


@dataclass(frozen=True, slots=True)
class FittedCalibration:
    calibrator: ProbabilityCalibrator
    evaluation: CalibrationEvaluation


def brier_score(labels: Sequence[int], probabilities: Sequence[float]) -> float:
    if not labels:
        raise ValueError("metrics require observations")
    return sum((probability - label) ** 2 for label, probability in zip(labels, probabilities)) / len(labels)


def binary_log_loss(labels: Sequence[int], probabilities: Sequence[float]) -> float:
    if not labels:
        raise ValueError("metrics require observations")
    total = 0.0
    for label, probability in zip(labels, probabilities):
        clipped = min(max(probability, _EPSILON), 1.0 - _EPSILON)
        total -= label * log(clipped) + (1 - label) * log(1.0 - clipped)
    return total / len(labels)


class CalibrationService:
    """Fit and audit horizon-specific probability calibration."""

    def __init__(self, *, bins: int = 10, minimum_events: int = 5, maximum_ece: float = 0.10) -> None:
        if bins < 2:
            raise ValueError("at least two reliability bins are required")
        self.bins = bins
        self.minimum_events = minimum_events
        self.maximum_ece = maximum_ece

    def fit(
        self,
        probabilities: Iterable[float],
        labels: Iterable[int],
        *,
        method: str = "platt",
        validation_dates: Iterable[date] | None = None,
        final_test_start: date | None = None,
        evaluation_probabilities: Iterable[float] | None = None,
        evaluation_labels: Iterable[int] | None = None,
        evaluation_dates: Iterable[date] | None = None,
    ) -> FittedCalibration:
        raw, targets = _validate(probabilities, labels)
        assert targets is not None
        dates = tuple(validation_dates) if validation_dates is not None else ()
        if dates and len(dates) != len(raw):
            raise ValueError("validation_dates must align with predictions")
        if dates and final_test_start is not None and max(dates) >= final_test_start:
            raise ValueError("calibration observations must precede the final test window")

        normalized = method.strip().lower().replace("-", "_")
        if normalized in {"none", "identity", "uncalibrated"}:
            calibrator: ProbabilityCalibrator = IdentityCalibrator()
        elif normalized in {"platt", "logistic"}:
            calibrator = PlattCalibrator()
        elif normalized in {"isotonic", "pav"}:
            calibrator = IsotonicCalibrator()
        else:
            raise ValueError(f"unsupported calibration method: {method}")
        calibrator.fit(raw, targets)
        assessment_supplied = evaluation_probabilities is not None or evaluation_labels is not None
        if assessment_supplied:
            if evaluation_probabilities is None or evaluation_labels is None:
                raise ValueError("both separate evaluation predictions and labels are required")
            assessment_raw, assessment_targets = _validate(evaluation_probabilities, evaluation_labels)
            assert assessment_targets is not None
            assessment_dates = tuple(evaluation_dates or ())
            if len(assessment_dates) != len(assessment_raw):
                raise ValueError("dated separate evaluation rows are required")
            if not dates:
                raise ValueError("dated calibrator-fitting rows are required for assessment")
            if dates and min(assessment_dates) <= max(dates):
                raise ValueError("calibration evaluation must follow calibrator fitting")
            if final_test_start is not None and max(assessment_dates) >= final_test_start:
                raise ValueError("calibration evaluation must precede the untouched final test")
            calibrated = calibrator.transform(assessment_raw)
            evaluation = self.evaluate(
                calibrated,
                assessment_targets,
                method=calibrator.method,
                validation_dates=dates,
                evaluation_dates=assessment_dates,
                raw_support=raw,
            )
        else:
            # In-sample calibration diagnostics are useful, but they are not an
            # independent assessment and can never authorize an ACCEPTABLE claim.
            calibrated = calibrator.transform(raw)
            evaluation = self.evaluate(
                calibrated,
                targets,
                method=calibrator.method,
                validation_dates=dates,
                raw_support=raw,
            )
            if calibrator.method != "none":
                evaluation = replace(evaluation, quality=CalibrationQuality.NOT_ASSESSED)
        return FittedCalibration(calibrator, evaluation)

    def evaluate(
        self,
        probabilities: Iterable[float],
        labels: Iterable[int],
        *,
        method: str,
        validation_dates: Iterable[date] = (),
        evaluation_dates: Iterable[date] = (),
        raw_support: Iterable[float] | None = None,
    ) -> CalibrationEvaluation:
        values, targets = _validate(probabilities, labels)
        assert targets is not None
        dates = tuple(validation_dates)
        assessment_dates = tuple(evaluation_dates)
        if assessment_dates and len(assessment_dates) != len(values):
            raise ValueError("evaluation_dates must align with predictions")
        reliability = self._reliability(values, targets)
        ece = sum(
            item.count / len(values) * abs(float(item.mean_prediction) - float(item.event_rate))
            for item in reliability
            if item.count
        ) if values else None
        intercept, slope = self._calibration_line(values, targets)
        events = sum(targets)
        if method == "none":
            quality = CalibrationQuality.UNCALIBRATED
        elif events < self.minimum_events or len(targets) - events < self.minimum_events:
            quality = CalibrationQuality.INSUFFICIENT_EVENTS
        elif ece is not None and ece <= self.maximum_ece and slope is not None and 0.5 <= slope <= 1.5:
            quality = CalibrationQuality.ACCEPTABLE
        else:
            quality = CalibrationQuality.WEAK
        support = tuple(raw_support) if raw_support is not None else values
        return CalibrationEvaluation(
            method=method,
            quality=quality,
            observation_count=len(values),
            event_count=events,
            brier_score=brier_score(targets, values) if values else None,
            log_loss=binary_log_loss(targets, values) if values else None,
            expected_calibration_error=ece,
            calibration_intercept=intercept,
            calibration_slope=slope,
            reliability=reliability,
            validation_start=min(dates) if dates else None,
            validation_end=max(dates) if dates else None,
            evaluation_start=min(assessment_dates) if assessment_dates else None,
            evaluation_end=max(assessment_dates) if assessment_dates else None,
            supported_probability_min=min(support) if support else None,
            supported_probability_max=max(support) if support else None,
        )

    def _reliability(self, values: tuple[float, ...], targets: tuple[int, ...]) -> tuple[ReliabilityBin, ...]:
        result = []
        for index in range(self.bins):
            lower = index / self.bins
            upper = (index + 1) / self.bins
            members = [
                (probability, target)
                for probability, target in zip(values, targets)
                if lower <= probability < upper or (index == self.bins - 1 and probability == 1.0)
            ]
            result.append(
                ReliabilityBin(
                    lower=lower,
                    upper=upper,
                    count=len(members),
                    mean_prediction=sum(item[0] for item in members) / len(members) if members else None,
                    event_rate=sum(item[1] for item in members) / len(members) if members else None,
                )
            )
        return tuple(result)

    @staticmethod
    def _calibration_line(values: tuple[float, ...], targets: tuple[int, ...]) -> tuple[float | None, float | None]:
        if not values or len(set(targets)) < 2:
            return None, None
        model = LogisticRegression(l2=1e-6, max_iterations=250)
        model.fit(((logit(value),) for value in values), targets)
        return model.intercept_, model.coefficients_[0]
