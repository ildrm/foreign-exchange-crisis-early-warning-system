# Changelog

All notable project changes are documented here. Versions follow semantic versioning for software; methodology, taxonomy, calibration, schema, and alert-policy versions evolve independently and are recorded in every report.

## 0.1.0 — 2026-08-27

### Added

- Point-in-time observation, provenance, missingness, vintage, and imputation contracts.
- Eight-hazard versioned taxonomy with uncertain onset intervals and event clustering.
- Country/currency/regime mappings, interval validation, currency succession, unions, dollarization, controls, and multiple-rate support.
- FX stress formulas including EMP, parallel premium, and global-factor residual surprise.
- Dependency-light model baselines, calibration tools, rare-event metrics, chronological backtests, holdouts, and FX ablation.
- Separate risk/evidence alert channels with hazard-specific policies, gating, momentum, and hysteresis.
- Canonical JSON schema 1.0.0 and deterministic report serialization/validation.
- Self-contained, responsive, print-safe institutional HTML report with inline SVG and accessibility semantics.
- Optional Playwright A4-landscape PDF exporter.
- CLI, panel builder, provenance audit, repository validator, CI, and multi-layer deterministic tests.
- Synthetic example report that is visibly and structurally `RESEARCH_UNCALIBRATED`.
- Architecture, methodology, taxonomy, data-source, backtesting, alert-policy, and model-card documentation.

### Scientific status

- No empirical calibrated model or operational threshold is released.
- Severe operational alerts remain disabled for bundled examples.
- Current performance is explicitly not established.

