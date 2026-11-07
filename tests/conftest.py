import csv

import pytest

HEAD = ["Campaign name", "Ad set name", "Ad name", "Amount spent (USD)", "Impressions", "Reach",
        "Link clicks", "Results", "Purchase ROAS (return on ad spend)", "Reporting starts", "Reporting ends"]


@pytest.fixture
def write_csv(tmp_path):
    def _write(name, rows, header=None):
        path = tmp_path / name
        header = header or HEAD
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(header)
            w.writerows(rows)
        return str(path)
    return _write


@pytest.fixture
def basic_csv(write_csv):
    return write_csv("a.csv", [
        ["Camp A", "Set 1", "Ad 1", "100", "10000", "5000", "200", "10", "3.0", "2026-01-01", "2026-01-07"],
        ["Camp A", "Set 1", "Ad 2", "50", "6000", "3000", "60", "2", "1.0", "2026-01-01", "2026-01-07"],
        ["Camp B", "Set 2", "Ad 3", "200", "40000", "10000", "300", "0", "", "2026-01-01", "2026-01-07"],
    ])
