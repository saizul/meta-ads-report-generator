import pytest

from meta_ads_report.cli import main
from meta_ads_report.config import Config, ConfigError, evaluate_target, load_config
from meta_ads_report.metrics import Stats, build_report
from meta_ads_report.render import render_html


def stats():
    s = Stats("x")
    s.add({"spend": 100, "impressions": 10000, "reach": 5000, "clicks": 200, "results": 10})
    return s


def test_load_config_defaults():
    assert load_config(None).theme == "light"


def test_load_config_yaml(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("brand: X\ntheme: dark\ntargets:\n  ctr_min: 1.5\n  cpa_max: 12\nthresholds:\n  frequency_warn: 2\n")
    c = load_config(str(p))
    assert c.brand == "X" and c.theme == "dark"
    assert c.targets == {"ctr_min": 1.5, "cpa_max": 12.0}
    assert c.thresholds["frequency_warn"] == 2.0 and c.thresholds["ctr_warn"] == 1.0


@pytest.mark.parametrize("body", ["foo: 1", "theme: neon", "targets:\n  bogus: 1", "thresholds:\n  nope: 1", "- a"])
def test_load_config_rejects_invalid(tmp_path, body):
    p = tmp_path / "c.yaml"
    p.write_text(body)
    with pytest.raises(ConfigError):
        load_config(str(p))


def test_evaluate_target_pass_fail():
    s = stats()  # ctr 2.0, cpa 10
    assert evaluate_target(s, "ctr_min", 1.5)["passed"] is True
    assert evaluate_target(s, "ctr_min", 2.5)["passed"] is False
    assert evaluate_target(s, "cpa_max", 12)["passed"] is True
    assert evaluate_target(s, "cpa_max", 8)["passed"] is False
    assert evaluate_target(Stats(), "roas_min", 3)["passed"] is None


def test_render_html_basic(basic_csv):
    rep = build_report([basic_csv])
    html = render_html(rep, Config(brand="Acme <b>", theme="dark"))
    assert 'data-theme="dark"' in html
    assert "Acme &lt;b&gt;" in html  # escaped
    assert "<svg" in html and "Camp A" in html
    assert "USD" in html


def test_render_badges(basic_csv):
    rep = build_report([basic_csv])
    html = render_html(rep, Config(targets={"ctr_min": 1.0, "roas_min": 99}))
    assert "badge pass" in html and "badge fail" in html


def test_cli_end_to_end(basic_csv, tmp_path, capsys):
    out = tmp_path / "r.html"
    xlsx = tmp_path / "r.xlsx"
    code = main([basic_csv, "-o", str(out), "--brand", "Demo Co", "--currency", "BDT", "--theme", "ocean",
                 "--xlsx", str(xlsx)])
    assert code == 0
    html = out.read_text(encoding="utf-8")
    assert "Demo Co" in html and "BDT" in html and 'data-theme="ocean"' in html
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.load_workbook(xlsx)
    assert {"Summary", "Campaigns", "Insights"} <= set(wb.sheetnames)


def test_cli_pdf_graceful_fallback(basic_csv, tmp_path, monkeypatch, capsys):
    import meta_ads_report.cli as cli
    from meta_ads_report.exporters import ExportUnavailable

    def boom(html, path):
        raise ExportUnavailable("PDF export needs weasyprint")
    monkeypatch.setattr(cli, "write_pdf", boom)
    out = tmp_path / "r.html"
    code = main([basic_csv, "-o", str(out), "--pdf", str(tmp_path / "r.pdf")])
    assert code == 1 and out.exists()
    assert "weasyprint" in capsys.readouterr().err


def test_cli_errors(tmp_path, capsys):
    assert main([str(tmp_path / "missing.csv")]) == 2
    assert "error" in capsys.readouterr().err


def test_cli_custom_rules_file(basic_csv, tmp_path):
    rules = tmp_path / "my_rules.py"
    rules.write_text(
        "from meta_ads_report.insights import Insight, rule\n"
        "@rule('shout')\n"
        "def shout(ctx):\n    return [Insight('info', 'CUSTOM RULE FIRED')]\n"
    )
    out = tmp_path / "r.html"
    try:
        assert main([basic_csv, "-o", str(out), "--rules", str(rules)]) == 0
        assert "CUSTOM RULE FIRED" in out.read_text(encoding="utf-8")
    finally:
        from meta_ads_report import insights
        insights._RULES.pop("shout", None)


def test_cli_multi_file_and_previous(write_csv, tmp_path):
    a = write_csv("a.csv", [["C", "S", "A", "10", "1000", "500", "20", "2", "", "2026-02-01", "2026-02-07"]])
    b = write_csv("b.csv", [["C", "S", "A", "10", "1000", "500", "20", "2", "", "2026-02-08", "2026-02-14"]])
    p = write_csv("p.csv", [["C", "S", "A", "10", "1000", "500", "10", "1", "", "2026-01-01", "2026-01-14"]])
    out = tmp_path / "r.html"
    assert main([a, b, "--previous", p, "-o", str(out)]) == 0
    html = out.read_text(encoding="utf-8")
    assert "2026-02-01 to 2026-02-14" in html and "compared with 2026-01-01" in html
    assert "2 files merged" in html


def _read_rows(path):
    import csv
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_metrics_csv_campaign_level(basic_csv, tmp_path, capsys):
    out = tmp_path / "metrics.csv"
    code = main([basic_csv, "-o", str(tmp_path / "r.html"), "--metrics-csv", str(out), "--currency", "USD"])
    assert code == 0
    assert "2 campaign rows" in capsys.readouterr().out
    rows = {r["Name"]: r for r in _read_rows(out)}
    assert set(rows) == {"Camp A", "Camp B"}
    a = rows["Camp A"]
    assert float(a["Spend (USD)"]) == 150.0
    assert int(a["Impressions"]) == 16000
    assert float(a["CTR %"]) == pytest.approx(260 / 16000 * 100, abs=1e-3)
    assert rows["Camp B"]["ROAS"] == ""  # no purchase value reported -> left empty, not "None"


def test_metrics_csv_ad_level(basic_csv, tmp_path):
    out = tmp_path / "ads.csv"
    assert main([basic_csv, "-o", str(tmp_path / "r.html"), "--metrics-csv", str(out), "--metrics-level", "ad"]) == 0
    assert {r["Name"] for r in _read_rows(out)} == {"Ad 1", "Ad 2", "Ad 3"}


def test_metrics_csv_unwritable_path(basic_csv, tmp_path, capsys):
    bad = tmp_path / "missing-dir" / "m.csv"
    assert main([basic_csv, "-o", str(tmp_path / "r.html"), "--metrics-csv", str(bad)]) == 2
    assert "cannot write" in capsys.readouterr().err
