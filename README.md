# meta-ads-report

[![CI](https://github.com/saizul/meta-ads-report-generator/actions/workflows/ci.yml/badge.svg)](https://github.com/saizul/meta-ads-report-generator/actions/workflows/ci.yml) ![Python](https://img.shields.io/badge/Python-ready-blue?logo=python&logoColor=white) ![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)

Turn Meta (Facebook) Ads Manager CSV exports into a clean, client-ready, single-file HTML report, with optional PDF and Excel output.

Built by [Saizul Amin](https://saizul.com). MIT licensed.

## Features

- **Flexible column mapping**: handles `Amount spent (USD)` / `(BDT)`, `Link clicks` vs `Clicks (all)`, `Purchase ROAS (return on ad spend)`, `Reporting starts/ends`, `Day` and more.
- **Metrics**: CTR, CPC, CPM, cost per result, ROAS (spend weighted), frequency, with totals and campaign / ad set / ad tables.
- **Multiple CSVs merged**: pass weekly exports for a date range; rows repeated across overlapping files are skipped.
- **Period over period**: `--previous` adds deltas (green when the change is an improvement) to KPIs and campaigns.
- **Breakdowns**: age, gender, placement, platform and region columns get their own tables and charts. Breakdown rows never inflate totals.
- **KPI targets**: YAML config produces pass/fail badges and per-cell checkmarks.
- **Insights engine**: pluggable rules (creative fatigue when frequency > 3, CTR < 1%, campaigns with zero results, expensive campaigns, ROAS below break-even, spend concentration, breakdown outliers, period regressions).
- **Output**: one self-contained HTML file with inline SVG charts and three themes (`light`, `dark`, `ocean`). Optional `--xlsx` and `--pdf`.
- Brand name and logo text, currency label (BDT / USD / anything).

[`examples/sample-report.html`](examples/sample-report.html) is a report generated from synthetic data (no real accounts).

## Install

```bash
pip install .                 # core (Jinja2 + PyYAML)
pip install ".[xlsx]"         # + Excel export
pip install ".[pdf]"          # + PDF export (weasyprint, needs system libs)
```

Python 3.9 or newer.

## Usage

```bash
# simplest
meta-ads-report export.csv -o report.html

# two weekly files, compared with the previous period, with targets and branding
meta-ads-report week1.csv week2.csv \
  --previous last-month.csv \
  --config examples/targets.yaml \
  --brand "Demo Studio" --currency BDT --theme dark \
  --xlsx report.xlsx --pdf report.pdf

# add breakdown exports (age/gender, placement, region) alongside the main export
meta-ads-report main.csv age-gender.csv placement.csv -o report.html
```

If weasyprint is not installed (or its system libraries are missing) the HTML is still written and the tool prints a warning and exits with status 1.

### Options

| Option | Purpose |
| --- | --- |
| `-o, --output` | HTML path (default `report.html`) |
| `--previous CSV...` | previous-period export(s) for comparison |
| `-c, --config` | YAML config (below) |
| `--currency` | label such as `BDT`, `USD` (default: detected from the spend column) |
| `--brand`, `--logo-text`, `--title` | header branding |
| `--theme` | `light`, `dark`, `ocean` |
| `--xlsx FILE`, `--pdf FILE` | extra exports |
| `--metrics-csv FILE`, `--metrics-level {campaign,adset,ad,daily}` | write the computed metrics (spend, CTR, CPC, CPM, frequency, cost per result, ROAS) as a flat CSV, one row per campaign (default), ad set, ad or day; ready for Sheets, BI tools or scripts |
| `--rules FILE.py` | load custom insight rules |
| `--no-dedupe` | keep rows repeated across files |

### Exporting from Ads Manager

Files are read as UTF-8 (with or without BOM), UTF-16 (some accounts download UTF-16 tab-separated files) or Windows-1252, and the delimiter (comma, tab, semicolon or pipe) is detected from the header row, so you can feed exports straight in without re-saving them.

Export with columns: Campaign name, Ad set name, Ad name, Amount spent, Impressions, Reach, Link clicks, Results, Result type, Cost per result, Purchases, Purchase ROAS. Use a "Day" breakdown to get the daily chart. Age, gender, placement and region breakdowns come from Ads Manager's Breakdown menu; export each as its own CSV.

## Config file

```yaml
brand: Demo Studio
logo_text: DS
title: Meta Ads Performance Report
currency: BDT
theme: ocean
targets:            # ctr_min, cpc_max, cpm_max, cpa_max, roas_min, frequency_max
  ctr_min: 1.5
  cpa_max: 450
  roas_min: 3
  frequency_max: 2.5
thresholds:         # tune the insight rules
  frequency_warn: 3
  ctr_warn: 1
disable_rules: [spend_concentration]
```

Command line flags override the config file.

## Custom insight rules

```python
# my_rules.py
from meta_ads_report.insights import Insight, rule

@rule("high_cpm")
def high_cpm(ctx):
    cpm = ctx.report.total.cpm
    if cpm and cpm > 300:
        return [Insight("warn", f"CPM is {ctx.money(cpm)}: check audience overlap.")]
    return []
```

```bash
meta-ads-report export.csv --rules my_rules.py
```

## Notes on the maths

- CTR = link clicks / impressions, CPC = spend / clicks, CPM = spend / impressions x 1000.
- Cost per result = spend / results (purchases are used when there is no results column). Mixed result types in one export are summed, so compare like with like.
- ROAS is spend weighted: sum(spend x ROAS) / sum(spend).
- Reach cannot be de-duplicated from a CSV, so summed reach (and therefore aggregate frequency) is an approximation.

## Development

```bash
pip install -e ".[dev]"
ruff check . && pytest -q
python examples/generate_sample.py   # regenerate synthetic CSVs
```

See [CONTRIBUTING.md](CONTRIBUTING.md). Licensed under the [MIT License](LICENSE).
