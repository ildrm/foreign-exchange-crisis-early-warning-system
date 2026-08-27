from __future__ import annotations

from datetime import date, datetime, timezone

from fx_cpm.application.alert_service import (
    AlertPolicyConfig,
    AlertService,
    AlertThresholds,
    ThresholdValidationArtifact,
)
from fx_cpm.application.feature_matrix import FeatureSample
from fx_cpm.application.forecast_service import ForecastService
from fx_cpm.application.point_in_time import VintageMode
from fx_cpm.application.provider import InMemoryProvider, ObservationProvider
from fx_cpm.application.report_service import REQUIRED_REPORT_SECTIONS, ReportVersions
from fx_cpm.application.suite_service import AnalysisRequest, SuiteService
from fx_cpm.domain.observations import Observation
from fx_cpm.reporting import validate_report


def current_observation(feature_id: str, value: float) -> Observation:
    return Observation(
        feature_id=feature_id,
        country_id="xx",
        currency_id="xxc",
        value=value,
        unit="index",
        frequency="monthly",
        period_start=date(2019, 12, 1),
        period_end=date(2019, 12, 31),
        release_date=date(2020, 1, 15),
        retrieval_date=date(2020, 1, 16),
        vintage="2020-01-15",
        source_name="offline fixture",
        source_url="https://example.test",
        source_type="official_statistics",
        license="CC-BY-4.0",
        base_quality=0.95,
        revision_status="first_release",
        provenance_type="raw",
    )


def test_full_offline_suite_retains_point_in_time_and_probability_metadata() -> None:
    training = tuple(
        FeatureSample(
            "xx",
            date(1990 + index, 1, 1),
            {"fx_emp": float(index % 3), "reserves": float(20 - index)},
            index % 2,
            hazard="fx",
            horizon="12m",
        )
        for index in range(20)
    )
    validation = tuple(
        FeatureSample(
            "xx",
            date(2010 + index, 1, 1),
            {"fx_emp": float(index % 3), "reserves": float(10 - index)},
            index % 2,
            hazard="fx",
            horizon="12m",
        )
        for index in range(10)
    )
    forecast_service = ForecastService()
    forecast_service.fit(
        training,
        hazard="fx",
        horizon="12m",
        validation_samples=validation,
        final_test_start=date(2020, 1, 1),
    )
    provider = InMemoryProvider(
        observations=[current_observation("fx_emp", 2.5), current_observation("reserves", 3.0)]
    )
    assert isinstance(provider, ObservationProvider)

    def build_features(country_id: str, as_of: date, observations: tuple[Observation, ...]) -> FeatureSample:
        return FeatureSample(
            country_id,
            as_of,
            {item.feature_id: item.value for item in observations},
            model_tier="modern_market_enhanced",
        )

    alerts = AlertService()
    methodology = "chronological validation utility threshold"
    alerts.register(
        AlertPolicyConfig(
            hazard="fx",
            horizon="12m",
            thresholds=AlertThresholds(0.10, 0.20, 0.35, 0.50),
            methodology=methodology,
            validation_artifact=ThresholdValidationArtifact.create(
                hazard="fx",
                horizon="12m",
                validation_start=date(1990, 1, 1),
                validation_end=date(2019, 12, 31),
                event_count=15,
                loss_utility_methodology=methodology,
                policy_version="fixture-alert-1.0",
            ),
        )
    )
    suite = SuiteService(
        provider=provider,
        feature_builder=build_features,
        forecast_service=forecast_service,
        alert_service=alerts,
    )
    request = AnalysisRequest(("xx",), ("fx",), ("12m",), date(2020, 6, 1), VintageMode.TRUE_VINTAGE)
    result = suite.run(
        request,
        versions=ReportVersions(model="fixture-model", calibration="fixture-calibration"),
        generated_at=datetime(2020, 6, 2, tzinfo=timezone.utc),
    )

    assert result.selections["xx"].is_genuine_real_time
    assert len(result.forecasts) == 1
    assert len(result.alerts) == 1
    assert 0.0 <= result.forecasts[0].displayed_probability <= 1.0
    assert result.forecasts[0].training_end_date == date(2009, 1, 1)
    assert result.report["analysis"]["point_in_time_status"] == "TRUE_VINTAGE"
    assert all(section in result.report for section in REQUIRED_REPORT_SECTIONS)
    assert result.report["provenance"][0]["release_date"] == "2020-01-15"
    assert result.report["provenance"][0]["provider"] == "offline fixture"
    assert not validate_report(result.report, use_jsonschema=True)
