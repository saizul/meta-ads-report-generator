"""Rule-based insights engine with a pluggable rule registry.

A rule is a function ``(ctx: InsightContext) -> list[Insight]`` registered with
:func:`rule`. Custom rules can be loaded from a Python file with
:func:`load_rule_module` (CLI: ``--rules my_rules.py``).
"""
from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from .config import DEFAULT_THRESHOLDS
from .metrics import Report, Stats, pct_change

LEVELS = ("good", "warn", "info")


@dataclass
class Insight:
    level: str  # one of LEVELS
    text: str
    rule: str = ""


@dataclass
class InsightContext:
    report: Report
    thresholds: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_THRESHOLDS))

    @property
    def cur(self) -> str:
        return self.report.currency

    def money(self, v: float) -> str:
        return f"{self.cur} {v:,.2f}"

    def significant_campaigns(self) -> List[Stats]:
        """Campaigns with enough spend/impressions to judge fairly."""
        total = self.report.total.spend
        if total <= 0:
            return []
        return [
            c for c in self.report.campaigns
            if c.spend / total >= self.thresholds["min_spend_share"]
            and c.impressions >= self.thresholds["min_impressions"]
        ]


RuleFn = Callable[[InsightContext], List[Insight]]
_RULES: Dict[str, RuleFn] = {}


def rule(name: str) -> Callable[[RuleFn], RuleFn]:
    """Decorator registering a rule under ``name``."""
    def deco(fn: RuleFn) -> RuleFn:
        _RULES[name] = fn
        return fn
    return deco


def registered_rules() -> List[str]:
    return list(_RULES)


def load_rule_module(path: str) -> None:
    """Import a Python file so that its ``@rule`` decorators register rules."""
    spec = importlib.util.spec_from_file_location("meta_ads_custom_rules", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load rules from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)


@rule("overall_frequency")
def _overall_frequency(ctx: InsightContext) -> List[Insight]:
    f = ctx.report.total.frequency
    if f is not None and f > ctx.thresholds["frequency_warn"]:
        return [Insight("warn", f"Overall frequency is {f:.2f} (above {ctx.thresholds['frequency_warn']:g}). "
                                "Expect creative fatigue: refresh ads or widen the audience.")]
    return []


@rule("overall_ctr")
def _overall_ctr(ctx: InsightContext) -> List[Insight]:
    t = ctx.report.total
    if t.ctr is None or t.impressions < ctx.thresholds["min_impressions"]:
        return []
    if t.ctr < ctx.thresholds["ctr_warn"]:
        return [Insight("warn", f"Overall link CTR is {t.ctr:.2f}%, below {ctx.thresholds['ctr_warn']:g}%. "
                                "Test stronger hooks, creatives or audience targeting.")]
    if t.ctr >= ctx.thresholds["ctr_good"]:
        return [Insight("good", f"Overall link CTR is a healthy {t.ctr:.2f}%.")]
    return []


@rule("overall_roas")
def _overall_roas(ctx: InsightContext) -> List[Insight]:
    r = ctx.report.total.roas
    if r is None:
        return []
    if r < 1:
        return [Insight("warn", f"Overall ROAS is {r:.2f}x, so the ads are not yet paying for themselves.")]
    if r >= ctx.thresholds["roas_good"]:
        return [Insight("good", f"Overall ROAS is {r:.2f}x. Consider scaling budgets gradually (about 20% at a time).")]
    return []


@rule("campaign_health")
def _campaign_health(ctx: InsightContext) -> List[Insight]:
    out: List[Insight] = []
    t = ctx.report.total
    th = ctx.thresholds
    for c in ctx.significant_campaigns():
        if c.results == 0 and c.purchases == 0:
            out.append(Insight("warn", f"Campaign '{c.name}' spent {ctx.money(c.spend)} with no results. Pause or rework it."))
            continue
        if c.frequency is not None and c.frequency > th["frequency_warn"]:
            out.append(Insight("warn", f"Campaign '{c.name}' has frequency {c.frequency:.2f}: the audience sees the same ads too often."))
        if c.ctr is not None and c.ctr < th["ctr_warn"]:
            out.append(Insight("warn", f"Campaign '{c.name}' has CTR {c.ctr:.2f}% (below {th['ctr_warn']:g}%)."))
        if c.roas is not None and c.roas < 1:
            out.append(Insight("warn", f"Campaign '{c.name}' ROAS is {c.roas:.2f}x (below break-even)."))
        if t.cpa and c.cpa and c.cpa > th["cpa_multiple"] * t.cpa:
            out.append(Insight("warn", f"Campaign '{c.name}' costs {ctx.money(c.cpa)} per result, over {th['cpa_multiple']:g}x the account average ({ctx.money(t.cpa)})."))
    return out


@rule("best_campaign")
def _best_campaign(ctx: InsightContext) -> List[Insight]:
    best = best_campaign(ctx)
    if best is not None and len(ctx.report.campaigns) > 1:
        return [Insight("good", f"Best efficiency: '{best.name}' at {ctx.money(best.cpa)} per result. Shift budget toward it if volume holds.")]
    return []


@rule("spend_concentration")
def _spend_concentration(ctx: InsightContext) -> List[Insight]:
    t = ctx.report.total
    cs = ctx.report.campaigns
    if len(cs) > 1 and t.spend > 0 and cs[0].spend / t.spend > ctx.thresholds["concentration_share"]:
        return [Insight("info", f"'{cs[0].name}' takes {cs[0].spend / t.spend:.0%} of total spend. Results depend heavily on one campaign.")]
    return []


@rule("breakdown_outliers")
def _breakdown_outliers(ctx: InsightContext) -> List[Insight]:
    out: List[Insight] = []
    for dim, items in ctx.report.breakdowns.items():
        total = sum(i.spend for i in items)
        ranked = [i for i in items if i.cpa and total and i.spend / total >= ctx.thresholds["min_spend_share"]]
        if len(ranked) < 2:
            continue
        best, worst = min(ranked, key=lambda i: i.cpa), max(ranked, key=lambda i: i.cpa)
        if worst.cpa > 1.5 * best.cpa:
            out.append(Insight("info", f"By {dim}: '{best.name}' delivers results at {ctx.money(best.cpa)} while '{worst.name}' costs {ctx.money(worst.cpa)}. Consider reallocating budget."))
    return out


@rule("period_comparison")
def _period_comparison(ctx: InsightContext) -> List[Insight]:
    prev = ctx.report.previous
    if prev is None:
        return []
    t, p = ctx.report.total, prev.total
    out: List[Insight] = []
    drop = ctx.thresholds["wow_drop_pct"]
    cpa_ch = pct_change(t.cpa, p.cpa)
    if cpa_ch is not None and cpa_ch > drop:
        out.append(Insight("warn", f"Cost per result rose {cpa_ch:.0f}% versus the previous period."))
    elif cpa_ch is not None and cpa_ch < -drop:
        out.append(Insight("good", f"Cost per result fell {abs(cpa_ch):.0f}% versus the previous period."))
    res_ch = pct_change(t.results, p.results)
    if res_ch is not None and res_ch < -drop:
        out.append(Insight("warn", f"Results dropped {abs(res_ch):.0f}% versus the previous period."))
    elif res_ch is not None and res_ch > drop:
        out.append(Insight("good", f"Results grew {res_ch:.0f}% versus the previous period."))
    return out


def best_campaign(ctx: InsightContext) -> Optional[Stats]:
    cands = [c for c in ctx.significant_campaigns() if c.cpa and (c.results + c.purchases) > 0]
    return min(cands, key=lambda c: c.cpa) if cands else None


def generate_insights(
    report: Report,
    thresholds: Optional[Dict[str, float]] = None,
    disable: Optional[List[str]] = None,
) -> List[Insight]:
    """Run all registered rules (except ``disable``) and return their insights."""
    if report.total.spend <= 0:
        return [Insight("info", "No spend recorded in this period.", "empty")]
    th = dict(DEFAULT_THRESHOLDS)
    th.update(thresholds or {})
    ctx = InsightContext(report, th)
    out: List[Insight] = []
    for name, fn in _RULES.items():
        if disable and name in disable:
            continue
        for ins in fn(ctx):
            ins.rule = ins.rule or name
            out.append(ins)
    order = {lvl: i for i, lvl in enumerate(("warn", "good", "info"))}
    out.sort(key=lambda i: order.get(i.level, 9))
    if not out:
        out.append(Insight("info", "No major issues detected by the automatic checks.", "none"))
    return out


def top_bottom(items: List[Stats], n: int = 3) -> Tuple[List[Stats], List[Stats]]:
    """Rank by cost per result (lower is better); entities without results are excluded.
    The ranking is split so the same entity never appears in both lists."""
    ranked = sorted((i for i in items if i.cpa), key=lambda s: s.cpa)
    top = ranked[: min(n, (len(ranked) + 1) // 2)]
    bottom = list(reversed(ranked[len(top):]))[:n]
    return top, bottom
