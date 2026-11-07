"""HTML rendering via Jinja2 (single self-contained file)."""
from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, List, Optional

from jinja2 import Environment, PackageLoader, select_autoescape

from . import __version__
from .charts import hbar_chart, line_chart
from .columns import BREAKDOWNS
from .config import TARGET_DEFS, Config, evaluate_targets
from .insights import Insight, generate_insights, top_bottom
from .metrics import Report, Stats, compare


def _env(currency: str) -> Environment:
    env = Environment(
        loader=PackageLoader("meta_ads_report", "templates"),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["money"] = lambda v: "-" if v is None else f"{v:,.2f}"
    env.filters["num"] = lambda v: "-" if v is None else f"{v:,.0f}"
    env.filters["pct"] = lambda v: "-" if v is None else f"{v:.2f}%"
    env.filters["ratio"] = lambda v: "-" if v is None else f"{v:.2f}"
    env.filters["x"] = lambda v: "-" if v is None else f"{v:.2f}x"
    return env


def fmt_metric(key: str, v: Optional[float], currency: str) -> str:
    """Human formatting of one metric for badges and charts."""
    if v is None:
        return "-"
    if key in ("ctr",):
        return f"{v:.2f}%"
    if key == "roas":
        return f"{v:.2f}x"
    if key == "frequency":
        return f"{v:.2f}"
    return f"{currency} {v:,.2f}"


def build_context(rep: Report, cfg: Config, insights: Optional[List[Insight]] = None) -> Dict[str, Any]:
    """Assemble everything the template needs (also reused by exporters)."""
    cur = rep.currency
    if insights is None:
        insights = generate_insights(rep, cfg.thresholds, cfg.disable_rules)
    prev_total = rep.previous.total if rep.previous else None
    kpis = []
    for key, label in (("spend", "Spend"), ("results", "Results"), ("cpa", "Cost / result"),
                       ("ctr", "CTR"), ("cpc", "CPC"), ("cpm", "CPM"), ("frequency", "Frequency"), ("roas", "ROAS")):
        v = rep.total.metric(key)
        if key == "roas" and v is None:
            continue
        kpis.append({
            "key": key, "label": label,
            "value": fmt_metric(key, v, cur) if key not in ("results",) else f"{v:,.0f}",
            "delta": compare(rep.total, prev_total, key),
        })
    badges = []
    for b in evaluate_targets(rep.total, cfg.targets):
        b["actual_s"] = fmt_metric(b["metric"], b["actual"], cur)
        b["target_s"] = fmt_metric(b["metric"], b["target"], cur)
        badges.append(b)
    camp_rows = []
    for c in rep.campaigns:
        camp_rows.append({
            "s": c,
            "checks": {b["metric"]: b["passed"] for b in evaluate_targets(c, cfg.targets)},
            "delta_cpa": compare(c, rep.previous.campaigns.get(c.name), "cpa") if rep.previous else None,
            "delta_spend": compare(c, rep.previous.campaigns.get(c.name), "spend") if rep.previous else None,
        })
    top, bottom = top_bottom(rep.campaigns, cfg.top_n)
    ad_top, ad_bottom = top_bottom(rep.ads, cfg.top_n)
    charts = {
        "spend": hbar_chart(rep.campaigns, lambda s: s.spend, lambda v: f"{v:,.0f}", "var(--accent)", f"Spend by campaign ({cur})"),
        "results": hbar_chart(rep.campaigns, lambda s: s.results or s.purchases, lambda v: f"{v:,.0f}", "var(--accent2)", "Results by campaign"),
        "daily": line_chart([d.name for d in rep.daily], [[d.spend for d in rep.daily], [d.results or d.purchases for d in rep.daily]],
                            ["var(--accent)", "var(--accent2)"], ["Spend", "Results"], "Daily spend vs results") if rep.daily else "",
    }
    breakdowns = []
    for dim, items in rep.breakdowns.items():
        breakdowns.append({
            "title": BREAKDOWNS[dim], "rows": items,
            "chart": hbar_chart(items, lambda s: s.spend, lambda v: f"{v:,.0f}", "var(--accent)", f"Spend by {BREAKDOWNS[dim].lower()}"),
        })
    return {
        "rep": rep, "cfg": cfg, "cur": cur, "kpis": kpis, "badges": badges, "camp_rows": camp_rows,
        "insights": insights, "top": top, "bottom": bottom, "ad_top": ad_top, "ad_bottom": ad_bottom,
        "charts": charts, "breakdowns": breakdowns, "has_roas": rep.total.roas is not None,
        "target_cols": {TARGET_DEFS[k][0] for k in cfg.targets},
        "generated": _dt.date.today().isoformat(), "version": __version__,
        "period": f"{rep.start} to {rep.end}" if rep.start else "",
        "prev_period": f"{rep.previous.start} to {rep.previous.end}" if rep.previous and rep.previous.start else "",
    }


def render_html(rep: Report, cfg: Config, insights: Optional[List[Insight]] = None) -> str:
    """Render the full report as a single HTML string."""
    ctx = build_context(rep, cfg, insights)
    return _env(rep.currency).get_template("report.html.j2").render(**ctx)


__all__ = ["render_html", "build_context", "fmt_metric", "Stats"]
