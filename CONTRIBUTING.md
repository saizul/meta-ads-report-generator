# Contributing

Thanks for taking the time to improve meta-ads-report.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Before you open a pull request

```bash
ruff check .      # lint
pytest -q         # tests
```

- Python 3.9 is the minimum supported version, so avoid `X | Y` type syntax at runtime
  and keep `from __future__ import annotations` in modules.
- Add tests for every behaviour change (column mapping, metric maths and insight rules each have their own test module).
- Use only synthetic data in tests and examples. Never commit real client exports.
  `python examples/generate_sample.py` regenerates the sample CSVs.

## Adding an insight rule

Rules live in `src/meta_ads_report/insights.py`. A rule is a function that takes an
`InsightContext` and returns a list of `Insight` objects:

```python
from meta_ads_report.insights import Insight, rule

@rule("my_rule")
def my_rule(ctx):
    if ctx.report.total.cpm and ctx.report.total.cpm > 500:
        return [Insight("warn", "CPM is unusually high.")]
    return []
```

Thresholds go in `DEFAULT_THRESHOLDS` in `config.py` so users can tune them from YAML.

## Adding a column alias

Add the normalised (lowercase, letters and digits only) header to `ALIASES` in
`columns.py` and extend `tests/test_columns.py`.

## Commit style

Small, focused commits with a clear message. Update `CHANGELOG.md` for user-facing changes.
