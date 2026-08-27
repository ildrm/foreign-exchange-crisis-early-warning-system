from datetime import date

import pytest

from fx_cpm.domain import (
    ContagionEdgeChannel,
    DatedContagionEdge,
    DomainValidationError,
    decompose_contagion_pressure,
    graph_from_edges,
)


def _edge(
    source: str,
    channel: ContagionEdgeChannel,
    weight: float,
    *,
    effective_to: date | None = None,
    available_on: date | None = None,
) -> DatedContagionEdge:
    return DatedContagionEdge(
        source_country=source,
        target_country="tr",
        channel=channel,
        weight=weight,
        effective_from=date(2020, 1, 1),
        effective_to=effective_to,
        available_on=available_on,
    )


def test_dated_graph_keeps_expired_and_not_yet_available_edges_out() -> None:
    graph = graph_from_edges(
        (
            _edge("de", ContagionEdgeChannel.TRADE, 2.0),
            _edge(
                "gb",
                ContagionEdgeChannel.BANKING_CLAIMS,
                1.0,
                available_on=date(2025, 1, 1),
            ),
            _edge(
                "ru",
                ContagionEdgeChannel.COMMODITY_LINKAGE,
                1.0,
                effective_to=date(2023, 1, 1),
            ),
        )
    )

    snapshot = graph.snapshot(date(2024, 1, 1))

    assert [(edge.source_country, edge.channel.value) for edge in snapshot.edges] == [
        ("DE", "trade")
    ]
    assert snapshot.interpretation == "DESCRIPTIVE_ASSOCIATION_NOT_CAUSAL"


def test_pressure_decomposition_keeps_own_common_and_network_terms_separate() -> None:
    graph = graph_from_edges(
        (
            _edge("de", ContagionEdgeChannel.TRADE, 2.0),
            _edge("gb", ContagionEdgeChannel.BANKING_CLAIMS, 1.0),
        )
    )

    result = decompose_contagion_pressure(
        graph=graph,
        country="tr",
        as_of=date(2024, 1, 1),
        own_country_pressure=3.0,
        common_factor_values={"global_usd": 2.0, "risk_sentiment": -1.0},
        common_factor_loadings={"global_usd": 0.5, "risk_sentiment": 0.25},
        source_pressures={"DE": 6.0, "GB": 2.0},
    )

    assert result.own_country_pressure == 3.0
    assert result.common_factor_pressure == pytest.approx(0.75)
    assert sum(
        item.weighted_pressure for item in result.common_factor_contributions
    ) == pytest.approx(result.common_factor_pressure)
    assert result.network_pressure == pytest.approx(14.0 / 3.0)
    assert result.combined_pressure == pytest.approx(3.75 + 14.0 / 3.0)
    assert result.network_coverage == 1.0
    assert {item.channel for item in result.network_contributions} == {
        ContagionEdgeChannel.TRADE,
        ContagionEdgeChannel.BANKING_CLAIMS,
    }
    assert sum(value for _, value in result.network_pressure_by_channel) == pytest.approx(
        result.network_pressure
    )


def test_missing_source_pressure_is_not_replaced_with_zero() -> None:
    graph = graph_from_edges((_edge("de", ContagionEdgeChannel.TRADE, 2.0),))

    result = decompose_contagion_pressure(
        graph=graph,
        country="tr",
        as_of=date(2024, 1, 1),
        own_country_pressure=1.0,
        common_factor_values={},
        common_factor_loadings={},
        source_pressures={"DE": None},
    )

    assert result.network_pressure is None
    assert result.combined_pressure is None
    assert result.network_coverage == 0.0


def test_contagion_edges_require_an_explicit_supported_channel() -> None:
    with pytest.raises(DomainValidationError, match="unsupported contagion edge channel"):
        DatedContagionEdge(
            "DE",
            "TR",
            "unspecified",
            1.0,
            date(2020, 1, 1),
        )
