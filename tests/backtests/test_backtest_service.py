from __future__ import annotations

from datetime import date, timedelta

import pytest

from fx_cpm.application.backtest_service import (
    BacktestService,
    BacktestWindow,
    average_precision,
    rare_event_metrics,
)
from fx_cpm.application.feature_matrix import FeatureSample
from fx_cpm.application.point_in_time import VintageMode


def monthly_samples(count: int = 72) -> tuple[FeatureSample, ...]:
    rows = []
    for index in range(count):
        year = 2010 + index // 12
        month = index % 12 + 1
        target = int(index % 5 == 0 or index % 11 == 0)
        rows.append(
            FeatureSample(
                country_id="xx" if index % 2 else "yy",
                analysis_date=date(year, month, 1),
                features={"macro_credit": index / count, "fx_surprise": 2.0 if target else -1.0},
                target=target,
                hazard="fx",
                horizon="12m",
                regime="float" if index % 3 else "peg",
                cluster_id="cluster_a" if 25 <= index <= 30 else "independent",
                event_id=f"event-{index}" if target else None,
                event_date=date(year, month, 1) + timedelta(days=90) if target else None,
            )
        )
    return tuple(rows)


def test_rare_event_metrics_report_base_rate_false_alerts_and_lead_time() -> None:
    labels = (0, 0, 1, 1)
    scores = (0.1, 0.2, 0.8, 0.9)
    samples = tuple(
        FeatureSample(
            "xx",
            date(2020, 1, index + 1),
            {"x": float(index)},
            target,
            event_id=f"event-{index}" if target else None,
            event_date=date(2020, 2, index + 1) if target else None,
        )
        for index, target in enumerate(labels)
    )
    metrics = rare_event_metrics(
        labels,
        scores,
        threshold=0.5,
        fixed_fpr=0.0,
        operational_alert_rate=0.25,
        samples=samples,
    )

    assert average_precision(labels, scores) == 1.0
    assert metrics.base_rate == 0.5
    assert metrics.brier_score == pytest.approx(0.025)
    assert metrics.recall == 1.0
    assert metrics.precision == 1.0
    assert metrics.false_alert_rate == 0.0
    assert metrics.missed_crisis_rate == 0.0
    assert metrics.recall_at_fixed_fpr == 1.0
    assert metrics.precision_at_alert_rate == 1.0
    assert metrics.mean_warning_lead_days == pytest.approx(31.0)


def test_expanding_backtest_keeps_training_and_calibration_before_test() -> None:
    rows = monthly_samples()
    window = BacktestWindow(
        "2014-2015",
        train_end=date(2012, 12, 31),
        calibration_start=date(2013, 1, 1),
        calibration_end=date(2013, 12, 31),
        test_start=date(2014, 1, 1),
        test_end=date(2015, 12, 31),
    )
    service = BacktestService()
    first = service.run_expanding(
        rows,
        (window,),
        hazard="fx",
        horizon="12m",
        vintage_mode=VintageMode.RECONSTRUCTED_POINT_IN_TIME,
        threshold=0.5,
    )
    second = service.run_expanding(
        rows,
        (window,),
        hazard="fx",
        horizon="12m",
        vintage_mode=VintageMode.RECONSTRUCTED_POINT_IN_TIME,
        threshold=0.5,
    )

    result = first.windows[0]
    assert result.training_latest_date <= window.train_end
    assert result.calibration_latest_date is not None
    assert result.calibration_latest_date < window.test_start
    assert all(item.sample.analysis_date >= window.test_start for item in result.predictions)
    assert first.aggregate_metrics == second.aggregate_metrics
    assert not first.genuine_real_time


def test_calibration_window_overlap_is_rejected_by_window_contract() -> None:
    with pytest.raises(ValueError, match="calibration"):
        BacktestWindow(
            "bad",
            train_end=date(2020, 1, 1),
            calibration_start=date(2020, 2, 1),
            calibration_end=date(2020, 4, 1),
            test_start=date(2020, 4, 1),
            test_end=date(2020, 5, 1),
        )


def test_country_cluster_and_regime_holdouts_remove_entire_groups() -> None:
    rows = monthly_samples(36)
    service = BacktestService()
    country = service.country_holdout(rows, ("xx",))
    cluster = service.crisis_cluster_holdout(rows, ("cluster_a",))
    regime = service.regime_holdout(rows, ("peg",))

    assert all(sample.country_id != "xx" for sample in country.training)
    assert all(sample.country_id == "xx" for sample in country.testing)
    assert all(sample.cluster_id != "cluster_a" for sample in cluster.training)
    assert all(sample.cluster_id == "cluster_a" for sample in cluster.testing)
    assert all(sample.regime != "peg" for sample in regime.training)
    assert all(sample.regime == "peg" for sample in regime.testing)


def test_fx_ablation_measures_incremental_information_without_assuming_a_gain() -> None:
    rows = []
    for index in range(100):
        year = 2000 + index // 12
        month = index % 12 + 1
        target = index % 2
        rows.append(
            FeatureSample(
                "xx",
                date(year, month, 1),
                {"macro_constant": 1.0, "fx_signal": 1.0 if target else -1.0},
                target,
                hazard="fx",
                horizon="12m",
            )
        )
    window = BacktestWindow(
        "ablation",
        train_end=date(2004, 12, 31),
        calibration_start=date(2005, 1, 1),
        calibration_end=date(2005, 12, 31),
        test_start=date(2006, 1, 1),
        test_end=date(2008, 12, 31),
    )
    result = BacktestService().run_fx_ablation(
        rows,
        (window,),
        fx_features=("fx_signal",),
        hazard="fx",
        horizon="12m",
    )

    assert result.with_fx.aggregate_metrics.average_precision > result.without_fx.aggregate_metrics.average_precision
    assert result.delta_average_precision > 0.0
