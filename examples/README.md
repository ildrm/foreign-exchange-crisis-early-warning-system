# Examples

All bundled examples are synthetic pipeline fixtures. They exercise country/currency regimes, explicit missingness, provenance, horizon term structures, alert gating, HTML rendering, and audit behavior. They are not observations or forecasts about the named countries.

- `example_report.json`: generated canonical report for the fixed 2024-01-31 synthetic Türkiye profile.
- `example_report.html`: the same canonical object rendered as one offline HTML file.
- `normalized_market.json`: optional normalized market-section override.
- `normalized_events.json`: optional event/timeline overlay illustrating the CLI input contract.

Regenerate the main artifacts from the repository root:

```bash
python crisis_dashboard.py --countries tr --as-of 2024-01-31 --no-web \
  --event-database examples/normalized_events.json \
  --validate --source-audit \
  --output examples/example_report.json \
  --html examples/example_report.html
```
