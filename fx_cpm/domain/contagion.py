"""Dated, descriptive cross-country exposure graph.

The quantities in this module are observable association summaries.  They do
not identify a transmission mechanism and must not be described as causal.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from .validation import (
    DomainValidationError,
    require_date,
    require_finite,
    require_non_empty,
    require_positive,
    require_probability,
)


class ContagionEdgeChannel(StrEnum):
    """Documented relationship represented by a graph edge."""

    TRADE = "trade"
    BANKING_CLAIMS = "banking_claims"
    PORTFOLIO_EXPOSURE = "portfolio_exposure"
    COMMON_CREDITORS = "common_creditors"
    COMMON_CURRENCY_ANCHOR = "common_currency_anchor"
    COMMODITY_LINKAGE = "commodity_linkage"
    GEOGRAPHIC_PROXIMITY = "geographic_proximity"
    MIGRATION = "migration"
    MILITARY_ALLIANCE = "military_alliance"
    HISTORICAL_CONFLICT_DIFFUSION = "historical_conflict_diffusion"

    @classmethod
    def parse(cls, value: ContagionEdgeChannel | str) -> ContagionEdgeChannel:
        if isinstance(value, cls):
            return value
        normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
        try:
            return cls(normalized)
        except ValueError as exc:
            raise DomainValidationError(f"unsupported contagion edge channel: {value!r}") from exc


@dataclass(frozen=True, slots=True)
class DatedContagionEdge:
    """One directed, dated exposure association between different countries."""

    source_country: str
    target_country: str
    channel: ContagionEdgeChannel
    weight: float
    effective_from: date
    effective_to: date | None = None
    available_on: date | None = None
    evidence_note: str = "descriptive exposure association"

    def __post_init__(self) -> None:
        source = require_non_empty(self.source_country, "source_country").strip().upper()
        target = require_non_empty(self.target_country, "target_country").strip().upper()
        if source == target:
            raise DomainValidationError("contagion graph edges must connect different countries")
        object.__setattr__(self, "source_country", source)
        object.__setattr__(self, "target_country", target)
        object.__setattr__(self, "channel", ContagionEdgeChannel.parse(self.channel))
        object.__setattr__(self, "weight", require_positive(self.weight, "weight"))
        require_date(self.effective_from, "effective_from")
        if self.effective_to is not None:
            require_date(self.effective_to, "effective_to")
            if self.effective_to <= self.effective_from:
                raise DomainValidationError("effective_to must be after effective_from")
        available_on = self.available_on or self.effective_from
        require_date(available_on, "available_on")
        object.__setattr__(self, "available_on", available_on)
        require_non_empty(self.evidence_note, "evidence_note")

    def is_visible_and_active(self, as_of: date) -> bool:
        require_date(as_of, "as_of")
        return bool(
            self.available_on <= as_of
            and self.effective_from <= as_of
            and (self.effective_to is None or as_of < self.effective_to)
        )


@dataclass(frozen=True, slots=True)
class ContagionGraphSnapshot:
    """Point-in-time graph containing only visible, active edges."""

    as_of: date
    nodes: tuple[str, ...]
    edges: tuple[DatedContagionEdge, ...]
    interpretation: str = "DESCRIPTIVE_ASSOCIATION_NOT_CAUSAL"

    def __post_init__(self) -> None:
        require_date(self.as_of, "as_of")
        normalized_nodes = tuple(
            sorted({require_non_empty(node, "node").strip().upper() for node in self.nodes})
        )
        object.__setattr__(self, "nodes", normalized_nodes)
        if any(not edge.is_visible_and_active(self.as_of) for edge in self.edges):
            raise DomainValidationError("snapshot contains an edge not visible and active as_of")
        if any(
            edge.source_country not in normalized_nodes or edge.target_country not in normalized_nodes
            for edge in self.edges
        ):
            raise DomainValidationError("every edge endpoint must appear in snapshot nodes")

    def incoming(self, country: str) -> tuple[DatedContagionEdge, ...]:
        target = require_non_empty(country, "country").strip().upper()
        return tuple(edge for edge in self.edges if edge.target_country == target)


@dataclass(frozen=True, slots=True)
class DatedContagionGraph:
    """Versioned edge collection that can produce leakage-safe snapshots."""

    edges: tuple[DatedContagionEdge, ...]
    additional_nodes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "edges", tuple(self.edges))
        nodes = tuple(
            sorted(
                {
                    *(edge.source_country for edge in self.edges),
                    *(edge.target_country for edge in self.edges),
                    *(
                        require_non_empty(node, "additional_node").strip().upper()
                        for node in self.additional_nodes
                    ),
                }
            )
        )
        object.__setattr__(self, "additional_nodes", nodes)

    def snapshot(self, as_of: date) -> ContagionGraphSnapshot:
        require_date(as_of, "as_of")
        active = tuple(
            sorted(
                (edge for edge in self.edges if edge.is_visible_and_active(as_of)),
                key=lambda edge: (edge.target_country, edge.source_country, edge.channel.value),
            )
        )
        return ContagionGraphSnapshot(as_of, self.additional_nodes, active)


@dataclass(frozen=True, slots=True)
class NetworkPressureContribution:
    source_country: str
    channel: ContagionEdgeChannel
    edge_weight: float
    source_pressure: float
    weighted_pressure: float


@dataclass(frozen=True, slots=True)
class CommonFactorPressureContribution:
    factor_name: str
    factor_value: float
    loading: float
    weighted_pressure: float


@dataclass(frozen=True, slots=True)
class PressureDecomposition:
    """Separate own, common-factor, and network association pressures."""

    country: str
    as_of: date
    own_country_pressure: float
    common_factor_pressure: float
    common_factor_contributions: tuple[CommonFactorPressureContribution, ...]
    network_pressure: float | None
    network_coverage: float
    network_contributions: tuple[NetworkPressureContribution, ...]
    network_pressure_by_channel: tuple[tuple[ContagionEdgeChannel, float], ...]
    combined_pressure: float | None
    interpretation: str = "DESCRIPTIVE_ASSOCIATION_NOT_CAUSAL"

    def __post_init__(self) -> None:
        require_non_empty(self.country, "country")
        require_date(self.as_of, "as_of")
        require_finite(self.own_country_pressure, "own_country_pressure")
        require_finite(self.common_factor_pressure, "common_factor_pressure")
        if self.network_pressure is not None:
            require_finite(self.network_pressure, "network_pressure")
        require_probability(self.network_coverage, "network_coverage")
        if self.combined_pressure is not None:
            require_finite(self.combined_pressure, "combined_pressure")
        if self.network_pressure is None and self.combined_pressure is not None:
            raise DomainValidationError("combined_pressure must be missing when network is missing")
        if self.network_pressure is not None:
            expected = (
                self.own_country_pressure
                + self.common_factor_pressure
                + self.network_pressure
            )
            if self.combined_pressure is None or not math.isclose(
                self.combined_pressure, expected, rel_tol=1e-12, abs_tol=1e-12
            ):
                raise DomainValidationError("combined_pressure must equal its three components")


def decompose_contagion_pressure(
    *,
    graph: DatedContagionGraph,
    country: str,
    as_of: date,
    own_country_pressure: float,
    common_factor_values: Mapping[str, float],
    common_factor_loadings: Mapping[str, float],
    source_pressures: Mapping[str, float | None],
    channel_weights: Mapping[ContagionEdgeChannel | str, float] | None = None,
    normalize_network_weights: bool = True,
) -> PressureDecomposition:
    """Build an additive pressure decomposition from information visible ``as_of``.

    Edge-weighted source pressure is an exposure association.  The calculation
    intentionally makes no claim that pressure in a source caused pressure in
    the target.
    """

    target = require_non_empty(country, "country").strip().upper()
    require_date(as_of, "as_of")
    own = require_finite(own_country_pressure, "own_country_pressure")
    if set(common_factor_values) != set(common_factor_loadings):
        raise DomainValidationError(
            "common_factor_values and common_factor_loadings must have identical keys"
        )
    common_contributions = tuple(
        CommonFactorPressureContribution(
            factor_name=require_non_empty(name, "common factor name"),
            factor_value=require_finite(value, f"common_factor_values[{name}]"),
            loading=require_finite(
                common_factor_loadings[name], f"common_factor_loadings[{name}]"
            ),
            weighted_pressure=require_finite(value, f"common_factor_values[{name}]")
            * require_finite(common_factor_loadings[name], f"common_factor_loadings[{name}]"),
        )
        for name, value in sorted(common_factor_values.items())
    )
    common = math.fsum(item.weighted_pressure for item in common_contributions)
    parsed_channel_weights = {
        ContagionEdgeChannel.parse(channel): require_positive(
            weight, f"channel_weights[{channel}]", allow_zero=True
        )
        for channel, weight in (channel_weights or {}).items()
    }
    normalized_source_pressures: dict[str, float | None] = {}
    for raw_source, pressure in source_pressures.items():
        source = require_non_empty(raw_source, "source pressure country").strip().upper()
        if source in normalized_source_pressures:
            raise DomainValidationError(f"duplicate source pressure after normalization: {source}")
        normalized_source_pressures[source] = pressure
    incoming = graph.snapshot(as_of).incoming(target)
    total_exposure_weight = math.fsum(
        edge.weight * parsed_channel_weights.get(edge.channel, 1.0) for edge in incoming
    )
    contributions: list[NetworkPressureContribution] = []
    available_weight = 0.0
    for edge in incoming:
        pressure = normalized_source_pressures.get(edge.source_country)
        if pressure is None:
            continue
        clean_pressure = require_finite(
            pressure, f"source_pressures[{edge.source_country}]"
        )
        exposure_weight = edge.weight * parsed_channel_weights.get(edge.channel, 1.0)
        if exposure_weight == 0.0:
            continue
        available_weight += exposure_weight
        contributions.append(
            NetworkPressureContribution(
                source_country=edge.source_country,
                channel=edge.channel,
                edge_weight=exposure_weight,
                source_pressure=clean_pressure,
                weighted_pressure=exposure_weight * clean_pressure,
            )
        )
    coverage = 1.0 if total_exposure_weight == 0.0 else available_weight / total_exposure_weight
    if incoming and available_weight == 0.0:
        network = None
    else:
        raw_network = math.fsum(item.weighted_pressure for item in contributions)
        network = (
            raw_network / available_weight
            if normalize_network_weights and available_weight > 0.0
            else raw_network
        )
    denominator = available_weight if normalize_network_weights and available_weight > 0.0 else 1.0
    pressure_by_channel = tuple(
        (
            channel,
            math.fsum(
                item.weighted_pressure for item in contributions if item.channel is channel
            )
            / denominator,
        )
        for channel in ContagionEdgeChannel
        if any(item.channel is channel for item in contributions)
    )
    combined = None if network is None else own + common + network
    return PressureDecomposition(
        country=target,
        as_of=as_of,
        own_country_pressure=own,
        common_factor_pressure=common,
        common_factor_contributions=common_contributions,
        network_pressure=network,
        network_coverage=coverage,
        network_contributions=tuple(contributions),
        network_pressure_by_channel=pressure_by_channel,
        combined_pressure=combined,
    )


def graph_from_edges(
    edges: Sequence[DatedContagionEdge], *, additional_nodes: Sequence[str] = ()
) -> DatedContagionGraph:
    """Convenience constructor that freezes caller-owned sequences."""

    return DatedContagionGraph(tuple(edges), tuple(additional_nodes))
