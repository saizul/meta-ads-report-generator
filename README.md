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
- **JSON summary**: `--json` writes the same numbers in a stable, versioned structure for dashboards, automations and CI checks.
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
| `--json FILE` | write a machine-readable JSON summary (see [JSON summary](#json-summary)) |
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

## JSON summary

`--json FILE` writes the numbers behind the report as JSON, so a script can post the weekly figures to Slack, feed a dashboard, or fail a scheduled job when a KPI target is missed.

```bash
meta-ads-report week.csv --previous last-week.csv -c targets.yaml --json summary.json
jq -r '.targets[] | select(.status == "fail") | "\(.label): \(.actual) (target \(.op) \(.target))"' summary.json
jq -e '.targets_summary.failed == 0' summary.json > /dev/null || echo "KPI targets missed"
```

```json
{
  "schema_version": 1,
  "currency": "BDT",
  "period": {"start": "2026-03-16", "end": "2026-03-29"},
  "totals": {"spend": 61250.4, "impressions": 318420, "clicks": 7410, "results": 142, "ctr": 2.3271, "cpa": 431.3408, "roas": 3.12},
  "previous": {"period": {"start": "2026-03-02", "end": "2026-03-15"}, "totals": {}, "changes": {"cpa": {"pct": -8.4, "direction": "better"}}},
  "targets": [{"key": "cpa_max", "metric": "cpa", "label": "Cost per result", "op": "<=", "target": 450.0, "actual": 431.3408, "status": "pass"}],
  "targets_summary": {"passed": 3, "failed": 1, "not_available": 0, "all_passed": false},
  "insights": [{"level": "warn", "rule": "campaign_health", "text": "..."}],
  "campaigns": [{"name": "Eid Sale - Prospecting", "spend": 30110.2, "spend_share": 49.16, "targets": {"cpa_max": "pass"}, "changes": {}}]
}
```

(The example is shortened and the numbers are illustrative.)

| Key | Content |
| --- | --- |
| `schema_version` | integer, raised only when a key is renamed or removed |
| `generator`, `generated`, `title`, `brand`, `currency` | report metadata |
| `period`, `sources` | date range, number of files merged and duplicate rows dropped |
| `totals` | spend, impressions, reach, clicks, results, purchases, ctr, cpc, cpm, cpa, frequency, roas |
| `previous` | `null` without `--previous`; otherwise the previous period, its totals and `changes` per metric (`pct` plus `direction`: `better`, `worse` or `flat`, which accounts for lower-is-better metrics such as CPA) |
| `targets`, `targets_summary` | each configured KPI target with `status` `pass`, `fail` or `n/a`, and the counts |
| `insights` | level (`good`, `warn`, `info`), rule name and text of every insight |
| `campaigns` | metrics per campaign plus `spend_share` (percent), per-target statuses and changes versus the previous period |
| `adsets`, `ads`, `daily`, `breakdowns` | the remaining tables of the report |

Metrics that cannot be computed (for example ROAS without purchase value) are `null`. Money is not formatted: values are plain numbers in the report currency. The same structure is available from Python:

```python
from meta_ads_report.config import load_config
from meta_ads_report.metrics import build_report
from meta_ads_report.summary import build_summary

summary = build_summary(build_report(["week.csv"]), load_config("targets.yaml"))
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
