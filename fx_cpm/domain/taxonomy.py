"""Versioned multi-hazard taxonomy and forecast-horizon semantics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import IntEnum, StrEnum
from types import MappingProxyType
from typing import ClassVar, Mapping

from .validation import (
    DomainValidationError,
    require_date,
    require_non_empty,
    require_probability,
)


class ForecastHorizon(IntEnum):
    """Standard cumulative forecast horizons, represented in calendar days."""

    DAYS_30 = 30
    DAYS_90 = 90
    DAYS_180 = 180
    MONTHS_12 = 365
    MONTHS_24 = 730
    MONTHS_36 = 1095

    # Readable aliases retained for callers using singular names.
    DAY_30 = DAYS_30
    DAY_90 = DAYS_90
    DAY_180 = DAYS_180
    MONTH_12 = MONTHS_12
    MONTH_24 = MONTHS_24
    MONTH_36 = MONTHS_36

    @property
    def days(self) -> int:
        return int(self)

    @property
    def label(self) -> str:
        labels = {
            30: "30d",
            90: "90d",
            180: "180d",
            365: "12m",
            730: "24m",
            1095: "36m",
        }
        return labels[int(self)]

    def end_date(self, analysis_date: date) -> date:
        require_date(analysis_date, "analysis_date")
        return analysis_date + timedelta(days=self.days)

    @classmethod
    def parse(cls, value: ForecastHorizon | int | str) -> ForecastHorizon:
        if isinstance(value, cls):
            return value
        if isinstance(value, int) and not isinstance(value, bool):
            try:
                return cls(value)
            except ValueError as exc:
                raise DomainValidationError(f"unsupported forecast horizon: {value} days") from exc
        normalized = str(value).strip().lower().replace("_", "").replace("-", "")
        aliases = {
            "30": cls.DAYS_30,
            "30d": cls.DAYS_30,
            "90": cls.DAYS_90,
            "90d": cls.DAYS_90,
            "180": cls.DAYS_180,
            "180d": cls.DAYS_180,
            "12m": cls.MONTHS_12,
            "12month": cls.MONTHS_12,
            "12months": cls.MONTHS_12,
            "1y": cls.MONTHS_12,
            "24m": cls.MONTHS_24,
            "24month": cls.MONTHS_24,
            "24months": cls.MONTHS_24,
            "2y": cls.MONTHS_24,
            "36m": cls.MONTHS_36,
            "36month": cls.MONTHS_36,
            "36months": cls.MONTHS_36,
            "3y": cls.MONTHS_36,
        }
        try:
            return aliases[normalized]
        except KeyError as exc:
            raise DomainValidationError(f"unsupported forecast horizon: {value!r}") from exc


class HazardType(StrEnum):
    CURRENCY_CRISIS = "fx"
    SYSTEMIC_BANKING_CRISIS = "banking"
    SOVEREIGN_DISTRESS = "sovereign"
    MONETARY_INFLATION_CRISIS = "monetary"
    POLITICAL_INSTABILITY = "political_instability"
    COUP = "coup"
    INTERNAL_ARMED_CONFLICT = "internal_conflict"
    INTERSTATE_ARMED_CONFLICT = "interstate_conflict"

    # Concise aliases mirror the mathematical vector in the research contract.
    FX = CURRENCY_CRISIS
    BANK = SYSTEMIC_BANKING_CRISIS
    SOV = SOVEREIGN_DISTRESS
    MON = MONETARY_INFLATION_CRISIS
    POL = POLITICAL_INSTABILITY
    CIV = INTERNAL_ARMED_CONFLICT
    WAR = INTERSTATE_ARMED_CONFLICT

    _ALIASES: ClassVar[dict[str, str]]

    @property
    def code(self) -> str:
        return {
            HazardType.CURRENCY_CRISIS: "FX",
            HazardType.SYSTEMIC_BANKING_CRISIS: "BANK",
            HazardType.SOVEREIGN_DISTRESS: "SOV",
            HazardType.MONETARY_INFLATION_CRISIS: "MON",
            HazardType.POLITICAL_INSTABILITY: "POL",
            HazardType.COUP: "COUP",
            HazardType.INTERNAL_ARMED_CONFLICT: "CIV",
            HazardType.INTERSTATE_ARMED_CONFLICT: "WAR",
        }[self]

    @classmethod
    def parse(cls, value: HazardType | str) -> HazardType:
        if isinstance(value, cls):
            return value
        normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "fx": cls.CURRENCY_CRISIS,
            "currency": cls.CURRENCY_CRISIS,
            "currency_crisis": cls.CURRENCY_CRISIS,
            "balance_of_payments": cls.CURRENCY_CRISIS,
            "bank": cls.SYSTEMIC_BANKING_CRISIS,
            "banking": cls.SYSTEMIC_BANKING_CRISIS,
            "banking_crisis": cls.SYSTEMIC_BANKING_CRISIS,
            "systemic_banking_crisis": cls.SYSTEMIC_BANKING_CRISIS,
            "sov": cls.SOVEREIGN_DISTRESS,
            "sovereign": cls.SOVEREIGN_DISTRESS,
            "sovereign_distress": cls.SOVEREIGN_DISTRESS,
            "sovereign_default": cls.SOVEREIGN_DISTRESS,
            "mon": cls.MONETARY_INFLATION_CRISIS,
            "monetary": cls.MONETARY_INFLATION_CRISIS,
            "inflation": cls.MONETARY_INFLATION_CRISIS,
            "monetary_inflation_crisis": cls.MONETARY_INFLATION_CRISIS,
            "pol": cls.POLITICAL_INSTABILITY,
            "political": cls.POLITICAL_INSTABILITY,
            "political_instability": cls.POLITICAL_INSTABILITY,
            "coup": cls.COUP,
            "civil": cls.INTERNAL_ARMED_CONFLICT,
            "civ": cls.INTERNAL_ARMED_CONFLICT,
            "internal_conflict": cls.INTERNAL_ARMED_CONFLICT,
            "internal_armed_conflict": cls.INTERNAL_ARMED_CONFLICT,
            "war": cls.INTERSTATE_ARMED_CONFLICT,
            "interstate_conflict": cls.INTERSTATE_ARMED_CONFLICT,
            "interstate_armed_conflict": cls.INTERSTATE_ARMED_CONFLICT,
        }
        try:
            return aliases[normalized]
        except KeyError as exc:
            raise DomainValidationError(f"unsupported hazard type: {value!r}") from exc


class UnitOfAnalysis(StrEnum):
    COUNTRY_DAY = "country_day"
    COUNTRY_MONTH = "country_month"
    COUNTRY_YEAR = "country_year"


@dataclass(frozen=True, slots=True)
class HazardDefinition:
    """Scientific event semantics for one separately modelled hazard."""

    hazard_type: HazardType
    formal_label: str
    event_definition: str
    onset_definition: str
    continuation_definition: str
    termination_definition: str
    minimum_severity: str
    label_sources: tuple[str, ...]
    historical_coverage_start: date | None
    historical_coverage_end: date | None
    known_ambiguities: tuple[str, ...]
    forecast_horizons: tuple[ForecastHorizon, ...]
    unit_of_analysis: UnitOfAnalysis
    baseline_prevalence: float | None = None
    baseline_prevalence_note: str = (
        "Estimate separately by hazard, horizon, era, and eligible population from training data."
    )
    taxonomy_version: str = "0.1.0"

    def __post_init__(self) -> None:
        if not isinstance(self.hazard_type, HazardType):
            raise DomainValidationError("hazard_type must be a HazardType")
        for field_name in (
            "formal_label",
            "event_definition",
            "onset_definition",
            "continuation_definition",
            "termination_definition",
            "minimum_severity",
            "baseline_prevalence_note",
            "taxonomy_version",
        ):
            require_non_empty(getattr(self, field_name), field_name)
        if not self.label_sources:
            raise DomainValidationError("label_sources must not be empty")
        if not self.forecast_horizons:
            raise DomainValidationError("forecast_horizons must not be empty")
        if tuple(sorted(set(self.forecast_horizons), key=int)) != self.forecast_horizons:
            raise DomainValidationError("forecast_horizons must be unique and increasing")
        if self.historical_coverage_start is not None:
            require_date(self.historical_coverage_start, "historical_coverage_start")
        if self.historical_coverage_end is not None:
            require_date(self.historical_coverage_end, "historical_coverage_end")
        if self.historical_coverage_start and self.historical_coverage_end:
            if self.historical_coverage_end < self.historical_coverage_start:
                raise DomainValidationError("historical coverage ends before it starts")
        if self.baseline_prevalence is not None:
            require_probability(self.baseline_prevalence, "baseline_prevalence")

    def supports(self, horizon: ForecastHorizon | int | str) -> bool:
        return ForecastHorizon.parse(horizon) in self.forecast_horizons


_SHORT = (ForecastHorizon.DAYS_30, ForecastHorizon.DAYS_90, ForecastHorizon.DAYS_180)
_MEDIUM = (ForecastHorizon.DAYS_180, ForecastHorizon.MONTHS_12, ForecastHorizon.MONTHS_24)
_ALL = (
    ForecastHorizon.DAYS_30,
    ForecastHorizon.DAYS_90,
    ForecastHorizon.DAYS_180,
    ForecastHorizon.MONTHS_12,
    ForecastHorizon.MONTHS_24,
    ForecastHorizon.MONTHS_36,
)


def _definitions() -> dict[HazardType, HazardDefinition]:
    """Construct the complete taxonomy without claiming unestimated base rates."""

    return {
        HazardType.CURRENCY_CRISIS: HazardDefinition(
            hazard_type=HazardType.CURRENCY_CRISIS,
            formal_label="Currency / balance-of-payments crisis onset",
            event_definition=(
                "A discrete collapse of confidence in the currency or external-payments regime, "
                "evidenced by exceptional depreciation, reserve loss, exchange-market pressure, "
                "devaluation, abandonment of a peg, or binding payments restrictions."
            ),
            onset_definition=(
                "The first date a versioned quantitative pressure criterion or reconciled event "
                "source identifies the episode; a range is retained when dating is disputed."
            ),
            continuation_definition=(
                "Pressure remains part of the same episode while threshold breaches, defensive "
                "policy measures, or payments restrictions persist without a documented recovery."
            ),
            termination_definition=(
                "The episode ends after pressure normalizes for the taxonomy's recovery window or "
                "the replacement regime has stabilized; a new breach after recovery is a new onset."
            ),
            minimum_severity=(
                "Must pass the versioned EMP/depreciation or authoritative event-source threshold; "
                "ordinary exchange-rate fluctuations are excluded."
            ),
            label_sources=("Laeven-Valencia", "Reinhart-Rogoff", "IMF AREAER", "versioned EMP rule"),
            historical_coverage_start=date(1920, 1, 1),
            historical_coverage_end=None,
            known_ambiguities=(
                "Official rates can conceal pressure under pegs or controls.",
                "Parallel-market and reserve series are incomplete historically.",
            ),
            forecast_horizons=_ALL,
            unit_of_analysis=UnitOfAnalysis.COUNTRY_MONTH,
        ),
        HazardType.SYSTEMIC_BANKING_CRISIS: HazardDefinition(
            hazard_type=HazardType.SYSTEMIC_BANKING_CRISIS,
            formal_label="Systemic banking crisis onset",
            event_definition=(
                "Severe distress across a material share of the banking system accompanied by "
                "bank runs, losses, closures, restructuring, guarantees, or extraordinary support."
            ),
            onset_definition=(
                "Earliest reconciled date of systemic distress or the first major public "
                "intervention attributable to that distress."
            ),
            continuation_definition=(
                "The episode continues while systemic impairment or extraordinary resolution and "
                "support measures remain active."
            ),
            termination_definition=(
                "System-wide solvency and liquidity conditions normalize and extraordinary crisis "
                "interventions cease, following the versioned label source."
            ),
            minimum_severity="Idiosyncratic failure of a non-systemic institution is excluded.",
            label_sources=("Laeven-Valencia", "Reinhart-Rogoff", "national resolution authorities"),
            historical_coverage_start=date(1920, 1, 1),
            historical_coverage_end=None,
            known_ambiguities=(
                "Intervention dates may lag private distress.",
                "Systemic importance changes with banking-system structure.",
            ),
            forecast_horizons=_MEDIUM + (ForecastHorizon.MONTHS_36,),
            unit_of_analysis=UnitOfAnalysis.COUNTRY_MONTH,
        ),
        HazardType.SOVEREIGN_DISTRESS: HazardDefinition(
            hazard_type=HazardType.SOVEREIGN_DISTRESS,
            formal_label="Sovereign distress or default onset",
            event_definition=(
                "Failure or coercive alteration of public-debt service, or a comparably severe "
                "sovereign financing episode defined by the versioned taxonomy."
            ),
            onset_definition=(
                "First missed payment, coercive exchange, repudiation, arrears threshold, or "
                "authoritatively dated severe-distress event."
            ),
            continuation_definition="The episode continues while default, arrears, or restructuring is unresolved.",
            termination_definition=(
                "Debt service resumes under an implemented settlement and the source marks the "
                "episode resolved; renewed default is a separate onset."
            ),
            minimum_severity=(
                "Voluntary liability management and ordinary spread widening without severe "
                "distress are excluded."
            ),
            label_sources=("World Bank IDS", "IMF", "Bank of Canada sovereign default database"),
            historical_coverage_start=date(1920, 1, 1),
            historical_coverage_end=None,
            known_ambiguities=(
                "Domestic-law restructurings are less consistently recorded.",
                "Distress and legal default dates can differ."
            ),
            forecast_horizons=_MEDIUM + (ForecastHorizon.MONTHS_36,),
            unit_of_analysis=UnitOfAnalysis.COUNTRY_MONTH,
        ),
        HazardType.MONETARY_INFLATION_CRISIS: HazardDefinition(
            hazard_type=HazardType.MONETARY_INFLATION_CRISIS,
            formal_label="Monetary / inflation crisis onset",
            event_definition=(
                "A versioned, sustained breach of the taxonomy's high-inflation or acceleration "
                "criterion indicating loss of monetary stability."
            ),
            onset_definition=(
                "First period in the sustained qualifying run; isolated price-level jumps are not "
                "backdated as onsets unless the rule explicitly treats them as such."
            ),
            continuation_definition="Inflation remains above the continuation threshold or monetary disorder persists.",
            termination_definition=(
                "Inflation remains below the lower recovery threshold for the required recovery "
                "window, preventing mechanical episode flicker."
            ),
            minimum_severity="Must pass a versioned level, acceleration, and persistence rule.",
            label_sources=("IMF IFS", "World Bank", "Reinhart-Rogoff", "national statistical offices"),
            historical_coverage_start=date(1920, 1, 1),
            historical_coverage_end=None,
            known_ambiguities=(
                "Price controls can suppress measured inflation.",
                "Index rebasing and missing monthly series affect historical comparability."
            ),
            forecast_horizons=_ALL,
            unit_of_analysis=UnitOfAnalysis.COUNTRY_MONTH,
        ),
        HazardType.POLITICAL_INSTABILITY: HazardDefinition(
            hazard_type=HazardType.POLITICAL_INSTABILITY,
            formal_label="Major political-instability crisis onset",
            event_definition=(
                "A major deterioration in political order involving sustained mass unrest, "
                "government breakdown, or political violence above a versioned severity threshold."
            ),
            onset_definition="First qualifying event date in reconciled event sources.",
            continuation_definition=(
                "Qualifying instability persists while events remain above continuation severity "
                "and are separated by less than the episode-gap rule."
            ),
            termination_definition="The episode ends after the specified event-free recovery interval.",
            minimum_severity=(
                "Routine cabinet turnover, peaceful protest, and normal electoral competition are excluded."
            ),
            label_sources=("V-Dem", "ACLED", "Mass Mobilization Data", "authoritative country chronologies"),
            historical_coverage_start=date(1945, 1, 1),
            historical_coverage_end=None,
            known_ambiguities=(
                "Reporting intensity varies across countries and eras.",
                "Political-instability concepts require a pre-registered severity rule."
            ),
            forecast_horizons=_SHORT + (ForecastHorizon.MONTHS_12,),
            unit_of_analysis=UnitOfAnalysis.COUNTRY_MONTH,
        ),
        HazardType.COUP: HazardDefinition(
            hazard_type=HazardType.COUP,
            formal_label="Coup or unconstitutional government-change onset",
            event_definition=(
                "An overt illegal attempt by military or civilian elites to remove or displace the "
                "sitting chief executive, whether successful or attempted, according to source coding."
            ),
            onset_definition="Date the attempt becomes operational rather than the date of later recognition.",
            continuation_definition="A single attempt continues through the associated seizure-of-power operation.",
            termination_definition=(
                "The attempt succeeds, fails, or is abandoned; a later distinct operation is a new event."
            ),
            minimum_severity="Rumours, private plotting, and constitutional removals are excluded.",
            label_sources=("Cline Center Coup d'Etat Project", "Powell-Thyne coup dataset"),
            historical_coverage_start=date(1945, 1, 1),
            historical_coverage_end=None,
            known_ambiguities=(
                "Self-coups and disputed constitutional procedures require explicit source coding.",
                "Failed attempts can be under-reported historically."
            ),
            forecast_horizons=_SHORT + (ForecastHorizon.MONTHS_12,),
            unit_of_analysis=UnitOfAnalysis.COUNTRY_MONTH,
        ),
        HazardType.INTERNAL_ARMED_CONFLICT: HazardDefinition(
            hazard_type=HazardType.INTERNAL_ARMED_CONFLICT,
            formal_label="Internal armed-conflict onset or escalation",
            event_definition=(
                "Onset of organized armed force within a state, or a separately labelled escalation "
                "across a pre-registered battle-death/intensity threshold."
            ),
            onset_definition="First qualifying conflict event or first date crossing the escalation threshold.",
            continuation_definition=(
                "Conflict remains active under the source's annual or event-gap continuation rule."
            ),
            termination_definition="The source's inactivity or settlement criterion is met.",
            minimum_severity=(
                "Criminal violence and isolated unrest without organized armed parties are excluded."
            ),
            label_sources=("UCDP", "ACLED", "Correlates of War"),
            historical_coverage_start=date(1946, 1, 1),
            historical_coverage_end=None,
            known_ambiguities=(
                "Onset and escalation are distinct targets and must not be mixed silently.",
                "Battle-death estimates and actor classification are uncertain."
            ),
            forecast_horizons=_SHORT + (ForecastHorizon.MONTHS_12, ForecastHorizon.MONTHS_24),
            unit_of_analysis=UnitOfAnalysis.COUNTRY_MONTH,
        ),
        HazardType.INTERSTATE_ARMED_CONFLICT: HazardDefinition(
            hazard_type=HazardType.INTERSTATE_ARMED_CONFLICT,
            formal_label="Interstate armed-conflict onset or escalation",
            event_definition=(
                "Onset of organized armed force between states, or separately labelled escalation "
                "above a pre-registered hostility/intensity threshold."
            ),
            onset_definition="First qualifying use of armed force or first threshold-crossing escalation date.",
            continuation_definition="Hostilities remain active under the source's episode-continuation rule.",
            termination_definition="A qualifying cessation, settlement, or inactivity interval is observed.",
            minimum_severity=(
                "Threats, exercises, and diplomatic disputes without qualifying force are excluded."
            ),
            label_sources=("UCDP", "Correlates of War", "International Crisis Behavior"),
            historical_coverage_start=date(1920, 1, 1),
            historical_coverage_end=None,
            known_ambiguities=(
                "Covert action and disputed state status complicate coding.",
                "Onset and escalation require separate labels in model training."
            ),
            forecast_horizons=_SHORT + (ForecastHorizon.MONTHS_12, ForecastHorizon.MONTHS_24),
            unit_of_analysis=UnitOfAnalysis.COUNTRY_MONTH,
        ),
    }


DEFAULT_HAZARD_TAXONOMY: Mapping[HazardType, HazardDefinition] = MappingProxyType(_definitions())
TAXONOMY_VERSION = "0.1.0"


def hazard_definition(hazard: HazardType | str) -> HazardDefinition:
    return DEFAULT_HAZARD_TAXONOMY[HazardType.parse(hazard)]


def validate_complete_taxonomy(
    definitions: Mapping[HazardType, HazardDefinition],
) -> None:
    missing = set(HazardType) - set(definitions)
    extra = set(definitions) - set(HazardType)
    if missing or extra:
        raise DomainValidationError(
            f"taxonomy must contain exactly eight hazards; missing={missing}, extra={extra}"
        )


validate_complete_taxonomy(DEFAULT_HAZARD_TAXONOMY)
