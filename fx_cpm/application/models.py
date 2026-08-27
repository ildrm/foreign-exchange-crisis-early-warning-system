"""Small deterministic statistical baselines implemented with the standard library."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from math import exp, isfinite, log, log1p, sqrt
from random import Random
from typing import Any, Callable, Iterable, Mapping, Sequence

_EPSILON = 1e-12


def sigmoid(value: float) -> float:
    """Numerically stable logistic transform."""

    if value >= 0.0:
        inverse = exp(-min(value, 709.0))
        return 1.0 / (1.0 + inverse)
    direct = exp(max(value, -709.0))
    return direct / (1.0 + direct)


def logit(probability: float) -> float:
    clipped = min(max(float(probability), _EPSILON), 1.0 - _EPSILON)
    return log(clipped / (1.0 - clipped))


def _validate_matrix(features: Iterable[Sequence[float]], labels: Iterable[int]) -> tuple[tuple[tuple[float, ...], ...], tuple[int, ...]]:
    matrix = tuple(tuple(float(value) for value in row) for row in features)
    targets = tuple(int(value) for value in labels)
    if not matrix:
        raise ValueError("at least one training row is required")
    if len(matrix) != len(targets):
        raise ValueError("features and labels must have equal length")
    width = len(matrix[0])
    if width == 0 or any(len(row) != width for row in matrix):
        raise ValueError("feature matrix must be rectangular and non-empty")
    if any(target not in (0, 1) for target in targets):
        raise ValueError("binary labels must be 0 or 1")
    if any(not isfinite(value) for row in matrix for value in row):
        raise ValueError("feature matrix values must be finite")
    return matrix, targets


def _solve_linear(matrix: Sequence[Sequence[float]], vector: Sequence[float]) -> list[float]:
    """Solve a small dense linear system with partial pivoting."""

    size = len(vector)
    augmented = [list(matrix[row]) + [float(vector[row])] for row in range(size)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-14:
            augmented[pivot][column] += 1e-8
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        if abs(divisor) < 1e-20:
            raise ArithmeticError("singular model Hessian")
        for index in range(column, size + 1):
            augmented[column][index] /= divisor
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            if factor == 0.0:
                continue
            for index in range(column, size + 1):
                augmented[row][index] -= factor * augmented[column][index]
    return [augmented[row][-1] for row in range(size)]


@dataclass(slots=True)
class LogisticRegression:
    """Binary logistic regression trained by damped Newton iterations.

    The implementation is intentionally dependency-free and deterministic.  It
    is suitable as an interpretable research baseline, not a replacement for a
    mature high-dimensional optimisation library.
    """

    l2: float = 0.0
    max_iterations: int = 200
    tolerance: float = 1e-8
    class_weight: str | None = None
    coefficients_: tuple[float, ...] = field(default=(), init=False)
    intercept_: float = field(default=0.0, init=False)
    converged_: bool = field(default=False, init=False)
    n_iterations_: int = field(default=0, init=False)
    n_features_in_: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if self.l2 < 0:
            raise ValueError("l2 regularization must be non-negative")
        if self.max_iterations < 1:
            raise ValueError("max_iterations must be positive")
        if self.tolerance <= 0:
            raise ValueError("tolerance must be positive")
        if self.class_weight not in (None, "balanced"):
            raise ValueError("class_weight must be None or 'balanced'")

    def fit(
        self,
        features: Iterable[Sequence[float]],
        labels: Iterable[int],
        *,
        sample_weight: Iterable[float] | None = None,
    ) -> "LogisticRegression":
        matrix, targets = _validate_matrix(features, labels)
        self.n_features_in_ = len(matrix[0])
        weights = self._weights(targets, sample_weight)
        total_weight = sum(weights)
        positives = sum(weight for weight, target in zip(weights, targets) if target == 1)
        smoothed_rate = (positives + 0.5) / (total_weight + 1.0)
        beta = [logit(smoothed_rate)] + [0.0] * self.n_features_in_

        # A one-class window has an identifiable smoothed base rate but no slopes.
        if len(set(targets)) == 1:
            self.intercept_ = beta[0]
            self.coefficients_ = tuple(beta[1:])
            self.converged_ = True
            self.n_iterations_ = 0
            return self

        augmented = tuple((1.0,) + row for row in matrix)
        previous = self._objective(augmented, targets, weights, beta)
        ridge = max(self.l2, 0.0)
        for iteration in range(1, self.max_iterations + 1):
            dimension = len(beta)
            gradient = [0.0] * dimension
            hessian = [[0.0] * dimension for _ in range(dimension)]
            for row, target, weight in zip(augmented, targets, weights):
                probability = sigmoid(sum(coefficient * value for coefficient, value in zip(beta, row)))
                residual = weight * (probability - target) / total_weight
                curvature = weight * max(probability * (1.0 - probability), 1e-9) / total_weight
                for left in range(dimension):
                    gradient[left] += residual * row[left]
                    for right in range(left + 1):
                        hessian[left][right] += curvature * row[left] * row[right]
            for left in range(dimension):
                for right in range(left):
                    hessian[right][left] = hessian[left][right]
            for index in range(1, dimension):
                gradient[index] += ridge * beta[index]
                hessian[index][index] += ridge
            hessian[0][0] += 1e-9

            direction = _solve_linear(hessian, gradient)
            step = 1.0
            candidate = beta
            candidate_objective = previous
            while step >= 2.0 ** -20:
                trial = [value - step * delta for value, delta in zip(beta, direction)]
                trial_objective = self._objective(augmented, targets, weights, trial)
                if trial_objective <= previous + 1e-14:
                    candidate = trial
                    candidate_objective = trial_objective
                    break
                step *= 0.5
            maximum_change = max(abs(new - old) for new, old in zip(candidate, beta))
            beta = candidate
            previous = candidate_objective
            self.n_iterations_ = iteration
            if maximum_change < self.tolerance:
                self.converged_ = True
                break

        self.intercept_ = beta[0]
        self.coefficients_ = tuple(beta[1:])
        return self

    def _weights(self, labels: tuple[int, ...], sample_weight: Iterable[float] | None) -> tuple[float, ...]:
        if sample_weight is None:
            weights = [1.0] * len(labels)
        else:
            weights = [float(value) for value in sample_weight]
            if len(weights) != len(labels):
                raise ValueError("sample_weight must match labels")
            if any(not isfinite(value) or value <= 0 for value in weights):
                raise ValueError("sample weights must be positive finite values")
        if self.class_weight == "balanced" and len(set(labels)) == 2:
            positives = sum(labels)
            negatives = len(labels) - positives
            positive_weight = len(labels) / (2.0 * positives)
            negative_weight = len(labels) / (2.0 * negatives)
            weights = [
                weight * (positive_weight if label else negative_weight)
                for weight, label in zip(weights, labels)
            ]
        return tuple(weights)

    def _objective(
        self,
        rows: Sequence[Sequence[float]],
        labels: Sequence[int],
        weights: Sequence[float],
        beta: Sequence[float],
    ) -> float:
        total_weight = sum(weights)
        loss = 0.0
        for row, target, weight in zip(rows, labels, weights):
            probability = min(max(sigmoid(sum(value * coefficient for value, coefficient in zip(row, beta))), _EPSILON), 1.0 - _EPSILON)
            loss -= weight * (target * log(probability) + (1 - target) * log(1.0 - probability))
        penalty = 0.5 * self.l2 * sum(value * value for value in beta[1:])
        return loss / total_weight + penalty

    def decision_function(self, features: Iterable[Sequence[float]]) -> tuple[float, ...]:
        self._require_fitted()
        result = []
        for row in features:
            values = tuple(float(value) for value in row)
            if len(values) != self.n_features_in_:
                raise ValueError("feature count does not match fitted model")
            result.append(self.intercept_ + sum(coefficient * value for coefficient, value in zip(self.coefficients_, values)))
        return tuple(result)

    def predict_proba(self, features: Iterable[Sequence[float]]) -> tuple[float, ...]:
        return tuple(sigmoid(score) for score in self.decision_function(features))

    def contributions(self, row: Sequence[float]) -> tuple[float, ...]:
        self._require_fitted()
        if len(row) != self.n_features_in_:
            raise ValueError("feature count does not match fitted model")
        return tuple(coefficient * float(value) for coefficient, value in zip(self.coefficients_, row))

    def _require_fitted(self) -> None:
        if not self.coefficients_ and self.n_features_in_ == 0:
            raise RuntimeError("model is not fitted")


class RegularizedLogisticRegression(LogisticRegression):
    """L2-regularized logistic baseline with a non-zero default penalty."""

    def __init__(
        self,
        l2: float = 1.0,
        max_iterations: int = 200,
        tolerance: float = 1e-8,
        class_weight: str | None = None,
    ) -> None:
        super().__init__(l2=l2, max_iterations=max_iterations, tolerance=tolerance, class_weight=class_weight)


@dataclass(slots=True)
class DiscreteTimeHazardModel:
    """Logistic discrete-time hazard with interval-specific baseline terms."""

    interval_edges: tuple[int, ...] = (1, 3, 6, 12, 24, 36)
    l2: float = 1.0
    class_weight: str | None = None
    model_: LogisticRegression = field(init=False, repr=False)
    n_covariates_: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if not self.interval_edges or any(edge <= 0 for edge in self.interval_edges):
            raise ValueError("interval edges must be positive")
        if tuple(sorted(set(self.interval_edges))) != self.interval_edges:
            raise ValueError("interval edges must be strictly increasing")
        self.model_ = RegularizedLogisticRegression(l2=self.l2, class_weight=self.class_weight)

    def _time_basis(self, interval: int) -> tuple[float, ...]:
        if interval < 1:
            raise ValueError("discrete-time intervals start at 1")
        bucket = next((index for index, edge in enumerate(self.interval_edges) if interval <= edge), len(self.interval_edges))
        one_hot = tuple(1.0 if index == bucket else 0.0 for index in range(len(self.interval_edges) + 1))
        return one_hot + (log1p(interval), sqrt(interval))

    def fit(
        self,
        features: Iterable[Sequence[float]],
        event_indicators: Iterable[int],
        intervals: Iterable[int],
    ) -> "DiscreteTimeHazardModel":
        rows = tuple(tuple(float(value) for value in row) for row in features)
        durations = tuple(int(value) for value in intervals)
        labels = tuple(int(value) for value in event_indicators)
        if len(rows) != len(durations) or len(rows) != len(labels):
            raise ValueError("features, event indicators, and intervals must align")
        if not rows:
            raise ValueError("at least one person-period row is required")
        self.n_covariates_ = len(rows[0])
        expanded = [row + self._time_basis(interval) for row, interval in zip(rows, durations)]
        self.model_.fit(expanded, labels)
        return self

    def predict_conditional(self, features: Sequence[float], interval: int) -> float:
        if len(features) != self.n_covariates_:
            raise ValueError("covariate count does not match fitted hazard model")
        row = tuple(float(value) for value in features) + self._time_basis(interval)
        return self.model_.predict_proba((row,))[0]

    def cumulative_incidence(self, features: Sequence[float], horizon: int) -> float:
        if horizon < 1:
            raise ValueError("horizon must contain at least one interval")
        survival = 1.0
        for interval in range(1, horizon + 1):
            survival *= 1.0 - self.predict_conditional(features, interval)
        return min(max(1.0 - survival, 0.0), 1.0)

    def term_structure(self, features: Sequence[float], horizons: Iterable[int]) -> dict[int, float]:
        requested = tuple(sorted(set(int(horizon) for horizon in horizons)))
        if not requested or requested[0] < 1:
            raise ValueError("horizons must be positive intervals")
        survival = 1.0
        result: dict[int, float] = {}
        requested_set = set(requested)
        for interval in range(1, requested[-1] + 1):
            survival *= 1.0 - self.predict_conditional(features, interval)
            if interval in requested_set:
                result[interval] = min(max(1.0 - survival, 0.0), 1.0)
        return result


@dataclass(slots=True)
class GeneralizedAdditiveLogisticModel:
    """Interpretable GAM baseline using linear and hinge-spline terms."""

    knots_per_feature: int = 3
    l2: float = 1.0
    model_: LogisticRegression = field(init=False, repr=False)
    knots_: tuple[tuple[float, ...], ...] = field(default=(), init=False)
    n_features_in_: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if self.knots_per_feature < 1:
            raise ValueError("knots_per_feature must be positive")
        self.model_ = RegularizedLogisticRegression(l2=self.l2)

    def fit(self, features: Iterable[Sequence[float]], labels: Iterable[int]) -> "GeneralizedAdditiveLogisticModel":
        matrix, targets = _validate_matrix(features, labels)
        self.n_features_in_ = len(matrix[0])
        knots = []
        for column in range(self.n_features_in_):
            values = sorted(row[column] for row in matrix)
            selected = []
            for index in range(1, self.knots_per_feature + 1):
                position = round(index * (len(values) - 1) / (self.knots_per_feature + 1))
                selected.append(values[position])
            knots.append(tuple(sorted(set(selected))))
        self.knots_ = tuple(knots)
        self.model_.fit((self._basis(row) for row in matrix), targets)
        return self

    def _basis(self, row: Sequence[float]) -> tuple[float, ...]:
        if len(row) != self.n_features_in_:
            raise ValueError("feature count does not match fitted GAM")
        result = []
        for value, knots in zip(row, self.knots_):
            numeric = float(value)
            result.append(numeric)
            result.extend(max(0.0, numeric - knot) for knot in knots)
        return tuple(result)

    def predict_proba(self, features: Iterable[Sequence[float]]) -> tuple[float, ...]:
        return self.model_.predict_proba(self._basis(row) for row in features)


@dataclass(frozen=True, slots=True)
class _RegressionStump:
    feature: int
    threshold: float
    left_value: float
    right_value: float

    def predict(self, row: Sequence[float]) -> float:
        return self.left_value if row[self.feature] <= self.threshold else self.right_value


def _best_regression_stump(matrix: Sequence[Sequence[float]], targets: Sequence[float], feature_ids: Iterable[int] | None = None) -> _RegressionStump:
    features = tuple(feature_ids) if feature_ids is not None else tuple(range(len(matrix[0])))
    best: tuple[float, int, float, float, float] | None = None
    for feature in features:
        values = sorted(set(row[feature] for row in matrix))
        thresholds = tuple((left + right) / 2.0 for left, right in zip(values, values[1:]))
        for threshold in thresholds:
            left = [target for row, target in zip(matrix, targets) if row[feature] <= threshold]
            right = [target for row, target in zip(matrix, targets) if row[feature] > threshold]
            if not left or not right:
                continue
            left_mean = sum(left) / len(left)
            right_mean = sum(right) / len(right)
            loss = sum((value - left_mean) ** 2 for value in left) + sum((value - right_mean) ** 2 for value in right)
            candidate = (loss, feature, threshold, left_mean, right_mean)
            if best is None or candidate[:3] < best[:3]:
                best = candidate
    if best is None:
        constant = sum(targets) / len(targets)
        return _RegressionStump(features[0], float("inf"), constant, constant)
    return _RegressionStump(best[1], best[2], best[3], best[4])


@dataclass(slots=True)
class GradientBoostedTreesClassifier:
    """Deterministic log-loss gradient boosting over shallow decision trees.

    Depth-one trees keep the challenger compact and auditable while still
    capturing non-linear thresholds and interactions through sequential fits.
    """

    n_estimators: int = 50
    learning_rate: float = 0.05
    intercept_: float = field(default=0.0, init=False)
    estimators_: tuple[_RegressionStump, ...] = field(default=(), init=False)
    n_features_in_: int = field(default=0, init=False)

    def fit(self, features: Iterable[Sequence[float]], labels: Iterable[int]) -> "GradientBoostedTreesClassifier":
        matrix, targets = _validate_matrix(features, labels)
        if self.n_estimators < 1 or not 0.0 < self.learning_rate <= 1.0:
            raise ValueError("invalid boosting parameters")
        self.n_features_in_ = len(matrix[0])
        self.intercept_ = logit((sum(targets) + 0.5) / (len(targets) + 1.0))
        scores = [self.intercept_] * len(matrix)
        estimators = []
        for _ in range(self.n_estimators):
            residuals = [target - sigmoid(score) for target, score in zip(targets, scores)]
            stump = _best_regression_stump(matrix, residuals)
            estimators.append(stump)
            for index, row in enumerate(matrix):
                scores[index] += self.learning_rate * stump.predict(row)
        self.estimators_ = tuple(estimators)
        return self

    def predict_proba(self, features: Iterable[Sequence[float]]) -> tuple[float, ...]:
        result = []
        for row in features:
            values = tuple(float(value) for value in row)
            if len(values) != self.n_features_in_:
                raise ValueError("feature count does not match fitted boosted model")
            score = self.intercept_ + sum(self.learning_rate * stump.predict(values) for stump in self.estimators_)
            result.append(sigmoid(score))
        return tuple(result)


@dataclass(frozen=True, slots=True)
class _ProbabilityStump:
    feature: int
    threshold: float
    left_probability: float
    right_probability: float

    def predict(self, row: Sequence[float]) -> float:
        return self.left_probability if row[self.feature] <= self.threshold else self.right_probability


@dataclass(slots=True)
class RandomForestChallenger:
    """Seeded bagged random-subspace forest of probability stumps."""

    n_estimators: int = 100
    max_features: int | None = None
    seed: int = 0
    estimators_: tuple[_ProbabilityStump, ...] = field(default=(), init=False)
    n_features_in_: int = field(default=0, init=False)

    def fit(self, features: Iterable[Sequence[float]], labels: Iterable[int]) -> "RandomForestChallenger":
        matrix, targets = _validate_matrix(features, labels)
        if self.n_estimators < 1:
            raise ValueError("n_estimators must be positive")
        self.n_features_in_ = len(matrix[0])
        feature_count = self.max_features or max(1, int(sqrt(self.n_features_in_)))
        feature_count = min(feature_count, self.n_features_in_)
        random = Random(self.seed)
        forest = []
        for _ in range(self.n_estimators):
            indices = [random.randrange(len(matrix)) for _ in matrix]
            boot_matrix = tuple(matrix[index] for index in indices)
            boot_targets = tuple(targets[index] for index in indices)
            feature_ids = tuple(sorted(random.sample(range(self.n_features_in_), feature_count)))
            regression = _best_regression_stump(boot_matrix, boot_targets, feature_ids)
            left = [target for row, target in zip(boot_matrix, boot_targets) if row[regression.feature] <= regression.threshold]
            right = [target for row, target in zip(boot_matrix, boot_targets) if row[regression.feature] > regression.threshold]
            global_probability = (sum(boot_targets) + 0.5) / (len(boot_targets) + 1.0)
            left_probability = (sum(left) + 0.5) / (len(left) + 1.0) if left else global_probability
            right_probability = (sum(right) + 0.5) / (len(right) + 1.0) if right else global_probability
            forest.append(_ProbabilityStump(regression.feature, regression.threshold, left_probability, right_probability))
        self.estimators_ = tuple(forest)
        return self

    def predict_proba(self, features: Iterable[Sequence[float]]) -> tuple[float, ...]:
        if not self.estimators_:
            raise RuntimeError("forest is not fitted")
        result = []
        for row in features:
            values = tuple(float(value) for value in row)
            if len(values) != self.n_features_in_:
                raise ValueError("feature count does not match fitted forest")
            result.append(sum(tree.predict(values) for tree in self.estimators_) / len(self.estimators_))
        return tuple(result)


@dataclass(slots=True)
class RegimeInteractionLogisticModel:
    """Regularized logistic model with explicit feature-by-regime interactions."""

    l2: float = 1.0
    model_: LogisticRegression = field(init=False, repr=False)
    regimes_: tuple[str, ...] = field(default=(), init=False)
    n_features_in_: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self.model_ = RegularizedLogisticRegression(l2=self.l2)

    def _expand(self, row: Sequence[float], regime: Any) -> tuple[float, ...]:
        values = tuple(float(value) for value in row)
        if len(values) != self.n_features_in_:
            raise ValueError("feature count does not match fitted regime model")
        label = str(getattr(regime, "value", regime))
        indicators = tuple(1.0 if label == item else 0.0 for item in self.regimes_)
        interactions = tuple(value * indicator for indicator in indicators for value in values)
        return values + indicators + interactions

    def fit(self, features: Iterable[Sequence[float]], labels: Iterable[int], regimes: Iterable[Any]) -> "RegimeInteractionLogisticModel":
        matrix, targets = _validate_matrix(features, labels)
        regime_rows = tuple(str(getattr(value, "value", value)) for value in regimes)
        if len(regime_rows) != len(matrix):
            raise ValueError("regimes must align with features")
        self.n_features_in_ = len(matrix[0])
        self.regimes_ = tuple(sorted(set(regime_rows)))
        self.model_.fit((self._expand(row, regime) for row, regime in zip(matrix, regime_rows)), targets)
        return self

    def predict_proba(self, features: Iterable[Sequence[float]], regimes: Iterable[Any]) -> tuple[float, ...]:
        rows = tuple(features)
        regime_rows = tuple(regimes)
        if len(rows) != len(regime_rows):
            raise ValueError("regimes must align with features")
        return self.model_.predict_proba(self._expand(row, regime) for row, regime in zip(rows, regime_rows))


@dataclass(slots=True)
class CompetingRiskHazardModel:
    """Cause-specific discrete hazards combined into cumulative incidence."""

    causes: tuple[str, ...]
    interval_edges: tuple[int, ...] = (1, 3, 6, 12, 24, 36)
    l2: float = 1.0
    models_: dict[str, DiscreteTimeHazardModel] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self.causes = tuple(dict.fromkeys(str(cause) for cause in self.causes))
        if len(self.causes) < 2:
            raise ValueError("competing-risk model requires at least two causes")

    def fit(self, features: Iterable[Sequence[float]], outcomes: Iterable[str | None], intervals: Iterable[int]) -> "CompetingRiskHazardModel":
        matrix = tuple(tuple(float(value) for value in row) for row in features)
        labels = tuple(None if value is None else str(value) for value in outcomes)
        durations = tuple(intervals)
        if len(matrix) != len(labels) or len(matrix) != len(durations):
            raise ValueError("competing-risk training arrays must align")
        unknown = {label for label in labels if label is not None} - set(self.causes)
        if unknown:
            raise ValueError(f"unknown competing causes: {sorted(unknown)}")
        self.models_ = {}
        for cause in self.causes:
            model = DiscreteTimeHazardModel(self.interval_edges, self.l2)
            model.fit(matrix, (int(label == cause) for label in labels), durations)
            self.models_[cause] = model
        return self

    def term_structure(self, features: Sequence[float], horizons: Iterable[int]) -> dict[int, dict[str, float]]:
        if not self.models_:
            raise RuntimeError("competing-risk model is not fitted")
        requested = tuple(sorted(set(int(value) for value in horizons)))
        if not requested or requested[0] < 1:
            raise ValueError("horizons must be positive")
        survival = 1.0
        cumulative = {cause: 0.0 for cause in self.causes}
        result = {}
        for interval in range(1, requested[-1] + 1):
            hazards = {cause: model.predict_conditional(features, interval) for cause, model in self.models_.items()}
            total = sum(hazards.values())
            if total > 1.0:
                hazards = {cause: value / total for cause, value in hazards.items()}
                total = 1.0
            for cause, hazard in hazards.items():
                cumulative[cause] += survival * hazard
            survival *= 1.0 - total
            if interval in requested:
                result[interval] = dict(cumulative)
        return result


@dataclass(slots=True)
class CalibratedStackingModel:
    """Logistic stack fitted only on held-out base-model predictions."""

    l2: float = 1.0
    model_: LogisticRegression = field(init=False, repr=False)
    validation_start_: date | None = field(default=None, init=False)
    validation_end_: date | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.model_ = RegularizedLogisticRegression(l2=self.l2)

    def fit(
        self,
        base_predictions: Iterable[Sequence[float]],
        labels: Iterable[int],
        *,
        validation_dates: Iterable[date],
        final_test_start: date,
    ) -> "CalibratedStackingModel":
        matrix, targets = _validate_matrix(base_predictions, labels)
        dates = tuple(validation_dates)
        if len(dates) != len(matrix):
            raise ValueError("validation dates must align with stack rows")
        if not dates or max(dates) >= final_test_start:
            raise ValueError("stacking calibration data must precede the final test")
        if any(value < 0.0 or value > 1.0 for row in matrix for value in row):
            raise ValueError("base-model predictions must be probabilities")
        self.validation_start_, self.validation_end_ = min(dates), max(dates)
        self.model_.fit(tuple(tuple(logit(value) for value in row) for row in matrix), targets)
        return self

    def predict_proba(self, base_predictions: Iterable[Sequence[float]]) -> tuple[float, ...]:
        rows = tuple(tuple(logit(value) for value in row) for row in base_predictions)
        return self.model_.predict_proba(rows)


@dataclass(frozen=True, slots=True)
class TournamentScore:
    name: str
    average_precision: float
    brier_score: float
    log_loss: float
    predictions: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class TournamentResult:
    scores: tuple[TournamentScore, ...]
    winner: str
    selection_rule: str


@dataclass(frozen=True, slots=True)
class ModelFamilySpec:
    name: str
    adapter: str
    context_specific: bool
    evaluation_contract: str


REQUIRED_MODEL_FAMILIES = (
    ModelFamilySpec("logistic", "LogisticRegression", False, "binary fit/predict on chronological holdout"),
    ModelFamilySpec("regularized_logistic", "RegularizedLogisticRegression", False, "binary fit/predict on chronological holdout"),
    ModelFamilySpec("discrete_time_hazard", "DiscreteTimeHazardModel", True, "person-period rows and interval indices"),
    ModelFamilySpec("competing_risk", "CompetingRiskHazardModel", True, "cause-labelled person-period rows"),
    ModelFamilySpec("generalized_additive", "GeneralizedAdditiveLogisticModel", False, "binary fit/predict on chronological holdout"),
    ModelFamilySpec("gradient_boosted_trees", "GradientBoostedTreesClassifier", False, "binary fit/predict on chronological holdout"),
    ModelFamilySpec("random_forest", "RandomForestChallenger", False, "binary fit/predict on chronological holdout"),
    ModelFamilySpec("regime_interaction", "RegimeInteractionLogisticModel", True, "rows plus historical FX-regime labels"),
    ModelFamilySpec("calibrated_ensemble_stack", "CalibratedStackingModel", True, "held-out base predictions before untouched final test"),
)


class ModelTournament:
    """Generic binary challengers evaluated on a chronological holdout.

    ``REQUIRED_MODEL_FAMILIES`` is the complete tournament manifest. Hazard,
    competing-risk, regime, and stacking entries use their context-specific
    adapters because pretending they share a generic binary fit signature would
    weaken their scientific contracts.
    """

    manifest = REQUIRED_MODEL_FAMILIES

    def __init__(self, candidates: Mapping[str, Callable[[], Any]] | None = None) -> None:
        self.candidates = dict(candidates or {
            "logistic": LogisticRegression,
            "regularized_logistic": RegularizedLogisticRegression,
            "gam": GeneralizedAdditiveLogisticModel,
            "gradient_boosted_trees": GradientBoostedTreesClassifier,
            "random_forest": RandomForestChallenger,
        })

    def evaluate(
        self,
        train_features: Iterable[Sequence[float]],
        train_labels: Iterable[int],
        test_features: Iterable[Sequence[float]],
        test_labels: Iterable[int],
        *,
        train_dates: Iterable[date] | None = None,
        test_dates: Iterable[date] | None = None,
    ) -> TournamentResult:
        x_train, y_train = _validate_matrix(train_features, train_labels)
        x_test, y_test = _validate_matrix(test_features, test_labels)
        if len(x_train[0]) != len(x_test[0]):
            raise ValueError("train and test feature dimensions differ")
        if train_dates is not None or test_dates is not None:
            left = tuple(train_dates or ())
            right = tuple(test_dates or ())
            if len(left) != len(x_train) or len(right) != len(x_test):
                raise ValueError("chronology dates must align with model rows")
            if not left or not right or max(left) >= min(right):
                raise ValueError("tournament test observations must strictly follow training")
        scores = []
        positives = sum(y_test)
        for name in sorted(self.candidates):
            model = self.candidates[name]()
            model.fit(x_train, y_train)
            predictions = tuple(model.predict_proba(x_test))
            ordered = sorted(zip(predictions, y_test), reverse=True)
            tp = 0
            ap = 0.0
            if positives:
                for rank, (_, target) in enumerate(ordered, start=1):
                    if target:
                        tp += 1
                        ap += tp / rank / positives
            brier = sum((prediction - target) ** 2 for prediction, target in zip(predictions, y_test)) / len(y_test)
            loss = -sum(target * log(max(prediction, _EPSILON)) + (1 - target) * log(max(1.0 - prediction, _EPSILON)) for prediction, target in zip(predictions, y_test)) / len(y_test)
            scores.append(TournamentScore(name, ap, brier, loss, predictions))
        ranked = sorted(scores, key=lambda item: (-item.average_precision, item.brier_score, item.log_loss, item.name))
        return TournamentResult(tuple(scores), ranked[0].name, "max average precision; then min Brier, log loss, and name")
