import pytest

from meta_ads_report.insights import (
    Insight,
    InsightContext,
    generate_insights,
    registered_rules,
    rule,
    top_bottom,
)
from meta_ads_report.metrics import Report, Stats


def make_stats(name, spend, impr, reach, clicks, results, roas=0.0):
    s = Stats(name)
    s.add({"spend": spend, "impressions": impr, "reach": reach, "clicks": clicks, "results": results, "roas": roas})
    return s


def make_report(*campaigns):
    rep = Report(currency="USD")
    for c in campaigns:
        rep.campaigns.append(c)
        for f in ("spend", "impressions", "reach", "clicks", "results", "purchase_value"):
            setattr(rep.total, f, getattr(rep.total, f) + getattr(c, f))
    rep.campaigns.sort(key=lambda s: s.spend, reverse=True)
    return rep


def texts(ins):
    return " | ".join(i.text for i in ins)


def test_high_frequency_warns():
    rep = make_report(make_stats("A", 100, 40000, 10000, 800, 10))  # freq 4
    ins = generate_insights(rep)
    assert any(i.level == "warn" and "frequency" in i.text.lower() for i in ins)


def test_frequency_threshold_configurable():
    rep = make_report(make_stats("A", 100, 25000, 10000, 800, 10))  # freq 2.5
    assert not any("frequency" in i.text.lower() for i in generate_insights(rep))
    assert any("frequency" in i.text.lower() for i in generate_insights(rep, {"frequency_warn": 2}))


def test_low_ctr_warns():
    rep = make_report(make_stats("A", 100, 50000, 40000, 250, 10))  # 0.5%
    assert "below 1%" in texts(generate_insights(rep))


def test_high_ctr_is_good():
    rep = make_report(make_stats("A", 100, 10000, 9000, 300, 10))  # 3%
    assert any(i.level == "good" and "CTR" in i.text for i in generate_insights(rep))


def test_small_sample_ctr_ignored():
    rep = make_report(make_stats("A", 1, 100, 90, 0, 0))
    assert "CTR" not in texts(generate_insights(rep))


def test_roas_below_one_and_scaling_hint():
    low = make_report(make_stats("A", 100, 10000, 9000, 200, 5, roas=0.5))
    assert "not yet paying" in texts(generate_insights(low))
    high = make_report(make_stats("A", 100, 10000, 9000, 200, 5, roas=4.0))
    assert "scaling" in texts(generate_insights(high))


def test_campaign_without_results_flagged():
    rep = make_report(make_stats("Winner", 100, 20000, 15000, 400, 20), make_stats("Dud", 100, 20000, 15000, 400, 0))
    assert "'Dud' spent USD 100.00 with no results" in texts(generate_insights(rep))


def test_expensive_campaign_flagged():
    rep = make_report(make_stats("Cheap", 100, 20000, 15000, 400, 50), make_stats("Pricey", 100, 20000, 15000, 400, 5))
    assert "'Pricey' costs USD 20.00" in texts(generate_insights(rep))


def test_best_campaign_and_concentration():
    rep = make_report(make_stats("Big", 800, 90000, 60000, 1800, 40), make_stats("Small", 100, 20000, 15000, 400, 10))
    t = texts(generate_insights(rep))
    assert "Best efficiency" in t
    assert "89%" in t


def test_no_spend():
    ins = generate_insights(Report())
    assert len(ins) == 1 and "No spend" in ins[0].text


def test_disable_rule():
    rep = make_report(make_stats("A", 100, 40000, 10000, 800, 10))
    assert any("Overall frequency" in i.text for i in generate_insights(rep))
    assert not any("Overall frequency" in i.text for i in generate_insights(rep, disable=["overall_frequency"]))


def test_custom_rule_registration():
    @rule("test_custom_rule")
    def _custom(ctx: InsightContext):
        return [Insight("info", f"custom saw {ctx.cur}")]

    try:
        assert "test_custom_rule" in registered_rules()
        rep = make_report(make_stats("A", 100, 10000, 5000, 200, 10))
        assert any(i.text == "custom saw USD" and i.rule == "test_custom_rule" for i in generate_insights(rep))
    finally:
        from meta_ads_report import insights
        insights._RULES.pop("test_custom_rule", None)


def test_warnings_sorted_first():
    rep = make_report(make_stats("A", 100, 40000, 10000, 800, 10))
    levels = [i.level for i in generate_insights(rep)]
    assert levels == sorted(levels, key=lambda x: {"warn": 0, "good": 1, "info": 2}[x])


def test_period_comparison_rule():
    from meta_ads_report.metrics import Comparison
    rep = make_report(make_stats("A", 100, 20000, 10000, 400, 5))
    prev = make_stats("P", 100, 20000, 10000, 400, 20)
    rep.previous = Comparison(total=prev, campaigns={})
    t = texts(generate_insights(rep))
    assert "Results dropped 75%" in t and "Cost per result rose" in t


def test_top_bottom_split():
    items = [make_stats(n, 100, 1000, 900, 10, r) for n, r in [("a", 50), ("b", 25), ("c", 10), ("d", 5), ("e", 0)]]
    top, bottom = top_bottom(items, 2)
    assert [s.name for s in top] == ["a", "b"]
    assert [s.name for s in bottom] == ["d", "c"]
    assert not {s.name for s in top} & {s.name for s in bottom}


@pytest.mark.parametrize("count", [0, 1, 2, 3])
def test_top_bottom_small_inputs(count):
    items = [make_stats(str(i), 100, 1000, 900, 10, i + 1) for i in range(count)]
    top, bottom = top_bottom(items, 3)
    assert len(top) + len(bottom) == count
