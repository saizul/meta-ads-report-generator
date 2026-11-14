"""Machine-readable JSON summary of a report (CLI: ``--json FILE``).

The HTML report is for people; the summary is for scripts: dashboards, Slack
or email automations, n8n/Zapier flows and CI checks. It carries the same
numbers as the report (totals, period comparison, KPI targets, insights and
the per-entity tables) in a stable, documented structure.
"""
from __future__ import annotations

import datetime as _dt
import json
import math
from typing import Any, Dict, List, Optional

from . import __version__
from .columns import BREAKDOWNS
from .config import Config, evaluate_targets
from .insights import Insight, generate_insights
from .metrics import METRIC_DIRECTION, Report, Stats, compare

#: bumped when a key is renamed or removed (adding keys does not bump it)
SCHEMA_VERSION = 1

#: metrics written for every entity, in output order
SUMMARY_METRICS = ("spend", "impressions", "reach", "clicks", "results", "purchases",
                   "ctr", "cpc", "cpm", "cpa", "frequency", "roas")

_COUNTS = ("impressions", "reach", "clicks", "results", "purchases")
_STATUS = {True: "pass", False: "fail", None: "n/a"}


def _num(value: Optional[float], key: str = "") -> Optional[float]:
    """Round for output; None for missing or non-finite values (JSON has no NaN)."""
    if value is None or not math.isfinite(value):
        return None
    if key in _COUNTS and float(value).is_integer():
        return int(value)
    return round(value, 2 if key == "spend" else 4)


def stats_dict(stats: Stats, with_name: bool = True) -> Dict[str, Any]:
    """One entity as a plain dict. ``results`` falls back to purchases like the report."""
    out: Dict[str, Any] = {}
    if with_name:
        out["name"] = stats.name
        if stats.parent:
            out["parent"] = stats.parent
    for key in SUMMARY_METRICS:
        value = stats.metric(key)
        if key == "results":
            value = stats.results or stats.purchases
        out[key] = _num(value, key)
    if stats.result_type:
        out["result_type"] = stats.result_type
    return out


def changes_dict(current: Stats, previous: Optional[Stats]) -> Dict[str, Any]:
    """Percentage change per metric versus the previous period.

    ``direction`` is ``better``, ``worse`` or ``flat`` taking into account
    whether a higher value is good (CTR, ROAS) or bad (CPC, CPA, frequency).
    """
    out: Dict[str, Any] = {}
    for key in METRIC_DIRECTION:
        delta = compare(current, previous, key)
        if delta is None:
            continue
        good = delta["good"]
        out[key] = {
            "pct": round(float(delta["pct"]), 2),
            "direction": "flat" if good is None else ("better" if good else "worse"),
        }
    return out


def targets_list(stats: Stats, targets: Dict[str, float]) -> List[Dict[str, Any]]:
    """KPI targets evaluated against ``stats`` with a pass/fail/n/a status."""
    out = []
    for b in evaluate_targets(stats, targets):
        out.append({
            "key": b["key"], "metric": b["metric"], "label": b["label"], "op": b["op"],
            "target": b["target"], "actual": _num(b["actual"]), "status": _STATUS[b["passed"]],
        })
    return out


def _campaign(stats: Stats, rep: Report, cfg: Config) -> Dict[str, Any]:
    row = stats_dict(stats)
    total = rep.total.spend
    row["spend_share"] = round(stats.spend / total * 100, 2) if total > 0 else None
    if cfg.targets:
        row["targets"] = {t["key"]: t["status"] for t in targets_list(stats, cfg.targets)}
    if rep.previous:
        row["changes"] = changes_dict(stats, rep.previous.campaigns.get(stats.name))
    return row


def build_summary(rep: Report, cfg: Config, insights: Optional[List[Insight]] = None) -> Dict[str, Any]:
    """Assemble the JSON-serialisable summary for a report."""
    if insights is None:
        insights = generate_insights(rep, cfg.thresholds, cfg.disable_rules)
    targets = targets_list(rep.total, cfg.targets)
    statuses = [t["status"] for t in targets]
    summary: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generator": {"name": "meta-ads-report", "version": __version__},
        "generated": _dt.date.today().isoformat(),
        "title": cfg.title,
        "brand": cfg.brand,
        "currency": rep.currency,
        "period": {"start": rep.start or None, "end": rep.end or None},
        "sources": {"files": len(rep.sources), "duplicates_dropped": rep.duplicates_dropped,
                    "rows_filtered": rep.rows_filtered},
        "filters": rep.filters.to_dict() if rep.filters else None,
        "totals": stats_dict(rep.total, with_name=False),
        "previous": None,
        "targets": targets,
        "targets_summary": {
            "passed": statuses.count("pass"), "failed": statuses.count("fail"),
            "not_available": statuses.count("n/a"),
            "all_passed": bool(targets) and all(s == "pass" for s in statuses),
        },
        "insights": [{"level": i.level, "rule": i.rule, "text": i.text} for i in insights],
        "campaigns": [_campaign(c, rep, cfg) for c in rep.campaigns],
        "adsets": [stats_dict(s) for s in rep.adsets],
        "ads": [stats_dict(s) for s in rep.ads],
        "daily": [dict(stats_dict(d, with_name=False), date=d.name) for d in rep.daily],
        "breakdowns": {
            dim: {"title": BREAKDOWNS[dim], "rows": [stats_dict(s) for s in rows]}
            for dim, rows in rep.breakdowns.items()
        },
    }
    if rep.previous:
        prev = rep.previous
        summary["previous"] = {
            "period": {"start": prev.start or None, "end": prev.end or None},
            "totals": stats_dict(prev.total, with_name=False),
            "changes": changes_dict(rep.total, prev.total),
        }
    return summary


def dumps_summary(summary: Dict[str, Any]) -> str:
    """Serialise deterministically (insertion order, UTF-8 text kept as is)."""
    return json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False) + "\n"


def write_summary_json(rep: Report, cfg: Config, path: str,
                       insights: Optional[List[Insight]] = None) -> Dict[str, Any]:
    """Write the summary to ``path`` and return it."""
    summary = build_summary(rep, cfg, insights)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(dumps_summary(summary))
    return summary
