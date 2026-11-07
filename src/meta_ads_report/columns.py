"""Column mapping layer.

Ads Manager exports differ by account language settings, selected columns and
breakdowns. This module maps the many header spellings onto a small set of
canonical field names so the rest of the code never sees raw headers.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

#: canonical field -> accepted normalised header aliases (first match wins)
ALIASES: Dict[str, List[str]] = {
    "campaign": ["campaignname", "campaign"],
    "adset": ["adsetname", "adset"],
    "ad": ["adname", "ad"],
    "spend": ["amountspent", "spend", "cost", "amountspentusd", "amountspentbdt"],
    "impressions": ["impressions"],
    "reach": ["reach"],
    "clicks": ["linkclicks", "clicks", "clicksall"],
    "results": ["results"],
    "result_type": ["resulttype", "resultindicator"],
    "cost_per_result": ["costperresult"],
    "purchases": ["purchases", "websitepurchases"],
    "roas": ["purchaseroas", "purchaseroasreturnonadspend", "roas", "websitepurchaseroas"],
    "frequency": ["frequency"],
    "start": ["reportingstarts", "start", "startdate"],
    "end": ["reportingends", "end", "enddate"],
    "day": ["day", "date"],
    # breakdown dimensions
    "age": ["age"],
    "gender": ["gender"],
    "placement": ["placement", "platformposition"],
    "platform": ["platform"],
    "region": ["region", "country", "state"],
}

NUMERIC_FIELDS = {
    "spend", "impressions", "reach", "clicks", "results",
    "cost_per_result", "purchases", "roas", "frequency",
}

#: breakdown dimension -> display title
BREAKDOWNS: Dict[str, str] = {
    "age": "Age",
    "gender": "Gender",
    "placement": "Placement",
    "platform": "Platform",
    "region": "Region",
}


def normalize_header(name: Optional[str]) -> str:
    """Lowercase and keep only letters/digits; parenthesised suffixes such as
    ``(USD)`` are dropped so ``Amount spent (BDT)`` equals ``Amount spent``."""
    name = re.sub(r"\([^)]*\)", "", name or "")
    return re.sub(r"[^a-z0-9]", "", name.lower())


def detect_currency(headers: List[str]) -> Optional[str]:
    """Return the currency code in a spend column header, if one is present."""
    for h in headers:
        if normalize_header(h) in ALIASES["spend"]:
            m = re.search(r"\(([A-Za-z]{3})\)", h)
            if m:
                return m.group(1).upper()
    return None


def build_mapping(headers: List[str]) -> Dict[str, str]:
    """Map canonical field -> actual CSV header."""
    mapping: Dict[str, str] = {}
    used = set()
    for field_name, aliases in ALIASES.items():
        for alias in aliases:
            hit = next((h for h in headers if h not in used and normalize_header(h) == alias), None)
            if hit:
                mapping[field_name] = hit
                used.add(hit)
                break
    return mapping


def parse_number(value) -> Optional[float]:
    """Parse ``'1,234.50'``, ``'$12'``, ``'3.2x'``; return None when empty/invalid."""
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in {"-", "n/a", "na", "nan", "null"}:
        return None
    s = re.sub(r"[^0-9.\-]", "", s.replace(",", ""))
    if s in {"", "-", "."}:
        return None
    try:
        return float(s)
    except ValueError:
        return None
