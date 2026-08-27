"""Chronological backtesting, geographic holdouts, and rare-event metrics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from math import ceil, log
from statistics import mean, median
from typing import Any, Callable, Iterable, Sequence

from .feature_matrix import FeatureSample, without_features
from .forecast_service import ForecastEstimate, ForecastService
from .point_in_time import VintageMode

_EPSILON = 1e-12


def _validate_predictions(labels: Iterable[int], probabilities: Iterable[float]) -> tuple[tuple[int, ...], tuple[float, ...]]:
    targets = tuple(int(value) for value in labels)
    scores = tuple(float(value) for value in probabilities)
    if not targets or len(targets) != len(scores):
        raise ValueError("labels and probabilities must be non-empty and aligned")
    if any(target not in (0, 1) for target in targets):
        raise ValueError("labels must be binary")
    if any(score < 0.0 or score > 1.0 for score in scores):
        raise ValueError("probabilities must lie in [0, 1]")
    return targets, scores


def average_precision(labels: Iterable[int], probabilities: Iterable[float]) -> float:
    """Threshold-grouped non-interpolated average precision."""

    targets, scores = _validate_predictions(labels, probabilities)
    positives = sum(targets)
    if positives == 0:
        return 0.0
    groups: dict[float, list[int]] = {}
    for target, score in zip(targets, scores):
        groups.setdefault(score, []).append(target)
    true_positives = false_positives = 0
    previous_recall = 0.0
    result = 0.0
    for score in sorted(groups, reverse=True):
        group = groups[score]
        true_positives += sum(group)
        false_positives += len(group) - sum(group)
        recall = true_positives / positives
        precision = true_positives / (true_positives + false_positives)
        result += (recall - previous_recall) * precision
        previous_recall = recall
    return result


def precision_recall_auc(labels: Iterable[int], probabilities: Iterable[float]) -> float:
    targets, scores = _validate_predictions(labels, probabilities)
    positives = sum(targets)
    if positives == 0:
        return 0.0
    groups: dict[float, list[int]] = {}
    for target, score in zip(targets, scores):
        groups.setdefault(score, []).append(target)
    points = [(0.0, 1.0)]
    tp = fp = 0
    for score in sorted(groups, reverse=True):
        values = groups[score]
        tp += sum(values)
        fp += len(values) - sum(values)
        points.append((tp / positives, tp / (tp + fp)))
    area = 0.0
    for (left_recall, left_precision), (right_recall, right_precision) in zip(points, points[1:]):
        area += (right_recall - left_recall) * (left_precision + right_precision) / 2.0
    return area


def roc_auc(labels: Iterable[int], probabilities: Iterable[float]) -> float | None:
    """Mann-Whitney ROC AUC with average ranks for ties."""

    targets, scores = _validate_predictions(labels, probabilities)
    positives = sum(targets)
    negatives = len(targets) - positives
    if positives == 0 or negatives == 0:
        return None
    ordered = sorted(enumerate(scores), key=lambda item: item[1])
    rank_sum = 0.0
    cursor = 0
    while cursor < len(ordered):
        end = cursor + 1
        while end < len(ordered) and ordered[end][1] == ordered[cursor][1]:
            end += 1
        average_rank = ((cursor + 1) + end) / 2.0
        rank_sum += average_rank * sum(targets[index] for index, _ in ordered[cursor:end])
        cursor = end
    return (rank_sum - positives * (positives + 1) / 2.0) / (positives * negatives)


@dataclass(frozen=True, slots=True)
class RareEventMetrics:
    observation_count: int
    event_count: int
    base_rate: float
    average_precision: float
    pr_auc: float
    roc_auc: float | None
    brier_score: float
    log_loss: float
    threshold: float
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int
    recall: float | None
    precision: float | None
    false_positive_rate: float | None
    false_alert_rate: float | None
    missed_crisis_rate: float | None
    recall_at_fixed_fpr: float | None
    fixed_fpr: float
    precision_at_alert_rate: float | None
    operational_alert_rate: float
    mean_warning_lead_days: float | None
    median_warning_lead_days: float | None


def rare_event_metrics(
    labels: Iterable[int],
    probabilities: Iterable[float],
    *,
    threshold: float = 0.5,
    fixed_fpr: float = 0.10,
    operational_alert_rate: float = 0.10,
    samples: Sequence[FeatureSample] | None = None,
) -> RareEventMetrics:
    targets, scores = _validate_predictions(labels, probabilities)
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must lie in [0, 1]")
    predictions = tuple(score >= threshold for score in scores)
    tp = sum(target == 1 and prediction for target, prediction in zip(targets, predictions))
    fp = sum(target == 0 and prediction for target, prediction in zip(targets, predictions))
    tn = sum(target == 0 and not prediction for target, prediction in zip(targets, predictions))
    fn = sum(target == 1 and not prediction for target, prediction in zip(targets, predictions))
    recall_fixed = _recall_at_fpr(targets, scores, fixed_fpr)
    alert_count = min(len(scores), max(1, ceil(len(scores) * operational_alert_rate)))
    top = sorted(range(len(scores)), key=lambda index: (-scores[index], index))[:alert_count]
    precision_operational = sum(targets[index] for index in top) / alert_count if top else None
    leads = _lead_times(targets, scores, threshold, samples)
    return RareEventMetrics(
        observation_count=len(targets),
        event_count=sum(targets),
        base_rate=sum(targets) / len(targets),
        average_precision=average_precision(targets, scores),
        pr_auc=precision_recall_auc(targets, scores),
        roc_auc=roc_auc(targets, scores),
        brier_score=sum((score - target) ** 2 for target, score in zip(targets, scores)) / len(targets),
        log_loss=-sum(
            target * log(min(max(score, _EPSILON), 1.0 - _EPSILON))
            + (1 - target) * log(1.0 - min(max(score, _EPSILON), 1.0 - _EPSILON))
            for target, score in zip(targets, scores)
        ) / len(targets),
        threshold=threshold,
        true_positives=tp,
        false_positives=fp,
        true_negatives=tn,
        false_negatives=fn,
        recall=tp / (tp + fn) if tp + fn else None,
        precision=tp / (tp + fp) if tp + fp else None,
        false_positive_rate=fp / (fp + tn) if fp + tn else None,
        false_alert_rate=fp / (tp + fp) if tp + fp else None,
        missed_crisis_rate=fn / (tp + fn) if tp + fn else None,
        recall_at_fixed_fpr=recall_fixed,
        fixed_fpr=fixed_fpr,
        precision_at_alert_rate=precision_operational,
        operational_alert_rate=operational_alert_rate,
        mean_warning_lead_days=mean(leads) if leads else None,
        median_warning_lead_days=median(leads) if leads else None,
    )


def _recall_at_fpr(targets: tuple[int, ...], scores: tuple[float, ...], maximum_fpr: float) -> float | None:
    positives = sum(targets)
    negatives = len(targets) - positives
    if positives == 0 or negatives == 0:
        return None
    best = 0.0
    for threshold in sorted(set(scores), reverse=True):
        tp = sum(target == 1 and score >= threshold for target, score in zip(targets, scores))
        fp = sum(target == 0 and score >= threshold for target, score in zip(targets, scores))
        if fp / negatives <= maximum_fpr + 1e-15:
            best = max(best, tp / positives)
    return best


def _lead_times(
    targets: tuple[int, ...],
    scores: tuple[float, ...],
    threshold: float,
    samples: Sequence[FeatureSample] | None,
) -> tuple[int, ...]:
    if samples is None or len(samples) != len(targets):
        return ()
    earliest: dict[tuple[str, str], tuple[date, date]] = {}
    for target, score, sample in zip(targets, scores, samples):
        if target != 1 or score < threshold or sample.event_date is None or sample.analysis_date > sample.event_date:
            continue
        key = (sample.country_id, sample.event_id or sample.event_date.isoformat())
        current = earliest.get(key)
        if current is None or sample.analysis_date < current[0]:
            earliest[key] = (sample.analysis_date, sample.event_date)
    return tuple((event_date - alert_date).days for alert_date, event_date in earliest.values())


@dataclass(frozen=True, slots=True)
class BacktestWindow:
    name: str
    train_end: date
    test_start: date
    test_end: date
    calibration_start: date | None = None
    calibration_end: date | None = None

    def __post_init__(self) -> None:
        if self.test_start > self.test_end:
            raise ValueError("test_start cannot follow test_end")
        if self.train_end >= self.test_start:
            raise ValueError("training period must end before the test period")
        if (self.calibration_start is None) != (self.calibration_end is None):
            raise ValueError("both calibration boundaries are required")
        if self.calibration_start is not None:
            assert self.calibration_end is not None
            if not self.train_end < self.calibration_start <= self.calibration_end < self.test_start:
                raise ValueError("calibration must be strictly between training and test periods")


@dataclass(frozen=True, slots=True)
class BacktestPrediction:
    window_name: str
    sample: FeatureSample
    estimate: ForecastEstimate


@dataclass(frozen=True, slots=True)
class BacktestWindowResult:
    window: BacktestWindow
    training_count: int
    calibration_count: int
    test_count: int
    training_latest_date: date
    calibration_latest_date: date | None
    predictions: tuple[BacktestPrediction, ...]
    metrics: RareEventMetrics


@dataclass(frozen=True, slots=True)
class BacktestRun:
    hazard: Any
    horizon: Any
    vintage_mode: VintageMode
    windows: tuple[BacktestWindowResult, ...]
    aggregate_metrics: RareEventMetrics

    @property
    def genuine_real_time(self) -> bool:
        return self.vintage_mode is VintageMode.TRUE_VINTAGE


@dataclass(frozen=True, slots=True)
class HoldoutSplit:
    kind: str
    held_out: tuple[str, ...]
    training: tuple[FeatureSample, ...]
    testing: tuple[FeatureSample, ...]

    def assert_disjoint(self) -> None:
        training_ids = {id(sample) for sample in self.training}
        if any(id(sample) in training_ids for sample in self.testing):
            raise AssertionError("holdout training and testing rows overlap")


@dataclass(frozen=True, slots=True)
class FXAblationResult:
    without_fx: BacktestRun
    with_fx: BacktestRun
    delta_average_precision: float
    delta_pr_auc: float
    brier_improvement: float
    log_loss_improvement: float
    recall_change: float | None
    false_alert_rate_change: float | None
    lead_time_change_days: float | None


class BacktestService:
    """Run expanding-window evaluation without any random time split."""

    def __init__(self, forecast_service_factory: Callable[[], ForecastService] = ForecastService) -> None:
        self.forecast_service_factory = forecast_service_factory

    def run_expanding(
        self,
        samples: Iterable[FeatureSample],
        windows: Iterable[BacktestWindow],
        *,
        hazard: Any,
        horizon: Any,
        vintage_mode: VintageMode | str = VintageMode.REVISED_HISTORY_ONLY,
        threshold: float = 0.5,
        calibration_method: str = "platt",
        regularized: bool = True,
        l2: float = 1.0,
        model_version: str = "backtest-logit-1.0",
    ) -> BacktestRun:
        rows = tuple(sorted(samples, key=lambda sample: (sample.analysis_date, sample.country_id)))
        if any(sample.target is None for sample in rows):
            raise ValueError("backtests require labels for every sample")
        mode = (
            vintage_mode
            if isinstance(vintage_mode, VintageMode)
            else VintageMode(str(getattr(vintage_mode, "value", vintage_mode)).upper())
        )
        results: list[BacktestWindowResult] = []
        all_predictions: list[BacktestPrediction] = []
        for window in windows:
            training = tuple(sample for sample in rows if sample.analysis_date <= window.train_end)
            calibration = (
                tuple(
                    sample
                    for sample in rows
                    if window.calibration_start <= sample.analysis_date <= window.calibration_end
                )
                if window.calibration_start is not None and window.calibration_end is not None
                else ()
            )
            testing = tuple(sample for sample in rows if window.test_start <= sample.analysis_date <= window.test_end)
            if not training or not testing:
                raise ValueError(f"window {window.name!r} has an empty training or test partition")
            if max(sample.analysis_date for sample in training) >= min(sample.analysis_date for sample in testing):
                raise AssertionError("training observations overlap the future test period")
            service = self.forecast_service_factory()
            service.fit(
                training,
                hazard=hazard,
                horizon=horizon,
                model_version=model_version,
                regularized=regularized,
                l2=l2,
                validation_samples=calibration,
                calibration_method=calibration_method,
                final_test_start=window.test_start,
            )
            predictions = tuple(
                BacktestPrediction(window.name, sample, service.forecast(sample, hazard=hazard, horizon=horizon))
                for sample in testing
            )
            scores = tuple(item.estimate.displayed_probability for item in predictions)
            labels = tuple(int(item.sample.target) for item in predictions if item.sample.target is not None)
            metrics = rare_event_metrics(labels, scores, threshold=threshold, samples=testing)
            result = BacktestWindowResult(
                window=window,
                training_count=len(training),
                calibration_count=len(calibration),
                test_count=len(testing),
                training_latest_date=max(sample.analysis_date for sample in training),
                calibration_latest_date=max((sample.analysis_date for sample in calibration), default=None),
                predictions=predictions,
                metrics=metrics,
            )
            results.append(result)
            all_predictions.extend(predictions)
        if not all_predictions:
            raise ValueError("at least one backtest window is required")
        aggregate_samples = tuple(item.sample for item in all_predictions)
        aggregate_labels = tuple(int(item.sample.target) for item in all_predictions if item.sample.target is not None)
        aggregate_scores = tuple(item.estimate.displayed_probability for item in all_predictions)
        aggregate = rare_event_metrics(
            aggregate_labels,
            aggregate_scores,
            threshold=threshold,
            samples=aggregate_samples,
        )
        return BacktestRun(hazard, horizon, mode, tuple(results), aggregate)

    @staticmethod
    def country_holdout(
        samples: Iterable[FeatureSample],
        held_out_countries: Iterable[str],
        *,
        train_end: date | None = None,
        test_start: date | None = None,
    ) -> HoldoutSplit:
        held = frozenset(held_out_countries)
        rows = tuple(samples)
        training = tuple(
            sample for sample in rows
            if sample.country_id not in held and (train_end is None or sample.analysis_date <= train_end)
        )
        testing = tuple(
            sample for sample in rows
            if sample.country_id in held and (test_start is None or sample.analysis_date >= test_start)
        )
        return HoldoutSplit("country", tuple(sorted(held)), training, testing)

    @staticmethod
    def crisis_cluster_holdout(
        samples: Iterable[FeatureSample],
        held_out_clusters: Iterable[str],
    ) -> HoldoutSplit:
        held = frozenset(held_out_clusters)
        rows = tuple(samples)
        training = tuple(sample for sample in rows if sample.cluster_id not in held)
        testing = tuple(sample for sample in rows if sample.cluster_id in held)
        return HoldoutSplit("crisis_cluster", tuple(sorted(held)), training, testing)

    @staticmethod
    def regime_holdout(samples: Iterable[FeatureSample], held_out_regimes: Iterable[Any]) -> HoldoutSplit:
        held = frozenset(str(getattr(value, "value", value)) for value in held_out_regimes)
        rows = tuple(samples)
        training = tuple(sample for sample in rows if str(getattr(sample.regime, "value", sample.regime)) not in held)
        testing = tuple(sample for sample in rows if str(getattr(sample.regime, "value", sample.regime)) in held)
        return HoldoutSplit("regime", tuple(sorted(held)), training, testing)

    def run_fx_ablation(
        self,
        samples: Iterable[FeatureSample],
        windows: Iterable[BacktestWindow],
        *,
        fx_features: Iterable[str],
        hazard: Any,
        horizon: Any,
        vintage_mode: VintageMode | str = VintageMode.REVISED_HISTORY_ONLY,
        threshold: float = 0.5,
    ) -> FXAblationResult:
        rows = tuple(samples)
        window_rows = tuple(windows)
        excluded = tuple(fx_features)
        if not excluded:
            raise ValueError("FX ablation requires at least one named FX feature")
        non_fx = tuple(without_features(sample, excluded) for sample in rows)
        baseline = self.run_expanding(
            non_fx,
            window_rows,
            hazard=hazard,
            horizon=horizon,
            vintage_mode=vintage_mode,
            threshold=threshold,
        )
        enhanced = self.run_expanding(
            rows,
            window_rows,
            hazard=hazard,
            horizon=horizon,
            vintage_mode=vintage_mode,
            threshold=threshold,
        )
        left = baseline.aggregate_metrics
        right = enhanced.aggregate_metrics
        return FXAblationResult(
            without_fx=baseline,
            with_fx=enhanced,
            delta_average_precision=right.average_precision - left.average_precision,
            delta_pr_auc=right.pr_auc - left.pr_auc,
            brier_improvement=left.brier_score - right.brier_score,
            log_loss_improvement=left.log_loss - right.log_loss,
            recall_change=_difference(right.recall, left.recall),
            false_alert_rate_change=_difference(right.false_alert_rate, left.false_alert_rate),
            lead_time_change_days=_difference(right.mean_warning_lead_days, left.mean_warning_lead_days),
        )


def _difference(right: float | None, left: float | None) -> float | None:
    return right - left if right is not None and left is not None else None


def expanding_windows(boundaries: Iterable[tuple[date, date]], *, prefix: str = "window") -> tuple[BacktestWindow, ...]:
    """Create contiguous expanding windows from ``(train_end, test_end)`` pairs."""

    result = []
    for index, (train_end, test_end) in enumerate(boundaries, start=1):
        result.append(
            BacktestWindow(
                name=f"{prefix}_{index}",
                train_end=train_end,
                test_start=train_end + timedelta(days=1),
                test_end=test_end,
            )
        )
    return tuple(result)
