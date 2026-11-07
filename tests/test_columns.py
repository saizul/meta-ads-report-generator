import pytest

from meta_ads_report.columns import build_mapping, detect_currency, normalize_header, parse_number


@pytest.mark.parametrize("raw,expected", [
    ("Amount spent (USD)", "amountspent"),
    ("Amount spent (BDT)", "amountspent"),
    ("Campaign name", "campaignname"),
    ("Purchase ROAS (return on ad spend)", "purchaseroas"),
    ("  Link  Clicks ", "linkclicks"),
    ("", ""),
    (None, ""),
])
def test_normalize_header(raw, expected):
    assert normalize_header(raw) == expected


def test_build_mapping_standard_headers():
    headers = ["Campaign name", "Ad set name", "Ad name", "Amount spent (USD)", "Impressions", "Reach",
               "Link clicks", "Results", "Result type", "Cost per result", "Purchases",
               "Purchase ROAS (return on ad spend)", "Reporting starts", "Reporting ends"]
    m = build_mapping(headers)
    assert m["campaign"] == "Campaign name"
    assert m["adset"] == "Ad set name"
    assert m["ad"] == "Ad name"
    assert m["spend"] == "Amount spent (USD)"
    assert m["clicks"] == "Link clicks"
    assert m["roas"] == "Purchase ROAS (return on ad spend)"
    assert m["start"] == "Reporting starts"
    assert m["result_type"] == "Result type"


def test_build_mapping_alternative_names_and_breakdowns():
    m = build_mapping(["Campaign", "Spend", "Clicks (all)", "Day", "Age", "Gender", "Placement", "Country"])
    assert m["campaign"] == "Campaign"
    assert m["spend"] == "Spend"
    assert m["clicks"] == "Clicks (all)"
    assert m["day"] == "Day"
    assert m["age"] == "Age" and m["gender"] == "Gender"
    assert m["placement"] == "Placement" and m["region"] == "Country"


def test_link_clicks_preferred_over_all_clicks():
    m = build_mapping(["Clicks (all)", "Link clicks", "Amount spent"])
    assert m["clicks"] == "Link clicks"


def test_unknown_columns_ignored():
    assert "spend" not in build_mapping(["Foo", "Bar"])


@pytest.mark.parametrize("headers,expected", [
    (["Amount spent (BDT)"], "BDT"),
    (["Amount spent (usd)"], "USD"),
    (["Amount spent"], None),
    (["Impressions"], None),
])
def test_detect_currency(headers, expected):
    assert detect_currency(headers) == expected


@pytest.mark.parametrize("raw,expected", [
    ("1,234.50", 1234.5), ("$12", 12.0), ("3.2x", 3.2), (" 7 ", 7.0), ("-4", -4.0),
    ("", None), ("-", None), ("N/A", None), (None, None), ("abc", None), (".", None),
])
def test_parse_number(raw, expected):
    assert parse_number(raw) == expected
