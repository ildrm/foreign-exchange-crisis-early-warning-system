"""Country-facing helpers for constructing and auditing regime histories."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from fx_cpm.domain.regimes import CountryCurrencyRegime, RegimeHistory


def build_regime_history(
    country_id: str,
    records: Iterable[CountryCurrencyRegime],
    *,
    require_contiguous: bool = False,
) -> RegimeHistory:
    return RegimeHistory(country_id, tuple(records), require_contiguous=require_contiguous)


def regime_at(
    records: Iterable[CountryCurrencyRegime],
    *,
    country_id: str,
    analysis_date: date,
) -> CountryCurrencyRegime | None:
    relevant = tuple(record for record in records if record.country_id == country_id)
    if not relevant:
        return None
    return RegimeHistory(country_id, relevant).at(analysis_date)

