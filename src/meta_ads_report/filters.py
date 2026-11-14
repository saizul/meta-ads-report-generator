"""Row filters: report on a date window or a subset of campaigns.

Agencies often export a whole ad account once and then need one report per
client, product line or week. ``RowFilter`` keeps only the rows that match a
date window (``--since`` / ``--until``) and campaign name patterns
(``--campaign`` / ``--exclude-campaign``) before any totals are computed, so
every table, chart, KPI target and insight reflects the filtered data.

Campaign patterns are case-insensitive. A pattern containing ``*``, ``?`` or
``[`` is a shell-style glob matched against the whole name (``Eid*``);
anything else matches when it appears anywhere in the name (``retarget``).
"""
from __future__ import annotations

import datetime as _dt
import fnmatch
import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

Row = Dict[str, object]

_DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d")
_GLOB_CHARS = re.compile(r"[*?\[]")


class FilterError(ValueError):
    """Raised for invalid filter arguments."""


def parse_date(value: object) -> Optional[_dt.date]:
    """Parse an Ads Manager date (``2026-03-16``; ``/`` or ``.`` separators and
    a trailing time are accepted). Returns None for empty or unknown values."""
    if value is None:
        return None
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    text = str(value).strip()
    if not text:
        return None
    text = re.split(r"[ T]", text, maxsplit=1)[0]
    for fmt in _DATE_FORMATS:
        try:
            return _dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_date_arg(value: Optional[str], name: str) -> Optional[_dt.date]:
    """Parse a ``--since`` / ``--until`` value, raising :class:`FilterError` if invalid."""
    if value is None or not str(value).strip():
        return None
    parsed = parse_date(value)
    if parsed is None:
        raise FilterError(f"{name}: invalid date {value!r}; use YYYY-MM-DD")
    return parsed


def _match(pattern: str, name: str) -> bool:
    pattern, name = pattern.casefold(), name.casefold()
    if _GLOB_CHARS.search(pattern):
        return fnmatch.fnmatchcase(name, pattern)
    return pattern in name


def row_dates(row: Row) -> Tuple[Optional[_dt.date], Optional[_dt.date]]:
    """``(first, last)`` day a row covers: the ``Day`` column, else the reporting range."""
    day = parse_date(row.get("day"))
    if day is not None:
        return day, day
    start = parse_date(row.get("start"))
    end = parse_date(row.get("end"))
    return (start or end), (end or start)


@dataclass
class RowFilter:
    """Which rows to keep. An empty filter keeps everything."""

    since: Optional[_dt.date] = None
    until: Optional[_dt.date] = None
    campaigns: List[str] = field(default_factory=list)
    exclude_campaigns: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.campaigns = [p.strip() for p in self.campaigns if p and p.strip()]
        self.exclude_campaigns = [p.strip() for p in self.exclude_campaigns if p and p.strip()]
        if self.since and self.until and self.since > self.until:
            raise FilterError(f"--since {self.since.isoformat()} is after --until {self.until.isoformat()}")

    @classmethod
    def from_args(
        cls,
        since: Optional[str] = None,
        until: Optional[str] = None,
        campaigns: Optional[Sequence[str]] = None,
        exclude_campaigns: Optional[Sequence[str]] = None,
    ) -> "RowFilter":
        """Build a filter from command line style strings."""
        return cls(
            since=parse_date_arg(since, "--since"),
            until=parse_date_arg(until, "--until"),
            campaigns=list(campaigns or []),
            exclude_campaigns=list(exclude_campaigns or []),
        )

    @property
    def active(self) -> bool:
        return bool(self.has_dates or self.campaigns or self.exclude_campaigns)

    @property
    def has_dates(self) -> bool:
        return self.since is not None or self.until is not None

    def campaign_ok(self, name: str) -> bool:
        """Whether a campaign name passes the include and exclude patterns."""
        name = name or ""
        if self.campaigns and not any(_match(p, name) for p in self.campaigns):
            return False
        return not any(_match(p, name) for p in self.exclude_campaigns)

    def dates_ok(self, row: Row) -> bool:
        """Whether a row lies entirely inside the date window.

        A row that only partly overlaps the window (for example a monthly row
        when filtering one week) cannot be split, so it is dropped. Rows
        without a usable date are dropped when a date window is set.
        """
        if not self.has_dates:
            return True
        first, last = row_dates(row)
        if first is None or last is None:
            return False
        if self.since is not None and first < self.since:
            return False
        return not (self.until is not None and last > self.until)

    def keep(self, row: Row, dates: bool = True) -> bool:
        """Whether to keep a row. ``dates=False`` applies only the campaign patterns."""
        if not self.campaign_ok(str(row.get("campaign") or "")):
            return False
        return self.dates_ok(row) if dates else True

    def apply(self, rows: Iterable[Row], dates: bool = True) -> Tuple[List[Row], int]:
        """Return ``(kept_rows, dropped_count)``."""
        kept: List[Row] = []
        dropped = 0
        for row in rows:
            if self.keep(row, dates):
                kept.append(row)
            else:
                dropped += 1
        return kept, dropped

    def describe(self) -> str:
        """Short human-readable description, empty when nothing is filtered."""
        parts = []
        if self.since and self.until:
            parts.append(f"{self.since.isoformat()} to {self.until.isoformat()}")
        elif self.since:
            parts.append(f"from {self.since.isoformat()}")
        elif self.until:
            parts.append(f"until {self.until.isoformat()}")
        if self.campaigns:
            parts.append("campaigns matching " + ", ".join(self.campaigns))
        if self.exclude_campaigns:
            parts.append("excluding " + ", ".join(self.exclude_campaigns))
        return "; ".join(parts)

    def to_dict(self) -> Dict[str, object]:
        """JSON-friendly form used in the summary."""
        return {
            "since": self.since.isoformat() if self.since else None,
            "until": self.until.isoformat() if self.until else None,
            "campaigns": list(self.campaigns),
            "exclude_campaigns": list(self.exclude_campaigns),
        }
