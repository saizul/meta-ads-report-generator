import datetime as dt
import json

import pytest

from meta_ads_report.cli import main
from meta_ads_report.config import ConfigError, load_config
from meta_ads_report.filters import FilterError, RowFilter, parse_date, row_dates
from meta_ads_report.metrics import build_report
from meta_ads_report.render import render_html

DAILY_HEAD = ["Day", "Campaign name", "Ad set name", "Ad name", "Amount spent (USD)", "Impressions",
              "Link clicks", "Results"]


@pytest.fixture
def daily_csv(write_csv):
    return write_csv("daily.csv", [
        ["2026-03-01", "Eid Sale - Prospecting", "Set 1", "Ad 1", "100", "10000", "100", "5"],
        ["2026-03-02", "Eid Sale - Prospecting", "Set 1", "Ad 1", "120", "11000", "110", "6"],
        ["2026-03-03", "Eid Sale - Retargeting", "Set 2", "Ad 2", "50", "4000", "80", "4"],
        ["2026-03-04", "Brand Awareness", "Set 3", "Ad 3", "30", "20000", "40", "0"],
        ["2026-03-05", "TEST campaign", "Set 4", "Ad 4", "10", "500", "5", "0"],
    ], header=DAILY_HEAD)


def test_parse_date_formats():
    assert parse_date("2026-03-16") == dt.date(2026, 3, 16)
    assert parse_date("2026/03/16") == dt.date(2026, 3, 16)
    assert parse_date("2026.03.16") == dt.date(2026, 3, 16)
    assert parse_date("20260316") == dt.date(2026, 3, 16)
    assert parse_date("2026-03-16 00:00:00") == dt.date(2026, 3, 16)
    assert parse_date("2026-03-16T10:00") == dt.date(2026, 3, 16)
    assert parse_date(dt.date(2026, 1, 2)) == dt.date(2026, 1, 2)
    assert parse_date(dt.datetime(2026, 1, 2, 5)) == dt.date(2026, 1, 2)
    for bad in (None, "", "  ", "16 March", "2026-13-01"):
        assert parse_date(bad) is None


def test_row_dates_prefers_day_then_range():
    assert row_dates({"day": "2026-03-02", "start": "2026-03-01", "end": "2026-03-31"}) == (
        dt.date(2026, 3, 2), dt.date(2026, 3, 2))
    assert row_dates({"start": "2026-03-01", "end": "2026-03-07"}) == (dt.date(2026, 3, 1), dt.date(2026, 3, 7))
    assert row_dates({"start": "2026-03-01"}) == (dt.date(2026, 3, 1), dt.date(2026, 3, 1))
    assert row_dates({}) == (None, None)


def test_empty_filter_keeps_everything():
    f = RowFilter()
    assert not f.active
    assert f.describe() == ""
    assert f.keep({"campaign": "anything"})
    assert f.keep({})


def test_campaign_patterns_substring_and_glob():
    f = RowFilter(campaigns=["eid*"], exclude_campaigns=["retarget"])
    assert f.campaign_ok("Eid Sale - Prospecting")
    assert not f.campaign_ok("Eid Sale - Retargeting")
    assert not f.campaign_ok("Brand Eid")  # glob is anchored
    assert RowFilter(campaigns=["sale"]).campaign_ok("Eid SALE")
    assert RowFilter(campaigns=["Camp ?"]).campaign_ok("camp b")
    assert not RowFilter(campaigns=["Camp ?"]).campaign_ok("camp bb")
    assert RowFilter(exclude_campaigns=["test"]).campaign_ok("Brand")
    assert not RowFilter(exclude_campaigns=["test"]).campaign_ok("TEST 1")


def test_blank_patterns_are_ignored():
    f = RowFilter(campaigns=["", "  "], exclude_campaigns=[" "])
    assert not f.active
    assert f.campaign_ok("x")


def test_date_window_requires_full_containment():
    f = RowFilter.from_args(since="2026-03-01", until="2026-03-07")
    assert f.dates_ok({"day": "2026-03-01"})
    assert f.dates_ok({"day": "2026-03-07"})
    assert not f.dates_ok({"day": "2026-02-28"})
    assert not f.dates_ok({"day": "2026-03-08"})
    assert f.dates_ok({"start": "2026-03-02", "end": "2026-03-05"})
    assert not f.dates_ok({"start": "2026-02-25", "end": "2026-03-03"})  # partial overlap
    assert not f.dates_ok({"campaign": "no dates"})


def test_open_ended_windows():
    assert RowFilter.from_args(since="2026-03-03").dates_ok({"day": "2026-12-31"})
    assert not RowFilter.from_args(since="2026-03-03").dates_ok({"day": "2026-03-02"})
    assert RowFilter.from_args(until="2026-03-03").dates_ok({"day": "2020-01-01"})
    assert RowFilter.from_args(until="2026-03-03").describe() == "until 2026-03-03"
    assert RowFilter.from_args(since="2026-03-03").describe() == "from 2026-03-03"


def test_invalid_arguments():
    with pytest.raises(FilterError, match="--since"):
        RowFilter.from_args(since="March")
    with pytest.raises(FilterError, match="after"):
        RowFilter.from_args(since="2026-03-10", until="2026-03-01")


def test_apply_counts_dropped():
    rows = [{"campaign": "A", "day": "2026-03-01"}, {"campaign": "B", "day": "2026-03-02"}]
    kept, dropped = RowFilter(campaigns=["a"]).apply(rows)
    assert [r["campaign"] for r in kept] == ["A"]
    assert dropped == 1
    kept, dropped = RowFilter.from_args(since="2026-03-05").apply(rows, dates=False)
    assert len(kept) == 2 and dropped == 0


def test_build_report_with_date_window(daily_csv):
    rep = build_report([daily_csv], row_filter=RowFilter.from_args(since="2026-03-02", until="2026-03-04"))
    assert rep.total.spend == pytest.approx(200)
    assert rep.start == "2026-03-02" and rep.end == "2026-03-04"
    assert [d.name for d in rep.daily] == ["2026-03-02", "2026-03-03", "2026-03-04"]
    assert rep.rows_filtered == 2
    assert rep.filters is not None


def test_build_report_with_campaign_patterns(daily_csv):
    f = RowFilter(campaigns=["eid*"], exclude_campaigns=["retarget"])
    rep = build_report([daily_csv], row_filter=f)
    assert [c.name for c in rep.campaigns] == ["Eid Sale - Prospecting"]
    assert rep.total.spend == pytest.approx(220)
    assert rep.total.results == pytest.approx(11)


def test_inactive_filter_changes_nothing(daily_csv):
    plain = build_report([daily_csv])
    filtered = build_report([daily_csv], row_filter=RowFilter())
    assert filtered.total.spend == plain.total.spend
    assert filtered.filters is None and filtered.rows_filtered == 0


def test_no_matching_rows_is_an_error(daily_csv):
    with pytest.raises(ValueError, match="no rows match"):
        build_report([daily_csv], row_filter=RowFilter(campaigns=["does not exist"]))


def test_previous_period_gets_campaign_filter_only(write_csv, daily_csv):
    prev = write_csv("prev.csv", [
        ["2026-02-01", "Eid Sale - Prospecting", "Set 1", "Ad 1", "80", "9000", "90", "4"],
        ["2026-02-02", "Brand Awareness", "Set 3", "Ad 3", "40", "15000", "30", "0"],
    ], header=DAILY_HEAD)
    f = RowFilter(since=dt.date(2026, 3, 1), until=dt.date(2026, 3, 2), campaigns=["eid"])
    rep = build_report([daily_csv], previous_paths=[prev], row_filter=f)
    assert rep.total.spend == pytest.approx(220)
    # February rows survive (date window is for the current period) but Brand is filtered out
    assert rep.previous.total.spend == pytest.approx(80)
    assert set(rep.previous.campaigns) == {"Eid Sale - Prospecting"}


def test_html_mentions_filter_and_escapes(daily_csv):
    f = RowFilter(campaigns=["<b>eid"])
    with pytest.raises(ValueError):
        build_report([daily_csv], row_filter=f)
    rep = build_report([daily_csv], row_filter=RowFilter(campaigns=["Eid"], exclude_campaigns=["<x>"]))
    html = render_html(rep, load_config(None))
    assert "Filtered: campaigns matching Eid; excluding &lt;x&gt;" in html


def test_config_filters(tmp_path):
    path = tmp_path / "cfg.yaml"
    path.write_text(
        "filters:\n  since: 2026-03-01\n  until: '2026-03-31'\n  campaigns: Eid*\n  exclude_campaigns: [test, 2026]\n",
        encoding="utf-8",
    )
    cfg = load_config(str(path))
    assert cfg.filters.since == dt.date(2026, 3, 1)
    assert cfg.filters.until == dt.date(2026, 3, 31)
    assert cfg.filters.campaigns == ["Eid*"]
    assert cfg.filters.exclude_campaigns == ["test", "2026"]


@pytest.mark.parametrize("body, message", [
    ("filters: [a]\n", "mapping"),
    ("filters:\n  from: 2026-01-01\n", "unknown filter"),
    ("filters:\n  since: soon\n", "invalid date"),
    ("filters:\n  campaigns: {a: 1}\n", "list of strings"),
])
def test_config_filter_errors(tmp_path, body, message):
    path = tmp_path / "cfg.yaml"
    path.write_text(body, encoding="utf-8")
    with pytest.raises(ConfigError, match=message):
        load_config(str(path))


def test_cli_filters_and_json(tmp_path, daily_csv, capsys):
    out = tmp_path / "r.html"
    js = tmp_path / "s.json"
    code = main([daily_csv, "-o", str(out), "--json", str(js), "--since", "2026-03-01", "--until", "2026-03-03",
                 "--campaign", "eid", "--exclude-campaign", "retarget"])
    assert code == 0
    stdout = capsys.readouterr().out
    assert "filtered: 2026-03-01 to 2026-03-03; campaigns matching eid; excluding retarget (3 rows left out)" in stdout
    data = json.loads(js.read_text(encoding="utf-8"))
    assert data["filters"] == {"since": "2026-03-01", "until": "2026-03-03",
                               "campaigns": ["eid"], "exclude_campaigns": ["retarget"]}
    assert data["sources"]["rows_filtered"] == 3
    assert data["totals"]["spend"] == pytest.approx(220)


def test_cli_overrides_config_filters(tmp_path, daily_csv):
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("filters:\n  campaigns: [Brand]\n  since: 2026-03-04\n", encoding="utf-8")
    js = tmp_path / "s.json"
    assert main([daily_csv, "-o", str(tmp_path / "r.html"), "-c", str(cfg), "--json", str(js)]) == 0
    assert json.loads(js.read_text(encoding="utf-8"))["totals"]["spend"] == pytest.approx(30)
    assert main([daily_csv, "-o", str(tmp_path / "r.html"), "-c", str(cfg), "--json", str(js),
                 "--campaign", "Eid", "--since", "2026-03-01"]) == 0
    data = json.loads(js.read_text(encoding="utf-8"))
    assert data["filters"]["campaigns"] == ["Eid"]
    assert data["totals"]["spend"] == pytest.approx(270)


def test_cli_bad_filter_exits_2(tmp_path, daily_csv, capsys):
    assert main([daily_csv, "-o", str(tmp_path / "r.html"), "--since", "yesterday"]) == 2
    assert "invalid date" in capsys.readouterr().err
    assert main([daily_csv, "-o", str(tmp_path / "r.html"), "--campaign", "nope"]) == 2
    assert "no rows match" in capsys.readouterr().err


def test_json_without_filters_has_null(tmp_path, daily_csv):
    js = tmp_path / "s.json"
    assert main([daily_csv, "-o", str(tmp_path / "r.html"), "--json", str(js)]) == 0
    data = json.loads(js.read_text(encoding="utf-8"))
    assert data["filters"] is None
    assert data["sources"]["rows_filtered"] == 0
