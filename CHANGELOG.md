# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- `--json FILE` writes a machine-readable summary of the report (totals, period-over-period changes, KPI target statuses, insights, campaign/ad set/ad/daily tables and breakdowns) with a versioned schema, for dashboards, automations and CI checks. Also available from Python as `meta_ads_report.summary.build_summary`.
- `--metrics-csv FILE` (with `--metrics-level campaign|adset|ad|daily`) exports the computed per-row metrics as a flat CSV.
- CSV exports are decoded automatically: UTF-8 with or without BOM, UTF-16 (LE/BE, with or without BOM, as some Ads Manager accounts export) and legacy cp1252.
- The delimiter is sniffed from the header row (comma, tab, semicolon or pipe), so tab-separated UTF-16 exports and semicolon files from spreadsheets load without conversion.
- Whitespace around header names is ignored.

## [0.1.0] - 2026-03-30

### Added
- CLI `meta-ads-report` that turns Ads Manager CSV exports into a single-file HTML report.
- Flexible column mapping layer (campaign, ad set, ad, spend, impressions, reach, link clicks, results, purchases, ROAS, dates).
- Metrics: CTR, CPC, CPM, cost per result, ROAS (spend weighted), frequency.
- Merging of several CSV files with duplicate-row protection for overlapping date ranges.
- Period-over-period comparison with `--previous`.
- Breakdown tables and charts for age, gender, placement, platform and region.
- Jinja2 template with `light`, `dark` and `ocean` themes; brand and logo text options.
- YAML config for KPI targets (pass/fail badges), insight thresholds and disabled rules.
- Pluggable rule-based insights engine, including loading custom rules with `--rules`.
- Optional XLSX export (openpyxl) and PDF export (weasyprint) with graceful fallback.
- Synthetic example data and a generated sample report.
