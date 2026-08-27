"""Transparent non-probabilistic aggregation of separate hazard stress scores."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from .taxonomy import HazardType
from .validation import DomainValidationError, require_finite, require_positive, require_probability


def _stress_score(value: float, field: str) -> float:
    score = require_finite(value, field)
    if not 0.0 <= score <= 100.0:
        raise DomainValidationError(f"{field} must be between 0 and 100")
    return score


@dataclass(frozen=True, slots=True)
class SystemicStressContribution:
    hazard: HazardType
    hazard_stress_score: float
    configured_weight: float
    normalized_available_weight: float
    index_points: float


@dataclass(frozen=True, slots=True)
class SystemicStressIndex:
    """A 0--100 weighted stress summary, explicitly not a probability."""

    score: float | None
    coverage: float
    contributions: tuple[SystemicStressContribution, ...]
    missing_hazards: tuple[HazardType, ...]
    elevated_hazards: tuple[HazardType, ...]
    elevated_threshold: float
    label: str = "SYSTEMIC_STRESS_INDEX"
    methodology: str = (
        "available-weight-renormalized arithmetic mean of 0-100 hazard stress scores; "
        "missing hazards are not zero; no probability independence calculation"
    )
    is_probability: bool = False

    def __post_init__(self) -> None:
        if self.score is not None:
            _stress_score(self.score, "score")
        require_probability(self.coverage, "coverage")
        _stress_score(self.elevated_threshold, "elevated_threshold")
        if self.is_probability:
            raise DomainValidationError("SystemicStressIndex must not be labelled as a probability")
        if self.score is not None and not math.isclose(
            self.score,
            math.fsum(item.index_points for item in self.contributions),
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise DomainValidationError("systemic stress contributions must sum to score")


def calculate_systemic_stress_index(
    hazard_stress_scores: Mapping[HazardType | str, float | None],
    *,
    weights: Mapping[HazardType | str, float] | None = None,
    minimum_coverage: float = 0.5,
    elevated_threshold: float = 60.0,
) -> SystemicStressIndex:
    """Aggregate multiple hazard *stress scores* with an arithmetic mean.

    Inputs are descriptive 0--100 stress scores, not crisis probabilities.
    Missing hazards reduce reported coverage and are never replaced with zero.
    """

    if len(hazard_stress_scores) < 2:
        raise DomainValidationError("SystemicStressIndex requires at least two hazards")
    require_probability(minimum_coverage, "minimum_coverage")
    elevated_threshold = _stress_score(elevated_threshold, "elevated_threshold")
    scores: dict[HazardType, float | None] = {}
    for raw_hazard, value in hazard_stress_scores.items():
        hazard = HazardType.parse(raw_hazard)
        if hazard in scores:
            raise DomainValidationError(f"duplicate hazard after normalization: {hazard.code}")
        scores[hazard] = (
            None if value is None else _stress_score(value, f"hazard_stress_scores[{hazard.code}]")
        )
    if weights is None:
        configured = {hazard: 1.0 for hazard in scores}
    else:
        configured: dict[HazardType, float] = {}
        for raw_hazard, weight in weights.items():
            hazard = HazardType.parse(raw_hazard)
            if hazard in configured:
                raise DomainValidationError(f"duplicate weight after normalization: {hazard.code}")
            configured[hazard] = require_positive(
                weight, f"weights[{hazard.code}]", allow_zero=True
            )
        if set(configured) != set(scores):
            raise DomainValidationError("weights must have exactly the same hazards as scores")
    total_weight = math.fsum(configured.values())
    if total_weight <= 0.0:
        raise DomainValidationError("at least one systemic stress weight must be positive")
    if sum(weight > 0.0 for weight in configured.values()) < 2:
        raise DomainValidationError(
            "SystemicStressIndex requires positive weight on at least two hazards"
        )
    available = tuple(
        (hazard, score, configured[hazard])
        for hazard, score in sorted(scores.items(), key=lambda item: item[0].code)
        if score is not None and configured[hazard] > 0.0
    )
    available_weight = math.fsum(weight for _, _, weight in available)
    coverage = available_weight / total_weight
    missing = tuple(
        hazard
        for hazard, score in sorted(scores.items(), key=lambda item: item[0].code)
        if score is None
    )
    elevated = tuple(
        hazard for hazard, score, _ in available if score >= elevated_threshold
    )
    if coverage < minimum_coverage or available_weight == 0.0:
        return SystemicStressIndex(
            score=None,
            coverage=coverage,
            contributions=(),
            missing_hazards=missing,
            elevated_hazards=elevated,
            elevated_threshold=elevated_threshold,
        )
    contributions = tuple(
        SystemicStressContribution(
            hazard=hazard,
            hazard_stress_score=score,
            configured_weight=weight,
            normalized_available_weight=weight / available_weight,
            index_points=score * weight / available_weight,
        )
        for hazard, score, weight in available
    )
    return SystemicStressIndex(
        score=math.fsum(item.index_points for item in contributions),
        coverage=coverage,
        contributions=contributions,
        missing_hazards=missing,
        elevated_hazards=elevated,
        elevated_threshold=elevated_threshold,
    )
