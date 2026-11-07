import codecs
from pathlib import Path

import pytest

from meta_ads_report.csvio import detect_encoding, read_text, sniff_delimiter
from meta_ads_report.metrics import load_dataset, read_csv

HEADER = ["Campaign name", "Amount spent (BDT)", "Impressions", "Link clicks", "Reporting starts", "Reporting ends"]
ROWS = [
    ["ঈদ সেল - Eid Sale", "1,250.50", "10000", "200", "2026-03-01", "2026-03-07"],
    ["Café Retargeting", "300", "4000", "80", "2026-03-01", "2026-03-07"],
]


def render(delimiter, rows=ROWS, header=HEADER):
    def cell(value):
        return f'"{value}"' if delimiter in value else value

    lines = [delimiter.join(cell(c) for c in r) for r in [header, *rows]]
    return "\r\n".join(lines) + "\r\n"


@pytest.fixture
def make(tmp_path):
    def _make(name, text, encoding, bom=b""):
        path = tmp_path / name
        path.write_bytes(bom + text.encode(encoding))
        return str(path)

    return _make


CASES = {
    "utf8": (",", "utf-8", b""),
    "utf8-bom": (",", "utf-8", codecs.BOM_UTF8),
    "utf16-le-bom-tab": ("\t", "utf-16-le", codecs.BOM_UTF16_LE),
    "utf16-be-bom-tab": ("\t", "utf-16-be", codecs.BOM_UTF16_BE),
    "utf16-le-nobom-tab": ("\t", "utf-16-le", b""),
    "utf16-be-nobom-tab": ("\t", "utf-16-be", b""),
    "utf8-semicolon": (";", "utf-8", b""),
    "utf8-pipe": ("|", "utf-8", b""),
}


@pytest.mark.parametrize("name", CASES)
def test_all_variants_load_identically(make, name):
    delimiter, encoding, bom = CASES[name]
    path = make(f"{name}.csv", render(delimiter), encoding, bom)
    rows, mapping, currency = read_csv(path)
    assert currency == "BDT"
    assert [r["campaign"] for r in rows] == ["ঈদ সেল - Eid Sale", "Café Retargeting"]
    assert rows[0]["spend"] == pytest.approx(1250.5)
    assert rows[0]["impressions"] == 10000
    assert rows[1]["clicks"] == 80
    assert mapping["spend"] == "Amount spent (BDT)"


def test_cp1252_export_is_decoded(make):
    path = make("legacy.csv", render(",", header=HEADER, rows=[["Café", "5", "100", "2", "", ""]]), "cp1252")
    rows, _, _ = read_csv(path)
    assert rows[0]["campaign"] == "Café"


def test_detect_encoding_variants():
    assert detect_encoding(codecs.BOM_UTF8 + b"a,b") == "utf-8-sig"
    assert detect_encoding(codecs.BOM_UTF16_LE + "a\tb".encode("utf-16-le")) == "utf-16"
    assert detect_encoding("Campaign\tSpend".encode("utf-16-le")) == "utf-16-le"
    assert detect_encoding("Campaign\tSpend".encode("utf-16-be")) == "utf-16-be"
    assert detect_encoding("plain ascii".encode()) == "utf-8"
    assert detect_encoding("café".encode("cp1252")) == "cp1252"


def test_read_text_strips_bom(make):
    path = make("b.csv", "a,b\n1,2\n", "utf-16", b"")  # Python's utf-16 writes its own BOM
    text, enc = read_text(path)
    assert text.startswith("a,b") and enc == "utf-16"


def test_sniff_delimiter():
    assert sniff_delimiter("a,b,c\n1,2,3") == ","
    assert sniff_delimiter("a\tb\tc\n") == "\t"
    assert sniff_delimiter("a;b;c\n") == ";"
    assert sniff_delimiter('"Name, with comma";Spend;Clicks\n') == ";"  # commas in quotes ignored
    assert sniff_delimiter("\n\nSingleColumn\n") == ","  # default when nothing found
    assert sniff_delimiter("") == ","


def test_load_dataset_merges_mixed_encodings(make):
    a = make("a.csv", render(","), "utf-8", codecs.BOM_UTF8)
    other = [["Another", "50", "900", "10", "2026-03-08", "2026-03-14"]]
    b = make("b.csv", render("\t", rows=other), "utf-16")
    ds = load_dataset([a, b])
    assert len(ds.rows) == 3
    assert ds.currency == "BDT"


def test_headers_with_stray_whitespace_still_map(make):
    header = [" Campaign name ", "Amount spent (USD)", "Impressions"]
    path = make("w.csv", render(",", header=header, rows=[["X", "10", "1000"]]), "utf-8")
    rows, mapping, _ = read_csv(path)
    assert rows[0]["campaign"] == "X" and mapping["campaign"] == "Campaign name"


def test_missing_spend_error_still_names_columns(make):
    path = make("n.csv", "Foo\tBar\r\n1\t2\r\n", "utf-16")
    with pytest.raises(ValueError, match="no spend column.*Foo, Bar"):
        read_csv(path)


FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE = FIXTURES.parent.parent / "examples" / "sample-week1.csv"


@pytest.mark.parametrize("name", ["week1-utf16-tab.csv", "week1-utf8bom-semicolon.csv"])
def test_fixture_exports_match_the_utf8_original(name):
    expected, expected_map, expected_cur = read_csv(str(SAMPLE))
    got, got_map, got_cur = read_csv(str(FIXTURES / name))
    assert expected and len(got) == len(expected)
    assert got_cur == expected_cur
    assert got_map == expected_map
    strip = lambda rows: [{k: v for k, v in r.items() if k != "_source"} for r in rows]  # noqa: E731
    assert strip(got) == strip(expected)
