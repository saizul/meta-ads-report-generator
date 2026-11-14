"""Metric maths, CSV loading, merging, breakdowns and period comparison."""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .columns import BREAKDOWNS, NUMERIC_FIELDS, build_mapping, detect_currency, parse_number
from .csvio import read_text, sniff_delimiter
from .filters import RowFilter

Row = Dict[str, object]


def safe_div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    """Divide, returning None when the denominator is zero/None."""
    if a is None or not b:
        return None
    return a / b


def pct_change(new: Optional[float], old: Optional[float]) -> Optional[float]:
    """Percentage change from ``old`` to ``new`` (None if undefined)."""
    if new is None or old in (None, 0):
        return None
    return (new - old) / abs(old) * 100


@dataclass
class Stats:
    """Additive counters plus derived metrics for one entity (campaign, ad...)."""

    name: str = ""
    parent: str = ""
    spend: float = 0.0
    impressions: float = 0.0
    reach: float = 0.0
    clicks: float = 0.0
    results: float = 0.0
    purchases: float = 0.0
    purchase_value: float = 0.0  # spend * ROAS, summed per row
    result_type: str = ""

    def add(self, row: Row) -> None:
        spend = float(row.get("spend") or 0.0)
        self.spend += spend
        self.impressions += float(row.get("impressions") or 0.0)
        self.reach += float(row.get("reach") or 0.0)
        self.clicks += float(row.get("clicks") or 0.0)
        self.results += float(row.get("results") or 0.0)
        self.purchases += float(row.get("purchases") or 0.0)
        if row.get("roas"):
            self.purchase_value += float(row["roas"]) * spend
        if not self.result_type and row.get("result_type"):
            self.result_type = str(row["result_type"])

    @property
    def ctr(self) -> Optional[float]:
        """Click-through rate in percent."""
        v = safe_div(self.clicks, self.impressions)
        return v * 100 if v is not None else None

    @property
    def cpc(self) -> Optional[float]:
        return safe_div(self.spend, self.clicks)

    @property
    def cpm(self) -> Optional[float]:
        v = safe_div(self.spend, self.impressions)
        return v * 1000 if v is not None else None

    @property
    def cpa(self) -> Optional[float]:
        """Cost per result (falls back to purchases when no results column)."""
        return safe_div(self.spend, self.results or self.purchases)

    @property
    def roas(self) -> Optional[float]:
        return safe_div(self.purchase_value, self.spend) if self.purchase_value else None

    @property
    def frequency(self) -> Optional[float]:
        return safe_div(self.impressions, self.reach)

    def metric(self, key: str) -> Optional[float]:
        """Look up a metric by name (used by config targets and comparisons)."""
        return getattr(self, key)


#: metric -> True when a higher value is better
METRIC_DIRECTION: Dict[str, bool] = {
    "spend": True, "impressions": True, "reach": True, "clicks": True, "results": True,
    "ctr": True, "roas": True, "cpc": False, "cpm": False, "cpa": False, "frequency": False,
}


@dataclass
class Dataset:
    """Rows loaded from one or more CSV files."""

    rows: List[Row] = field(default_factory=list)
    currency: Optional[str] = None
    mapping: Dict[str, str] = field(default_factory=dict)
    sources: List[str] = field(default_factory=list)
    duplicates_dropped: int = 0


@dataclass
class Comparison:
    """Previous-period totals and per-campaign stats."""

    total: Stats
    campaigns: Dict[str, Stats]
    start: str = ""
    end: str = ""


@dataclass
class Report:
    currency: str = "USD"
    start: str = ""
    end: str = ""
    sources: List[str] = field(default_factory=list)
    duplicates_dropped: int = 0
    total: Stats = field(default_factory=lambda: Stats("Total"))
    campaigns: List[Stats] = field(default_factory=list)
    adsets: List[Stats] = field(default_factory=list)
    ads: List[Stats] = field(default_factory=list)
    daily: List[Stats] = field(default_factory=list)
    breakdowns: Dict[str, List[Stats]] = field(default_factory=dict)
    previous: Optional[Comparison] = None
    filters: Optional[RowFilter] = None
    rows_filtered: int = 0


_DIM_FIELDS = ("campaign", "adset", "ad", "start", "end", "day") + tuple(BREAKDOWNS)


def read_csv(path: str) -> Tuple[List[Row], Dict[str, str], Optional[str]]:
    """Read one export; rows use canonical keys. Total/summary rows are skipped.

    The encoding (UTF-8 with/without BOM, UTF-16, cp1252) and the delimiter
    (comma, tab, semicolon, pipe) are detected automatically.
    """
    text, _encoding = read_text(path)
    reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=sniff_delimiter(text))
    headers = [h.strip() for h in (reader.fieldnames or [])]
    reader.fieldnames = headers
    mapping = build_mapping(headers)
    if "spend" not in mapping:
        raise ValueError(
            f"{path}: no spend column found (expected e.g. 'Amount spent (USD)'). "
            f"Columns: {', '.join(headers)}"
        )
    rows: List[Row] = []
    for raw in reader:
        row: Row = {}
        for fld, header in mapping.items():
            val = raw.get(header)
            row[fld] = parse_number(val) if fld in NUMERIC_FIELDS else (val or "").strip()
        if str(row.get("campaign", "x")).lower() in {"total", "results from all campaigns", "all"}:
            continue
        if not any(row.get(k) for k in ("spend", "impressions")) and not row.get("campaign"):
            continue
        row["_dims"] = tuple(d for d in BREAKDOWNS if d in mapping)
        row["_source"] = path
        rows.append(row)
    return rows, mapping, detect_currency(headers)


def _row_key(row: Row) -> Tuple:
    return tuple(row.get(k, "") for k in _DIM_FIELDS)


def load_dataset(paths: Sequence[str], dedupe: bool = True) -> Dataset:
    """Load and merge several exports (e.g. weekly files covering a date range).

    Rows from a later file that repeat a row (same campaign/ad set/ad/dates/
    breakdowns) already seen in an earlier file are dropped, so overlapping
    exports do not double count.
    """
    if not paths:
        raise ValueError("at least one CSV file is required")
    ds = Dataset()
    seen: set = set()
    for path in paths:
        rows, mapping, cur = read_csv(path)
        ds.mapping.update({k: v for k, v in mapping.items() if k not in ds.mapping})
        ds.currency = ds.currency or cur
        ds.sources.append(path)
        new_keys = set()
        for r in rows:
            k = _row_key(r)
            if dedupe and k in seen and (r.get("start") or r.get("day")):
                ds.duplicates_dropped += 1
                continue
            new_keys.add(k)
            ds.rows.append(r)
        seen |= new_keys
    return ds


def _group(rows: Iterable[Row], key: str, parent: Optional[str] = None) -> List[Stats]:
    groups: Dict[str, Stats] = {}
    for r in rows:
        name = str(r.get(key) or "(unnamed)")
        pname = str(r.get(parent, "")) if parent else ""
        st = groups.setdefault(f"{pname}\x00{name}", Stats(name=name, parent=pname))
        st.add(r)
    return sorted(groups.values(), key=lambda s: s.spend, reverse=True)


def split_rows(rows: List[Row]) -> Tuple[List[Row], Dict[str, List[Row]]]:
    """Separate core rows (no breakdown columns) from breakdown rows.

    Totals must come from a single coherent set of rows, otherwise an age
    export and a placement export would double count spend. We use non-breakdown
    rows when present, otherwise the rows of the first file that has data.
    """
    core = [r for r in rows if not r["_dims"]]
    by_dim: Dict[str, List[Row]] = {}
    for r in rows:
        for d in r["_dims"]:
            by_dim.setdefault(d, []).append(r)
    if not core and rows:
        first = rows[0]["_source"]
        core = [r for r in rows if r["_source"] == first]
    return core, by_dim


def _dates(rows: List[Row]) -> Tuple[str, str]:
    starts = sorted(str(r.get("start") or r.get("day") or "") for r in rows if r.get("start") or r.get("day"))
    ends = sorted(str(r.get("end") or r.get("day") or "") for r in rows if r.get("end") or r.get("day"))
    return (starts[0] if starts else "", ends[-1] if ends else "")


def build_report(
    paths: Sequence[str],
    currency: Optional[str] = None,
    previous_paths: Optional[Sequence[str]] = None,
    dedupe: bool = True,
    row_filter: Optional[RowFilter] = None,
) -> Report:
    """Build a :class:`Report` from current (and optionally previous) exports.

    ``row_filter`` keeps only rows inside a date window and/or matching
    campaign patterns. The date window applies to the current period only;
    campaign patterns apply to the previous period too, so the comparison
    covers the same campaigns.
    """
    ds = load_dataset(paths, dedupe)
    rows_filtered = 0
    if row_filter is not None and row_filter.active:
        ds.rows, rows_filtered = row_filter.apply(ds.rows)
        if not ds.rows:
            raise ValueError(f"no rows match the filters ({row_filter.describe()})")
    core, by_dim = split_rows(ds.rows)
    rep = Report(
        currency=(currency or ds.currency or "USD").upper(),
        sources=ds.sources,
        duplicates_dropped=ds.duplicates_dropped,
        filters=row_filter if row_filter is not None and row_filter.active else None,
        rows_filtered=rows_filtered,
    )
    rep.start, rep.end = _dates(core)
    for r in core:
        rep.total.add(r)
    m = ds.mapping
    rep.campaigns = _group(core, "campaign") if "campaign" in m else []
    rep.adsets = _group(core, "adset", "campaign") if "adset" in m else []
    rep.ads = _group(core, "ad", "adset") if "ad" in m else []
    if "day" in m:
        rep.daily = sorted(_group(core, "day"), key=lambda s: s.name)
    for dim, rows in by_dim.items():
        # use one file per dimension to avoid combining overlapping cuts
        rep.breakdowns[dim] = _group(rows, dim)
    if previous_paths:
        pds = load_dataset(previous_paths, dedupe)
        if rep.filters is not None:
            pds.rows, _ = rep.filters.apply(pds.rows, dates=False)
        pcore, _ = split_rows(pds.rows)
        ptotal = Stats("Previous total")
        for r in pcore:
            ptotal.add(r)
        pstart, pend = _dates(pcore)
        rep.previous = Comparison(
            total=ptotal,
            campaigns={s.name: s for s in _group(pcore, "campaign")},
            start=pstart,
            end=pend,
        )
    return rep


def compare(current: Stats, previous: Optional[Stats], key: str) -> Optional[Dict[str, object]]:
    """Return ``{'pct': float, 'good': bool}`` for a metric, or None."""
    if previous is None:
        return None
    pc = pct_change(current.metric(key), previous.metric(key))
    if pc is None:
        return None
    higher_better = METRIC_DIRECTION.get(key, True)
    return {"pct": pc, "good": (pc >= 0) == higher_better if abs(pc) >= 0.05 else None}
