import pytest

from meta_ads_report.metrics import Stats, build_report, compare, load_dataset, pct_change, safe_div


def test_safe_div():
    assert safe_div(10, 4) == 2.5
    assert safe_div(10, 0) is None
    assert safe_div(None, 5) is None


def test_pct_change():
    assert pct_change(110, 100) == pytest.approx(10)
    assert pct_change(50, 100) == pytest.approx(-50)
    assert pct_change(5, 0) is None
    assert pct_change(None, 3) is None


def test_stats_math():
    s = Stats()
    s.add({"spend": 100, "impressions": 10000, "reach": 5000, "clicks": 200, "results": 10, "roas": 3.0})
    assert s.ctr == pytest.approx(2.0)
    assert s.cpc == pytest.approx(0.5)
    assert s.cpm == pytest.approx(10.0)
    assert s.cpa == pytest.approx(10.0)
    assert s.roas == pytest.approx(3.0)
    assert s.frequency == pytest.approx(2.0)


def test_stats_empty_is_safe():
    s = Stats()
    assert s.ctr is None and s.cpc is None and s.cpm is None
    assert s.cpa is None and s.roas is None and s.frequency is None


def test_roas_is_spend_weighted():
    s = Stats()
    s.add({"spend": 100, "roas": 4.0})
    s.add({"spend": 300, "roas": 0.0})
    assert s.roas == pytest.approx(1.0)  # 400 revenue / 400 spend


def test_cpa_falls_back_to_purchases():
    s = Stats()
    s.add({"spend": 90, "purchases": 3})
    assert s.cpa == pytest.approx(30)


def test_build_report_totals_and_levels(basic_csv):
    rep = build_report([basic_csv])
    assert rep.currency == "USD"
    assert rep.total.spend == 350
    assert rep.total.impressions == 56000
    assert rep.start == "2026-01-01" and rep.end == "2026-01-07"
    assert [c.name for c in rep.campaigns] == ["Camp B", "Camp A"]  # sorted by spend
    assert len(rep.adsets) == 2 and len(rep.ads) == 3
    camp_a = next(c for c in rep.campaigns if c.name == "Camp A")
    assert camp_a.results == 12
    assert camp_a.roas == pytest.approx((100 * 3 + 50 * 1) / 150)


def test_currency_override(basic_csv):
    assert build_report([basic_csv], currency="bdt").currency == "BDT"


def test_missing_spend_column_raises(write_csv):
    p = write_csv("bad.csv", [["x"]], header=["Campaign name"])
    with pytest.raises(ValueError, match="no spend column"):
        build_report([p])


def test_total_rows_are_skipped(write_csv):
    p = write_csv("t.csv", [
        ["Camp A", "", "", "10", "100", "50", "1", "1", "", "", ""],
        ["Total", "", "", "10", "100", "50", "1", "1", "", "", ""],
    ])
    assert build_report([p]).total.spend == 10


def test_merge_multiple_files_sums(write_csv):
    a = write_csv("a.csv", [["C", "S", "A", "10", "100", "50", "5", "1", "", "2026-01-01", "2026-01-07"]])
    b = write_csv("b.csv", [["C", "S", "A", "20", "300", "80", "9", "2", "", "2026-01-08", "2026-01-14"]])
    rep = build_report([a, b])
    assert rep.total.spend == 30 and rep.total.clicks == 14
    assert rep.start == "2026-01-01" and rep.end == "2026-01-14"


def test_overlapping_rows_deduped(write_csv):
    row = ["C", "S", "A", "10", "100", "50", "5", "1", "", "2026-01-01", "2026-01-07"]
    a = write_csv("a.csv", [row])
    b = write_csv("b.csv", [row])
    ds = load_dataset([a, b])
    assert len(ds.rows) == 1 and ds.duplicates_dropped == 1
    assert build_report([a, b]).total.spend == 10
    assert build_report([a, b], dedupe=False).total.spend == 20


def test_load_dataset_requires_files():
    with pytest.raises(ValueError):
        load_dataset([])


def test_previous_period_comparison(write_csv, basic_csv):
    prev = write_csv("p.csv", [["Camp A", "S", "A", "100", "10000", "5000", "100", "5", "", "2025-12-01", "2025-12-07"]])
    rep = build_report([basic_csv], previous_paths=[prev])
    assert rep.previous is not None
    assert rep.previous.total.spend == 100
    assert rep.previous.start == "2025-12-01"
    d = compare(rep.total, rep.previous.total, "spend")
    assert d["pct"] == pytest.approx(250)
    # lower CPC is good, higher spend counts as "good" direction
    cpc = compare(rep.total, rep.previous.total, "cpc")
    assert cpc["good"] is True
    assert compare(rep.total, None, "spend") is None


def test_breakdown_files_do_not_double_count(write_csv, basic_csv):
    head = ["Campaign name", "Amount spent (USD)", "Impressions", "Reach", "Link clicks", "Results", "Age", "Gender"]
    age = write_csv("age.csv", [["Camp A", "60", "1000", "500", "10", "1", "18-24", "female"],
                                ["Camp A", "40", "800", "400", "8", "1", "25-34", "male"]], header=head)
    rep = build_report([basic_csv, age])
    assert rep.total.spend == 350  # unchanged: breakdown rows excluded from totals
    assert {s.name for s in rep.breakdowns["age"]} == {"18-24", "25-34"}
    assert {s.name for s in rep.breakdowns["gender"]} == {"female", "male"}


def test_only_breakdown_files_use_first_file_for_totals(write_csv):
    head = ["Campaign name", "Amount spent (USD)", "Impressions", "Age", "Placement"]
    a = write_csv("a.csv", [["C", "30", "100", "18-24", ""], ["C", "70", "200", "25-34", ""]],
                  header=["Campaign name", "Amount spent (USD)", "Impressions", "Age"])
    b = write_csv("b.csv", [["C", "40", "100", "", "Feed"], ["C", "60", "200", "", "Reels"]], header=head)
    rep = build_report([a, b])
    assert rep.total.spend == 100
    assert "placement" in rep.breakdowns


def test_daily_series(write_csv):
    head = ["Day", "Campaign name", "Amount spent (USD)", "Impressions"]
    p = write_csv("d.csv", [["2026-01-02", "C", "5", "10"], ["2026-01-01", "C", "3", "10"], ["2026-01-01", "D", "2", "10"]], header=head)
    rep = build_report([p])
    assert [d.name for d in rep.daily] == ["2026-01-01", "2026-01-02"]
    assert rep.daily[0].spend == 5
