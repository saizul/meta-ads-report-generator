import json

import pytest

from meta_ads_report.cli import main
from meta_ads_report.config import Config
from meta_ads_report.insights import Insight
from meta_ads_report.metrics import Stats, build_report
from meta_ads_report.summary import (
    SCHEMA_VERSION,
    SUMMARY_METRICS,
    build_summary,
    changes_dict,
    dumps_summary,
    stats_dict,
    targets_list,
    write_summary_json,
)


def make(**kw):
    s = Stats(kw.pop("name", "x"), kw.pop("parent", ""))
    s.add(kw)
    return s


def test_stats_dict_values_and_rounding():
    s = make(name="Camp", spend=100.456, impressions=30000, reach=7000, clicks=200, results=3, roas=2.0)
    d = stats_dict(s)
    assert d["name"] == "Camp" and "parent" not in d
    assert d["spend"] == 100.46
    assert d["impressions"] == 30000 and isinstance(d["impressions"], int)
    assert d["ctr"] == 0.6667
    assert d["cpa"] == round(100.456 / 3, 4)
    assert d["roas"] == 2.0
    assert d["frequency"] == round(30000 / 7000, 4)
    assert list(k for k in d if k != "name") == list(SUMMARY_METRICS)


def test_stats_dict_missing_metrics_are_null():
    d = stats_dict(Stats("empty"))
    assert d["ctr"] is None and d["cpc"] is None and d["cpa"] is None and d["roas"] is None
    assert d["spend"] == 0 and d["impressions"] == 0


def test_stats_dict_parent_result_type_and_no_name():
    s = make(name="Ad 1", parent="Set 1", spend=10, impressions=100, result_type="Purchases")
    d = stats_dict(s)
    assert d["parent"] == "Set 1" and d["result_type"] == "Purchases"
    assert "name" not in stats_dict(s, with_name=False)


def test_stats_dict_results_fall_back_to_purchases():
    d = stats_dict(make(spend=50, impressions=100, purchases=5))
    assert d["results"] == 5 and d["purchases"] == 5 and d["cpa"] == 10.0


def test_stats_dict_fractional_counts_kept():
    assert stats_dict(make(spend=1, impressions=10, results=2.5))["results"] == 2.5


def test_changes_dict_direction_respects_lower_is_better():
    cur = make(spend=100, impressions=10000, clicks=300, results=20)
    prev = make(spend=100, impressions=10000, clicks=200, results=10)
    ch = changes_dict(cur, prev)
    assert ch["cpa"] == {"pct": -50.0, "direction": "better"}
    assert ch["ctr"] == {"pct": 50.0, "direction": "better"}
    assert ch["spend"] == {"pct": 0.0, "direction": "flat"}
    assert ch["cpc"]["direction"] == "better"
    worse = changes_dict(prev, cur)
    assert worse["cpa"] == {"pct": 100.0, "direction": "worse"}
    assert worse["clicks"]["direction"] == "worse"


def test_changes_dict_skips_undefined_and_missing_previous():
    cur = make(spend=100, impressions=1000, clicks=10)
    assert changes_dict(cur, None) == {}
    ch = changes_dict(cur, make(spend=50))
    assert "spend" in ch and "ctr" not in ch and "roas" not in ch and "impressions" not in ch


def test_targets_list_statuses():
    s = make(spend=100, impressions=10000, reach=5000, clicks=200, results=10)  # ctr 2, cpa 10
    out = targets_list(s, {"ctr_min": 1.5, "cpa_max": 8, "roas_min": 3})
    by = {t["key"]: t for t in out}
    assert by["ctr_min"]["status"] == "pass" and by["ctr_min"]["actual"] == 2.0 and by["ctr_min"]["op"] == ">="
    assert by["cpa_max"]["status"] == "fail" and by["cpa_max"]["target"] == 8
    assert by["roas_min"]["status"] == "n/a" and by["roas_min"]["actual"] is None
    assert targets_list(s, {}) == []


def test_build_summary_basic(basic_csv):
    rep = build_report([basic_csv])
    s = build_summary(rep, Config(brand="Acme", targets={"ctr_min": 1.0, "cpa_max": 5}))
    assert s["schema_version"] == SCHEMA_VERSION == 1
    assert s["generator"]["name"] == "meta-ads-report" and s["generator"]["version"]
    assert s["brand"] == "Acme" and s["currency"] == "USD"
    assert s["period"] == {"start": "2026-01-01", "end": "2026-01-07"}
    assert s["sources"] == {"files": 1, "duplicates_dropped": 0, "rows_filtered": 0}
    assert s["filters"] is None
    assert s["totals"]["spend"] == 350 and s["totals"]["results"] == 12
    assert "name" not in s["totals"]
    assert s["previous"] is None
    assert s["targets_summary"]["passed"] + s["targets_summary"]["failed"] == 2
    assert [c["name"] for c in s["campaigns"]] == ["Camp B", "Camp A"]  # by spend
    assert s["campaigns"][0]["spend_share"] == round(200 / 350 * 100, 2)
    assert sum(c["spend_share"] for c in s["campaigns"]) == pytest.approx(100, abs=0.02)
    assert set(s["campaigns"][0]["targets"]) == {"ctr_min", "cpa_max"}
    assert "changes" not in s["campaigns"][0]
    assert len(s["adsets"]) == 2 and s["adsets"][0]["parent"]
    assert len(s["ads"]) == 3
    assert s["daily"] == [] and s["breakdowns"] == {}
    assert s["insights"] and all(set(i) == {"level", "rule", "text"} for i in s["insights"])


def test_build_summary_target_counts(basic_csv):
    rep = build_report([basic_csv])  # total ctr ~0.99, cpa ~29.17, roas present
    s = build_summary(rep, Config(targets={"ctr_min": 0.5, "cpa_max": 5, "frequency_max": 10}))
    assert s["targets_summary"] == {"passed": 2, "failed": 1, "not_available": 0, "all_passed": False}
    ok = build_summary(rep, Config(targets={"ctr_min": 0.5}))
    assert ok["targets_summary"]["all_passed"] is True
    none = build_summary(rep, Config())
    assert none["targets"] == [] and none["targets_summary"]["all_passed"] is False
    assert "targets" not in none["campaigns"][0]
    camp_b = next(c for c in s["campaigns"] if c["name"] == "Camp B")
    assert camp_b["targets"]["cpa_max"] == "n/a"  # zero results


def test_build_summary_previous_period(write_csv):
    cur = write_csv("c.csv", [
        ["Old", "S", "A", "100", "10000", "5000", "200", "20", "", "2026-02-08", "2026-02-14"],
        ["New", "S", "B", "50", "5000", "2500", "50", "5", "", "2026-02-08", "2026-02-14"],
    ])
    prev = write_csv("p.csv", [["Old", "S", "A", "100", "10000", "5000", "100", "10", "", "2026-02-01", "2026-02-07"]])
    s = build_summary(build_report([cur], previous_paths=[prev]), Config())
    assert s["previous"]["period"] == {"start": "2026-02-01", "end": "2026-02-07"}
    assert s["previous"]["totals"]["spend"] == 100
    assert s["previous"]["changes"]["spend"] == {"pct": 50.0, "direction": "better"}
    old = next(c for c in s["campaigns"] if c["name"] == "Old")
    assert old["changes"]["cpa"] == {"pct": -50.0, "direction": "better"}
    new = next(c for c in s["campaigns"] if c["name"] == "New")
    assert new["changes"] == {}  # campaign did not run in the previous period


def test_build_summary_daily_and_breakdowns(write_csv):
    head = ["Day", "Campaign name", "Amount spent (BDT)", "Impressions", "Link clicks", "Results"]
    main_csv = write_csv("d.csv", [
        ["2026-03-02", "C", "20", "2000", "40", "2"],
        ["2026-03-01", "C", "10", "1000", "10", "1"],
    ], header=head)
    age = write_csv("age.csv", [
        ["C", "18-24", "12", "1500", "20", "1"],
        ["C", "25-34", "18", "1500", "30", "2"],
    ], header=["Campaign name", "Age", "Amount spent (BDT)", "Impressions", "Link clicks", "Results"])
    s = build_summary(build_report([main_csv, age]), Config())
    assert s["currency"] == "BDT"
    assert [d["date"] for d in s["daily"]] == ["2026-03-01", "2026-03-02"]
    assert "name" not in s["daily"][0] and s["daily"][1]["spend"] == 20
    assert s["totals"]["spend"] == 30  # breakdown rows do not inflate totals
    assert s["breakdowns"]["age"]["title"] == "Age"
    assert [r["name"] for r in s["breakdowns"]["age"]["rows"]] == ["25-34", "18-24"]


def test_build_summary_uses_given_insights(basic_csv):
    rep = build_report([basic_csv])
    s = build_summary(rep, Config(), insights=[Insight("warn", "Custom text", "my_rule")])
    assert s["insights"] == [{"level": "warn", "rule": "my_rule", "text": "Custom text"}]


def test_build_summary_respects_disabled_rules(basic_csv):
    rep = build_report([basic_csv])
    all_rules = {i["rule"] for i in build_summary(rep, Config())["insights"]}
    assert all_rules
    disabled = build_summary(rep, Config(disable_rules=sorted(all_rules)))
    assert not ({i["rule"] for i in disabled["insights"]} & all_rules)


def test_build_summary_zero_spend(write_csv):
    path = write_csv("z.csv", [["C", "S", "A", "0", "0", "0", "0", "0", "", "2026-01-01", "2026-01-07"]])
    s = build_summary(build_report([path]), Config(targets={"ctr_min": 1}))
    assert s["totals"]["ctr"] is None
    assert s["campaigns"][0]["spend_share"] is None
    assert s["targets"][0]["status"] == "n/a"
    assert s["targets_summary"] == {"passed": 0, "failed": 0, "not_available": 1, "all_passed": False}
    json.loads(dumps_summary(s))


def test_dumps_summary_is_valid_json_and_keeps_unicode(write_csv):
    path = write_csv("u.csv", [["ঈদ সেল", "S", "A", "10", "1000", "500", "20", "2", "", "2026-01-01", "2026-01-07"]])
    text = dumps_summary(build_summary(build_report([path]), Config(brand="Café")))
    assert text.endswith("\n") and "ঈদ সেল" in text and "Café" in text and "NaN" not in text
    data = json.loads(text)
    assert list(data)[:2] == ["schema_version", "generator"]


def test_write_summary_json_roundtrip(basic_csv, tmp_path):
    out = tmp_path / "s.json"
    rep = build_report([basic_csv])
    returned = write_summary_json(rep, Config(targets={"ctr_min": 1}), str(out))
    assert json.loads(out.read_text(encoding="utf-8")) == returned


def test_cli_json(basic_csv, tmp_path, capsys):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("brand: Demo\ntargets:\n  ctr_min: 0.5\n  cpa_max: 5\n")
    out, js = tmp_path / "r.html", tmp_path / "s.json"
    assert main([basic_csv, "-o", str(out), "-c", str(cfg), "--currency", "bdt", "--json", str(js)]) == 0
    data = json.loads(js.read_text(encoding="utf-8"))
    assert data["currency"] == "BDT" and data["brand"] == "Demo"
    assert data["targets_summary"]["passed"] == 1 and data["targets_summary"]["failed"] == 1
    assert f"wrote {js} (1 of 2 KPI targets passed)" in capsys.readouterr().out
    assert out.exists()


def test_cli_json_without_targets_and_with_previous(write_csv, tmp_path, capsys):
    a = write_csv("a.csv", [["C", "S", "A", "10", "1000", "500", "20", "2", "", "2026-02-08", "2026-02-14"]])
    p = write_csv("p.csv", [["C", "S", "A", "10", "1000", "500", "10", "1", "", "2026-02-01", "2026-02-07"]])
    js = tmp_path / "s.json"
    assert main([a, "--previous", p, "-o", str(tmp_path / "r.html"), "--json", str(js)]) == 0
    assert f"wrote {js}\n" in capsys.readouterr().out
    data = json.loads(js.read_text(encoding="utf-8"))
    assert data["previous"]["changes"]["clicks"] == {"pct": 100.0, "direction": "better"}


def test_cli_json_unwritable_path(basic_csv, tmp_path, capsys):
    code = main([basic_csv, "-o", str(tmp_path / "r.html"), "--json", str(tmp_path / "nope" / "s.json")])
    assert code == 2
    assert "cannot write" in capsys.readouterr().err
