"""Optional exporters: XLSX (openpyxl) and PDF (weasyprint)."""
from __future__ import annotations

import csv
from typing import Any, Dict, List

from .metrics import Stats


class ExportUnavailable(RuntimeError):
    """Raised when an optional dependency is missing or fails."""


_HEAD = ["Name", "Parent", "Spend", "Impressions", "Reach", "Clicks", "CTR %", "CPC", "CPM",
         "Frequency", "Results", "Cost per result", "ROAS"]


def _row(s: Stats) -> List[Any]:
    return [s.name, s.parent, round(s.spend, 2), s.impressions, s.reach, s.clicks,
            _r(s.ctr), _r(s.cpc), _r(s.cpm), _r(s.frequency), s.results or s.purchases, _r(s.cpa), _r(s.roas)]


def _r(v):
    return None if v is None else round(v, 4)


def _cell(v: Any) -> Any:
    if v is None:
        return ""
    return int(v) if isinstance(v, float) and v.is_integer() else v


METRICS_LEVELS = ("campaign", "adset", "ad", "daily")


def write_metrics_csv(rep: Any, path: str, level: str = "campaign") -> int:
    """Write the computed metrics (CTR, CPC, CPM, CPA, ROAS ...) for one level to a CSV file.

    ``level`` is one of ``METRICS_LEVELS``. Returns the number of data rows written.
    Metrics that cannot be computed (e.g. ROAS without purchase value) are left empty.
    """
    if level not in METRICS_LEVELS:
        raise ValueError(f"unknown level {level!r}; choose from {', '.join(METRICS_LEVELS)}")
    items = {"campaign": rep.campaigns, "adset": rep.adsets, "ad": rep.ads, "daily": rep.daily}[level]
    head = [f"Spend ({rep.currency})" if h == "Spend" else h for h in _HEAD]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(head)
        for it in items:
            writer.writerow([_cell(v) for v in _row(it)])
    return len(items)


def write_xlsx(ctx: Dict[str, Any], path: str) -> None:
    """Write summary, tables, breakdowns and insights to an .xlsx workbook."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError as exc:  # pragma: no cover - depends on env
        raise ExportUnavailable("XLSX export needs openpyxl: pip install 'meta-ads-report[xlsx]'") from exc

    rep = ctx["rep"]
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    ws.append([ctx["cfg"].title])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append(["Period", ctx["period"]])
    ws.append(["Currency", rep.currency])
    ws.append([])
    ws.append(["Metric", "Value"] + (["Previous period"] if rep.previous else []))
    for c in ws[5]:
        c.font = Font(bold=True)
    for key in ("spend", "impressions", "reach", "clicks", "results", "ctr", "cpc", "cpm", "cpa", "frequency", "roas"):
        row = [key, _r(rep.total.metric(key))]
        if rep.previous:
            row.append(_r(rep.previous.total.metric(key)))
        ws.append(row)
    if ctx["badges"]:
        ws.append([])
        ws.append(["KPI target", "Actual", "Target", "Status"])
        for b in ctx["badges"]:
            status = "n/a" if b["passed"] is None else ("PASS" if b["passed"] else "FAIL")
            ws.append([b["label"], _r(b["actual"]), b["target"], status])
            ws.cell(row=ws.max_row, column=4).fill = PatternFill(
                "solid", fgColor={"PASS": "C6EFCE", "FAIL": "FFC7CE"}.get(status, "EEEEEE"))

    def sheet(title: str, items: List[Stats]) -> None:
        if not items:
            return
        s = wb.create_sheet(title[:31])
        s.append(_HEAD)
        for c in s[1]:
            c.font = Font(bold=True)
        for it in items:
            s.append(_row(it))
        for i in range(1, len(_HEAD) + 1):
            s.column_dimensions[get_column_letter(i)].width = 16 if i > 2 else 30
        s.freeze_panes = "A2"

    sheet("Campaigns", rep.campaigns)
    sheet("Ad sets", rep.adsets)
    sheet("Ads", rep.ads)
    sheet("Daily", rep.daily)
    for b in ctx["breakdowns"]:
        sheet(f"By {b['title']}", b["rows"])
    ins = wb.create_sheet("Insights")
    ins.append(["Level", "Insight"])
    for i in ctx["insights"]:
        ins.append([i.level, i.text])
    ins.column_dimensions["B"].width = 120
    wb.save(path)


def write_pdf(html: str, path: str) -> None:
    """Render HTML to PDF with weasyprint; raises :class:`ExportUnavailable`."""
    try:
        from weasyprint import HTML
    except Exception as exc:  # ImportError or missing system libraries
        raise ExportUnavailable("PDF export needs weasyprint: pip install 'meta-ads-report[pdf]'") from exc
    try:
        HTML(string=html).write_pdf(path)
    except Exception as exc:  # pragma: no cover
        raise ExportUnavailable(f"weasyprint failed: {exc}") from exc
