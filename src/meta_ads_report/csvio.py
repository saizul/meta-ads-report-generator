"""Read Ads Manager exports whatever their encoding or delimiter.

Ads Manager normally writes UTF-8 (sometimes with a BOM) and commas, but some
accounts and locales download UTF-16 tab-separated files, and spreadsheets
that re-save a file may use semicolons. ``read_text`` and ``sniff_delimiter``
make the reader tolerant of all of these.
"""
from __future__ import annotations

import codecs
from typing import Tuple

#: candidate delimiters; earlier entries win ties
DELIMITERS = (",", "\t", ";", "|")

_BOMS = (
    (codecs.BOM_UTF32_LE, "utf-32"),
    (codecs.BOM_UTF32_BE, "utf-32"),
    (codecs.BOM_UTF8, "utf-8-sig"),
    (codecs.BOM_UTF16_LE, "utf-16"),
    (codecs.BOM_UTF16_BE, "utf-16"),
)


def detect_encoding(raw: bytes) -> str:
    """Pick a codec for ``raw``: BOM first, then BOM-less UTF-16, UTF-8, cp1252."""
    for bom, name in _BOMS:
        if raw.startswith(bom):
            return name
    sample = raw[:4096]
    if len(sample) >= 2 and b"\x00" in sample:
        # ASCII-heavy text in UTF-16 has a NUL in every other byte
        even = sample[0::2].count(0)
        odd = sample[1::2].count(0)
        half = len(sample) // 2
        if odd > half * 0.3 and even < half * 0.1:
            return "utf-16-le"
        if even > half * 0.3 and odd < half * 0.1:
            return "utf-16-be"
    try:
        raw.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "cp1252"


def read_text(path: str) -> Tuple[str, str]:
    """Return ``(text, encoding)`` for a CSV file, with the BOM removed."""
    with open(path, "rb") as fh:
        raw = fh.read()
    encoding = detect_encoding(raw)
    try:
        text = raw.decode(encoding)
    except UnicodeDecodeError:
        encoding = "latin-1"  # never fails; better than refusing the file
        text = raw.decode(encoding)
    return text.lstrip("﻿"), encoding


def _count_outside_quotes(line: str, delimiter: str) -> int:
    count, quoted = 0, False
    for ch in line:
        if ch == '"':
            quoted = not quoted
        elif ch == delimiter and not quoted:
            count += 1
    return count


def sniff_delimiter(text: str) -> str:
    """Guess the delimiter from the header line (the one with most separators)."""
    header = next((ln for ln in text.splitlines() if ln.strip()), "")
    best, best_count = ",", 0
    for delimiter in DELIMITERS:
        count = _count_outside_quotes(header, delimiter)
        if count > best_count:
            best, best_count = delimiter, count
    return best
