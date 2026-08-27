# FX-CPM Data Sources

Data-source catalog version: 0.1.0  
Reviewed: 2026-08-27  
Bundled data: synthetic demonstration records only

## Admission policy

A source is not admitted merely because it is publicly downloadable. Every adapter must record provider, dataset/series, frequency, geographic/temporal coverage, observed release date, retrieval time, vintage, access method, license/terms URL, transformation lineage, and known limitations. Dataset-specific terms override a portal's general terms.

Licensing states used here:

- **approved for adapter research**: current terms permit the intended use with stated attribution/conditions;
- **conditional**: series-level or commercial-use rights must be checked before redistribution;
- **metadata only / review required**: no data may be redistributed by this repository until permission is resolved;
- **unbundled commercial**: users may supply data they are licensed to use; FX-CPM does not redistribute it.

This catalog is not legal advice. Terms can change; production snapshots must archive the terms URL and review date.

## Open/official macro-financial sources

| Provider / dataset | Candidate variables | Frequency and coverage | Access | Revision / release behavior | License status and limitations |
|---|---|---|---|---|---|
| [World Bank World Development Indicators](https://datacatalog.worldbank.org/search/dataset/0037712/world-development-indicators) | GDP, trade, inflation, reserves proxies, credit, fiscal/external structure | Primarily annual; broad global coverage, many series from 1960 | [Indicators API v2](https://datahelpdesk.worldbank.org/knowledgebase/articles/889392), bulk files | Values and metadata are revised; the standard API is generally latest-vintage, so historical simulations are `REVISED_HISTORY_ONLY` unless releases are archived | Default World Bank-produced open datasets are CC BY 4.0 with attribution/additional terms; individual source metadata still require review. Approved for adapter research. |
| [World Bank International Debt Statistics](https://www.worldbank.org/en/programs/debt-statistics/ids) and QEDS/QPSD | external/public debt, maturity, currency composition, debt service | Annual/quarterly; mostly developing/emerging sovereigns | World Bank API/DataBank/bulk downloads | Revisions and country reporting lags are material; release calendars must be captured | Check the catalog record for each extract; typically World Bank open-data terms. Approved only after dataset-record license check. |
| [IMF statistical data](https://www.imf.org/en/about/copyright-and-terms) (IFS, BOP, GFS, DOTS, reserves, exchange rates) | official FX, reserves, CPI, money, rates, balance of payments, fiscal and trade data | Monthly/quarterly/annual; coverage varies by member/series and era | IMF data portals and SDMX services | Revisions are common and release lags vary. A current download is not a true vintage; store release/vintage metadata or reconstruct conservatively | IMF's current published-statistical-data terms permit download, derivatives, publication, and distribution with IMF attribution and transformation disclosure, subject to third-party data and commercial-reuse conditions. Conditional per series. |
| [IMF World Economic Outlook](https://www.imf.org/en/Publications/WEO/weo-database) | macro history and forecasts, fiscal/external indicators | Semiannual database; annual observations and forecasts | bulk download | Each edition is a natural vintage. Never replace an old WEO edition in a historical forecast | IMF statistical-data terms; record edition and distinguish forecast from realized/revised data. Conditional. |
| [BIS Data Portal](https://www.bis.org/statistics/dataportal/index.htm) | real/nominal effective exchange rates, credit gaps, property prices, debt service, banking claims, global liquidity | Monthly/quarterly, dataset-specific; strongest modern coverage | [BIS SDMX REST API](https://stats.bis.org/api-doc/v1/) and bulk files | Releases and revisions are dataset-specific; retain release calendar and retrieved snapshot | [BIS statistics terms](https://www.bis.org/terms_statistics.htm) permit use subject to citation, non-misleading use, no endorsement, and commercial-product conditions. Approved for adapter research with attribution; API availability is not guaranteed. |
| [ECB Data Portal](https://data.ecb.europa.eu/help/api/overview) | euro/European FX, rates, monetary aggregates, securities, banking and balance-of-payments data | Daily to annual; euro area and European emphasis | ECB Data Portal SDMX API | Series are revised; use update timestamps/release calendars and do not infer member-country currency variation inside the euro | [ECB copyright policy](https://www.ecb.europa.eu/services/copyright/html/index.en.html) and dataset metadata govern reuse. Review dataset/source attribution, particularly third-party series. Conditional. |
| National central banks and statistical offices | policy rates, official/parallel rates, reserves, interventions, CPI, banking balance sheets | Daily to annual; jurisdiction-specific | API, SDMX, release files, gazettes | Often best source for exact release dates but interfaces and back-series revisions vary | Adapter-by-adapter license and methodology review. Never scrape around access controls. Conditional. |
| [FRED / ALFRED](https://fred.stlouisfed.org/docs/api/fred/overview.html) | global factors and convenient access to US/third-party macro series; ALFRED vintages | Daily to annual; series-specific | REST API; key required | ALFRED exposes real-time periods for supported series and is useful for vintage tests | [FRED API terms](https://fred.stlouisfed.org/docs/api/terms_of_use.html) require attribution/notices and do not override third-party copyrights. Copyright-marked series require owner permission. Conditional; never assume every FRED series is redistributable. |

## Crisis-label and political/conflict sources

| Provider / dataset | Target use | Coverage / frequency | Revision behavior | License and limitations |
|---|---|---|---|---|
| [IMF Systemic Banking Crises Database: 1970–2025](https://www.elibrary.imf.org/view/journals/001/2026/094/article-A001-en.xml) | `BANK` labels and linked currency/sovereign episode context | Country episodes, 1970–2025; 2026 paper reports 164 systemic/borderline episodes | Later editions revise episode classification, start/end, costs, and add recent events; freeze the cited edition | IMF publication/data terms and file-specific terms apply. Treat borderline status explicitly; do not turn annual dates into exact days. |
| [UCDP downloads](https://ucdp.uu.se/downloads/) | `CIV` and `WAR` onset/escalation labels; lagged conflict features | Current v26.1 core yearly data cover 1946–2025; event data are disaggregated for later eras | Current, historical versions, codebooks, and version histories are available; IDs changed in v17.1, so use translation tables | UCDP states its datasets are CC BY 4.0 with required scholarly citation. Approved for adapter research. Candidate-event data are preliminary and must not be treated like finalized labels. |
| [V-Dem dataset](https://www.v-dem.net/data/the-v-dem-dataset/) | political institutions/state-capacity predictors and candidate `POL` corroboration | Annual/country-date products; v16 published March 2026 | Annual versions, uncertainty/measurement-model outputs, caution notes, and archive | CC BY-SA 4.0. Share-alike implications for redistributed derivatives require explicit compliance. Expert-coded uncertainty is substantive, not noise to discard. |
| National constitutions, election commissions, official gazettes, and recognized international organizations | confirm executive succession, emergency declarations, constitutional discontinuities | Event-specific | May be corrected; archive retrieval and document status | Terms vary. High authority does not guarantee comparable cross-country coding. Metadata/evidence source unless an adapter passes review. |
| Versioned academic coup datasets | `COUP` attempt/success labels | Dataset-specific, usually country-day/year | Definitions (attempt, self-coup, conspiracy) differ and updates can recode cases | **Review required.** No coup dataset is bundled in 0.1.0 because redistribution and definitional compatibility have not been approved. Users must record exact edition/codebook/license. |

## Market and FX sensor sources

Modern market inputs often carry restrictive licenses and shall not be committed to the open repository.

| Source class | Candidate variables | Status | Key limitations |
|---|---|---|---|
| Central-bank/reference-rate feeds | official fixes, policy rates, reserve announcements | Conditional official adapters | Official rates may be non-tradable; intervention and publication delays differ. |
| Licensed market vendors/exchanges | spot, forwards, NDFs, options, risk reversals, CDS, sovereign yields, bid-ask/depth | Unbundled commercial | Entitlements, redistribution, symbology, historical corrections, and market-close conventions must be enforced by the user. |
| Dealer/venue contribution data | liquidity, volume, order-book depth | Unbundled commercial | Venue-specific and structurally non-comparable; missingness is often non-random. |
| Public price aggregators | exploratory cross-checks only | Review required | Quote provenance, stale ticks, synthetic crosses, rate limits, and redistribution rights can be unclear. Never promote to authoritative silently. |
| Parallel-market observations | official publications, documented surveys, licensed/news research | Review per country/source | Illegality, thin trading, multiple quote types, and source safety create measurement and ethical risks. Report uncertainty and never invent continuity. |

## Global, commodity, and network inputs

- Global USD/rates/risk factors should be derived from individually licensed official or market series and frozen inside each training window.
- Commodity exposure can use World Bank/IMF public commodity indices subject to the corresponding terms; country-specific export weights must be dated.
- Trade networks may be built from IMF Direction of Trade Statistics or UN Comtrade after verifying current terms and revision behavior.
- BIS international banking claims are preferred for banking-exposure edges under BIS terms.
- Geographic proximity is static reference data, but state-boundary validity must be dated.
- Military alliances, migration, refugees, sanctions, and portfolio/common-creditor networks require separate source and license reviews; absence of an approved source is `MISSING`, not a zero edge.

## Publication lags and vintages

An adapter configuration must declare one of:

1. an observed source release timestamp;
2. a versioned release-calendar rule with archive evidence;
3. a conservative reconstructed lag;
4. unknown, which makes the value ineligible for a point-in-time model until resolved.

Period-end dating is not a release date. The source audit flags records whose release precedes period end, retrieval precedes release, vintage is absent for a revised source, license is unknown, or URL/provider metadata are missing.

## Source quality

Source authority and source quality are separate:

- authority measures the provider's institutional/measurement role;
- quality measures fitness of this series for this use, including comparability, coverage, revisions, and methodology;
- freshness measures age relative to the source's expected publication cadence;
- agreement measures consistency among independent sources.

These values affect evidence confidence and model inputs only as predeclared. They do not rewrite observed economics and do not cause low-coverage countries to appear safer.

## Reproducibility and redistribution

Production runs should create a manifest containing request URL/parameters, response digest, retrieval time, source release/vintage, terms URL/review date, parser version, and transformation lineage. Raw files remain in a user-controlled data store according to their licenses. Repository examples contain synthetic observations designed to exercise the pipeline; they must never be cited as empirical evidence about the named country.

