"""Dependency-free inline SVG charts. Colours come from CSS variables so the
charts follow the selected theme."""
from __future__ import annotations

from typing import Callable, List, Sequence
from xml.sax.saxutils import escape

from .metrics import Stats


def _trunc(s: str, n: int = 26) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def hbar_chart(
    items: Sequence[Stats],
    value: Callable[[Stats], float],
    fmt: Callable[[float], str],
    color: str = "var(--accent)",
    title: str = "",
) -> str:
    """Horizontal bar chart (one bar per item)."""
    items = [i for i in items][:10]
    if not items:
        return ""
    label_w, bar_w, row_h, pad = 190, 330, 28, 10
    height = pad * 2 + row_h * len(items) + (22 if title else 0)
    top = pad + (22 if title else 0)
    vmax = max((value(i) or 0 for i in items), default=0) or 1
    parts: List[str] = [
        f'<svg viewBox="0 0 {label_w + bar_w + 90} {height}" role="img" aria-label="{escape(title)}" '
        'xmlns="http://www.w3.org/2000/svg" class="chart">'
    ]
    if title:
        parts.append(f'<text x="0" y="16" class="chart-title">{escape(title)}</text>')
    for n, it in enumerate(items):
        y = top + n * row_h
        v = value(it) or 0
        w = max(1.0, v / vmax * bar_w) if v else 0
        parts.append(f'<text x="{label_w - 8}" y="{y + 15}" text-anchor="end" class="chart-label">{escape(_trunc(it.name))}</text>')
        parts.append(f'<rect x="{label_w}" y="{y + 3}" width="{w:.1f}" height="16" rx="3" fill="{color}"/>')
        parts.append(f'<text x="{label_w + w + 6:.1f}" y="{y + 15}" class="chart-value">{escape(fmt(v))}</text>')
    parts.append("</svg>")
    return "".join(parts)


def line_chart(
    labels: Sequence[str],
    series: Sequence[Sequence[float]],
    colors: Sequence[str],
    names: Sequence[str],
    title: str = "",
) -> str:
    """Multi-series line chart with each series scaled to its own maximum, so
    spend and results can share one plot."""
    if not labels or len(labels) < 2:
        return ""
    w, h, left, right, top, bottom = 640, 220, 14, 14, 34, 28
    pw, ph = w - left - right, h - top - bottom
    parts = [
        f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{escape(title)}" '
        'xmlns="http://www.w3.org/2000/svg" class="chart">',
        f'<text x="0" y="16" class="chart-title">{escape(title)}</text>',
    ]
    for g in range(5):
        y = top + ph * g / 4
        parts.append(f'<line x1="{left}" x2="{w - right}" y1="{y:.1f}" y2="{y:.1f}" class="grid"/>')
    for s, c in zip(series, colors):
        m = max(s) or 1
        pts = " ".join(
            f"{left + pw * i / (len(s) - 1):.1f},{top + ph - (v / m) * ph:.1f}" for i, v in enumerate(s)
        )
        parts.append(f'<polyline points="{pts}" fill="none" stroke="{c}" stroke-width="2.2" stroke-linejoin="round"/>')
    for k, (c, nm) in enumerate(zip(colors, names)):
        x = w - right - 170 + k * 85
        parts.append(f'<rect x="{x}" y="6" width="10" height="10" rx="2" fill="{c}"/>')
        parts.append(f'<text x="{x + 14}" y="15" class="chart-label">{escape(nm)}</text>')
    step = max(1, len(labels) // 6)
    for i in range(0, len(labels), step):
        parts.append(f'<text x="{left + pw * i / (len(labels) - 1):.1f}" y="{h - 8}" text-anchor="middle" class="chart-label">{escape(labels[i][-5:])}</text>')
    parts.append("</svg>")
    return "".join(parts)
