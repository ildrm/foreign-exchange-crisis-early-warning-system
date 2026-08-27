"""End-to-end application orchestration without presentation dependencies."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Any, Callable, Iterable, Mapping, Sequence

from .alert_service import AlertDecision, AlertService
from .feature_matrix import FeatureSample
from .forecast_service import ForecastEstimate, ForecastService
from .point_in_time import PointInTimeSelection, PointInTimeSelector, VintageMode
from .provider import ObservationProvider
from .report_service import ReportService, ReportVersions

FeatureBuilder = Callable[[str, date, Sequence[Any]], FeatureSample]


@dataclass(frozen=True, slots=True)
class AnalysisRequest:
    country_ids: tuple[str, ...]
    hazards: tuple[Any, ...]
    horizons: tuple[Any, ...]
    as_of: date
    vintage_mode: VintageMode = VintageMode.TRUE_VINTAGE
    feature_ids: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if not self.country_ids:
            raise ValueError("at least one country is required")
        if not self.hazards or not self.horizons:
            raise ValueError("at least one hazard and horizon are required")


@dataclass(frozen=True, slots=True)
class AnalysisSuiteResult:
    request: AnalysisRequest
    selections: Mapping[str, PointInTimeSelection]
    forecasts: tuple[ForecastEstimate, ...]
    alerts: tuple[AlertDecision, ...]
    report: Mapping[str, Any]


class SuiteService:
    """Join provider, point-in-time, forecast, alert, and report services."""

    def __init__(
        self,
        *,
        provider: ObservationProvider,
        feature_builder: FeatureBuilder,
        forecast_service: ForecastService,
        alert_service: AlertService | None = None,
        report_service: ReportService | None = None,
        point_in_time_selector: PointInTimeSelector | None = None,
    ) -> None:
        self.provider = provider
        self.feature_builder = feature_builder
        self.forecast_service = forecast_service
        self.alert_service = alert_service or AlertService()
        self.report_service = report_service or ReportService()
        self.point_in_time_selector = point_in_time_selector or PointInTimeSelector()

    def run(
        self,
        request: AnalysisRequest,
        *,
        versions: ReportVersions = ReportVersions(),
        probability_momentum: Mapping[tuple[str, str, str], Mapping[str, float]] | None = None,
        limitations: Iterable[str] = (),
        generated_at: datetime | None = None,
    ) -> AnalysisSuiteResult:
        selections: dict[str, PointInTimeSelection] = {}
        samples: dict[str, FeatureSample] = {}
        provenance = []
        quality_by_country: dict[str, float] = {}
        for country_id in request.country_ids:
            raw = self.provider.get_observations(
                country_id=country_id,
                feature_ids=request.feature_ids,
                period_end=request.as_of,
            )
            selection = self.point_in_time_selector.select(
                raw,
                as_of=request.as_of,
                mode=request.vintage_mode,
                latest_per_series=True,
            )
            selections[country_id] = selection
            samples[country_id] = self.feature_builder(country_id, request.as_of, selection.observations)
            provenance.extend(selection.observations)
            quality_by_country[country_id] = self._mean_quality(selection.observations)

        estimates: list[ForecastEstimate] = []
        decisions: list[AlertDecision] = []
        report_limitations = list(limitations)
        momentum = probability_momentum or {}
        for country_id, sample in samples.items():
            for hazard in request.hazards:
                for horizon in request.horizons:
                    target_sample = replace(sample, hazard=hazard, horizon=horizon)
                    estimate = self.forecast_service.forecast(target_sample, hazard=hazard, horizon=horizon)
                    estimates.append(estimate)
                    changes = momentum.get(
                        (country_id, str(getattr(hazard, "value", hazard)), str(getattr(horizon, "value", horizon))),
                        {},
                    )
                    try:
                        decision = self.alert_service.evaluate(
                            hazard=hazard,
                            horizon=horizon,
                            analysis_date=request.as_of,
                            probability=estimate.displayed_probability,
                            base_rate=estimate.base_rate,
                            coverage=estimate.data_coverage,
                            data_quality=quality_by_country[country_id],
                            calibration_status=estimate.calibration_quality,
                            ood_status="IN_DOMAIN" if estimate.calibration_in_domain else "MODEL_OUT_OF_DOMAIN",
                            calibration_in_domain=estimate.calibration_in_domain,
                            regime=sample.regime,
                            probability_change_7d=changes.get("7d"),
                            probability_change_30d=changes.get("30d"),
                            probability_change_90d=changes.get("90d"),
                            contributors=estimate.predictive_contributors,
                            country_id=country_id,
                        )
                    except KeyError:
                        message = f"No historically validated alert policy exists for {hazard}/{horizon}; no operational alert was issued."
                        if message not in report_limitations:
                            report_limitations.append(message)
                    else:
                        decisions.append(decision)

        if any(not selection.leakage_safe for selection in selections.values()):
            report_limitations.append("Historical inputs use revised-history-only data and do not constitute a genuine real-time information set.")
        resolved_modes = {selection.vintage_mode.value for selection in selections.values()}
        report_point_in_time = next(iter(resolved_modes)) if len(resolved_modes) == 1 else "MIXED"
        report = self.report_service.build(
            as_of=request.as_of,
            forecasts=estimates,
            alerts=decisions,
            versions=versions,
            point_in_time_mode=report_point_in_time,
            countries=request.country_ids,
            hazards=request.hazards,
            generated_at=generated_at,
            limitations=report_limitations,
            provenance=provenance,
            data_quality={country: quality for country, quality in quality_by_country.items()},
        )
        return AnalysisSuiteResult(request, selections, tuple(estimates), tuple(decisions), report)

    @staticmethod
    def _mean_quality(observations: Sequence[Any]) -> float:
        values = []
        for observation in observations:
            raw = getattr(observation, "base_quality", getattr(observation, "source_quality", None))
            if raw is None:
                continue
            if isinstance(raw, (int, float)):
                values.append(min(max(float(raw), 0.0), 1.0))
                continue
            text = str(getattr(raw, "value", raw)).upper()
            values.append({"HIGH": 0.9, "MEDIUM": 0.7, "LOW": 0.4, "UNRELIABLE": 0.2}.get(text, 0.5))
        return sum(values) / len(values) if values else 0.0
